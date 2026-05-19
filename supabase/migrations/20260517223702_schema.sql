-- ============================================================
-- Face-Match Event Gallery - Supabase Schema
-- ============================================================

-- Enable pgvector for cosine similarity on embeddings
create extension if not exists vector;

-- EVENTS
create table events (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  description text,
  date        date,
  created_at  timestamptz default now()
);

-- PHOTOS
-- Stores metadata for each original photo; actual file lives in Supabase Storage
create table photos (
  id              uuid primary key default gen_random_uuid(),
  event_id        uuid references events(id) on delete cascade,
  storage_path    text not null unique,   -- e.g. "events/{event_id}/photos/{filename}"
  drive_file_id   text unique,            -- Google Drive file ID (source)
  width           int,
  height          int,
  taken_at        timestamptz,
  processed       boolean default false,  -- true after face detection is done
  created_at      timestamptz default now()
);

create index idx_photos_event on photos(event_id);
create index idx_photos_processed on photos(processed);

-- FACES
-- Each row = one unique person identified across all photos
create table faces (
  id            uuid primary key default gen_random_uuid(),
  event_id      uuid references events(id) on delete cascade,
  avatar_path   text not null,            -- cropped face thumbnail in Storage
  embedding     vector(512),              -- FaceNet/DeepFace 512-d vector
  label         text,                     -- optional human-readable label
  photo_count   int default 0,            -- denormalised for fast sorting
  created_at    timestamptz default now()
);

create index idx_faces_event on faces(event_id);
-- HNSW index for fast approximate nearest-neighbour search
create index idx_faces_embedding on faces using hnsw (embedding vector_cosine_ops);

-- PHOTO_FACES (junction)
-- Maps which faces appear in which photos, with bounding box info
create table photo_faces (
  id          uuid primary key default gen_random_uuid(),
  photo_id    uuid references photos(id) on delete cascade,
  face_id     uuid references faces(id) on delete cascade,
  bbox_x      float,  -- normalised 0-1
  bbox_y      float,
  bbox_w      float,
  bbox_h      float,
  confidence  float,  -- detection confidence score
  unique (photo_id, face_id)
);

create index idx_pf_photo on photo_faces(photo_id);
create index idx_pf_face on photo_faces(face_id);

-- RPC: find nearest faces
-- Used by backend to find the closest known face for a given embedding
create or replace function match_face(
  query_embedding vector(512),
  event           uuid,
  threshold       float default 0.40,   -- cosine distance threshold
  max_results     int   default 1
)
returns table (face_id uuid, distance float)
language sql stable
as $$
  select id as face_id,
         embedding <=> query_embedding as distance
  from   faces
  where  event_id = event
    and  embedding <=> query_embedding < threshold
  order  by distance
  limit  max_results;
$$;

-- RPC: increment photo_count
create or replace function increment_face_photo_count(p_face_id uuid)
returns void language sql as $$
  update faces set photo_count = photo_count + 1 where id = p_face_id;
$$;
