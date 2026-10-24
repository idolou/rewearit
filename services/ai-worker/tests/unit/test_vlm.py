"""Unit tests for VLM attribute extraction and condition grading."""
import pytest

from app.pipeline.vlm.base import VLMAppraisalResult
from app.pipeline.vlm.heuristic import HeuristicVLMClient


@pytest.mark.asyncio
async def test_heuristic_vlm_denim_jacket() -> None:
    client = HeuristicVLMClient()
    dummy_image = b"fake_image_bytes_12345"
    title = "Vintage Levi's 90s Denim Jacket"
    desc = "Classic distressed trucker jacket with slight fraying at cuffs"

    result: VLMAppraisalResult = await client.analyze(
        image_bytes=dummy_image,
        title=title,
        description=desc,
        declared_condition="VERY_GOOD",
    )

    assert result.brand == "Levi's"
    assert result.category == "Outerwear"
    assert result.condition_grade == "VERY_GOOD"
    assert result.condition_confidence >= 0.85
    assert "vintage" in result.detected_attributes
    assert "denim" in result.detected_attributes
    assert result.suggested_min_price > 0
    assert result.suggested_max_price >= result.suggested_min_price


@pytest.mark.asyncio
async def test_heuristic_vlm_brand_new_sneakers() -> None:
    client = HeuristicVLMClient()
    dummy_image = b"fake_image_bytes_67890"
    title = "Nike Air Jordan 1 High OG"
    desc = "Brand new with tags and original box never worn"

    result = await client.analyze(
        image_bytes=dummy_image,
        title=title,
        description=desc,
        declared_condition="NEW_WITH_TAGS",
    )

    assert result.brand == "Nike"
    assert result.category == "Footwear"
    assert result.condition_grade == "NEW_WITH_TAGS"
    assert result.condition_confidence >= 0.90
    assert "sneakers" in result.detected_attributes or "streetwear" in result.detected_attributes
