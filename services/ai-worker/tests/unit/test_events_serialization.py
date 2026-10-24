"""Unit tests for protobuf event serialization and deserialization."""
import uuid

from app.events import events_pb2
from app.events.schemas import (
    build_event_header,
    create_appraisal_completed_event,
    map_condition_grade_to_proto,
    map_proto_to_condition_str,
)


def test_build_event_header() -> None:
    correlation_id = str(uuid.uuid4())
    header = build_event_header("item.created", correlation_id=correlation_id)
    assert header.event_type == "item.created"
    assert header.producer_service == "ai-worker"
    assert header.correlation_id == correlation_id
    assert header.schema_version == 1
    assert header.event_id != ""


def test_condition_grade_mapping() -> None:
    assert map_condition_grade_to_proto("NEW_WITH_TAGS") == events_pb2.ConditionGrade.CONDITION_GRADE_NEW_WITH_TAGS
    assert map_condition_grade_to_proto("EXCELLENT") == events_pb2.ConditionGrade.CONDITION_GRADE_EXCELLENT
    assert map_condition_grade_to_proto("VERY_GOOD") == events_pb2.ConditionGrade.CONDITION_GRADE_VERY_GOOD
    assert map_condition_grade_to_proto("GOOD") == events_pb2.ConditionGrade.CONDITION_GRADE_GOOD
    assert map_condition_grade_to_proto("FAIR") == events_pb2.ConditionGrade.CONDITION_GRADE_FAIR
    assert map_condition_grade_to_proto("UNKNOWN") == events_pb2.ConditionGrade.CONDITION_GRADE_UNSPECIFIED

    assert map_proto_to_condition_str(events_pb2.ConditionGrade.CONDITION_GRADE_EXCELLENT) == "EXCELLENT"


def test_create_appraisal_completed_event_serialization() -> None:
    item_id = str(uuid.uuid4())
    embedding = [0.1] * 512

    event = create_appraisal_completed_event(
        item_id=item_id,
        detected_brand="Levi's",
        detected_category="Outerwear",
        condition_grade="VERY_GOOD",
        condition_confidence=0.92,
        detected_attributes=["denim", "vintage", "distressed"],
        min_price_units=45,
        max_price_units=65,
        currency="USD",
        visual_embedding=embedding,
        correlation_id=item_id,
    )

    serialized = event.SerializeToString()
    assert len(serialized) > 0

    deserialized = events_pb2.AIAppraisalCompletedEvent()
    deserialized.ParseFromString(serialized)

    assert deserialized.item_id == item_id
    assert deserialized.detected_brand == "Levi's"
    assert deserialized.detected_category == "Outerwear"
    assert deserialized.condition_grade == events_pb2.ConditionGrade.CONDITION_GRADE_VERY_GOOD
    assert abs(deserialized.condition_confidence - 0.92) < 1e-4
    assert list(deserialized.detected_attributes) == ["denim", "vintage", "distressed"]
    assert deserialized.suggested_min_price.units == 45
    assert deserialized.suggested_max_price.units == 65
    assert len(deserialized.visual_embedding) == 512
