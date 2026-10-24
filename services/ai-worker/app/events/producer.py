"""Kafka producer for publishing AI appraisal events."""
from aiokafka import AIOKafkaProducer

from app.core.config import settings
from app.core.logging import logger
from app.core.telemetry import inject_kafka_headers
from app.events import events_pb2


class AIEventProducer:
    def __init__(self, bootstrap_servers: str | None = None) -> None:
        self.bootstrap_servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self.producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        logger.info(f"Starting AI Kafka producer connecting to {self.bootstrap_servers}...")
        self.producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
        await self.producer.start()
        logger.info("AI Kafka producer started successfully.")

    async def stop(self) -> None:
        if self.producer:
            await self.producer.stop()
            self.producer = None
            logger.info("AI Kafka producer stopped.")

    async def publish_appraisal_completed(self, event: events_pb2.AIAppraisalCompletedEvent) -> None:
        if not self.producer:
            raise RuntimeError("AIEventProducer is not started")

        serialized_event = event.SerializeToString()
        headers = [
            ("event_type", b"ai.appraisal_completed"),
            ("event_id", event.header.event_id.encode("utf-8")),
            ("correlation_id", event.header.correlation_id.encode("utf-8")),
        ]
        headers = inject_kafka_headers(headers)

        logger.info(
            f"Publishing ai.appraisal_completed for item_id={event.item_id} "
            f"to topic={settings.KAFKA_AI_EVENTS_TOPIC}"
        )
        await self.producer.send_and_wait(
            topic=settings.KAFKA_AI_EVENTS_TOPIC,
            key=event.item_id.encode("utf-8"),
            value=serialized_event,
            headers=headers,
        )
