"""
Drive erişim testi — scope ve klasör içeriğini kontrol eder.
Çalıştır: python check_drive.py
"""
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv
import os

load_dotenv(".env.local")

REFRESH_TOKEN  = os.environ["GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN"]
CLIENT_ID      = os.environ["GOOGLE_DRIVE_OAUTH_CLIENT_ID"]
CLIENT_SECRET  = os.environ["GOOGLE_DRIVE_OAUTH_CLIENT_SECRET"]
FOLDER_ID      = os.environ["GOOGLE_DRIVE_FOLDER_ID"]

creds = Credentials(
    token=None,
    refresh_token=REFRESH_TOKEN,
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    token_uri="https://oauth2.googleapis.com/token",
)
creds.refresh(Request())

print("=== TOKEN SCOPES ===")
print(creds.scopes or "scope bilgisi yok (token'a gömülü)")

service = build("drive", "v3", credentials=creds, cache_discovery=False)

print("\n=== KLASÖR BİLGİSİ ===")
folder = service.files().get(
    fileId=FOLDER_ID,
    fields="id,name,mimeType",
    supportsAllDrives=True,
).execute()
print(folder)

print("\n=== KLASÖR İÇERİĞİ (ilk 20) ===")
resp = service.files().list(
    q=f"'{FOLDER_ID}' in parents and trashed = false",
    fields="files(id, name, mimeType, size)",
    pageSize=20,
    supportsAllDrives=True,
    includeItemsFromAllDrives=True,
).execute()

files = resp.get("files", [])
print(f"Toplam görünen: {len(files)}")
for f in files:
    print(f"  {f['name']:50s}  {f['mimeType']}")
