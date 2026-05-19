import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

bearer = HTTPBearer(auto_error=False)


def _require_admin_password() -> str:
    if not settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin login is not configured",
        )
    return settings.admin_password


def _session_secret() -> str:
    return settings.admin_session_secret or _require_admin_password()


def _encode_payload(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_payload(value: str) -> dict:
    padding = "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode(value + padding))


def _signature(payload: str) -> str:
    digest = hmac.new(_session_secret().encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def create_admin_token() -> tuple[str, int]:
    expires_at = int(time.time()) + settings.admin_session_ttl_seconds
    payload = _encode_payload({"role": "admin", "exp": expires_at})
    return f"{payload}.{_signature(payload)}", expires_at


def verify_admin_password(password: str) -> None:
    expected = _require_admin_password()
    if not secrets.compare_digest(password, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")


def require_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin login required")

    try:
        payload, signature = credentials.credentials.rsplit(".", 1)
        if not secrets.compare_digest(signature, _signature(payload)):
            raise ValueError("bad signature")
        data = _decode_payload(payload)
        if data.get("role") != "admin" or int(data.get("exp", 0)) <= int(time.time()):
            raise ValueError("expired or invalid token")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin session") from exc
