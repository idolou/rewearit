"""Stateless HS256 JWT tokens and scrypt password hashing using Python stdlib.

shortcut: auth lives in catalog-service; extract to a dedicated auth-service when
non-marketplace clients or user volume require independent auth scaling.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from app.core.config import settings

_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1


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


def hash_password(password: str) -> str:
    """Hash password with per-user 16-byte random salt via scrypt."""
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return f"scrypt${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time password verification against stored scrypt hash."""
    try:
        scheme, salt_hex, hash_hex = stored_hash.split("$", 2)
        if scheme != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return hmac.compare_digest(derived, expected)


def create_access_token(
    user_id: uuid.UUID,
    email: str,
    display_name: str,
    secret: str | None = None,
    expires_in: int | None = None,
) -> str:
    """Sign a standard RFC 7519 HS256 JWT."""
    now = int(time.time())
    ttl = expires_in if expires_in is not None else settings.JWT_EXPIRE_SECONDS
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8"))
    payload_obj = {
        "sub": str(user_id),
        "email": email,
        "name": display_name,
        "iat": now,
        "exp": now + ttl,
    }
    payload = _b64url_encode(json.dumps(payload_obj, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header}.{payload}".encode("ascii")
    key = (secret or settings.JWT_SECRET).encode("utf-8")
    sig = _b64url_encode(hmac.new(key, signing_input, hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def decode_access_token(token: str, secret: str | None = None) -> AuthenticatedUser:
    """Verify HS256 signature and expiration, returning the authenticated user claims."""
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
