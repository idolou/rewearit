"""Integration test for full AI worker appraisal pipeline."""
import io
import uuid
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.events import events_pb2
from app.events.schemas import build_event_header, map_proto_to_condition_str
from app.pipeline.cache import AppraisalCache
from app.pipeline.embeddings.encoder import VisualEmbeddingEncoder
from app.pipeline.preprocessor import ImagePreprocessor
from app.pipeline.vlm.heuristic import HeuristicVLMClient
from app.worker import AIAppraisalWorker


def generate_test_jpeg() -> bytes:
    img = Image.new("RGB", (640, 480), color=(30, 90, 150))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_end_to_end_appraisal_pipeline() -> None:
    mock_producer = AsyncMock()
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None  # Cache miss

    cache = AppraisalCache(redis_client=mock_redis)
    preprocessor = ImagePreprocessor()
    vlm_client = HeuristicVLMClient()
    encoder = VisualEmbeddingEncoder(dimension=512)

    worker = AIAppraisalWorker(
        producer=mock_producer,
        cache=cache,
        preprocessor=preprocessor,
        vlm_client=vlm_client,
        embedding_encoder=encoder,
    )

    item_id = str(uuid.uuid4())
    seller_id = str(uuid.uuid4())
    test_image = generate_test_jpeg()

    # Stub preprocessor fetch_image to return our generated test image
    worker.preprocessor.fetch_image = AsyncMock(return_value=test_image)  # type: ignore[method-assign]

    item_event = events_pb2.ItemCreatedEvent(
        header=build_event_header("item.created"),
        item_id=item_id,
        seller_id=seller_id,
        title="Patagonia Retro-X Fleece Jacket",
        category="Outerwear",
        brand="Patagonia",
        description="Warm vintage fleece jacket in excellent condition",
        size="M",
        image_urls=["http://minio/garments/fleece.jpg"],
    )

    await worker.handle_item_created(item_event)

    # Verify event published
    mock_producer.publish_appraisal_completed.assert_awaited_once()
    appraisal_event: events_pb2.AIAppraisalCompletedEvent = mock_producer.publish_appraisal_completed.call_args[0][0]

    assert appraisal_event.item_id == item_id
    assert appraisal_event.detected_brand == "Patagonia"
    assert appraisal_event.detected_category == "Outerwear"
    assert map_proto_to_condition_str(appraisal_event.condition_grade) == "EXCELLENT"
    assert len(appraisal_event.visual_embedding) == 512
    assert appraisal_event.suggested_min_price.units > 0
    assert appraisal_event.suggested_max_price.units >= appraisal_event.suggested_min_price.units
