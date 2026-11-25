"""Catalog service layer coordinating persistence and Kafka event emission."""
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.logging import logger
from app.events.producer import producer
from app.models.item import ConditionGrade, Item, ItemBase, ItemStatus


class ItemNotFoundError(Exception):
    """Raised when a catalog item does not exist."""


class ItemOwnershipError(Exception):
    """Raised when a user tries to modify another seller's listing."""


class ItemStateConflictError(Exception):
    """Raised when an item's current status blocks the requested action."""


class CatalogService:
    @staticmethod
    async def create_item(
        session: AsyncSession,
        item_in: ItemBase,
        correlation_id: str | None = None,
    ) -> Item:
        """Create item in ANALYZING state and publish ItemCreatedEvent to Kafka."""
        item = Item.model_validate(item_in)
        item.status = ItemStatus.ANALYZING
        session.add(item)
        await session.commit()
        await session.refresh(item)

        try:
            await producer.publish_item_created(item, correlation_id=correlation_id)
        except Exception as e:
            logger.error(f"Failed to publish ItemCreatedEvent for item {item.id}: {e}", exc_info=True)
            # We don't rollback DB creation; outbox / event sync can retry

        return item

    @staticmethod
    async def get_item_by_id(session: AsyncSession, item_id: uuid.UUID) -> Item | None:
        """Fetch item by UUID."""
        result = await session.execute(select(Item).where(col(Item.id) == item_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_items(
        session: AsyncSession,
        category: str | None = None,
        brand: str | None = None,
        condition_grade: ConditionGrade | None = None,
        status: ItemStatus | None = None,
        seller_id: uuid.UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Item]:
        """List items with optional filters."""
        query = select(Item)
        if category:
            query = query.where(col(Item.category) == category)
        if brand:
            query = query.where(col(Item.brand) == brand)
        if condition_grade:
            query = query.where(col(Item.condition_grade) == condition_grade)
        if status:
            query = query.where(col(Item.status) == status)
        if seller_id:
            query = query.where(col(Item.seller_id) == seller_id)

        query = query.order_by(col(Item.created_at).desc()).limit(limit).offset(offset)
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def delist_item(
        session: AsyncSession,
        item_id: uuid.UUID,
        seller_id: uuid.UUID,
    ) -> Item:
        """Cancel an ACTIVE or ANALYZING listing owned by seller_id."""
        result = await session.execute(select(Item).where(col(Item.id) == item_id).with_for_update())
        item = result.scalar_one_or_none()
        if item is None:
            raise ItemNotFoundError(f"Item '{item_id}' not found")
        if item.seller_id != seller_id:
            raise ItemOwnershipError("You can only delist your own listings")
        if item.status not in (ItemStatus.ACTIVE, ItemStatus.ANALYZING, ItemStatus.DRAFT):
            raise ItemStateConflictError(f"Cannot delist item in status {item.status.value}")

        item.status = ItemStatus.CANCELLED
        item.updated_at = datetime.now(UTC)
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item

    @staticmethod
    async def search_visual(
        session: AsyncSession,
        embedding: list[float],
        limit: int = 10,
        max_distance: float = 1.0,
    ) -> list[tuple[Item, float]]:
        """Search items by CLIP visual vector cosine distance (<->)."""
        if len(embedding) != 512:
            raise ValueError(f"Visual embedding must be exactly 512 dimensions, got {len(embedding)}")

        distance_col = col(Item.embedding).cosine_distance(embedding).label("distance")  # type: ignore[attr-defined]
        query = (
            select(Item, distance_col)
            .where(col(Item.status) == ItemStatus.ACTIVE)
            .where(col(Item.embedding).isnot(None))
            .where(distance_col <= max_distance)
            .order_by(distance_col.asc())
            .limit(limit)
        )
        result = await session.execute(query)
        rows = result.all()
        return [(row[0], float(row[1])) for row in rows]
