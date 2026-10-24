"""Unit tests for FastAPI catalog endpoints using TestClient."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.item import ConditionGrade, Item, ItemCategory, ItemStatus


@pytest.mark.asyncio
async def test_healthz_endpoint() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "rewearit-catalog-service"


@pytest.mark.asyncio
async def test_create_item_endpoint() -> None:
    seller_id = str(uuid.uuid4())
    item_payload = {
        "seller_id": seller_id,
        "title": "Cashmere Knit Sweater",
        "description": "100% pure Scottish cashmere",
        "category": ItemCategory.TOPS.value,
        "brand": "Pringle of Scotland",
        "size": "M",
        "condition_grade": "EXCELLENT",
        "price_currency": "USD",
        "price_units": 180,
        "price_nanos": 0,
        "image_urls": ["http://localhost:9000/garments/sweater.jpg"],
    }

    mock_created_item = Item(
        id=uuid.uuid4(),
        seller_id=uuid.UUID(seller_id),
        title=item_payload["title"],
        description=item_payload["description"],
        category=item_payload["category"],
        brand=item_payload["brand"],
        size=item_payload["size"],
        condition_grade=ConditionGrade.EXCELLENT,
        price_currency="USD",
        price_units=180,
        price_nanos=0,
        status=ItemStatus.ANALYZING,
        image_urls=item_payload["image_urls"],
    )

    with patch("app.services.catalog_service.CatalogService.create_item", new=AsyncMock(return_value=mock_created_item)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/items", json=item_payload)
            assert response.status_code == 201
            data = response.json()
            assert data["title"] == "Cashmere Knit Sweater"
            assert data["status"] == "ANALYZING"
            assert data["brand"] == "Pringle of Scotland"


@pytest.mark.asyncio
async def test_visual_search_validation_fails_on_wrong_dimensions() -> None:
    invalid_embedding = [0.1] * 128  # Wrong dimension (must be 512)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/items/search/visual",
            json={"embedding": invalid_embedding, "limit": 5},
        )
        assert response.status_code == 422
