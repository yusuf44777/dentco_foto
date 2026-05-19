import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import events, faces, ingestion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)

app = FastAPI(title="Face-Match Gallery API", version="1.0.0")

import os

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "https://dentcooutliersfoto.vercel.app",
    *([o] if (o := os.getenv("EXTRA_ORIGIN")) else []),
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router)
app.include_router(faces.router)
app.include_router(ingestion.router)


@app.get("/healthz")
def health():
    return {"ok": True}
