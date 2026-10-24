"""Kafka consumer subscribing to ItemCreatedEvent messages."""
import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from aiokafka import AIOKafkaConsumer
from opentelemetry import trace

from app.core.config import settings
from app.core.logging import logger
from app.core.telemetry import extract_kafka_context
from app.events import events_pb2

tracer = trace.get_tracer("rewearit-ai-worker")


class ItemEventConsumer:
    def __init__(
        self,
        on_item_created: Callable[[events_pb2.ItemCreatedEvent], Coroutine[Any, Any, None]],
        bootstrap_servers: str | None = None,
    ) -> None:
        self.on_item_created = on_item_created
        self.bootstrap_servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self.consumer: AIOKafkaConsumer | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        logger.info(
            f"Starting ItemEventConsumer for topic={settings.KAFKA_ITEMS_TOPIC} "
            f"(group={settings.CONSUMER_GROUP_AI_WORKER})..."
        )
        self.consumer = AIOKafkaConsumer(
            settings.KAFKA_ITEMS_TOPIC,
            bootstrap_servers=self.bootstrap_servers,
            group_id=settings.CONSUMER_GROUP_AI_WORKER,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )
        await self.consumer.start()
        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info("ItemEventConsumer loop started.")

    async def stop(self) -> None:
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
            logger.info("ItemEventConsumer stopped.")

    async def _consume_loop(self) -> None:
        assert self.consumer is not None
        while self._running:
            try:
                msg = await self.consumer.getone()
                await self.process_message(msg.value, msg.headers)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in ItemEventConsumer consume loop: {e}", exc_info=True)
                await asyncio.sleep(0.5)

    async def process_message(self, value: bytes, headers: list[tuple[str, bytes]]) -> None:
        header_dict = {k: v.decode("utf-8") if isinstance(v, bytes) else str(v) for k, v in headers}
        event_type = header_dict.get("event_type", "")
        ctx = extract_kafka_context(headers)
        span_name = f"ai_worker.consume_{event_type or 'item.created'}"

        with tracer.start_as_current_span(span_name, context=ctx):
            if event_type == "item.created" or not event_type:
                try:
                    event = events_pb2.ItemCreatedEvent()
                    event.ParseFromString(value)
                    logger.info(f"Received item.created for item_id={event.item_id}, title='{event.title}'")
                    await self.on_item_created(event)
                except Exception as e:
                    logger.error(f"Failed to parse or process ItemCreatedEvent: {e}", exc_info=True)
            else:
                logger.debug(f"Ignoring unhandled item event_type={event_type}")
