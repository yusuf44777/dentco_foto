import json
import logging

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.supabase import get_client
from app.core.config import settings

router = APIRouter(prefix="/faces", tags=["faces"])
logger = logging.getLogger(__name__)


class MergeFacesRequest(BaseModel):
    target_face_id: str
    source_face_ids: list[str]


class DeleteFacesRequest(BaseModel):
    face_ids: list[str]


def _chunks(items: list[str], size: int = 75):
    for start in range(0, len(items), size):
        yield items[start:start + size]


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


def _parse_embedding(value) -> np.ndarray | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = json.loads(value)
    return np.asarray(value, dtype=np.float32)


def _refresh_photo_count(sb, face_id: str) -> int:
    res = sb.table("photo_faces").select("id", count="exact").eq("face_id", face_id).execute()
    count = res.count or 0
    sb.table("faces").update({"photo_count": count}).eq("id", face_id).execute()
    return count


def _update_merged_centroid(sb, target: dict, sources: list[dict]):
    vectors: list[np.ndarray] = []
    weights: list[int] = []

    for face in [target, *sources]:
        embedding = _parse_embedding(face.get("embedding"))
        if embedding is None:
            continue
        vectors.append(embedding)
        weights.append(max(int(face.get("photo_count") or 0), 1))

    if not vectors:
        return

    merged = np.average(np.vstack(vectors), axis=0, weights=np.asarray(weights))
    norm = np.linalg.norm(merged)
    if norm == 0:
        return

    sb.table("faces").update({"embedding": (merged / norm).tolist()}).eq("id", target["id"]).execute()


@router.get("/")
def list_faces(event_id: str = Query(...)):
    """Return all unique faces for an event, sorted by how many photos they appear in."""
    sb = get_client()
    res = (
        sb.table("faces")
        .select("id, avatar_path, label, photo_count")
        .eq("event_id", event_id)
        .order("photo_count", desc=True)
        .execute()
    )
    # Attach public URL for the avatar
    bucket = settings.storage_bucket
    face_ids = [face["id"] for face in res.data]
    exact_counts = {face_id: 0 for face_id in face_ids}
    for chunk in _chunks(face_ids):
        links = _fetch_all(
            sb.table("photo_faces")
            .select("face_id")
            .in_("face_id", chunk)
        )
        for link in links:
            exact_counts[link["face_id"]] = exact_counts.get(link["face_id"], 0) + 1

    for face in res.data:
        face["avatar_url"] = sb.storage.from_(bucket).get_public_url(face["avatar_path"])
        face["photo_count"] = exact_counts.get(face["id"], int(face.get("photo_count") or 0))
    res.data.sort(key=lambda face: face["photo_count"], reverse=True)
    return res.data


@router.post("/merge")
def merge_faces(body: MergeFacesRequest):
    """Merge duplicate face clusters into a single target face."""
    source_ids = [face_id for face_id in body.source_face_ids if face_id != body.target_face_id]
    if not source_ids:
        raise HTTPException(status_code=400, detail="source_face_ids must contain another face")

    sb = get_client()
    face_ids = [body.target_face_id, *source_ids]
    faces_res = (
        sb.table("faces")
        .select("id, event_id, embedding, photo_count")
        .in_("id", face_ids)
        .execute()
    )
    faces_by_id = {face["id"]: face for face in faces_res.data}
    missing = [face_id for face_id in face_ids if face_id not in faces_by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Face not found: {', '.join(missing)}")

    target = faces_by_id[body.target_face_id]
    sources = [faces_by_id[face_id] for face_id in source_ids]
    if any(face["event_id"] != target["event_id"] for face in sources):
        raise HTTPException(status_code=400, detail="All faces must belong to the same event")

    _update_merged_centroid(sb, target, sources)

    links_res = (
        sb.table("photo_faces")
        .select("photo_id, bbox_x, bbox_y, bbox_w, bbox_h, confidence")
        .in_("face_id", source_ids)
        .execute()
    )
    for link in links_res.data:
        sb.table("photo_faces").upsert(
            {
                "photo_id": link["photo_id"],
                "face_id": body.target_face_id,
                "bbox_x": link["bbox_x"],
                "bbox_y": link["bbox_y"],
                "bbox_w": link["bbox_w"],
                "bbox_h": link["bbox_h"],
                "confidence": link["confidence"],
            },
            on_conflict="photo_id,face_id",
        ).execute()

    sb.table("photo_faces").delete().in_("face_id", source_ids).execute()
    sb.table("faces").delete().in_("id", source_ids).execute()
    photo_count = _refresh_photo_count(sb, body.target_face_id)

    return {
        "target_face_id": body.target_face_id,
        "merged_face_ids": source_ids,
        "photo_count": photo_count,
    }


def _delete_faces(face_ids: list[str]):
    unique_ids = list(dict.fromkeys(face_ids))
    if not unique_ids:
        raise HTTPException(status_code=400, detail="face_ids must not be empty")

    sb = get_client()
    rows = []
    for chunk in _chunks(unique_ids):
        res = (
            sb.table("faces")
            .select("id, avatar_path")
            .in_("id", chunk)
            .execute()
        )
        rows.extend(res.data or [])

    found_by_id = {row["id"]: row for row in rows}
    missing = [face_id for face_id in unique_ids if face_id not in found_by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Face not found: {', '.join(missing)}")

    for chunk in _chunks(unique_ids):
        sb.table("faces").delete().in_("id", chunk).execute()

    avatar_paths = [row.get("avatar_path") for row in rows if row.get("avatar_path")]
    avatar_delete_failed = False
    if avatar_paths:
        try:
            for chunk in _chunks(avatar_paths):
                sb.storage.from_(settings.storage_bucket).remove(chunk)
        except Exception as exc:
            avatar_delete_failed = True
            logger.warning("Deleted faces but failed to remove avatar files: %s", exc)

    return {
        "deleted_face_ids": unique_ids,
        "deleted_count": len(unique_ids),
        "avatar_delete_failed": avatar_delete_failed,
    }


@router.post("/delete")
def delete_faces(body: DeleteFacesRequest):
    """Delete bogus face clusters without deleting the underlying photos."""
    return _delete_faces(body.face_ids)


@router.delete("/{face_id}")
def delete_face(face_id: str):
    """Delete one bogus face cluster without deleting the underlying photos."""
    return _delete_faces([face_id])


@router.get("/{face_id}/photos")
def get_photos_for_face(face_id: str):
    """Return all photos that contain this face."""
    sb = get_client()
    res = (
        sb.table("photo_faces")
        .select("photos(id, storage_path, taken_at), bbox_x, bbox_y, bbox_w, bbox_h")
        .eq("face_id", face_id)
        .execute()
    )
    bucket = settings.storage_bucket
    photos = []
    for row in res.data:
        p = row["photos"]
        p["url"] = sb.storage.from_(bucket).get_public_url(p["storage_path"])
        p["bbox"] = {k: row[k] for k in ("bbox_x", "bbox_y", "bbox_w", "bbox_h")}
        photos.append(p)
    return photos
