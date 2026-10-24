"""Unit tests for AIAppraisalWorker orchestration."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.events import events_pb2
from app.events.schemas import build_event_header
from app.pipeline.cache import CachedAppraisal
from app.pipeline.preprocessor import ProcessedImage
from app.pipeline.vlm.base import VLMAppraisalResult
from app.worker import AIAppraisalWorker


@pytest.mark.asyncio
async def test_worker_processes_item_created_cache_miss() -> None:
    mock_producer = AsyncMock()
    mock_cache = AsyncMock()
    mock_preprocessor = MagicMock()
    mock_preprocessor.fetch_image = AsyncMock(return_value=b"raw_img_bytes")
    mock_vlm = AsyncMock()
    mock_encoder = MagicMock()

    # Setup preprocessor mock
    mock_preprocessor.process_bytes.return_value = ProcessedImage(
        sha256="sha256_mock_hash",
        cleaned_bytes=b"cleaned_img_bytes",
        width=800,
        height=600,
    )

    # Cache miss
    mock_cache.get.return_value = None

    # VLM mock
    mock_vlm.analyze.return_value = VLMAppraisalResult(
        brand="Levi's",
        category="Outerwear",
        condition_grade="VERY_GOOD",
        condition_confidence=0.88,
        detected_attributes=["denim", "vintage"],
        suggested_min_price=40,
        suggested_max_price=70,
    )

    # Embedding mock
    mock_encoder.encode_image.return_value = [0.1] * 512

    worker = AIAppraisalWorker(
        producer=mock_producer,
        cache=mock_cache,
        preprocessor=mock_preprocessor,
        vlm_client=mock_vlm,
        embedding_encoder=mock_encoder,
    )

    item_event = events_pb2.ItemCreatedEvent(
        header=build_event_header("item.created"),
        item_id="11111111-1111-1111-1111-111111111111",
        seller_id="22222222-2222-2222-2222-222222222222",
        title="Vintage Denim Trucker Jacket",
        category="Outerwear",
        brand="Levi's",
        description="Classic 90s wash",
        size="L",
        image_urls=["http://minio/garments/jacket1.jpg"],
    )

    await worker.handle_item_created(item_event)

    # Assertions
    mock_cache.get.assert_awaited_once_with("sha256_mock_hash")
    mock_vlm.analyze.assert_awaited_once()
    mock_encoder.encode_image.assert_called_once()
    mock_cache.set.assert_awaited_once()
    mock_producer.publish_appraisal_completed.assert_awaited_once()

    published_event = mock_producer.publish_appraisal_completed.call_args[0][0]
    assert published_event.item_id == "11111111-1111-1111-1111-111111111111"
    assert published_event.detected_brand == "Levi's"
    assert len(published_event.visual_embedding) == 512


@pytest.mark.asyncio
async def test_worker_processes_item_created_cache_hit() -> None:
    mock_producer = AsyncMock()
    mock_cache = AsyncMock()
    mock_preprocessor = MagicMock()
    mock_preprocessor.fetch_image = AsyncMock(return_value=b"raw_img_bytes")
    mock_vlm = AsyncMock()
    mock_encoder = MagicMock()

    mock_preprocessor.process_bytes.return_value = ProcessedImage(
        sha256="cached_sha_hash",
        cleaned_bytes=b"cleaned_img_bytes",
        width=800,
        height=600,
    )

    # Cache hit
    mock_cache.get.return_value = CachedAppraisal(
        brand="Nike",
        category="Footwear",
        condition_grade="EXCELLENT",
        condition_confidence=0.95,
        attributes=["sneakers"],
        min_price=60,
        max_price=90,
        visual_embedding=[0.2] * 512,
    )

    worker = AIAppraisalWorker(
        producer=mock_producer,
        cache=mock_cache,
        preprocessor=mock_preprocessor,
        vlm_client=mock_vlm,
        embedding_encoder=mock_encoder,
    )

    item_event = events_pb2.ItemCreatedEvent(
        header=build_event_header("item.created"),
        item_id="33333333-3333-3333-3333-333333333333",
        seller_id="44444444-4444-4444-4444-444444444444",
        title="Nike Air Jordan",
        category="Footwear",
        brand="Nike",
        description="Mint condition",
        size="10",
        image_urls=["http://minio/garments/jordan.jpg"],
    )

    await worker.handle_item_created(item_event)

    # VLM and encoder should NOT be called on cache hit!
    mock_vlm.analyze.assert_not_called()
    mock_encoder.encode_image.assert_not_called()
    mock_producer.publish_appraisal_completed.assert_awaited_once()

    published_event = mock_producer.publish_appraisal_completed.call_args[0][0]
    assert published_event.item_id == "33333333-3333-3333-3333-333333333333"
    assert published_event.detected_brand == "Nike"
