"""Unit tests for Order SQLModel and schema validation."""
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.order import (
    Order,
    OrderCreateRequest,
    OrderResponse,
    OrderStatus,
)


def test_order_creation_defaults() -> None:
    order_id = uuid.uuid4()
    buyer_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    item_id = uuid.uuid4()
    idempotency_key = "idemp-key-123"

    order = Order(
        id=order_id,
        buyer_id=buyer_id,
        seller_id=seller_id,
        item_id=item_id,
        idempotency_key=idempotency_key,
        total_amount_units=120,
    )

    assert order.id == order_id
    assert order.buyer_id == buyer_id
    assert order.seller_id == seller_id
    assert order.item_id == item_id
    assert order.status == OrderStatus.CREATED
    assert order.total_amount_units == 120
    assert order.currency == "USD"
    assert order.idempotency_key == idempotency_key
    assert order.created_at is not None
    assert order.escrow_locked_at is None


def test_order_create_request_validation() -> None:
    buyer_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    item_id = uuid.uuid4()

    req = OrderCreateRequest(
        buyer_id=buyer_id,
        seller_id=seller_id,
        item_id=item_id,
        total_amount_units=50,
        currency="USD",
    )
    assert req.total_amount_units == 50

    # Negative amounts should be invalid
    with pytest.raises(ValidationError):
        OrderCreateRequest(
            buyer_id=buyer_id,
            seller_id=seller_id,
            item_id=item_id,
            total_amount_units=-10,
        )


def test_order_response_serialization() -> None:
    order = Order(
        buyer_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        item_id=uuid.uuid4(),
        idempotency_key="key-abc-456",
        total_amount_units=99,
        status=OrderStatus.ESCROW_HELD,
        escrow_locked_at=datetime.now(UTC),
    )

    resp = OrderResponse.model_validate(order, from_attributes=True)
    assert resp.status == OrderStatus.ESCROW_HELD
    assert resp.total_amount_units == 99
    assert resp.escrow_locked_at is not None
