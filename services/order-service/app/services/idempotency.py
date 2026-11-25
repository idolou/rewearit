"""Redis-backed atomic idempotency lock preventing duplicate in-flight order processing."""
import redis.asyncio as aioredis
from opentelemetry import trace

from app.core.config import settings
from app.core.logging import logger

tracer = trace.get_tracer("rewearit-order-service")


class IdempotencyManager:
    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis: aioredis.Redis | None = None

    async def get_client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def ping(self) -> bool:
        client = await self.get_client()
        return bool(await client.ping())

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def acquire_lock(self, idempotency_key: str, ttl_seconds: int = 60) -> bool:
        """Atomically acquire processing lock for the given idempotency key."""
        with tracer.start_as_current_span("idempotency.acquire_lock"):
            client = await self.get_client()
            lock_key = f"idemp:lock:{idempotency_key}"
            acquired = await client.set(lock_key, "IN_PROGRESS", nx=True, ex=ttl_seconds)
            return bool(acquired)

    async def release_lock(self, idempotency_key: str) -> None:
        """Release processing lock after checkout completes or fails."""
        try:
            client = await self.get_client()
            lock_key = f"idemp:lock:{idempotency_key}"
            await client.delete(lock_key)
        except Exception as e:
            logger.warning(f"Failed to release idempotency lock for key={idempotency_key}: {e}")
