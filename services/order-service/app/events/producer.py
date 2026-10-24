"""Kafka event producer for ReWearIt Order events with distributed trace propagation."""
import uuid
from datetime import UTC, datetime

from aiokafka import AIOKafkaProducer
from google.protobuf.timestamp_pb2 import Timestamp

from app.core.config import settings
from app.core.logging import logger
from app.core.telemetry import inject_kafka_headers
from app.grpc.schemas import events_pb2
from app.models.order import Order


def _current_proto_timestamp() -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(datetime.now(UTC))
    return ts


def _create_event_header(event_type: str, correlation_id: str | None = None) -> events_pb2.EventHeader:
    event_id = str(uuid.uuid4())
    corr_id = correlation_id or event_id
    header = events_pb2.EventHeader()
    header.event_id = event_id
    header.event_type = event_type
    header.timestamp.CopyFrom(_current_proto_timestamp())
    header.correlation_id = corr_id
    header.producer_service = settings.SERVICE_NAME
    header.schema_version = 1
    return header


class OrderEventProducer:
    def __init__(self, bootstrap_servers: str | None = None) -> None:
        self.bootstrap_servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self.producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        logger.info(f"Starting Order Kafka producer connecting to {self.bootstrap_servers}...")
        self.producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
        await self.producer.start()
        logger.info("Order Kafka producer started successfully.")

    async def stop(self) -> None:
        if self.producer:
            await self.producer.stop()
            self.producer = None
            logger.info("Order Kafka producer stopped.")

    async def _send_event(self, event_type: str, key: str, payload_bytes: bytes, correlation_id: str) -> None:
        if not self.producer:
            raise RuntimeError("OrderEventProducer is not started")

        headers = [
            ("event_type", event_type.encode("utf-8")),
            ("correlation_id", correlation_id.encode("utf-8")),
            ("producer_service", settings.SERVICE_NAME.encode("utf-8")),
        ]
        headers = inject_kafka_headers(headers)

        await self.producer.send_and_wait(
            topic=settings.KAFKA_ORDERS_TOPIC,
            key=key.encode("utf-8"),
            value=payload_bytes,
            headers=headers,
        )

    async def publish_order_placed(self, order: Order) -> None:
        header = _create_event_header("order.placed", correlation_id=order.idempotency_key)
        event = events_pb2.OrderPlacedEvent(
            header=header,
            order_id=str(order.id),
            item_id=str(order.item_id),
            buyer_id=str(order.buyer_id),
            seller_id=str(order.seller_id),
            total_amount=events_pb2.Money(
                currency=order.currency,
                units=order.total_amount_units,
                nanos=order.total_amount_nanos,
            ),
            idempotency_key=order.idempotency_key,
        )
        logger.info(f"Publishing order.placed for order_id={order.id}, item_id={order.item_id}")
        await self._send_event(
            event_type="order.placed",
            key=str(order.id),
            payload_bytes=event.SerializeToString(),
            correlation_id=order.idempotency_key,
        )

    async def publish_order_escrow_locked(self, order: Order) -> None:
        header = _create_event_header("order.escrow_locked", correlation_id=order.idempotency_key)
        locked_at = Timestamp()
        if order.escrow_locked_at:
            locked_at.FromDatetime(order.escrow_locked_at)
        else:
            locked_at.CopyFrom(_current_proto_timestamp())

        event = events_pb2.OrderEscrowLockedEvent(
            header=header,
            order_id=str(order.id),
            item_id=str(order.item_id),
            escrow_amount=events_pb2.Money(
                currency=order.currency,
                units=order.total_amount_units,
                nanos=order.total_amount_nanos,
            ),
            locked_at=locked_at,
        )
        logger.info(f"Publishing order.escrow_locked for order_id={order.id}, item_id={order.item_id}")
        await self._send_event(
            event_type="order.escrow_locked",
            key=str(order.id),
            payload_bytes=event.SerializeToString(),
            correlation_id=order.idempotency_key,
        )

    async def publish_order_completed(self, order: Order) -> None:
        header = _create_event_header("order.completed", correlation_id=str(order.id))
        completed_at = Timestamp()
        if order.completed_at:
            completed_at.FromDatetime(order.completed_at)
        else:
            completed_at.CopyFrom(_current_proto_timestamp())

        event = events_pb2.OrderCompletedEvent(
            header=header,
            order_id=str(order.id),
            item_id=str(order.item_id),
            buyer_id=str(order.buyer_id),
            seller_id=str(order.seller_id),
            payout_amount=events_pb2.Money(
                currency=order.currency,
                units=order.total_amount_units,
                nanos=order.total_amount_nanos,
            ),
            completed_at=completed_at,
        )
        logger.info(f"Publishing order.completed for order_id={order.id}, item_id={order.item_id}")
        await self._send_event(
            event_type="order.completed",
            key=str(order.id),
            payload_bytes=event.SerializeToString(),
            correlation_id=str(order.id),
        )

    async def publish_order_cancelled(self, order: Order, reason: str) -> None:
        header = _create_event_header("order.cancelled", correlation_id=str(order.id))
        cancelled_at = Timestamp()
        if order.cancelled_at:
            cancelled_at.FromDatetime(order.cancelled_at)
        else:
            cancelled_at.CopyFrom(_current_proto_timestamp())

        event = events_pb2.OrderCancelledEvent(
            header=header,
            order_id=str(order.id),
            item_id=str(order.item_id),
            buyer_id=str(order.buyer_id),
            seller_id=str(order.seller_id),
            cancellation_reason=reason,
            cancelled_at=cancelled_at,
        )
        logger.info(f"Publishing order.cancelled for order_id={order.id}, item_id={order.item_id}, reason='{reason}'")
        await self._send_event(
            event_type="order.cancelled",
            key=str(order.id),
            payload_bytes=event.SerializeToString(),
            correlation_id=str(order.id),
        )
