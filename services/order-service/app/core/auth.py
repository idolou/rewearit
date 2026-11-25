"""Stateless HS256 JWT verification shared with catalog-service."""
import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from app.core.config import settings


@dataclass(frozen=True)
class AuthenticatedUser:
    id: uuid.UUID
    email: str
    display_name: str


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def decode_access_token(token: str, secret: str | None = None) -> AuthenticatedUser:
    """Verify HS256 JWT signature and expiration."""
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        header = json.loads(_b64url_decode(header_b64))
        if header.get("alg") != "HS256":
            raise ValueError("Unsupported JWT algorithm")
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        key = (secret or settings.JWT_SECRET).encode("utf-8")
        expected_sig = _b64url_encode(hmac.new(key, signing_input, hashlib.sha256).digest())
        if not hmac.compare_digest(sig_b64, expected_sig):
            raise ValueError("Invalid JWT signature")
        payload = json.loads(_b64url_decode(payload_b64))
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise ValueError("JWT expired")
        return AuthenticatedUser(
            id=uuid.UUID(str(payload["sub"])),
            email=str(payload.get("email", "")),
            display_name=str(payload.get("name", "")),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def get_current_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    """FastAPI dependency enforcing Bearer JWT authentication."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(token)
