"""
Admin endpoint to trigger ingestion from Google Drive.
Runs in a background thread so the HTTP response returns immediately.
"""

import logging
import traceback
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from app.services.ingestion import run_ingestion

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


class IngestRequest(BaseModel):
    event_id: str
    folder_id: str | None = None


def _safe_ingest(event_id: str, folder_id: str | None):
    try:
        run_ingestion(event_id, folder_id)
    except Exception:
        logger.error("Ingestion crashed:\n%s", traceback.format_exc())


@router.post("/ingest", status_code=202)
def trigger_ingestion(body: IngestRequest, bg: BackgroundTasks):
    bg.add_task(_safe_ingest, body.event_id, body.folder_id)
    return {"status": "accepted", "event_id": body.event_id}
