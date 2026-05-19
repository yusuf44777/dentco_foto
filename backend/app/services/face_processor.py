"""
Core AI pipeline:
  1. Detect faces + extract 512-d ArcFace embeddings via InsightFace (buffalo_l)
  2. Match against existing embeddings via Supabase pgvector RPC
  3. Insert new unique face or link to existing face
"""

import io
import uuid
import logging
import json

import cv2
import numpy as np
import pillow_heif
from PIL import Image
from insightface.app import FaceAnalysis

pillow_heif.register_heif_opener()

from app.core.config import settings
from app.core.supabase import get_client, with_retry

logger = logging.getLogger(__name__)

_analyzer: FaceAnalysis | None = None


def _get_analyzer() -> FaceAnalysis:
    global _analyzer
    if _analyzer is None:
        # buffalo_l = RetinaFace detector + ArcFace recognition (best accuracy)
        _analyzer = FaceAnalysis(
            name="buffalo_l",
            providers=["CPUExecutionProvider"],
        )
        _analyzer.prepare(ctx_id=0, det_size=(640, 640))
        logger.info("InsightFace buffalo_l model loaded.")
    return _analyzer


# ── image helpers ───────────────────────────────────────────────────────────

def _bytes_to_bgr(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is not None:
        return img
    # pillow_heif ile dene
    try:
        heif_file = pillow_heif.open_heif(data, convert_hdr_to_8bit=True)
        pil_img = Image.frombytes(heif_file.mode, heif_file.size, heif_file.data)
        return cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
    except Exception:
        pass
    # iPhone HEIC (depth map'li): macOS sips ile dön
    try:
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".heic", delete=False) as f:
            f.write(data)
            src = f.name
        dst = src.replace(".heic", ".jpg")
        r = subprocess.run(["sips", "-s", "format", "jpeg", src, "--out", dst],
                           capture_output=True, timeout=30)
        if r.returncode == 0:
            img = cv2.imread(dst)
        os.unlink(src)
        if os.path.exists(dst):
            os.unlink(dst)
        if r.returncode == 0 and img is not None:
            return img
    except Exception:
        pass
    try:
        pil_img = Image.open(io.BytesIO(data)).convert("RGB")
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    except Exception as exc:
        raise ValueError(f"Could not decode image: {exc}") from exc


def _crop_face(img_bgr: np.ndarray, x1: int, y1: int, x2: int, y2: int, pad: float = 0.20) -> np.ndarray:
    H, W = img_bgr.shape[:2]
    w, h = x2 - x1, y2 - y1
    px, py = int(w * pad), int(h * pad)
    return img_bgr[max(0, y1 - py):min(H, y2 + py), max(0, x1 - px):min(W, x2 + px)]


def _bgr_to_jpeg_bytes(img: np.ndarray) -> bytes:
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes()


# ── Supabase helpers ────────────────────────────────────────────────────────

@with_retry()
def _upload_to_storage(bucket: str, path: str, data: bytes, content_type: str = "image/jpeg"):
    get_client().storage.from_(bucket).upload(
        path=path,
        file=data,
        file_options={"content-type": content_type, "upsert": "true"},
    )


@with_retry()
def _find_matching_face(event_id: str, embedding: list[float]) -> str | None:
    res = get_client().rpc("match_face", {
        "query_embedding": embedding,
        "event": event_id,
        "threshold": settings.face_similarity_threshold,
        "max_results": 1,
    }).execute()
    return res.data[0]["face_id"] if res.data else None


def _parse_embedding(value) -> np.ndarray | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = json.loads(value)
    return np.asarray(value, dtype=np.float32)


@with_retry()
def _update_face_centroid(face_id: str, embedding: list[float]):
    sb = get_client()
    res = sb.table("faces").select("embedding, photo_count").eq("id", face_id).single().execute()
    current = _parse_embedding(res.data.get("embedding"))
    if current is None:
        return

    incoming = np.asarray(embedding, dtype=np.float32)
    weight = max(int(res.data.get("photo_count") or 0), 1)
    centroid = (current * weight) + incoming
    norm = np.linalg.norm(centroid)
    if norm == 0:
        return

    sb.table("faces").update({"embedding": (centroid / norm).tolist()}).eq("id", face_id).execute()


@with_retry()
def _create_face(event_id: str, avatar_path: str, embedding: list[float]) -> str:
    res = get_client().table("faces").insert({
        "event_id": event_id,
        "avatar_path": avatar_path,
        "embedding": embedding,
    }).execute()
    return res.data[0]["id"]


@with_retry()
def _refresh_face_photo_count(face_id: str):
    sb = get_client()
    res = sb.table("photo_faces").select("id", count="exact").eq("face_id", face_id).execute()
    sb.table("faces").update({"photo_count": res.count or 0}).eq("id", face_id).execute()


@with_retry()
def _link_photo_face(photo_id: str, face_id: str, bbox: dict, confidence: float):
    sb = get_client()
    sb.table("photo_faces").upsert(
        {
            "photo_id": photo_id,
            "face_id": face_id,
            "bbox_x": bbox["x"],
            "bbox_y": bbox["y"],
            "bbox_w": bbox["w"],
            "bbox_h": bbox["h"],
            "confidence": confidence,
        },
        on_conflict="photo_id,face_id",
    ).execute()
    _refresh_face_photo_count(face_id)


@with_retry()
def _mark_photo_processed(photo_id: str):
    get_client().table("photos").update({"processed": True}).eq("id", photo_id).execute()


# ── main entry point ────────────────────────────────────────────────────────

def process_photo(
    *,
    photo_id: str,
    event_id: str,
    image_bytes: bytes,
    storage_path: str,
) -> int:
    img_bgr = _bytes_to_bgr(image_bytes)
    H, W = img_bgr.shape[:2]

    analyzer = _get_analyzer()
    faces = analyzer.get(img_bgr)

    face_count = 0

    for face in faces:
        if face.det_score < settings.yolo_confidence:
            continue

        x1, y1, x2, y2 = face.bbox.astype(int)
        w, h = x2 - x1, y2 - y1
        if w < 30 or h < 30:
            continue

        # ArcFace embedding — normalize to unit vector
        raw_emb = face.embedding
        embedding = (raw_emb / np.linalg.norm(raw_emb)).tolist()

        face_id = _find_matching_face(event_id, embedding)

        if face_id is None:
            face_crop = _crop_face(img_bgr, x1, y1, x2, y2)
            avatar_key = f"events/{event_id}/avatars/{uuid.uuid4()}.jpg"
            _upload_to_storage(settings.storage_bucket, avatar_key, _bgr_to_jpeg_bytes(face_crop))
            face_id = _create_face(event_id, avatar_key, embedding)
            logger.info("New face created: %s", face_id)
        else:
            _update_face_centroid(face_id, embedding)

        bbox = {"x": x1 / W, "y": y1 / H, "w": w / W, "h": h / H}
        _link_photo_face(photo_id, face_id, bbox, float(face.det_score))
        face_count += 1

    _mark_photo_processed(photo_id)
    logger.info("Photo %s → %d face(s)", photo_id, face_count)
    return face_count
