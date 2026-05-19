"""
Convert existing HEIC/HEIF gallery photos in Supabase Storage to browser-friendly JPEG.

Dry run:
  python scripts/convert_heic_photos_to_jpeg.py --event-id <uuid>

Apply:
  python scripts/convert_heic_photos_to_jpeg.py --event-id <uuid> --apply
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pillow_heif
from dotenv import load_dotenv
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.local", override=True)

from app.core.config import settings  # noqa: E402
from app.core.supabase import get_client  # noqa: E402


logger = logging.getLogger(__name__)
pillow_heif.register_heif_opener()


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


def _is_heic_path(path: str) -> bool:
    return path.lower().endswith((".heic", ".heif"))


def _jpeg_path(path: str) -> str:
    stem = path.rsplit(".", 1)[0]
    return f"{stem}.jpg"


def _to_jpeg(data: bytes) -> bytes:
    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image).convert("RGB")
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=92, optimize=True)
        return out.getvalue()
    except Exception:
        pass

    src = dst = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".heic", delete=False) as temp:
            temp.write(data)
            src = temp.name
        dst = f"{src}.jpg"
        result = subprocess.run(
            ["sips", "-s", "format", "jpeg", src, "--out", dst],
            capture_output=True,
            timeout=45,
            check=False,
        )
        if result.returncode != 0:
            raise ValueError(result.stderr.decode("utf-8", errors="ignore") or "sips failed")
        with open(dst, "rb") as f:
            return f.read()
    finally:
        for path in (src, dst):
            if path and os.path.exists(path):
                os.unlink(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--delete-originals", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    sb = get_client()
    rows = _fetch_all(
        sb.table("photos")
        .select("id, storage_path")
        .eq("event_id", args.event_id)
    )
    heic_rows = [row for row in rows if _is_heic_path(row.get("storage_path") or "")]

    print(f"photos_total={len(rows)}")
    print(f"heic_photos={len(heic_rows)}")
    if not args.apply:
        for row in heic_rows[:20]:
            print(f"{row['id']} {row['storage_path']} -> {_jpeg_path(row['storage_path'])}")
        print("dry_run=true")
        return

    converted = 0
    failed = 0
    bucket = sb.storage.from_(settings.storage_bucket)
    for index, row in enumerate(heic_rows, start=1):
        old_path = row["storage_path"]
        new_path = _jpeg_path(old_path)
        try:
            data = bucket.download(old_path)
            jpeg = _to_jpeg(data)
            bucket.upload(
                path=new_path,
                file=jpeg,
                file_options={"content-type": "image/jpeg", "upsert": "true"},
            )
            sb.table("photos").update({"storage_path": new_path}).eq("id", row["id"]).execute()
            if args.delete_originals:
                bucket.remove([old_path])
            converted += 1
            if converted % 25 == 0 or index == len(heic_rows):
                logger.info("converted=%d failed=%d scanned=%d/%d", converted, failed, index, len(heic_rows))
        except Exception as exc:
            failed += 1
            logger.warning("failed %s: %s", old_path, exc)

    print(f"applied=true converted={converted} failed={failed}")


if __name__ == "__main__":
    main()
