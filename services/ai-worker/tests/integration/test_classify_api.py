"""Integration test for AI Worker /api/v1/classify HTTP endpoint."""
import base64
import io
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.server import app


def _create_mock_image(color=(40, 100, 180), size=(300, 300)) -> bytes:
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_classify_multipart_upload() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        image_bytes = _create_mock_image()
        files = {
            "file": ("garment.jpg", image_bytes, "image/jpeg"),
        }
        data = {
            "title": "Levi's Denim Jacket",
            "description": "Vintage blue trucker jacket size L",
            "declared_condition": "VERY_GOOD",
        }

        response = await client.post("/api/v1/classify", files=files, data=data)

    assert response.status_code == 200
    res_data = response.json()

    assert "clean_image_url" in res_data
    assert "original_image_url" in res_data
    assert "rewearit-garments" in res_data["clean_image_url"]

    auto_fill = res_data["auto_fill"]
    assert auto_fill["brand"] == "Levi's"
    assert auto_fill["category"] == "Outerwear"
    assert auto_fill["size"] == "L"
    assert auto_fill["color"] in ("Blue", "Navy", "Denim")
    assert auto_fill["condition_grade"] == "VERY_GOOD"

    prices = res_data["suggested_price_range"]
    assert prices["min_price"] > 0
    assert prices["target_price"] >= prices["min_price"]
    assert prices["max_price"] >= prices["target_price"]


@pytest.mark.asyncio
async def test_classify_json_base64_upload() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        image_bytes = _create_mock_image(color=(200, 20, 20))
        b64_str = base64.b64encode(image_bytes).decode("utf-8")
        payload = {
            "image_base64": b64_str,
            "title": "Nike Sports Tee",
            "description": "Size M cotton red shirt brand new with tags",
        }

        response = await client.post("/api/v1/classify", json=payload)

    assert response.status_code == 200
    res_data = response.json()
    assert "clean_image_url" in res_data
    auto_fill = res_data["auto_fill"]
    assert auto_fill["brand"] == "Nike"
    assert auto_fill["category"] == "Tops"
    assert auto_fill["condition_grade"] == "NEW_WITH_TAGS"
