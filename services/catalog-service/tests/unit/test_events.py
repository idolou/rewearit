"""Unit tests for Kafka event schemas and serialization."""
import uuid

from app.events.schemas import (
    build_item_created_event,
    map_condition_grade_to_proto,
    map_proto_to_condition_grade,
)
from app.grpc.schemas import events_pb2
from app.models.item import ConditionGrade, Item, ItemCategory


def test_build_item_created_event_serialization() -> None:
    seller_id = uuid.uuid4()
    item = Item(
        seller_id=seller_id,
        title="Silk Slip Dress",
        description="100% mulberry silk dress in olive green",
        category=ItemCategory.TOPS.value,
        brand="Reformation",
        size="S",
        condition_grade=ConditionGrade.EXCELLENT,
        price_currency="USD",
        price_units=120,
        price_nanos=500000000,
        image_urls=["http://localhost:9000/garments/ref-1.jpg"],
    )

    proto_event = build_item_created_event(item, correlation_id="test-corr-123")

    # Serialize to bytes and deserialize
    payload_bytes = proto_event.SerializeToString()
    assert len(payload_bytes) > 0

    deserialized = events_pb2.ItemCreatedEvent()
    deserialized.ParseFromString(payload_bytes)

    assert deserialized.header.event_type == "item.created"
    assert deserialized.header.correlation_id == "test-corr-123"
    assert deserialized.header.producer_service == "catalog-service"
    assert deserialized.item_id == str(item.id)
    assert deserialized.seller_id == str(seller_id)
    assert deserialized.title == "Silk Slip Dress"
    assert deserialized.brand == "Reformation"
    assert deserialized.proposed_price.units == 120
    assert deserialized.proposed_price.nanos == 500000000
    assert deserialized.declared_condition == events_pb2.ConditionGrade.CONDITION_GRADE_EXCELLENT


def test_condition_grade_mapping_roundtrip() -> None:
    for grade in ConditionGrade:
        proto_grade = map_condition_grade_to_proto(grade)
        mapped_back = map_proto_to_condition_grade(proto_grade)
        assert mapped_back == grade
