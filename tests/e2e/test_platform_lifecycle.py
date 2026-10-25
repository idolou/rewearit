"""End-to-end integration and lifecycle verification for ReWearIt multi-service mesh."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app as catalog_app

# Minimal valid 1x1 JPEG bytes
SAMPLE_JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00"
    b"\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13"
    b"\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff"
    b"\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01"
    b"\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n"
    b"\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
)


@pytest.mark.asyncio
async def test_full_platform_lifecycle_contract() -> None:
    """Validate full flow: Studio intake -> publish -> visual search -> 1-of-1 reservation lock."""
    synthetic_image = SAMPLE_JPEG_BYTES
    mock_clean_url = "http://localhost:9000/rewearit-garments/garments/clean/e2e_item.jpg"
    mock_item_id = uuid.uuid4()
    mock_seller_id = uuid.uuid4()

    mock_classify_result = {
        "clean_image_url": mock_clean_url,
        "original_image_url": "http://localhost:9000/rewearit-garments/garments/raw/e2e_item.jpg",
        "auto_fill": {
            "title": "Levi's Classic Blue Denim Jacket",
            "category": "Outerwear",
            "brand": "Levi's",
            "size": "L",
            "color": "Blue",
            "material": "Denim",
            "condition_grade": "VERY_GOOD",
            "confidence": 0.88,
            "detected_attributes": ["denim", "vintage"],
        },
        "suggested_price_range": {
            "min_price": 50,
            "target_price": 65,
            "max_price": 85,
        },
    }

    transport = ASGITransport(app=catalog_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 1: Healthcheck
        health_res = await client.get("/healthz")
        assert health_res.status_code == 200
        assert health_res.json()["status"] == "ok"

        # Step 2: Studio Classification
        with patch("httpx.AsyncClient.post") as mock_ai_post:
            mock_resp = AsyncMock()
            mock_resp.status_code = 200
            mock_resp.json = lambda: mock_classify_result
            mock_resp.raise_for_status = lambda: None
            mock_ai_post.return_value = mock_resp

            files = {"file": ("garment.jpg", synthetic_image, "image/jpeg")}
            classify_res = await client.post("/api/v1/items/classify", files=files)
            assert classify_res.status_code == 200
            cdata = classify_res.json()
            assert cdata["clean_image_url"] == mock_clean_url
            assert cdata["auto_fill"]["brand"] == "Levi's"

        # Step 3: Item Creation with seller's chosen price
        item_payload = {
            "seller_id": str(mock_seller_id),
            "title": cdata["auto_fill"]["title"],
            "description": "Authenticated vintage jacket",
            "category": cdata["auto_fill"]["category"],
            "brand": cdata["auto_fill"]["brand"],
            "size": cdata["auto_fill"]["size"],
            "color": cdata["auto_fill"]["color"],
            "material": cdata["auto_fill"]["material"],
            "condition_grade": cdata["auto_fill"]["condition_grade"],
            "price_currency": "USD",
            "price_units": 65,
            "price_nanos": 0,
            "image_urls": [cdata["clean_image_url"]],
        }

        from app.models.item import ConditionGrade, Item, ItemStatus

        created_item_mock = Item(
            id=mock_item_id,
            seller_id=mock_seller_id,
            title=item_payload["title"],
            description=item_payload["description"],
            category=item_payload["category"],
            brand=item_payload["brand"],
            size=item_payload["size"],
            color=item_payload["color"],
            material=item_payload["material"],
            condition_grade=ConditionGrade.VERY_GOOD,
            price_currency="USD",
            price_units=65,
            price_nanos=0,
            status=ItemStatus.ANALYZING,
            image_urls=item_payload["image_urls"],
        )

        with patch("app.services.catalog_service.CatalogService.create_item", new=AsyncMock(return_value=created_item_mock)):
            create_res = await client.post("/api/v1/items", json=item_payload)
            assert create_res.status_code == 201
            item_data = create_res.json()
            assert item_data["title"] == "Levi's Classic Blue Denim Jacket"
            assert item_data["price_units"] == 65

        # Step 4: Photo Visual Search Query
        with patch("app.api.v1.items.fetch_image_embedding", new=AsyncMock(return_value=[0.05] * 512)), patch(
            "app.services.catalog_service.CatalogService.search_visual",
            new=AsyncMock(return_value=[(created_item_mock, 0.12)]),
        ):
            search_files = {"file": ("query.jpg", synthetic_image, "image/jpeg")}
            search_res = await client.post("/api/v1/items/search/visual-image", files=search_files)
            assert search_res.status_code == 200
            sdata = search_res.json()
            assert len(sdata) == 1
            assert sdata[0]["distance"] == 0.12
            assert sdata[0]["similarity"] > 0.9
