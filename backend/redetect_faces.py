"""
Face verilerini sıfırlayıp Storage'daki fotoğraflardan yeniden tespit eder.
Drive'dan indirme/upload olmadığı için ingestion'dan ~3x hızlı.

Kullanım:
  python redetect_faces.py --event-id <uuid>
"""

import argparse
import logging

from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv(".env.local")

from app.core.config import settings
from app.core.supabase import get_client
from app.services.face_processor import process_photo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EVENT_ID = "00cb7c6b-7953-4c6a-8ae9-3b3e71451b64"


def reset(event_id: str):
    sb = get_client()
    # Cascade delete: faces silinince photo_faces otomatik silinir
    deleted = sb.table("faces").delete().eq("event_id", event_id).execute()
    logger.info("Silinen yüz: %d", len(deleted.data))
    sb.table("photos").update({"processed": False}).eq("event_id", event_id).execute()
    logger.info("Tüm fotoğraflar unprocessed olarak işaretlendi.")


def redetect(event_id: str):
    sb = get_client()
    photos = (
        sb.table("photos")
        .select("id, storage_path")
        .eq("event_id", event_id)
        .eq("processed", False)
        .execute()
    )
    logger.info("%d fotoğraf işlenecek.", len(photos.data))

    errors = 0
    for photo in tqdm(photos.data, desc="photos"):
        try:
            data = sb.storage.from_(settings.storage_bucket).download(photo["storage_path"])
            process_photo(
                photo_id=photo["id"],
                event_id=event_id,
                image_bytes=data,
                storage_path=photo["storage_path"],
            )
        except Exception as exc:
            logger.error("Hata [%s]: %s", photo["id"], exc)
            errors += 1

    logger.info("Tamamlandı. Hata: %d", errors)
    remaining = sb.table("faces").select("id", count="exact").eq("event_id", event_id).execute()
    logger.info("Toplam benzersiz yüz: %d", remaining.count or 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", default=EVENT_ID)
    parser.add_argument("--skip-reset", action="store_true",
                        help="Mevcut yüzleri silmeden sadece işlenmemiş fotoğrafları çalıştır")
    args = parser.parse_args()

    if not args.skip_reset:
        logger.info("Faces sıfırlanıyor...")
        reset(args.event_id)

    logger.info("Tespit başlıyor...")
    redetect(args.event_id)
