# Face-Match Event Gallery

## Hızlı Başlangıç

### 1. Supabase Şemasını Uygula
Supabase → SQL Editor'de `supabase/schema.sql` içeriğini çalıştır.

### 2. Backend
> Python 3.11 kullan. Anaconda/base Python 3.13 ile Pillow, NumPy, OpenCV ve DeepFace pinleri wheel bulamayip build hatasina dusebilir.

Conda ile onerilen kurulum:
```bash
conda env create -f environment.yml
conda activate dentco-foto
```

Venv ile kurulum:
```bash
cd backend
cp .env.example .env           # bilgileri doldur
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload   # http://localhost:8000
```

### 3. Fotoğrafları Drive'dan İçe Aktar
```bash
# Önce Supabase'de bir event oluştur, id'yi not al
curl -X POST http://localhost:8000/events/ \
  -H "Content-Type: application/json" \
  -d '{"name":"Düğün 2024-06","date":"2024-06-15"}'

# Sonra ingestion'ı tetikle
curl -X POST http://localhost:8000/admin/ingest \
  -H "Content-Type: application/json" \
  -d '{"event_id":"<uuid-buraya>"}'
```

Drive API `File not found` hatasi verirse klasor ID yanlis olmak zorunda degil;
OAuth refresh token'in bagli oldugu Google hesabi o klasoru goremiyor olabilir.
Klasoru bu hesaba paylas veya refresh token'i klasoru gorebilen hesapla yeniden uret:

```bash
cd backend
python scripts/google_drive_refresh_token.py
```

`redirect_uri_mismatch` hatasi alirsan Google Cloud Console'da OAuth client ayarina gir:
`APIs & Services` -> `Credentials` -> OAuth 2.0 Client ID. `Authorized redirect URIs`
alanina script'in bastigi URI'yi ekle. Varsayilan deger:

```text
http://localhost:8080/
```

URI birebir ayni olmali; sondaki `/` dahil.

Script'in bastigi `GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN` degerini `.env.local` ve deploy
environment degiskenlerinde guncelle.

> İşlem arka planda çalışır. 11 GB için birkaç saat sürebilir.

### 4. Frontend
```bash
cd frontend
npm install
npm run dev     # http://localhost:5173
```

## Mimari

```
dentco_foto/
├── supabase/schema.sql        ← pgvector şeması
├── backend/
│   └── app/
│       ├── main.py            ← FastAPI app
│       ├── core/              ← config, supabase client
│       ├── routers/           ← events, faces, admin/ingest
│       └── services/
│           ├── drive.py       ← Google Drive OAuth2 stream
│           ├── face_processor.py  ← YOLO + DeepFace pipeline
│           └── ingestion.py   ← orchestrator
└── frontend/
    └── src/
        ├── components/
        │   ├── FaceGrid.tsx   ← yüz avatarları grid
        │   └── PhotoGallery.tsx ← masonry galeri + lightbox
        ├── hooks/useEvent.ts
        ├── lib/api.ts
        └── types/index.ts
```

## Eşik Ayarları
`.env` içindeki `FACE_SIMILARITY_THRESHOLD=0.50` değeri:
- **Düşür (0.30)** → daha katı eşleşme, yanlış pozitifler azalır
- **Artır (0.55)** → daha toleranslı, aynı kişi kesin birleşir ama yanlış eşleşme riski artar
