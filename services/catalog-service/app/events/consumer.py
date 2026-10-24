"""Kafka event consumer synchronizing AI appraisals and Order states into Catalog DB."""
import asyncio
import uuid
from datetime import UTC, datetime

from aiokafka import AIOKafkaConsumer
from opentelemetry import trace
from sqlmodel import select

from app.core.config import settings
from app.core.database import async_session_maker
from app.core.logging import logger
from app.core.telemetry import extract_kafka_context
from app.events.schemas import map_proto_to_condition_grade
from app.grpc.schemas import events_pb2
from app.models.item import Item, ItemStatus

tracer = trace.get_tracer("rewearit-catalog-service")


class CatalogEventConsumer:
    def __init__(self, bootstrap_servers: str | None = None) -> None:
        self.bootstrap_servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self.consumer: AIOKafkaConsumer | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start async Kafka consumer and background consumption task."""
        topics = [settings.KAFKA_AI_EVENTS_TOPIC, settings.KAFKA_ORDER_EVENTS_TOPIC]
        logger.info(f"Starting Kafka consumer for topics={topics} (group={settings.CONSUMER_GROUP_CATALOG_SYNC})...")
        self.consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self.bootstrap_servers,
            group_id=settings.CONSUMER_GROUP_CATALOG_SYNC,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )
        await self.consumer.start()
        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info("Kafka consumer loop started.")

    async def stop(self) -> None:
        """Stop background consumption loop and consumer client."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self.consumer:
            await self.consumer.stop()
            self.consumer = None
            logger.info("Kafka consumer stopped.")

    async def _consume_loop(self) -> None:
        assert self.consumer is not None
        while self._running:
            try:
                msg = await self.consumer.getone()
                await self.process_message(msg.topic, msg.value, msg.headers)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing Kafka message: {e}", exc_info=True)
                await asyncio.sleep(0.5)

    async def process_message(self, topic: str, value: bytes, headers: list[tuple[str, bytes]]) -> None:
        header_dict = {k: v.decode("utf-8") if isinstance(v, bytes) else str(v) for k, v in headers}
        event_type = header_dict.get("event_type", "")
        span_name = f"catalog.consume_{event_type or topic}"

        ctx = extract_kafka_context(headers)
        with tracer.start_as_current_span(span_name, context=ctx):
            if topic == settings.KAFKA_AI_EVENTS_TOPIC or event_type == "ai.appraisal_completed":
                await self._handle_ai_appraisal(value)
            elif topic == settings.KAFKA_ORDER_EVENTS_TOPIC:
                if event_type == "order.completed":
                    await self._handle_order_completed(value)
                elif event_type == "order.cancelled":
                    await self._handle_order_cancelled(value)
                else:
                    logger.debug(f"Unhandled order event_type: {event_type}")

    async def _handle_ai_appraisal(self, value: bytes) -> None:
        event = events_pb2.AIAppraisalCompletedEvent()
        event.ParseFromString(value)
        item_id_str = event.item_id
        logger.info(f"Received AI appraisal for item_id={item_id_str}")

        try:
            item_uuid = uuid.UUID(item_id_str)
        except ValueError:
            logger.warning(f"Invalid item_id UUID: {item_id_str}")
            return

        async with async_session_maker() as session:
            result = await session.execute(select(Item).where(Item.id == item_uuid))
            item = result.scalar_one_or_none()
            if not item:
                logger.warning(f"Item not found in catalog for appraisal: {item_uuid}")
                return

            if event.visual_embedding:
                item.embedding = list(event.visual_embedding)
            if not item.condition_grade:
                item.condition_grade = map_proto_to_condition_grade(event.condition_grade)
            item.status = ItemStatus.ACTIVE
            item.updated_at = datetime.now(UTC)

            session.add(item)
            await session.commit()
            logger.info(f"Item {item_uuid} successfully updated with AI embedding and activated.")

    async def _handle_order_completed(self, value: bytes) -> None:
        event = events_pb2.OrderCompletedEvent()
        event.ParseFromString(value)
        item_uuid = uuid.UUID(event.item_id)
        logger.info(f"Handling order.completed for item_id={item_uuid}")

        async with async_session_maker() as session:
            result = await session.execute(select(Item).where(Item.id == item_uuid))
            item = result.scalar_one_or_none()
            if item:
                item.status = ItemStatus.SOLD
                item.updated_at = datetime.now(UTC)
                session.add(item)
                await session.commit()
                logger.info(f"Item {item_uuid} marked as SOLD.")

    async def _handle_order_cancelled(self, value: bytes) -> None:
        event = events_pb2.OrderCancelledEvent()
        event.ParseFromString(value)
        item_uuid = uuid.UUID(event.item_id)
        logger.info(f"Handling order.cancelled for item_id={item_uuid}")

        async with async_session_maker() as session:
            result = await session.execute(select(Item).where(Item.id == item_uuid))
            item = result.scalar_one_or_none()
            if item and item.status == ItemStatus.RESERVED:
                item.status = ItemStatus.ACTIVE
                item.reserved_by_order_id = None
                item.reserved_until_timestamp = None
                item.updated_at = datetime.now(UTC)
                session.add(item)
                await session.commit()
                logger.info(f"Item {item_uuid} reservation released back to ACTIVE.")


consumer = CatalogEventConsumer()
