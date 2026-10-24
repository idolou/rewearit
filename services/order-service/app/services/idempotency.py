"""Redis-backed atomic idempotency manager preventing duplicate order checkout processing."""
import json
from typing import Any

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
        """Release processing lock if order processing fails before completion."""
        try:
            client = await self.get_client()
            lock_key = f"idemp:lock:{idempotency_key}"
            await client.delete(lock_key)
        except Exception as e:
            logger.warning(f"Failed to release idempotency lock for key={idempotency_key}: {e}")

    async def store_response(
        self,
        idempotency_key: str,
        response_data: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """Persist cached response payload for completed idempotency key."""
        ttl = ttl_seconds or settings.IDEMPOTENCY_TTL_SECONDS
        with tracer.start_as_current_span("idempotency.store_response"):
            client = await self.get_client()
            resp_key = f"idemp:resp:{idempotency_key}"
            await client.set(resp_key, json.dumps(response_data, default=str), ex=ttl)
            # Remove in-progress lock now that permanent response is cached
            await self.release_lock(idempotency_key)

    async def get_cached_response(self, idempotency_key: str) -> dict[str, Any] | None:
        """Retrieve previously processed response for idempotent requests."""
        with tracer.start_as_current_span("idempotency.get_cached"):
            client = await self.get_client()
            resp_key = f"idemp:resp:{idempotency_key}"
            raw = await client.get(resp_key)
            if raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception as e:
                    logger.error(f"Failed to deserialize cached response: {e}")
            return None
