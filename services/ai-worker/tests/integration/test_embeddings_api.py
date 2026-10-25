"""Integration test for AI Worker /api/v1/embeddings HTTP endpoint."""
import base64
import io
import math

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.server import app


def _create_mock_image(color=(50, 120, 200), size=(200, 200)) -> bytes:
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_generate_embedding_multipart() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        image_bytes = _create_mock_image()
        files = {"file": ("query.jpg", image_bytes, "image/jpeg")}
        data = {"context_text": "vintage denim jacket"}

        response = await client.post("/api/v1/embeddings", files=files, data=data)

    assert response.status_code == 200
    res_data = response.json()
    assert "embedding" in res_data
    assert res_data["dimension"] == 512
    embedding = res_data["embedding"]
    assert len(embedding) == 512

    # Verify L2 normalization
    norm = math.sqrt(sum(x * x for x in embedding))
    assert abs(norm - 1.0) < 1e-3


@pytest.mark.asyncio
async def test_generate_embedding_json_base64() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        image_bytes = _create_mock_image(color=(220, 40, 40))
        b64_str = base64.b64encode(image_bytes).decode("utf-8")
        payload = {"image_base64": b64_str, "context_text": "red hoodie"}

        response = await client.post("/api/v1/embeddings", json=payload)

    assert response.status_code == 200
    res_data = response.json()
    assert len(res_data["embedding"]) == 512
