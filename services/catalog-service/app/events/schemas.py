"""Protobuf event conversion helpers for Kafka."""
import uuid
from datetime import UTC, datetime

from app.grpc.schemas import events_pb2
from app.models.item import ConditionGrade, Item, ItemStatus


def create_event_header(
    event_type: str,
    correlation_id: str | None = None,
    producer_service: str = "catalog-service",
) -> events_pb2.EventHeader:
    """Build standardized EventHeader envelope."""
    header = events_pb2.EventHeader(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        correlation_id=correlation_id or str(uuid.uuid4()),
        producer_service=producer_service,
        schema_version=1,
    )
    header.timestamp.FromDatetime(datetime.now(UTC))
    return header


def map_condition_grade_to_proto(grade: ConditionGrade) -> events_pb2.ConditionGrade:
    mapping = {
        ConditionGrade.NEW_WITH_TAGS: events_pb2.ConditionGrade.CONDITION_GRADE_NEW_WITH_TAGS,
        ConditionGrade.EXCELLENT: events_pb2.ConditionGrade.CONDITION_GRADE_EXCELLENT,
        ConditionGrade.VERY_GOOD: events_pb2.ConditionGrade.CONDITION_GRADE_VERY_GOOD,
        ConditionGrade.GOOD: events_pb2.ConditionGrade.CONDITION_GRADE_GOOD,
        ConditionGrade.FAIR: events_pb2.ConditionGrade.CONDITION_GRADE_FAIR,
    }
    return mapping.get(grade, events_pb2.ConditionGrade.CONDITION_GRADE_GOOD)


def map_proto_to_condition_grade(proto_grade: events_pb2.ConditionGrade) -> ConditionGrade:
    mapping = {
        events_pb2.ConditionGrade.CONDITION_GRADE_NEW_WITH_TAGS: ConditionGrade.NEW_WITH_TAGS,
        events_pb2.ConditionGrade.CONDITION_GRADE_EXCELLENT: ConditionGrade.EXCELLENT,
        events_pb2.ConditionGrade.CONDITION_GRADE_VERY_GOOD: ConditionGrade.VERY_GOOD,
        events_pb2.ConditionGrade.CONDITION_GRADE_GOOD: ConditionGrade.GOOD,
        events_pb2.ConditionGrade.CONDITION_GRADE_FAIR: ConditionGrade.FAIR,
    }
    return mapping.get(proto_grade, ConditionGrade.GOOD)


def map_status_to_proto(status: ItemStatus) -> events_pb2.ItemStatus:
    mapping = {
        ItemStatus.DRAFT: events_pb2.ItemStatus.ITEM_STATUS_DRAFT,
        ItemStatus.ANALYZING: events_pb2.ItemStatus.ITEM_STATUS_ANALYZING,
        ItemStatus.ACTIVE: events_pb2.ItemStatus.ITEM_STATUS_ACTIVE,
        ItemStatus.RESERVED: events_pb2.ItemStatus.ITEM_STATUS_RESERVED,
        ItemStatus.SOLD: events_pb2.ItemStatus.ITEM_STATUS_SOLD,
        ItemStatus.CANCELLED: events_pb2.ItemStatus.ITEM_STATUS_CANCELLED,
    }
    return mapping.get(status, events_pb2.ItemStatus.ITEM_STATUS_DRAFT)


def build_item_created_event(item: Item, correlation_id: str | None = None) -> events_pb2.ItemCreatedEvent:
    """Build serialized ItemCreatedEvent protobuf payload."""
    header = create_event_header("item.created", correlation_id=correlation_id)
    money_proto = events_pb2.Money(
        currency=item.price_currency,
        units=item.price_units,
        nanos=item.price_nanos,
    )
    return events_pb2.ItemCreatedEvent(
        header=header,
        item_id=str(item.id),
        seller_id=str(item.seller_id),
        title=item.title,
        description=item.description,
        category=item.category,
        brand=item.brand,
        size=item.size,
        declared_condition=map_condition_grade_to_proto(item.condition_grade),
        proposed_price=money_proto,
        image_urls=item.image_urls,
    )
