"""Async Kafka event producer for Catalog Service."""

from aiokafka import AIOKafkaProducer

from app.core.config import settings
from app.core.logging import logger
from app.core.telemetry import inject_kafka_headers
from app.events.schemas import build_item_created_event
from app.models.item import Item


class KafkaEventProducer:
    def __init__(self, bootstrap_servers: str | None = None) -> None:
        self.bootstrap_servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self.producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        """Start async Kafka producer client."""
        logger.info(f"Starting Kafka producer connecting to {self.bootstrap_servers}...")
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            client_id=f"{settings.SERVICE_NAME}-producer",
        )
        await self.producer.start()
        logger.info("Kafka producer started successfully.")

    async def stop(self) -> None:
        """Gracefully stop Kafka producer."""
        if self.producer:
            logger.info("Stopping Kafka producer...")
            await self.producer.stop()
            self.producer = None
            logger.info("Kafka producer stopped.")

    async def publish_item_created(self, item: Item, correlation_id: str | None = None) -> None:
        """Publish an ItemCreatedEvent to Kafka topic rewearit.items.events."""
        if not self.producer:
            raise RuntimeError("Kafka producer is not running. Call start() first.")

        event = build_item_created_event(item, correlation_id=correlation_id)
        payload = event.SerializeToString()
        key = str(item.id).encode("utf-8")
        headers = [
            ("event_type", b"item.created"),
            ("event_id", event.header.event_id.encode("utf-8")),
            ("correlation_id", event.header.correlation_id.encode("utf-8")),
        ]
        headers = inject_kafka_headers(headers)

        logger.info(f"Publishing item.created for item_id={item.id} to topic={settings.KAFKA_ITEM_EVENTS_TOPIC}")
        await self.producer.send_and_wait(
            topic=settings.KAFKA_ITEM_EVENTS_TOPIC,
            value=payload,
            key=key,
            headers=headers,
        )


producer = KafkaEventProducer()
