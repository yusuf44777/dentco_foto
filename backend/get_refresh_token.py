"""
Yeni Google Drive refresh token üretir.
Çalıştır: python get_refresh_token.py
Tarayıcıda Drive'a erişimi olan hesapla giriş yap.
"""
from google_auth_oauthlib.flow import InstalledAppFlow
import json, os
from dotenv import load_dotenv

load_dotenv(".env.local")

CLIENT_CONFIG = {
    "installed": {
        "client_id":     os.environ["GOOGLE_DRIVE_OAUTH_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_DRIVE_OAUTH_CLIENT_SECRET"],
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
        "token_uri":     "https://oauth2.googleapis.com/token",
    }
}

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
creds = flow.run_local_server(port=8080, prompt="consent", access_type="offline")

print("\n=== YENİ REFRESH TOKEN ===")
print(creds.refresh_token)
print("\n.env.local dosyandaki GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN satırını bununla güncelle.")
