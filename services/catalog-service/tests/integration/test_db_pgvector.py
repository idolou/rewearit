"""Integration tests against live PostgreSQL catalog_db with pgvector."""
import uuid

import pytest
from sqlmodel import select

from app.core.database import async_session_maker, init_db
from app.models.item import ConditionGrade, Item, ItemStatus
from tests.conftest import requires_postgres

pytestmark = requires_postgres


@pytest.mark.asyncio
async def test_init_db_and_insert_vector() -> None:
    # Initialize extension and tables
    await init_db()

    # Generate test embedding (512 dimensions)
    sample_vector = [0.05] * 512

    seller_id = uuid.uuid4()
    item = Item(
        seller_id=seller_id,
        title="Test Trench Coat",
        description="Waterproof classic coat",
        category="Outerwear",
        brand="Burberry",
        size="M",
        condition_grade=ConditionGrade.EXCELLENT,
        price_units=450,
        price_nanos=0,
        status=ItemStatus.ACTIVE,
        embedding=sample_vector,
        image_urls=["http://localhost:9000/garments/burberry.jpg"],
    )

    async with async_session_maker() as session:
        session.add(item)
        await session.commit()
        await session.refresh(item)

        item_id = item.id
        assert item_id is not None

        # Query item back and verify vector retrieval
        result = await session.execute(select(Item).where(Item.id == item_id))
        queried_item = result.scalar_one()

        assert queried_item.title == "Test Trench Coat"
        assert queried_item.embedding is not None
        assert len(queried_item.embedding) == 512

        # Clean up
        await session.delete(queried_item)
        await session.commit()
