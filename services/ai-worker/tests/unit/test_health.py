"""Unit tests for health and ready probes."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.server import app, set_healthy, set_ready


@pytest.mark.asyncio
async def test_healthz_endpoint() -> None:
    set_healthy(True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "rewearit-ai-worker"}


@pytest.mark.asyncio
async def test_healthz_unhealthy() -> None:
    set_healthy(False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/healthz")
    assert response.status_code == 503
    set_healthy(True)


@pytest.mark.asyncio
async def test_ready_endpoint() -> None:
    set_ready(False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/ready")
    assert response.status_code == 503

    set_ready(True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "rewearit-ai-worker"}
