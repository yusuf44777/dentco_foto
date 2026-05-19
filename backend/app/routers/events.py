from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.supabase import get_client

router = APIRouter(prefix="/events", tags=["events"])


class EventCreate(BaseModel):
    name: str
    description: str | None = None
    date: str | None = None


@router.post("/", status_code=201)
def create_event(body: EventCreate):
    sb = get_client()
    res = sb.table("events").insert(body.model_dump(exclude_none=True)).execute()
    return res.data[0]


@router.get("/")
def list_events():
    sb = get_client()
    res = sb.table("events").select("*").order("created_at", desc=True).execute()
    return res.data
