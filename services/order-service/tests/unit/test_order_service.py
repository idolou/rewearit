"""Unit tests for OrderService with mocked dependencies."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.clients.catalog_client import CatalogGrpcClient, ReservationResult
from app.events.producer import OrderEventProducer
from app.models.order import (
    Order,
    OrderCreateRequest,
    OrderStatus,
)
from app.services.idempotency import IdempotencyManager
from app.services.order_service import (
    DuplicateProcessingError,
    InvalidStateTransitionError,
    ItemReservationError,
    OrderService,
)


@pytest.fixture
def mock_catalog_client() -> MagicMock:
    client = MagicMock(spec=CatalogGrpcClient)
    client.reserve_item = AsyncMock(return_value=ReservationResult(success=True))
    client.release_item = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_idempotency_mgr() -> MagicMock:
    mgr = MagicMock(spec=IdempotencyManager)
    mgr.acquire_lock = AsyncMock(return_value=True)
    mgr.release_lock = AsyncMock()
    mgr.store_response = AsyncMock()
    mgr.get_cached_response = AsyncMock(return_value=None)
    return mgr


@pytest.fixture
def mock_producer() -> MagicMock:
    producer = MagicMock(spec=OrderEventProducer)
    producer.publish_order_placed = AsyncMock()
    producer.publish_order_escrow_locked = AsyncMock()
    producer.publish_order_completed = AsyncMock()
    producer.publish_order_cancelled = AsyncMock()
    return producer


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    # Mock scalar_one_or_none
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)
    return session


@pytest.mark.asyncio
async def test_create_order_success(
    mock_catalog_client: MagicMock,
    mock_idempotency_mgr: MagicMock,
    mock_producer: MagicMock,
    mock_session: MagicMock,
) -> None:
    service = OrderService(
        catalog_client=mock_catalog_client,
        idempotency_mgr=mock_idempotency_mgr,
        producer=mock_producer,
    )

    req = OrderCreateRequest(
        buyer_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        item_id=uuid.uuid4(),
        total_amount_units=150,
        currency="USD",
    )

    order = await service.create_order(mock_session, req, idempotency_key="key-test-1")

    assert order.buyer_id == req.buyer_id
    assert order.item_id == req.item_id
    assert order.status == OrderStatus.ESCROW_HELD
    assert order.total_amount_units == 150

    mock_idempotency_mgr.acquire_lock.assert_awaited_once_with("key-test-1")
    mock_catalog_client.reserve_item.assert_awaited_once()
    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()
    mock_producer.publish_order_placed.assert_awaited_once()
    mock_producer.publish_order_escrow_locked.assert_awaited_once()
    mock_idempotency_mgr.store_response.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_order_reservation_failed(
    mock_catalog_client: MagicMock,
    mock_idempotency_mgr: MagicMock,
    mock_producer: MagicMock,
    mock_session: MagicMock,
) -> None:
    mock_catalog_client.reserve_item = AsyncMock(
        return_value=ReservationResult(success=False, error_message="Item already reserved")
    )

    service = OrderService(
        catalog_client=mock_catalog_client,
        idempotency_mgr=mock_idempotency_mgr,
        producer=mock_producer,
    )

    req = OrderCreateRequest(
        buyer_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        item_id=uuid.uuid4(),
        total_amount_units=150,
    )

    with pytest.raises(ItemReservationError, match="Item already reserved"):
        await service.create_order(mock_session, req, idempotency_key="key-test-2")

    mock_idempotency_mgr.release_lock.assert_awaited_once_with("key-test-2")
    mock_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_order_duplicate_lock_held(
    mock_catalog_client: MagicMock,
    mock_idempotency_mgr: MagicMock,
    mock_producer: MagicMock,
    mock_session: MagicMock,
) -> None:
    mock_idempotency_mgr.acquire_lock = AsyncMock(return_value=False)
    mock_idempotency_mgr.get_cached_response = AsyncMock(return_value=None)

    service = OrderService(
        catalog_client=mock_catalog_client,
        idempotency_mgr=mock_idempotency_mgr,
        producer=mock_producer,
    )

    req = OrderCreateRequest(
        buyer_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        item_id=uuid.uuid4(),
        total_amount_units=150,
    )

    with pytest.raises(DuplicateProcessingError):
        await service.create_order(mock_session, req, idempotency_key="key-in-flight")


@pytest.mark.asyncio
async def test_order_lifecycle_transitions(
    mock_catalog_client: MagicMock,
    mock_producer: MagicMock,
    mock_session: MagicMock,
) -> None:
    service = OrderService(
        catalog_client=mock_catalog_client,
        producer=mock_producer,
    )

    order_id = uuid.uuid4()
    item_id = uuid.uuid4()
    order = Order(
        id=order_id,
        buyer_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        item_id=item_id,
        status=OrderStatus.ESCROW_HELD,
        total_amount_units=100,
        idempotency_key="test-key-lifecycle",
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = order
    mock_session.execute = AsyncMock(return_value=mock_result)

    # 1. Ship Order
    shipped = await service.ship_order(mock_session, order_id, tracking_number="TRACK123")
    assert shipped.status == OrderStatus.SHIPPED
    assert shipped.tracking_number == "TRACK123"

    # 2. Complete Order
    completed = await service.complete_order(mock_session, order_id)
    assert completed.status == OrderStatus.COMPLETED
    assert completed.completed_at is not None
    mock_producer.publish_order_completed.assert_awaited_once()

    # 3. Trying to ship completed order should fail
    with pytest.raises(InvalidStateTransitionError):
        await service.ship_order(mock_session, order_id, tracking_number="ANOTHER")
