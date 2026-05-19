"""
Ingestion pipeline: pull photos from Google Drive → upload to Supabase Storage
→ queue them for face processing.

Run directly:  python -m app.services.ingestion --event-id <uuid>
Restart-safe: already-processed photos are skipped automatically.
"""

import argparse
import logging

from tqdm import tqdm

from app.core.config import settings
from app.core.supabase import get_client, with_retry
from app.services.drive import iter_photos
from app.services.face_processor import process_photo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@with_retry()
def _get_processed_drive_ids(event_id: str) -> set[str]:
    """Return drive_file_id set for photos already fully processed."""
    sb = get_client()
    res = (
        sb.table("photos")
        .select("drive_file_id")
        .eq("event_id", event_id)
        .eq("processed", True)
        .execute()
    )
    return {row["drive_file_id"] for row in res.data}


@with_retry()
def _register_photo(event_id: str, drive_file_id: str, storage_path: str) -> str:
    sb = get_client()
    existing = sb.table("photos").select("id").eq("drive_file_id", drive_file_id).execute()
    if existing.data:
        return existing.data[0]["id"]
    res = sb.table("photos").insert({
        "event_id": event_id,
        "drive_file_id": drive_file_id,
        "storage_path": storage_path,
    }).execute()
    return res.data[0]["id"]


def run_ingestion(event_id: str, folder_id: str | None = None):
    logger.info("Starting ingestion for event %s", event_id)
    sb = get_client()

    try:
        sb.storage.create_bucket(settings.storage_bucket, options={"public": True})
    except Exception:
        pass  # already exists

    # Load already-processed IDs once — skip them during iteration
    done_ids = _get_processed_drive_ids(event_id)
    logger.info("Already processed: %d photo(s) — will skip.", len(done_ids))

    skipped = 0
    for meta, image_bytes in tqdm(iter_photos(folder_id), desc="photos"):
        drive_id = meta["id"]
        filename = meta["name"]

        if drive_id in done_ids:
            skipped += 1
            continue

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
        storage_path = f"events/{event_id}/photos/{drive_id}.{ext}"

        try:
            sb.storage.from_(settings.storage_bucket).upload(
                path=storage_path,
                file=image_bytes,
                file_options={"content-type": meta.get("mimeType", "image/jpeg"), "upsert": "true"},
            )
        except Exception as e:
            logger.error("Storage upload failed for %s: %s", filename, e)
            continue

        photo_id = _register_photo(event_id, drive_id, storage_path)

        try:
            process_photo(
                photo_id=photo_id,
                event_id=event_id,
                image_bytes=image_bytes,
                storage_path=storage_path,
            )
        except Exception as e:
            logger.error("Face processing failed for %s: %s", filename, e)

    logger.info("Ingestion complete. Skipped %d already-processed photo(s).", skipped)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--folder-id", default=None)
    args = parser.parse_args()
    run_ingestion(args.event_id, args.folder_id)
