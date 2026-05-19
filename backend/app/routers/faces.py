import os
import re
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

from app.core.supabase import get_client
from app.core.config import settings

router = APIRouter(prefix="/faces", tags=["faces"])


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
