"""
Google Drive service — streams photos from the configured folder (recursively).
Uses OAuth2 refresh token so no interactive login is needed.
"""

import io
import logging
import re
from collections import Counter
from typing import Generator
from urllib.parse import parse_qs, urlparse

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from app.core.config import settings

logger = logging.getLogger(__name__)

_FOLDER_MIME = "application/vnd.google-apps.folder"
_SHORTCUT_MIME = "application/vnd.google-apps.shortcut"
_GOOGLE_APPS_PREFIX = "application/vnd.google-apps."
_PHOTO_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


def _build_service():
    creds = Credentials(
        token=None,
        refresh_token=settings.google_drive_oauth_refresh_token,
        client_id=settings.google_drive_oauth_client_id,
        client_secret=settings.google_drive_oauth_client_secret,
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _get_authenticated_user(service) -> str:
    about = service.about().get(fields="user(emailAddress)").execute()
    return about.get("user", {}).get("emailAddress", "unknown")


def _extract_drive_id(value: str) -> str:
    """Accept either a raw Drive ID or a Drive URL."""
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        match = re.search(r"/folders/([^/?#]+)", parsed.path)
        if match:
            return match.group(1)

        query_id = parse_qs(parsed.query).get("id")
        if query_id:
            return query_id[0]

    return value


def _validate_folder_access(service, folder_id: str) -> None:
    try:
        folder = service.files().get(
            fileId=folder_id,
            fields="id,name,mimeType",
            supportsAllDrives=True,
        ).execute()
    except HttpError as exc:
        if exc.resp.status == 404:
            user_email = _get_authenticated_user(service)
            raise RuntimeError(
                f"Google Drive folder {folder_id} is not accessible to {user_email}. "
                "Share the folder with this account or generate a refresh token "
                "from the Google account that can access it."
            ) from exc
        raise

    if folder.get("mimeType") != _FOLDER_MIME:
        raise ValueError(f"Google Drive ID {folder_id} is not a folder.")

    logger.info("Drive root folder: %s (%s)", folder["name"], folder["id"])


def _is_photo_file(item: dict) -> bool:
    mime = item.get("mimeType", "")
    if mime.startswith("image/"):
        return True

    name = item.get("name", "").lower()
    return any(name.endswith(ext) for ext in _PHOTO_EXTENSIONS)


def _normalise_shortcut(item: dict) -> dict | None:
    details = item.get("shortcutDetails") or {}
    target_id = details.get("targetId")
    if not target_id:
        return None

    return {
        **item,
        "id": target_id,
        "shortcut_id": item.get("id"),
        "mimeType": details.get("targetMimeType") or item.get("mimeType", ""),
    }


def _list_folder(service, folder_id: str) -> list[dict]:
    """List all files and subfolders directly inside folder_id."""
    results, page_token = [], None
    while True:
        resp = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields=(
                "nextPageToken, "
                "files(id, name, mimeType, size, shortcutDetails(targetId,targetMimeType))"
            ),
            pageSize=1000,
            pageToken=page_token,
            supportsAllDrives=True,        # Shared Drive desteği
            includeItemsFromAllDrives=True,
        ).execute()
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results


def list_photo_files(folder_id: str | None = None) -> list[dict]:
    """
    Recursively return metadata for every image under the given folder.
    Descends into subfolders automatically.
    """
    service = _build_service()
    root = _extract_drive_id(folder_id or settings.google_drive_folder_id)
    _validate_folder_access(service, root)

    photos: list[dict] = []
    seen_folders: set[str] = set()
    seen_files: set[str] = set()
    queue: list[str] = [root]
    stats: Counter[str] = Counter()

    logger.info("Scanning Drive folder: %s", root)

    while queue:
        fid = queue.pop()
        if fid in seen_folders:
            continue

        seen_folders.add(fid)
        stats["folders_scanned"] += 1

        items = _list_folder(service, fid)
        stats["items_seen"] += len(items)
        logger.info("Drive folder %s returned %d item(s)", fid, len(items))

        for item in items:
            mime = item.get("mimeType", "")
            if mime == _SHORTCUT_MIME:
                stats["shortcuts_seen"] += 1
                item = _normalise_shortcut(item)
                if item is None:
                    stats["shortcuts_skipped"] += 1
                    continue
                mime = item.get("mimeType", "")

            if mime == _FOLDER_MIME:
                logger.info("Entering subfolder: %s (%s)", item["name"], item["id"])
                queue.append(item["id"])
            elif _is_photo_file(item):
                if item["id"] in seen_files:
                    stats["duplicates_skipped"] += 1
                    continue
                seen_files.add(item["id"])
                photos.append(item)
            elif mime.startswith(_GOOGLE_APPS_PREFIX):
                stats["google_workspace_skipped"] += 1
            else:
                stats["non_photo_skipped"] += 1

    logger.info(
        "Drive scan complete: photos=%d folders=%d items=%d shortcuts=%d "
        "non_photo_skipped=%d google_workspace_skipped=%d duplicates_skipped=%d",
        len(photos),
        stats["folders_scanned"],
        stats["items_seen"],
        stats["shortcuts_seen"],
        stats["non_photo_skipped"],
        stats["google_workspace_skipped"],
        stats["duplicates_skipped"],
    )
    return photos


def download_file(file_id: str) -> bytes:
    """Download a Drive file and return its raw bytes."""
    service = _build_service()
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request, chunksize=8 * 1024 * 1024)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def iter_photos(folder_id: str | None = None) -> Generator[tuple[dict, bytes], None, None]:
    """Yield (file_metadata, raw_bytes) for every photo, recursively."""
    for meta in list_photo_files(folder_id):
        data = download_file(meta["id"])
        yield meta, data
