"""Domain models and schemas for ReWearIt Orders and Escrow State Machine."""
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    ESCROW_HELD = "ESCROW_HELD"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class OrderBase(SQLModel):
    buyer_id: uuid.UUID = SQLField(index=True)
    seller_id: uuid.UUID = SQLField(index=True)
    item_id: uuid.UUID = SQLField(index=True)
    status: OrderStatus = SQLField(default=OrderStatus.CREATED, index=True)
    total_amount_units: int = SQLField(ge=0, description="Amount in whole currency units (e.g. dollars or cents)")
    total_amount_nanos: int = SQLField(default=0, ge=0)
    currency: str = SQLField(default="USD", max_length=3)
    idempotency_key: str = SQLField(index=True, unique=True, max_length=255)
    cancellation_reason: str | None = SQLField(default=None)
    tracking_number: str | None = SQLField(default=None, max_length=128)


class Order(OrderBase, table=True):
    __tablename__ = "orders"

    id: uuid.UUID = SQLField(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        nullable=False,
    )
    created_at: datetime = SQLField(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: datetime = SQLField(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
    )
    escrow_locked_at: datetime | None = SQLField(default=None)
    completed_at: datetime | None = SQLField(default=None)
    cancelled_at: datetime | None = SQLField(default=None)


# API DTOs
class OrderCreateRequest(BaseModel):
    item_id: uuid.UUID
    seller_id: uuid.UUID
    buyer_id: uuid.UUID
    total_amount_units: int = Field(gt=0)
    total_amount_nanos: int = Field(default=0, ge=0)
    currency: str = Field(default="USD", max_length=3)


class OrderShipRequest(BaseModel):
    tracking_number: str = Field(min_length=3, max_length=128)


class OrderCancelRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


class OrderResponse(BaseModel):
    id: uuid.UUID
    buyer_id: uuid.UUID
    seller_id: uuid.UUID
    item_id: uuid.UUID
    status: OrderStatus
    total_amount_units: int
    total_amount_nanos: int
    currency: str
    idempotency_key: str
    tracking_number: str | None
    cancellation_reason: str | None
    created_at: datetime
    updated_at: datetime
    escrow_locked_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
