"""Unit tests for stateless HS256 JWT auth, password hashing, and seller dashboard routes."""
import uuid

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.main import app


def test_password_hash_and_verify() -> None:
    hashed = hash_password("super-secret-pass")
    assert hashed.startswith("scrypt$")
    assert verify_password("super-secret-pass", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_jwt_sign_verify_and_reject_tampered_or_expired() -> None:
    uid = uuid.uuid4()
    token = create_access_token(uid, "seller@example.com", "Alex", expires_in=300)
    user = decode_access_token(token)
    assert user.id == uid
    assert user.email == "seller@example.com"

    # Tampered signature fails with 401
    tampered = token[:-4] + "AAAA"
    with pytest.raises(HTTPException) as exc:
        decode_access_token(tampered)
    assert exc.value.status_code == 401

    # Expired token fails with 401
    expired = create_access_token(uid, "seller@example.com", "Alex", expires_in=-10)
    with pytest.raises(HTTPException) as exc_exp:
        decode_access_token(expired)
    assert exc_exp.value.status_code == 401


@pytest.mark.asyncio
async def test_unauthenticated_item_creation_rejected_and_seller_dashboard_served() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unauth = await client.post("/api/v1/items", json={"title": "Test"})
        assert unauth.status_code == 401

        dash = await client.get("/seller")
        assert dash.status_code == 200
        assert "Seller &amp; Orders Dashboard" in dash.text

        js = await client.get("/static/auth.js")
        assert js.status_code == 200
        assert "ReWearAuth" in js.text
