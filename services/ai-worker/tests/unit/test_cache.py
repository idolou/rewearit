"""Unit tests for AppraisalCache with mock Redis."""
from unittest.mock import AsyncMock

import pytest

from app.pipeline.cache import AppraisalCache, CachedAppraisal


@pytest.mark.asyncio
async def test_appraisal_cache_hit_and_miss() -> None:
    mock_redis = AsyncMock()
    cache = AppraisalCache(redis_client=mock_redis, ttl_seconds=3600)

    # Test cache miss
    mock_redis.get.return_value = None
    miss_result = await cache.get("nonexistent_hash")
    assert miss_result is None

    # Test cache set and hit
    appraisal = CachedAppraisal(
        brand="Nike",
        category="Footwear",
        condition_grade="EXCELLENT",
        condition_confidence=0.95,
        attributes=["sneakers", "streetwear"],
        min_price=60,
        max_price=90,
        visual_embedding=[0.5] * 512,
    )

    await cache.set("test_hash_123", appraisal)
    mock_redis.setex.assert_awaited_once()

    # Test cache hit retrieval
    mock_redis.get.return_value = appraisal.model_dump_json()
    hit_result = await cache.get("test_hash_123")
    assert hit_result is not None
    assert hit_result.brand == "Nike"
    assert hit_result.category == "Footwear"
    assert hit_result.condition_grade == "EXCELLENT"
    assert len(hit_result.visual_embedding) == 512
