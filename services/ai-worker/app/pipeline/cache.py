"""Redis caching for AI appraisals and visual embeddings keyed by image SHA-256."""
import redis.asyncio as aioredis
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import logger


class CachedAppraisal(BaseModel):
    brand: str
    category: str
    condition_grade: str
    condition_confidence: float
    attributes: list[str]
    min_price: int
    max_price: int
    visual_embedding: list[float]


class AppraisalCache:
    def __init__(
        self,
        redis_client: aioredis.Redis | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        self.redis = redis_client
        self.ttl = ttl_seconds or settings.CACHE_TTL_SECONDS
        self._key_prefix = "ai:appraisal:"

    async def connect(self) -> None:
        if self.redis is None:
            self.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            logger.info(f"Connected to Redis cache at {settings.REDIS_URL}")

    async def close(self) -> None:
        if self.redis:
            await self.redis.aclose()
            self.redis = None

    async def get(self, image_hash: str) -> CachedAppraisal | None:
        """Retrieve appraisal from Redis cache by image SHA-256 hash."""
        if not self.redis:
            return None

        key = f"{self._key_prefix}{image_hash}"
        try:
            cached_data = await self.redis.get(key)
            if cached_data:
                logger.info(f"Cache HIT for image hash {image_hash[:10]}...")
                return CachedAppraisal.model_validate_json(cached_data)
            logger.debug(f"Cache MISS for image hash {image_hash[:10]}...")
            return None
        except Exception as e:
            logger.warning(f"Error reading from Redis cache: {e}")
            return None

    async def set(self, image_hash: str, appraisal: CachedAppraisal) -> None:
        """Store appraisal and visual embedding in Redis cache."""
        if not self.redis:
            return

        key = f"{self._key_prefix}{image_hash}"
        try:
            serialized = appraisal.model_dump_json()
            await self.redis.setex(key, self.ttl, serialized)
            logger.info(f"Saved appraisal to cache key {key} (ttl={self.ttl}s)")
        except Exception as e:
            logger.warning(f"Error writing to Redis cache: {e}")
