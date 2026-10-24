"""Catalog service layer coordinating persistence and Kafka event emission."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.logging import logger
from app.events.producer import producer
from app.models.item import ConditionGrade, Item, ItemBase, ItemStatus


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

        query = query.order_by(col(Item.created_at).desc()).limit(limit).offset(offset)
        result = await session.execute(query)
        return list(result.scalars().all())

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
