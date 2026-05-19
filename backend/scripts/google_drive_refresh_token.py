"""
Generate a Google Drive OAuth refresh token for the account that can see
the event photo folder.

Usage:
  python scripts/google_drive_refresh_token.py
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import urlparse

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
DEFAULT_REDIRECT_URI = "http://localhost:8080/"


def _parse_loopback_redirect_uri(value: str) -> tuple[str, int, bool]:
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("Redirect URI must be http://localhost:<port>/ or http://127.0.0.1:<port>/")

    if parsed.path not in {"", "/"}:
        raise ValueError("Redirect URI path must be empty or '/'.")

    if parsed.port is None:
        raise ValueError("Redirect URI must include a port, e.g. http://localhost:8080/")

    return parsed.hostname, parsed.port, parsed.path == "/"


def main() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    load_dotenv(backend_dir / ".env")
    load_dotenv(backend_dir / ".env.local", override=True)

    parser = argparse.ArgumentParser()
    parser.add_argument("--client-id", default=os.getenv("GOOGLE_DRIVE_OAUTH_CLIENT_ID"))
    parser.add_argument("--client-secret", default=os.getenv("GOOGLE_DRIVE_OAUTH_CLIENT_SECRET"))
    parser.add_argument(
        "--redirect-uri",
        default=os.getenv("GOOGLE_DRIVE_OAUTH_REDIRECT_URI", DEFAULT_REDIRECT_URI),
        help="Must match a Google Cloud authorized redirect URI exactly.",
    )
    args = parser.parse_args()

    if not args.client_id:
        parser.error(
            "Missing GOOGLE_DRIVE_OAUTH_CLIENT_ID. Add it to backend/.env.local "
            "or pass --client-id."
        )

    if not args.client_secret:
        parser.error(
            "Missing GOOGLE_DRIVE_OAUTH_CLIENT_SECRET. Add it to backend/.env.local "
            "or pass --client-secret."
        )

    try:
        host, port, trailing_slash = _parse_loopback_redirect_uri(args.redirect_uri)
    except ValueError as exc:
        parser.error(str(exc))

    print(f"Using OAuth redirect URI: {args.redirect_uri}")
    print("If Google returns redirect_uri_mismatch, add this exact URI in Google Cloud Console.")

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": args.client_id,
                "client_secret": args.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [args.redirect_uri],
            }
        },
        scopes=SCOPES,
    )

    creds: Credentials = flow.run_local_server(
        host=host,
        port=port,
        redirect_uri_trailing_slash=trailing_slash,
        access_type="offline",
        prompt="consent",
    )

    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    about = drive.about().get(fields="user(emailAddress,displayName)").execute()
    user = about.get("user", {})

    print()
    print(f"Google account: {user.get('emailAddress', 'unknown')}")
    print("GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN=")
    print(creds.refresh_token or "")

    if not creds.refresh_token:
        print()
        print("No refresh token returned. Revoke the app access in Google Account")
        print("permissions, then run this script again with prompt=consent.")


if __name__ == "__main__":
    main()
