from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import create_admin_token, require_admin, verify_admin_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_at: int


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest):
    verify_admin_password(body.password)
    token, expires_at = create_admin_token()
    return LoginResponse(token=token, expires_at=expires_at)


@router.get("/session")
def session(_: None = Depends(require_admin)):
    return {"ok": True}
