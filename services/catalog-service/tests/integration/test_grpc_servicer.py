"""Unit and integration tests for gRPC CatalogServicer with reservation locking."""
import time
import uuid
from unittest.mock import AsyncMock

import pytest

from app.core.database import async_session_maker, init_db
from app.grpc.catalog_servicer import CatalogServicer
from app.grpc.schemas import catalog_service_pb2
from app.models.item import ConditionGrade, Item, ItemStatus
from tests.conftest import requires_postgres

pytestmark = requires_postgres


@pytest.mark.asyncio
async def test_grpc_reserve_and_release_flow() -> None:
    # Prepare database tables
    await init_db()

    seller_id = uuid.uuid4()
    item = Item(
        seller_id=seller_id,
        title="Vintage Denim Jacket",
        category="Outerwear",
        brand="Levi's",
        size="M",
        condition_grade=ConditionGrade.EXCELLENT,
        price_units=85,
        price_nanos=0,
        status=ItemStatus.ACTIVE,
        image_urls=["http://localhost:9000/garments/levis.jpg"],
    )

    async with async_session_maker() as session:
        session.add(item)
        await session.commit()
        await session.refresh(item)
        item_id = item.id

    servicer = CatalogServicer()
    mock_context = AsyncMock()

    order_1 = str(uuid.uuid4())
    order_2 = str(uuid.uuid4())
    buyer_id = str(uuid.uuid4())

    # 1. Reserve with Order 1 -> Must succeed
    req1 = catalog_service_pb2.ReserveItemRequest(
        item_id=str(item_id),
        order_id=order_1,
        buyer_id=buyer_id,
        ttl_seconds=300,
    )
    res1 = await servicer.ReserveItem(req1, mock_context)
    assert res1.success is True
    assert res1.expires_at_timestamp > int(time.time())

    # 2. Idempotent reservation with same Order 1 -> Must succeed
    res1_idempotent = await servicer.ReserveItem(req1, mock_context)
    assert res1_idempotent.success is True

    # 3. Concurrent reservation attempt with Order 2 -> Must fail (1-of-1 inventory lock)
    req2 = catalog_service_pb2.ReserveItemRequest(
        item_id=str(item_id),
        order_id=order_2,
        buyer_id=buyer_id,
        ttl_seconds=300,
    )
    res2 = await servicer.ReserveItem(req2, mock_context)
    assert res2.success is False
    assert "currently reserved" in res2.error_message

    # 4. Release Order 1 -> Item becomes ACTIVE again
    rel_req = catalog_service_pb2.ReleaseItemRequest(
        item_id=str(item_id),
        order_id=order_1,
        reason="Buyer cancelled checkout",
    )
    rel_res = await servicer.ReleaseItem(rel_req, mock_context)
    assert rel_res.success is True

    # 5. Order 2 can now successfully reserve it
    res2_retry = await servicer.ReserveItem(req2, mock_context)
    assert res2_retry.success is True

    # 6. Finalize order 2 -> Mark Sold
    sold_req = catalog_service_pb2.MarkItemSoldRequest(
        item_id=str(item_id),
        order_id=order_2,
        buyer_id=buyer_id,
    )
    sold_res = await servicer.MarkItemSold(sold_req, mock_context)
    assert sold_res.item_id == str(item_id)

    # Clean up item
    async with async_session_maker() as session:
        del_item = await session.get(Item, item_id)
        if del_item:
            await session.delete(del_item)
            await session.commit()
