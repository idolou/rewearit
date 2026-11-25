"""Integration tests for Order Service FastAPI endpoints."""
import base64
import hashlib
import hmac
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.orders import get_order_service
from app.clients.catalog_client import CatalogGrpcClient, CatalogItemSnapshot, ReservationResult
from app.core.config import settings
from app.core.database import get_session
from app.events.producer import OrderEventProducer
from app.main import app
from app.models.order import (
    Order,
)
from app.services.idempotency import IdempotencyManager
from app.services.order_service import OrderService


def _make_jwt(user_id: str | uuid.UUID) -> str:
    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    h = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    p = _b64(
        json.dumps(
            {"sub": str(user_id), "email": "u@example.com", "name": "Test", "exp": int(time.time()) + 300},
            separators=(",", ":"),
        ).encode()
    )
    sig = _b64(hmac.new(settings.JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
    return f"{h}.{p}.{sig}"


@pytest.fixture
def mock_dependencies() -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    catalog_client = MagicMock(spec=CatalogGrpcClient)
    catalog_client.reserve_item = AsyncMock(return_value=ReservationResult(success=True))
    catalog_client.release_item = AsyncMock(return_value=True)
    catalog_client.mark_item_sold = AsyncMock(return_value=True)
    catalog_client.get_item = AsyncMock(
        side_effect=lambda item_id: CatalogItemSnapshot(
            item_id=item_id,
            seller_id=uuid.uuid4(),
            price_units=180,
            price_nanos=0,
            currency="USD",
        )
    )

    idemp_mgr = MagicMock(spec=IdempotencyManager)
    idemp_mgr.acquire_lock = AsyncMock(return_value=True)
    idemp_mgr.release_lock = AsyncMock()

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
    mock_conn = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_conn
    mock_ctx.__aexit__.return_value = False

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_ctx

    with (
        patch("app.main.engine", mock_engine),
        patch("app.main.idempotency_mgr.ping", new=AsyncMock(return_value=True)),
    ):
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
            headers={
                "Idempotency-Key": "test-idemp-api-1",
                "Authorization": f"Bearer {_make_jwt(buyer_id)}",
            },
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["buyer_id"] == buyer_id
        assert data["status"] == "ESCROW_HELD"
        assert data["total_amount_units"] == 180

        # Unauthenticated request must be rejected with 401
        unauth = await client.post(
            "/api/v1/orders",
            json=payload,
            headers={"Idempotency-Key": "test-idemp-unauth"},
        )
        assert unauth.status_code == 401

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
        buyer_id = str(uuid.uuid4())
        payload = {
            "buyer_id": buyer_id,
            "seller_id": str(uuid.uuid4()),
            "item_id": str(uuid.uuid4()),
            "total_amount_units": 120,
        }
        resp = await client.post(
            "/api/v1/orders",
            json=payload,
            headers={
                "Idempotency-Key": "test-idemp-reject",
                "Authorization": f"Bearer {_make_jwt(buyer_id)}",
            },
        )
        assert resp.status_code == 409
        assert "Item already sold" in resp.json()["detail"]

    app.dependency_overrides.clear()
