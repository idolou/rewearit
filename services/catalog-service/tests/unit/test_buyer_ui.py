"""Unit tests for buyer catalog web interface."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_root_serves_buyer_catalog() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "ReWearIt Marketplace" in response.text
        assert "Search by Photo" in response.text


@pytest.mark.asyncio
async def test_explore_route_serves_buyer_catalog() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/explore")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "ReWearIt Marketplace" in response.text
