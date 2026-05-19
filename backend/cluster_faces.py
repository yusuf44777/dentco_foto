"""
ArcFace embedding'lerini DBSCAN ile kümeleyip aynı kişileri birleştirir.

Önce preview:
  python cluster_faces.py --event-id <uuid> --preview

Beğendiğin eps ile çalıştır:
  python cluster_faces.py --event-id <uuid> --eps 0.65
"""

import argparse
import json
import logging

import numpy as np
from sklearn.cluster import DBSCAN
from dotenv import load_dotenv

load_dotenv(".env.local")

from app.core.supabase import get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_faces(event_id: str) -> tuple[list[str], np.ndarray]:
    sb = get_client()
    res = (
        sb.table("faces")
        .select("id, embedding, photo_count")
        .eq("event_id", event_id)
        .execute()
    )
    face_ids, vectors = [], []
    for row in res.data:
        emb = row["embedding"]
        if isinstance(emb, str):
            emb = json.loads(emb)
        v = np.array(emb, dtype=np.float32)
        v /= np.linalg.norm(v)          # normalize
        face_ids.append(row["id"])
        vectors.append(v)
    return face_ids, np.vstack(vectors)


def preview(face_ids: list[str], X: np.ndarray):
    """Farklı eps değerlerinde kaç cluster oluştuğunu göster."""
    print(f"\n{'eps':>6}  {'kümeler':>8}  {'tekil (gürültü)':>16}")
    print("-" * 36)
    for eps in [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
        labels = DBSCAN(eps=eps, min_samples=2, metric="cosine", n_jobs=-1).fit_predict(X)
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        n_noise    = (labels == -1).sum()
        print(f"{eps:>6.2f}  {n_clusters:>8}  {n_noise:>16}")
    print()
    print("Hedef kişi sayısına (~100) en yakın eps'i seç.")


def merge(event_id: str, face_ids: list[str], X: np.ndarray, eps: float):
    labels = DBSCAN(eps=eps, min_samples=2, metric="cosine", n_jobs=-1).fit_predict(X)
    sb = get_client()

    # fotoğraf sayısını önceden al (canonical seçimi için)
    res = sb.table("faces").select("id, photo_count").eq("event_id", event_id).execute()
    count_map = {r["id"]: r["photo_count"] for r in res.data}

    # her cluster için en çok fotoğrafı olan yüzü canonical seç
    clusters: dict[int, list[str]] = {}
    for idx, label in enumerate(labels):
        if label == -1:
            continue
        clusters.setdefault(label, []).append(face_ids[idx])

    logger.info("Toplam %d cluster bulundu, %d tekil yüz gürültü.",
                len(clusters), (labels == -1).sum())

    merged_total = 0
    for group in clusters.values():
        if len(group) < 2:
            continue
        canonical = max(group, key=lambda fid: count_map.get(fid, 0))
        sources   = [fid for fid in group if fid != canonical]

        # photo_faces'i canonical'a taşı
        for src in sources:
            rows = sb.table("photo_faces").select(
                "photo_id, bbox_x, bbox_y, bbox_w, bbox_h, confidence"
            ).eq("face_id", src).execute().data

            for row in rows:
                sb.table("photo_faces").upsert(
                    {**row, "face_id": canonical},
                    on_conflict="photo_id,face_id",
                ).execute()

            sb.table("photo_faces").delete().eq("face_id", src).execute()
            sb.table("faces").delete().eq("id", src).execute()

        # canonical photo_count güncelle
        cnt = sb.table("photo_faces").select("id", count="exact").eq("face_id", canonical).execute()
        sb.table("faces").update({"photo_count": cnt.count or 0}).eq("id", canonical).execute()
        merged_total += len(sources)

    logger.info("Bitti. %d yüz birleştirildi.", merged_total)
    remaining = sb.table("faces").select("id", count="exact").eq("event_id", event_id).execute()
    logger.info("Kalan benzersiz yüz: %d", remaining.count or 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--eps", type=float, default=None,
                        help="DBSCAN cosine distance threshold (0-2). Belirtilmezse preview gösterilir.")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()

    logger.info("Yüzler yükleniyor...")
    face_ids, X = load_faces(args.event_id)
    logger.info("%d yüz yüklendi.", len(face_ids))

    if args.preview or args.eps is None:
        preview(face_ids, X)
    else:
        merge(args.event_id, face_ids, X, args.eps)
