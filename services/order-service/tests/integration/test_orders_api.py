"""Integration tests for Order Service FastAPI endpoints."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.orders import get_order_service
from app.clients.catalog_client import CatalogGrpcClient, ReservationResult
from app.core.database import get_session
from app.events.producer import OrderEventProducer
from app.main import app
from app.models.order import (
    Order,
)
from app.services.idempotency import IdempotencyManager
from app.services.order_service import OrderService


@pytest.fixture
def mock_dependencies() -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    catalog_client = MagicMock(spec=CatalogGrpcClient)
    catalog_client.reserve_item = AsyncMock(return_value=ReservationResult(success=True))
    catalog_client.release_item = AsyncMock(return_value=True)

    idemp_mgr = MagicMock(spec=IdempotencyManager)
    idemp_mgr.acquire_lock = AsyncMock(return_value=True)
    idemp_mgr.release_lock = AsyncMock()
    idemp_mgr.store_response = AsyncMock()
    idemp_mgr.get_cached_response = AsyncMock(return_value=None)

    producer = MagicMock(spec=OrderEventProducer)
    producer.publish_order_placed = AsyncMock()
    producer.publish_order_escrow_locked = AsyncMock()
    producer.publish_order_completed = AsyncMock()
    producer.publish_order_cancelled = AsyncMock()

    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    return catalog_client, idemp_mgr, producer, session


@pytest.mark.asyncio
async def test_health_endpoints() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        live_resp = await client.get("/health/live")
        assert live_resp.status_code == 200
        assert live_resp.json()["status"] == "ok"

        ready_resp = await client.get("/health/ready")
        assert ready_resp.status_code == 200
        assert ready_resp.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_create_order_api_success(
    mock_dependencies: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    catalog_client, idemp_mgr, producer, session = mock_dependencies

    # In-memory store for orders in this test
    orders_db: dict[uuid.UUID, Order] = {}

    def fake_add(order: Order) -> None:
        orders_db[order.id] = order

    session.add = MagicMock(side_effect=fake_add)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    service = OrderService(
        catalog_client=catalog_client,
        idempotency_mgr=idemp_mgr,
        producer=producer,
    )

    app.dependency_overrides[get_order_service] = lambda: service
    app.dependency_overrides[get_session] = lambda: session

    buyer_id = str(uuid.uuid4())
    seller_id = str(uuid.uuid4())
    item_id = str(uuid.uuid4())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "buyer_id": buyer_id,
            "seller_id": seller_id,
            "item_id": item_id,
            "total_amount_units": 180,
            "currency": "USD",
        }
        resp = await client.post(
            "/api/v1/orders",
            json=payload,
            headers={"Idempotency-Key": "test-idemp-api-1"},
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["buyer_id"] == buyer_id
        assert data["status"] == "ESCROW_HELD"
        assert data["total_amount_units"] == 180

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_order_rejected_by_reservation(
    mock_dependencies: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    catalog_client, idemp_mgr, producer, session = mock_dependencies
    catalog_client.reserve_item = AsyncMock(
        return_value=ReservationResult(success=False, error_message="Item already sold")
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    service = OrderService(
        catalog_client=catalog_client,
        idempotency_mgr=idemp_mgr,
        producer=producer,
    )

    app.dependency_overrides[get_order_service] = lambda: service
    app.dependency_overrides[get_session] = lambda: session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "buyer_id": str(uuid.uuid4()),
            "seller_id": str(uuid.uuid4()),
            "item_id": str(uuid.uuid4()),
            "total_amount_units": 120,
        }
        resp = await client.post(
            "/api/v1/orders",
            json=payload,
            headers={"Idempotency-Key": "test-idemp-reject"},
        )
        assert resp.status_code == 409
        assert "Item already sold" in resp.json()["detail"]

    app.dependency_overrides.clear()
