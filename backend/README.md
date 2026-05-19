---
title: DentCo Foto Backend
sdk: docker
app_port: 7860
pinned: false
---

# DentCo Foto Backend

FastAPI backend for the DentCo photo gallery.

## Required environment variables

Set these as Space secrets:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Admin merge/delete tools require:

- `ADMIN_PASSWORD`

Google Drive ingestion is optional at runtime, but these are required if you call `/admin/ingest`:

- `GOOGLE_DRIVE_OAUTH_CLIENT_ID`
- `GOOGLE_DRIVE_OAUTH_CLIENT_SECRET`
- `GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN`
- `GOOGLE_DRIVE_FOLDER_ID`

Optional:

- `EXTRA_ORIGIN`
- `FACE_SIMILARITY_THRESHOLD`
- `YOLO_CONFIDENCE`
- `STORAGE_BUCKET`
- `ADMIN_SESSION_SECRET`
- `ADMIN_SESSION_TTL_SECONDS`
