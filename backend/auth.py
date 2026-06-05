import base64
import hashlib
import hmac
import json
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config import get_settings


_bearer = HTTPBearer(auto_error=False)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def verify_admin_password(password: str) -> bool:
    configured = get_settings().admin_password
    return bool(configured) and hmac.compare_digest(password, configured)


def create_admin_token(now: int | None = None) -> tuple[str, int]:
    settings = get_settings()
    if not settings.token_secret:
        raise RuntimeError("ADMIN_PASSWORD 或 ADMIN_TOKEN_SECRET 尚未設定")
    issued_at = int(now or time.time())
    expires_at = issued_at + settings.admin_token_ttl_seconds
    payload = _b64encode(json.dumps({"sub": "admin", "exp": expires_at}, separators=(",", ":")).encode())
    signature = _b64encode(hmac.new(settings.token_secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}", expires_at


def decode_admin_token(token: str, now: int | None = None) -> dict:
    settings = get_settings()
    if not settings.token_secret:
        raise ValueError("管理者驗證尚未設定")
    try:
        payload, signature = token.split(".", 1)
        expected = _b64encode(hmac.new(settings.token_secret.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("token signature invalid")
        data = json.loads(_b64decode(payload))
        if data.get("sub") != "admin" or int(data.get("exp", 0)) <= int(now or time.time()):
            raise ValueError("token expired")
        return data
    except Exception as exc:
        raise ValueError("invalid admin token") from exc


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="需要管理者登入")
    try:
        return decode_admin_token(credentials.credentials)
    except ValueError:
        raise HTTPException(status_code=401, detail="管理者登入已失效")
