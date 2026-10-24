"""Unit tests for Item model and enums."""
import uuid

from app.models.item import ConditionGrade, Item, ItemCategory, ItemStatus, Money


def test_item_defaults() -> None:
    seller_id = uuid.uuid4()
    item = Item(
        seller_id=seller_id,
        title="Vintage Leather Jacket",
        category=ItemCategory.OUTERWEAR.value,
        brand="Schott",
        size="L",
        price_units=150,
        price_nanos=0,
        image_urls=["https://storage.local/garments/schott-1.jpg"],
    )

    assert item.title == "Vintage Leather Jacket"
    assert item.condition_grade == ConditionGrade.GOOD
    assert item.status == ItemStatus.ANALYZING
    assert item.price_currency == "USD"
    assert item.price_units == 150
    assert len(item.image_urls) == 1
    assert item.embedding is None
    assert item.reserved_by_order_id is None


def test_money_value_object() -> None:
    money = Money(currency="USD", units=99, nanos=500000000)
    assert money.units == 99
    assert money.nanos == 500000000
