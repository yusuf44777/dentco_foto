import os
import re
import tempfile
import zipfile
from pathlib import Path

import json
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

from app.core.auth import require_admin
from app.core.supabase import get_client
from app.core.config import settings

router = APIRouter(prefix="/faces", tags=["faces"])


class MergeFacesRequest(BaseModel):
    target_face_id: str
    source_face_ids: list[str] = Field(min_length=1)


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


def _safe_filename(value: str | None, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value or "").strip("._-")
    return cleaned or fallback


def _parse_embedding(value) -> np.ndarray:
    if isinstance(value, str):
        value = json.loads(value)
    arr = np.asarray(value, dtype=np.float32)
    norm = np.linalg.norm(arr)
    if norm == 0:
        raise ValueError("zero embedding")
    return arr / norm


def _refresh_photo_count(sb, face_id: str) -> int:
    res = sb.table("photo_faces").select("id", count="exact").eq("face_id", face_id).execute()
    count = res.count or 0
    sb.table("faces").update({"photo_count": count}).eq("id", face_id).execute()
    return count


def _update_merged_embedding(sb, target_id: str, face_rows: list[dict]) -> None:
    vectors = []
    weights = []
    for face in face_rows:
        if face.get("embedding") is None:
            continue
        vectors.append(_parse_embedding(face["embedding"]))
        weights.append(max(int(face.get("photo_count") or 0), 1))

    if not vectors:
        return

    merged = np.average(np.vstack(vectors), axis=0, weights=np.asarray(weights))
    norm = np.linalg.norm(merged)
    if norm == 0:
        return
    sb.table("faces").update({"embedding": (merged / norm).tolist()}).eq("id", target_id).execute()


def _photo_rows_for_face(sb, face_id: str) -> list[dict]:
    return _fetch_all(
        sb.table("photo_faces")
        .select("photos(id, storage_path, taken_at), bbox_x, bbox_y, bbox_w, bbox_h")
        .eq("face_id", face_id)
    )


def _zip_entry_name(index: int, storage_path: str) -> str:
    original = _safe_filename(Path(storage_path).name, f"photo_{index:04d}.jpg")
    stem, ext = os.path.splitext(original)
    if not ext:
        ext = ".jpg"
    return f"{index:04d}_{_safe_filename(stem, 'photo')}{ext.lower()}"


def _cleanup_file(path: str):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _write_photos_zip(sb, rows: list[dict]) -> tuple[str, int]:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    zip_path = tmp.name
    tmp.close()

    written = 0
    failures: list[str] = []
    bucket = sb.storage.from_(settings.storage_bucket)

    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for index, row in enumerate(rows, start=1):
                photo = row.get("photos") or {}
                storage_path = photo.get("storage_path")
                if not storage_path:
                    continue

                try:
                    archive.writestr(_zip_entry_name(index, storage_path), bucket.download(storage_path))
                    written += 1
                except Exception as exc:
                    failures.append(f"{storage_path}: {exc}")

            if failures:
                archive.writestr(
                    "_eksik_fotograflar.txt",
                    "Bu dosyalar storage'dan indirilemedi:\n" + "\n".join(failures),
                )
    except Exception:
        _cleanup_file(zip_path)
        raise

    if written == 0:
        _cleanup_file(zip_path)
        raise HTTPException(status_code=404, detail="No downloadable photos found for this face")

    return zip_path, written


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
    faces = res.data or []
    face_ids = [face["id"] for face in faces]
    exact_counts = {face_id: 0 for face_id in face_ids}
    for chunk in _chunks(face_ids):
        links = _fetch_all(
            sb.table("photo_faces")
            .select("face_id")
            .in_("face_id", chunk)
        )
        for link in links:
            exact_counts[link["face_id"]] = exact_counts.get(link["face_id"], 0) + 1

    for face in faces:
        face["avatar_url"] = sb.storage.from_(bucket).get_public_url(face["avatar_path"])
        face["photo_count"] = exact_counts.get(face["id"], int(face.get("photo_count") or 0))
    faces.sort(key=lambda face: face["photo_count"], reverse=True)
    return faces


@router.post("/merge")
def merge_faces(body: MergeFacesRequest, _: None = Depends(require_admin)):
    """Merge source face clusters into the selected target cluster."""
    source_ids = list(dict.fromkeys(body.source_face_ids))
    if body.target_face_id in source_ids:
        raise HTTPException(status_code=400, detail="Target face cannot also be a source face")

    all_ids = [body.target_face_id, *source_ids]
    sb = get_client()
    face_rows = (
        sb.table("faces")
        .select("id, event_id, embedding, photo_count")
        .in_("id", all_ids)
        .execute()
        .data
        or []
    )
    if len(face_rows) != len(all_ids):
        raise HTTPException(status_code=404, detail="One or more faces were not found")

    event_ids = {face["event_id"] for face in face_rows}
    if len(event_ids) != 1:
        raise HTTPException(status_code=400, detail="Faces must belong to the same event")

    _update_merged_embedding(sb, body.target_face_id, face_rows)

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
                "face_id": body.target_face_id,
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

    photo_count = _refresh_photo_count(sb, body.target_face_id)
    return {
        "target_face_id": body.target_face_id,
        "merged_face_ids": source_ids,
        "photo_count": photo_count,
    }


@router.get("/{face_id}/download")
def download_face_photos(face_id: str):
    """Download all photos for a face cluster as a ZIP archive."""
    sb = get_client()
    face_res = sb.table("faces").select("id, label").eq("id", face_id).limit(1).execute()
    faces = face_res.data or []
    if not faces:
        raise HTTPException(status_code=404, detail="Face not found")

    rows = _photo_rows_for_face(sb, face_id)
    if not rows:
        raise HTTPException(status_code=404, detail="No photos found for this face")

    zip_path, written = _write_photos_zip(sb, rows)
    label = _safe_filename(faces[0].get("label") or f"kisi_{face_id[:8]}", "dentco_fotograflar")
    filename = f"{label}_{written}_fotograf.zip"
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(_cleanup_file, zip_path),
    )


@router.delete("/{face_id}")
def delete_face(face_id: str, _: None = Depends(require_admin)):
    """Delete one face cluster while keeping the original photos."""
    sb = get_client()
    face_res = sb.table("faces").select("id").eq("id", face_id).limit(1).execute()
    if not (face_res.data or []):
        raise HTTPException(status_code=404, detail="Face not found")

    sb.table("photo_faces").delete().eq("face_id", face_id).execute()
    sb.table("faces").delete().eq("id", face_id).execute()
    return {"deleted_face_id": face_id}


@router.get("/{face_id}/photos")
def get_photos_for_face(face_id: str):
    """Return all photos that contain this face."""
    sb = get_client()
    bucket = settings.storage_bucket
    photos = []
    for row in _photo_rows_for_face(sb, face_id):
        if not row.get("photos"):
            continue
        p = dict(row["photos"])
        p["url"] = sb.storage.from_(bucket).get_public_url(p["storage_path"])
        p["bbox"] = {k: row[k] for k in ("bbox_x", "bbox_y", "bbox_w", "bbox_h")}
        photos.append(p)
    return photos
