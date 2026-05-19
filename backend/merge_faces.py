"""
Aynı kişiye ait ayrı face kayıtlarını birleştirir.
Çalıştır: python merge_faces.py --event-id <uuid> --threshold 0.55
"""
import argparse
import logging
from collections import defaultdict

import numpy as np
from dotenv import load_dotenv

load_dotenv(".env.local")

from app.core.supabase import get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _parse_embedding(raw) -> np.ndarray:
    if isinstance(raw, str):
        import json
        raw = json.loads(raw)
    return np.array(raw, dtype=np.float32)


def cosine_distance(a, b) -> float:
    a, b = _parse_embedding(a), _parse_embedding(b)
    return float(1 - np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def find_groups(face_ids: list[str], embeddings: list[list], threshold: float) -> list[list[str]]:
    """Union-Find ile eşik altındaki tüm yüzleri grupla."""
    parent = {fid: fid for fid in face_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    n = len(face_ids)
    for i in range(n):
        for j in range(i + 1, n):
            if cosine_distance(embeddings[i], embeddings[j]) < threshold:
                union(face_ids[i], face_ids[j])

    groups: dict[str, list[str]] = defaultdict(list)
    for fid in face_ids:
        groups[find(fid)].append(fid)

    return [g for g in groups.values() if len(g) > 1]


def merge_faces(event_id: str, threshold: float, dry_run: bool = False):
    sb = get_client()

    logger.info("Fetching all faces for event %s ...", event_id)
    res = sb.table("faces").select("id, embedding, photo_count, avatar_path").eq("event_id", event_id).execute()
    faces = res.data

    if not faces:
        logger.info("No faces found.")
        return

    face_ids   = [f["id"] for f in faces]
    embeddings = [f["embedding"] for f in faces]
    counts     = {f["id"]: f["photo_count"] for f in faces}

    logger.info("Loaded %d faces. Computing pairwise distances ...", len(faces))
    groups = find_groups(face_ids, embeddings, threshold)
    logger.info("Found %d merge group(s).", len(groups))

    for group in groups:
        # canonical = en çok fotoğrafı olan yüz
        canonical = max(group, key=lambda fid: counts.get(fid, 0))
        duplicates = [fid for fid in group if fid != canonical]

        logger.info("Merging %d face(s) → %s", len(duplicates), canonical)

        if dry_run:
            logger.info("  [dry-run] would merge: %s", duplicates)
            continue

        for dup_id in duplicates:
            # photo_faces kayıtlarını canonical'a taşı
            sb.table("photo_faces").update({"face_id": canonical}).eq("face_id", dup_id).execute()
            # duplicate face kaydını sil
            sb.table("faces").delete().eq("id", dup_id).execute()
            logger.info("  Deleted duplicate face %s", dup_id)

        # canonical'ın photo_count'ını yeniden hesapla
        cnt_res = sb.table("photo_faces").select("id", count="exact").eq("face_id", canonical).execute()
        new_count = cnt_res.count or 0
        sb.table("faces").update({"photo_count": new_count}).eq("id", canonical).execute()
        logger.info("  Canonical %s → photo_count=%d", canonical, new_count)

    logger.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument("--dry-run", action="store_true", help="Değişiklik yapmadan sadece göster")
    args = parser.parse_args()
    merge_faces(args.event_id, args.threshold, args.dry_run)
