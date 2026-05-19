"""
Merge duplicate face clusters for one event using stored face embeddings.

Dry run:
  python scripts/merge_duplicate_faces.py --event-id <uuid> --threshold 0.55

Apply:
  python scripts/merge_duplicate_faces.py --event-id <uuid> --threshold 0.55 --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.local", override=True)

from app.core.supabase import get_client  # noqa: E402


logger = logging.getLogger(__name__)


def _chunks(items: list[str], size: int = 75):
    for start in range(0, len(items), size):
        yield items[start:start + size]


@dataclass
class FaceRow:
    id: str
    avatar_path: str
    embedding: np.ndarray
    photo_count: int


def _fetch_all(query, page_size: int = 1000) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        res = query.range(start, start + page_size - 1).execute()
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def _parse_embedding(value) -> np.ndarray:
    if isinstance(value, str):
        value = json.loads(value)
    arr = np.asarray(value, dtype=np.float32)
    norm = np.linalg.norm(arr)
    if norm == 0:
        raise ValueError("zero embedding")
    return arr / norm


def _load_faces(event_id: str) -> list[FaceRow]:
    sb = get_client()
    rows = _fetch_all(
        sb.table("faces")
        .select("id, avatar_path, embedding, photo_count")
        .eq("event_id", event_id)
    )
    faces: list[FaceRow] = []
    for row in rows:
        if row.get("embedding") is None:
            continue
        faces.append(
            FaceRow(
                id=row["id"],
                avatar_path=row["avatar_path"],
                embedding=_parse_embedding(row["embedding"]),
                photo_count=int(row.get("photo_count") or 0),
            )
        )
    return faces


def _load_face_photos(face_ids: list[str]) -> dict[str, set[str]]:
    sb = get_client()
    face_photos = {face_id: set() for face_id in face_ids}
    if not face_ids:
        return face_photos

    for chunk in _chunks(face_ids):
        rows = _fetch_all(
            sb.table("photo_faces")
            .select("face_id, photo_id")
            .in_("face_id", chunk)
        )
        for row in rows:
            face_photos.setdefault(row["face_id"], set()).add(row["photo_id"])
    return face_photos


class DisjointSet:
    def __init__(self, face_ids: list[str], photo_sets: dict[str, set[str]]):
        self.parent = {face_id: face_id for face_id in face_ids}
        self.photos = {face_id: set(photo_sets.get(face_id, set())) for face_id in face_ids}

    def find(self, face_id: str) -> str:
        parent = self.parent[face_id]
        if parent != face_id:
            self.parent[face_id] = self.find(parent)
        return self.parent[face_id]

    def union_if_safe(self, a: str, b: str) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.photos[ra] & self.photos[rb]:
            return False
        if len(self.photos[ra]) < len(self.photos[rb]):
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.photos[ra].update(self.photos[rb])
        return True

    def groups(self) -> list[list[str]]:
        grouped: dict[str, list[str]] = {}
        for face_id in self.parent:
            grouped.setdefault(self.find(face_id), []).append(face_id)
        return [ids for ids in grouped.values() if len(ids) > 1]


def _find_duplicate_groups(
    faces: list[FaceRow],
    photo_sets: dict[str, set[str]],
    threshold: float,
) -> list[list[str]]:
    ids = [face.id for face in faces]
    matrix = np.vstack([face.embedding for face in faces])
    distances = 1 - (matrix @ matrix.T)

    pairs: list[tuple[float, str, str]] = []
    for i in range(len(faces)):
        for j in range(i + 1, len(faces)):
            distance = float(distances[i, j])
            if distance <= threshold:
                pairs.append((distance, faces[i].id, faces[j].id))

    pairs.sort(key=lambda item: item[0])
    dsu = DisjointSet(ids, photo_sets)
    skipped_conflicts = 0
    merged_edges = 0

    for _, a, b in pairs:
        if dsu.union_if_safe(a, b):
            merged_edges += 1
        else:
            skipped_conflicts += 1

    groups = dsu.groups()
    logger.info(
        "threshold=%.3f candidate_pairs=%d merged_edges=%d conflict_or_duplicate_edges=%d groups=%d",
        threshold,
        len(pairs),
        merged_edges,
        skipped_conflicts,
        len(groups),
    )
    return groups


def _target_for_group(group: list[str], by_id: dict[str, FaceRow]) -> str:
    return max(group, key=lambda face_id: by_id[face_id].photo_count)


def _refresh_photo_count(sb, face_id: str) -> int:
    res = sb.table("photo_faces").select("id", count="exact").eq("face_id", face_id).execute()
    count = res.count or 0
    sb.table("faces").update({"photo_count": count}).eq("id", face_id).execute()
    return count


def _update_target_embedding(sb, target_id: str, group: list[str], by_id: dict[str, FaceRow]):
    vectors = []
    weights = []
    for face_id in group:
        face = by_id[face_id]
        vectors.append(face.embedding)
        weights.append(max(face.photo_count, 1))

    merged = np.average(np.vstack(vectors), axis=0, weights=np.asarray(weights))
    merged = merged / np.linalg.norm(merged)
    sb.table("faces").update({"embedding": merged.tolist()}).eq("id", target_id).execute()


def _merge_group(group: list[str], by_id: dict[str, FaceRow]) -> tuple[str, list[str], int]:
    sb = get_client()
    target_id = _target_for_group(group, by_id)
    source_ids = [face_id for face_id in group if face_id != target_id]

    _update_target_embedding(sb, target_id, group, by_id)

    rows = []
    for chunk in _chunks(source_ids):
        rows.extend(_fetch_all(
            sb.table("photo_faces")
            .select("photo_id, bbox_x, bbox_y, bbox_w, bbox_h, confidence")
            .in_("face_id", chunk)
        ))
    for row in rows:
        sb.table("photo_faces").upsert(
            {
                "photo_id": row["photo_id"],
                "face_id": target_id,
                "bbox_x": row["bbox_x"],
                "bbox_y": row["bbox_y"],
                "bbox_w": row["bbox_w"],
                "bbox_h": row["bbox_h"],
                "confidence": row["confidence"],
            },
            on_conflict="photo_id,face_id",
        ).execute()

    for chunk in _chunks(source_ids):
        sb.table("photo_faces").delete().in_("face_id", chunk).execute()
        sb.table("faces").delete().in_("id", chunk).execute()
    photo_count = _refresh_photo_count(sb, target_id)
    return target_id, source_ids, photo_count


def _refresh_all_counts(face_ids: list[str]) -> None:
    sb = get_client()
    for face_id in face_ids:
        _refresh_photo_count(sb, face_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--refresh-counts", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    faces = _load_faces(args.event_id)
    by_id = {face.id: face for face in faces}
    photo_sets = _load_face_photos(list(by_id))
    if args.refresh_counts:
        _refresh_all_counts(list(by_id))
        faces = _load_faces(args.event_id)
        by_id = {face.id: face for face in faces}

    groups = _find_duplicate_groups(faces, photo_sets, args.threshold)
    duplicate_faces = sum(len(group) - 1 for group in groups)
    estimated_remaining = len(faces) - duplicate_faces

    print(f"faces_before={len(faces)}")
    print(f"duplicate_groups={len(groups)}")
    print(f"faces_to_merge={duplicate_faces}")
    print(f"estimated_faces_after={estimated_remaining}")

    for group in sorted(groups, key=len, reverse=True)[:20]:
        target = _target_for_group(group, by_id)
        counts = sorted((by_id[face_id].photo_count for face_id in group), reverse=True)
        print(f"group_size={len(group)} target={target} counts={counts[:8]}")

    if not args.apply:
        print("dry_run=true")
        return

    merged_sources = 0
    for index, group in enumerate(groups, start=1):
        target_id, source_ids, photo_count = _merge_group(group, by_id)
        merged_sources += len(source_ids)
        logger.info(
            "merged group %d/%d target=%s sources=%d photo_count=%d",
            index,
            len(groups),
            target_id,
            len(source_ids),
            photo_count,
        )

    print(f"applied=true merged_sources={merged_sources}")


if __name__ == "__main__":
    main()
