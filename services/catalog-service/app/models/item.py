"""Domain models and SQLModel entities for Catalog Service."""
import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from pydantic import BaseModel
from sqlmodel import JSON, Column, Field, Index, SQLModel


class ConditionGrade(enum.StrEnum):
    NEW_WITH_TAGS = "NEW_WITH_TAGS"
    EXCELLENT = "EXCELLENT"
    VERY_GOOD = "VERY_GOOD"
    GOOD = "GOOD"
    FAIR = "FAIR"


class ItemStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    ANALYZING = "ANALYZING"
    ACTIVE = "ACTIVE"
    RESERVED = "RESERVED"
    SOLD = "SOLD"
    CANCELLED = "CANCELLED"


class ItemCategory(enum.StrEnum):
    TOPS = "Tops"
    BOTTOMS = "Bottoms"
    OUTERWEAR = "Outerwear"
    FOOTWEAR = "Footwear"
    ACCESSORIES = "Accessories"


class Money(BaseModel):
    currency: str = "USD"
    units: int
    nanos: int = 0


class ItemBase(SQLModel):
    seller_id: uuid.UUID = Field(index=True)
    title: str = Field(max_length=255)
    description: str = Field(default="")
    category: str = Field(index=True)
    brand: str = Field(max_length=100, index=True)
    size: str = Field(max_length=50)
    color: str | None = Field(default=None, max_length=50)
    material: str | None = Field(default=None, max_length=100)
    condition_grade: ConditionGrade = Field(default=ConditionGrade.GOOD, index=True)
    price_currency: str = Field(default="USD", max_length=3)
    price_units: int = Field(ge=0)
    price_nanos: int = Field(default=0, ge=0)
    status: ItemStatus = Field(default=ItemStatus.ANALYZING, index=True)
    image_urls: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class Item(ItemBase, table=True):
    __tablename__ = "items"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    
    # 512-dimensional CLIP embedding for visual search
    embedding: Any | None = Field(
        default=None,
        sa_column=Column(Vector(512), nullable=True),
    )

    # Concurrency and reservation tracking
    reserved_by_order_id: uuid.UUID | None = Field(default=None, index=True)
    reserved_until_timestamp: int | None = Field(default=None)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        index=True,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index(
            "ix_items_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
