"""Unit tests for catalog service visual photo search endpoint."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.item import ConditionGrade, Item, ItemCategory, ItemStatus


@pytest.mark.asyncio
async def test_search_by_photo_endpoint() -> None:
    mock_embedding = [0.044] * 512

    mock_item = Item(
        id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        title="Vintage Levi's 501 Original Jeans",
        description="Classic blue straight fit denim",
        category=ItemCategory.BOTTOMS.value,
        brand="Levi's",
        size="32x30",
        condition_grade=ConditionGrade.VERY_GOOD,
        price_currency="USD",
        price_units=65,
        price_nanos=0,
        status=ItemStatus.ACTIVE,
        image_urls=["http://localhost:9000/rewearit-garments/garments/clean/sample.jpg"],
    )

    with patch(
        "app.api.v1.items.fetch_image_embedding",
        new=AsyncMock(return_value=mock_embedding),
    ), patch(
        "app.services.catalog_service.CatalogService.search_visual",
        new=AsyncMock(return_value=[(mock_item, 0.15)]),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"file": ("query.jpg", b"fake_query_image_bytes", "image/jpeg")}
            response = await client.post("/api/v1/items/search/visual-image", files=files)

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            result = data[0]
            assert result["item"]["title"] == "Vintage Levi's 501 Original Jeans"
            assert result["distance"] == 0.15
            assert result["similarity"] > 0.9
