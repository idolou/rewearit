"""Unit tests for GarmentClassifier end-to-end auto-fill and price estimation."""
import io

import pytest
from PIL import Image

from app.pipeline.classifier import GarmentClassificationResult, GarmentClassifier


def _create_sample_garment_image(color=(30, 80, 160), width=400, height=500) -> bytes:
    """Create a mock garment image on a textured/noisy background."""
    img = Image.new("RGB", (width, height), color=(220, 210, 200))
    # Draw a garment-like colored shape in the center
    for x in range(80, width - 80):
        for y in range(80, height - 80):
            img.putpixel((x, y), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_classifier_with_hints() -> None:
    classifier = GarmentClassifier()
    image_bytes = _create_sample_garment_image(color=(30, 80, 160))  # Blueish
    hints = {
        "title": "Levi's Vintage Denim Trucker Jacket Size L",
        "description": "Used lightly, 100% cotton denim, great condition",
        "declared_condition": "VERY_GOOD",
    }

    result: GarmentClassificationResult = await classifier.classify_and_enhance(
        image_bytes=image_bytes,
        hints=hints,
    )

    # Verify studio enhancement output
    assert result.clean_image_bytes is not None
    assert len(result.clean_image_bytes) > 0
    assert result.original_image_bytes == image_bytes

    # Verify auto-fill attributes
    auto_fill = result.auto_fill
    assert auto_fill.brand == "Levi's"
    assert auto_fill.category == "Outerwear"
    assert auto_fill.condition_grade == "VERY_GOOD"
    assert "Denim" in auto_fill.material or "Cotton" in auto_fill.material
    assert auto_fill.size == "L"
    assert auto_fill.color in ("Blue", "Navy", "Denim")
    assert "Levi's" in auto_fill.title

    # Verify valuation guidance
    prices = result.suggested_price_range
    assert prices.min_price > 0
    assert prices.target_price >= prices.min_price
    assert prices.max_price >= prices.target_price


@pytest.mark.asyncio
async def test_classifier_image_only_no_hints() -> None:
    """When a seller uploads only a photo, the classifier infers color, title, and sensible defaults."""
    classifier = GarmentClassifier()
    red_image_bytes = _create_sample_garment_image(color=(210, 30, 30))  # Red

    result: GarmentClassificationResult = await classifier.classify_and_enhance(
        image_bytes=red_image_bytes,
        hints=None,
    )

    assert result.clean_image_bytes is not None
    auto_fill = result.auto_fill
    assert auto_fill.color == "Red"
    assert auto_fill.category in ("Tops", "Bottoms", "Outerwear", "Footwear", "Dresses")
    assert auto_fill.size in ("S", "M", "L", "XL", "One Size")
    assert len(auto_fill.title) > 0
    assert "Red" in auto_fill.title

    prices = result.suggested_price_range
    assert prices.min_price > 0
    assert prices.target_price >= prices.min_price
    assert prices.max_price >= prices.target_price
