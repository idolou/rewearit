"""Core AI appraisal worker orchestrating preprocessor, cache, VLM, and embedding encoder."""
import io

from PIL import Image

from app.core.logging import logger
from app.events import events_pb2
from app.events.consumer import ItemEventConsumer
from app.events.producer import AIEventProducer
from app.events.schemas import (
    create_appraisal_completed_event,
    map_proto_to_condition_str,
)
from app.pipeline.cache import AppraisalCache, CachedAppraisal
from app.pipeline.embeddings.encoder import VisualEmbeddingEncoder
from app.pipeline.preprocessor import ImagePreprocessor
from app.pipeline.vlm.base import VLMClient
from app.pipeline.vlm.gemini import get_vlm_client


def _generate_fallback_image_bytes() -> bytes:
    img = Image.new("RGB", (256, 256), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class AIAppraisalWorker:
    def __init__(
        self,
        producer: AIEventProducer | None = None,
        consumer: ItemEventConsumer | None = None,
        cache: AppraisalCache | None = None,
        preprocessor: ImagePreprocessor | None = None,
        vlm_client: VLMClient | None = None,
        embedding_encoder: VisualEmbeddingEncoder | None = None,
    ) -> None:
        self.producer = producer or AIEventProducer()
        self.cache = cache or AppraisalCache()
        self.preprocessor = preprocessor or ImagePreprocessor()
        self.vlm_client = vlm_client or get_vlm_client()
        self.embedding_encoder = embedding_encoder or VisualEmbeddingEncoder()
        self.consumer = consumer or ItemEventConsumer(on_item_created=self.handle_item_created)

    async def start(self) -> None:
        """Start worker dependencies, cache connection, Kafka producer, and consumer."""
        logger.info("Starting AIAppraisalWorker...")
        await self.cache.connect()
        await self.producer.start()
        await self.consumer.start()
        logger.info("AIAppraisalWorker started and listening for item events.")

    async def stop(self) -> None:
        """Gracefully stop consumer, producer, and cache."""
        logger.info("Stopping AIAppraisalWorker...")
        await self.consumer.stop()
        await self.producer.stop()
        await self.cache.close()
        logger.info("AIAppraisalWorker stopped.")

    async def handle_item_created(self, event: events_pb2.ItemCreatedEvent) -> None:
        """Process item.created event and publish ai.appraisal_completed."""
        item_id = event.item_id
        logger.info(f"Initiating AI appraisal for item_id={item_id}, title='{event.title}'")

        # 1. Obtain image bytes
        image_bytes: bytes
        if event.image_urls:
            first_url = event.image_urls[0]
            try:
                image_bytes = await self.preprocessor.fetch_image(first_url)
            except Exception as e:
                logger.warning(f"Could not fetch image from {first_url} ({e}); using placeholder.")
                image_bytes = _generate_fallback_image_bytes()
        else:
            logger.info(f"No image URLs provided for item {item_id}; using placeholder.")
            image_bytes = _generate_fallback_image_bytes()

        # 2. Preprocess & Hash
        processed = self.preprocessor.process_bytes(image_bytes)
        image_hash = processed.sha256

        # 3. Check Redis Cache
        cached = await self.cache.get(image_hash)
        if cached:
            logger.info(f"Appraisal cache HIT for item {item_id} (hash={image_hash[:10]}...)")
            brand = cached.brand
            category = cached.category
            condition_grade = cached.condition_grade
            condition_confidence = cached.condition_confidence
            attributes = cached.attributes
            min_price = cached.min_price
            max_price = cached.max_price
            embedding = cached.visual_embedding
        else:
            logger.info(f"Appraisal cache MISS for item {item_id}. Invoking VLM & Embedding encoder...")
            declared_cond = map_proto_to_condition_str(event.declared_condition)
            vlm_res = await self.vlm_client.analyze(
                image_bytes=processed.cleaned_bytes,
                title=event.title,
                description=event.description,
                declared_condition=declared_cond,
            )

            # Generate 512-dim embedding
            embedding = self.embedding_encoder.encode_image(
                image_bytes=processed.cleaned_bytes,
                context_text=f"{event.title} {vlm_res.category} {vlm_res.brand}",
            )

            brand = vlm_res.brand
            category = vlm_res.category
            condition_grade = vlm_res.condition_grade
            condition_confidence = vlm_res.condition_confidence
            attributes = vlm_res.detected_attributes
            min_price = vlm_res.suggested_min_price
            max_price = vlm_res.suggested_max_price

            # Save to Redis cache
            new_cache_entry = CachedAppraisal(
                brand=brand,
                category=category,
                condition_grade=condition_grade,
                condition_confidence=condition_confidence,
                attributes=attributes,
                min_price=min_price,
                max_price=max_price,
                visual_embedding=embedding,
            )
            await self.cache.set(image_hash, new_cache_entry)

        # 4. Construct AIAppraisalCompletedEvent Protobuf
        appraisal_event = create_appraisal_completed_event(
            item_id=item_id,
            detected_brand=brand,
            detected_category=category,
            condition_grade=condition_grade,
            condition_confidence=condition_confidence,
            detected_attributes=attributes,
            min_price_units=min_price,
            max_price_units=max_price,
            currency="USD",
            visual_embedding=embedding,
            correlation_id=event.header.correlation_id,
        )

        # 5. Publish to Kafka
        await self.producer.publish_appraisal_completed(appraisal_event)
        logger.info(f"Successfully published AI appraisal for item {item_id} (grade={condition_grade}).")
