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


@pytest.mark.asyncio
async def test_classify_item_proxy_endpoint() -> None:
    mock_ai_response = {
        "clean_image_url": "http://localhost:9000/rewearit-garments/clean/sample.jpg",
        "original_image_url": "http://localhost:9000/rewearit-garments/raw/sample.jpg",
        "auto_fill": {
            "title": "Vintage Levi's Blue Denim Trucker Jacket",
            "category": "Outerwear",
            "brand": "Levi's",
            "size": "L",
            "color": "Blue",
            "material": "Denim",
            "condition_grade": "VERY_GOOD",
            "confidence": 0.88,
            "detected_attributes": ["vintage", "denim"],
        },
        "suggested_price_range": {
            "min_price": 50,
            "target_price": 65,
            "max_price": 85,
        },
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: mock_ai_response
        mock_resp.raise_for_status = lambda: None
        mock_post.return_value = mock_resp

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"file": ("test.jpg", b"fake_jpeg_content", "image/jpeg")}
            response = await client.post("/api/v1/items/classify", files=files)
            assert response.status_code == 200
            data = response.json()
            assert data["clean_image_url"] == mock_ai_response["clean_image_url"]
            assert data["auto_fill"]["brand"] == "Levi's"
            assert data["auto_fill"]["color"] == "Blue"
            assert data["suggested_price_range"]["target_price"] == 65


@pytest.mark.asyncio
async def test_upload_preview_page() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/upload")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "Studio Catalog Frame" in response.text or "ReWearIt" in response.text

