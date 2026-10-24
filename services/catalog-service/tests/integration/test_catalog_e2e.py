"""End-to-end integration test verifying complete catalog lifecycle:
REST creation -> DB persistence -> AI Appraisal event consumption -> Vector Search -> gRPC Reservation.
"""
import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import async_session_maker, init_db
from app.events.consumer import consumer
from app.grpc.catalog_servicer import CatalogServicer
from app.grpc.schemas import catalog_service_pb2, events_pb2
from app.main import app
from app.models.item import ConditionGrade, Item, ItemCategory, ItemStatus
from tests.conftest import requires_postgres

pytestmark = requires_postgres


@pytest.mark.asyncio
async def test_complete_catalog_lifecycle_e2e() -> None:
    # 1. Initialize schema in database
    await init_db()

    seller_id = str(uuid.uuid4())
    create_payload = {
        "seller_id": seller_id,
        "title": "E2E Silk Slip Dress",
        "description": "Emerald green 100% silk maxi dress",
        "category": ItemCategory.TOPS.value,
        "brand": "Reformation",
        "size": "S",
        "condition_grade": "GOOD",
        "price_currency": "USD",
        "price_units": 135,
        "price_nanos": 0,
        "image_urls": ["http://localhost:9000/garments/ref-e2e.jpg"],
    }

    # 2. Create listing via FastAPI REST API
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/items", json=create_payload)
        assert create_resp.status_code == 201
        created_data = create_resp.json()
        item_id = created_data["id"]
        assert created_data["status"] == "ANALYZING"

    item_uuid = uuid.UUID(item_id)

    # 3. Verify item in PostgreSQL has status ANALYZING and no embedding yet
    async with async_session_maker() as session:
        item = await session.get(Item, item_uuid)
        assert item is not None
        assert item.status == ItemStatus.ANALYZING
        assert item.embedding is None

    # 4. Simulate AI Worker completing visual appraisal & producing embedding
    test_embedding = [0.1] * 512
    ai_event = events_pb2.AIAppraisalCompletedEvent(
        header=events_pb2.EventHeader(
            event_id=str(uuid.uuid4()),
            event_type="ai.appraisal_completed",
            schema_version=1,
        ),
        item_id=str(item_id),
        detected_brand="Reformation",
        detected_category="Tops",
        condition_grade=events_pb2.ConditionGrade.CONDITION_GRADE_EXCELLENT,
        condition_confidence=0.98,
        visual_embedding=test_embedding,
    )
    ai_event_bytes = ai_event.SerializeToString()

    # Process AI event through consumer
    await consumer.process_message(
        topic="rewearit.ai.events",
        value=ai_event_bytes,
        headers=[("event_type", b"ai.appraisal_completed")],
    )

    # 5. Verify item is now ACTIVE with 512-dim embedding and updated condition
    async with async_session_maker() as session:
        item = await session.get(Item, item_uuid)
        assert item is not None
        assert item.status == ItemStatus.ACTIVE
        assert item.condition_grade == ConditionGrade.EXCELLENT
        assert item.embedding is not None
        assert len(item.embedding) == 512

    # 6. Perform visual vector search via REST
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        search_resp = await client.post(
            "/api/v1/items/search/visual",
            json={"embedding": test_embedding, "limit": 5, "max_distance": 0.5},
        )
        assert search_resp.status_code == 200
        search_data = search_resp.json()
        assert len(search_data) >= 1
        matched_ids = [res["item"]["id"] for res in search_data]
        assert item_id in matched_ids
        top_match = next(res for res in search_data if res["item"]["id"] == item_id)
        assert top_match["similarity"] > 0.99  # Identical vector -> distance ~ 0

    # 7. Execute gRPC ReserveItem call (simulating order checkout lock)
    servicer = CatalogServicer()
    mock_context = AsyncMock()
    order_id = str(uuid.uuid4())
    buyer_id = str(uuid.uuid4())

    reserve_req = catalog_service_pb2.ReserveItemRequest(
        item_id=str(item_id),
        order_id=order_id,
        buyer_id=buyer_id,
        ttl_seconds=600,
    )
    reserve_res = await servicer.ReserveItem(reserve_req, mock_context)
    assert reserve_res.success is True

    # 8. Verify item is marked RESERVED in database
    async with async_session_maker() as session:
        item = await session.get(Item, item_uuid)
        assert item is not None
        assert item.status == ItemStatus.RESERVED
        assert str(item.reserved_by_order_id) == order_id

    # 9. Clean up test record
    async with async_session_maker() as session:
        item = await session.get(Item, item_uuid)
        if item:
            await session.delete(item)
            await session.commit()
