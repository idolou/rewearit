"""Protobuf event serialization helpers and enum mappers for ai-worker."""
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from google.protobuf.timestamp_pb2 import Timestamp

from app.events import events_pb2


def build_event_header(event_type: str, correlation_id: str | None = None) -> events_pb2.EventHeader:
    now = datetime.now(UTC)
    ts = Timestamp()
    ts.FromDatetime(now)

    return events_pb2.EventHeader(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        timestamp=ts,
        correlation_id=correlation_id or str(uuid.uuid4()),
        producer_service="ai-worker",
        schema_version=1,
    )


def map_condition_grade_to_proto(grade_str: str) -> events_pb2.ConditionGrade:
    clean = grade_str.strip().upper().replace(" ", "_")
    mapping = {
        "NEW_WITH_TAGS": events_pb2.ConditionGrade.CONDITION_GRADE_NEW_WITH_TAGS,
        "BRAND_NEW": events_pb2.ConditionGrade.CONDITION_GRADE_NEW_WITH_TAGS,
        "LIKE_NEW": events_pb2.ConditionGrade.CONDITION_GRADE_NEW_WITH_TAGS,
        "EXCELLENT": events_pb2.ConditionGrade.CONDITION_GRADE_EXCELLENT,
        "VERY_GOOD": events_pb2.ConditionGrade.CONDITION_GRADE_VERY_GOOD,
        "GOOD": events_pb2.ConditionGrade.CONDITION_GRADE_GOOD,
        "FAIR": events_pb2.ConditionGrade.CONDITION_GRADE_FAIR,
    }
    return mapping.get(clean, events_pb2.ConditionGrade.CONDITION_GRADE_UNSPECIFIED)


def map_proto_to_condition_str(proto_grade: events_pb2.ConditionGrade) -> str:
    reverse_map = {
        events_pb2.ConditionGrade.CONDITION_GRADE_NEW_WITH_TAGS: "NEW_WITH_TAGS",
        events_pb2.ConditionGrade.CONDITION_GRADE_EXCELLENT: "EXCELLENT",
        events_pb2.ConditionGrade.CONDITION_GRADE_VERY_GOOD: "VERY_GOOD",
        events_pb2.ConditionGrade.CONDITION_GRADE_GOOD: "GOOD",
        events_pb2.ConditionGrade.CONDITION_GRADE_FAIR: "FAIR",
        events_pb2.ConditionGrade.CONDITION_GRADE_UNSPECIFIED: "GOOD",
    }
    return reverse_map.get(proto_grade, "GOOD")


def create_appraisal_completed_event(
    item_id: str,
    detected_brand: str,
    detected_category: str,
    condition_grade: str,
    condition_confidence: float,
    detected_attributes: Sequence[str],
    min_price_units: int,
    max_price_units: int,
    currency: str = "USD",
    visual_embedding: Sequence[float] | None = None,
    correlation_id: str | None = None,
) -> events_pb2.AIAppraisalCompletedEvent:
    header = build_event_header("ai.appraisal_completed", correlation_id=correlation_id or item_id)
    grade_enum = map_condition_grade_to_proto(condition_grade)

    min_money = events_pb2.Money(currency=currency, units=min_price_units, nanos=0)
    max_money = events_pb2.Money(currency=currency, units=max_price_units, nanos=0)

    event = events_pb2.AIAppraisalCompletedEvent(
        header=header,
        item_id=item_id,
        detected_brand=detected_brand,
        detected_category=detected_category,
        condition_grade=grade_enum,
        condition_confidence=condition_confidence,
        suggested_min_price=min_money,
        suggested_max_price=max_money,
    )
    event.detected_attributes.extend(detected_attributes)

    if visual_embedding:
        event.visual_embedding.extend(visual_embedding)

    return event
