import logging
from typing import Optional
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger("joy.idempotency")

# Shared async Redis client
_redis_client: Optional[aioredis.Redis] = None


def get_redis_client() -> aioredis.Redis:
    """Get or initialize singleton async Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
    return _redis_client


# In-memory fallback dictionary with timestamps if Redis is offline
_in_memory_cache: dict = {}


class IdempotencyService:
    """
    Manages Redis SETNX idempotency keys with a 24-hour TTL (86,400 seconds)
    to enforce strict at-most-once processing across webhooks.
    Gracefully falls back to in-memory tracking if Redis is unreachable.
    """

    @staticmethod
    async def check_and_set_event(
        tenant_id: str,
        event_id: str,
        ttl_seconds: int = 86400,
    ) -> bool:
        """
        Attempts to acquire an idempotency lock for (tenant_id, event_id).
        Key pattern: idempotency:{tenant_id}:{event_id}
        
        Returns:
            True: If the event is NEW (lock acquired, proceed with processing).
            False: If the event is a DUPLICATE within the TTL (drop silently).
        """
        if not event_id:
            return True

        key = f"idempotency:{tenant_id}:{event_id}"
        import time
        now = time.time()

        try:
            r = get_redis_client()
            # SETNX with expiration (86400s = 24h)
            is_new = await r.set(key, "processing", ex=ttl_seconds, nx=True)
            if not is_new:
                logger.info(f"Duplicate webhook event detected and dropped via Redis: {key}")
                return False
            return True
        except Exception as e:
            logger.debug(f"Redis unavailable for idempotency key {key}: {e}. Using in-memory fallback.")
            # In-memory fallback check
            if key in _in_memory_cache:
                expires_at = _in_memory_cache[key]
                if now < expires_at:
                    logger.info(f"Duplicate webhook event detected and dropped via in-memory cache: {key}")
                    return False
            _in_memory_cache[key] = now + ttl_seconds
            return True

    @staticmethod
    async def mark_event_completed(
        tenant_id: str,
        event_id: str,
        ttl_seconds: int = 86400,
    ) -> None:
        """Update event status to 'completed'."""
        if not event_id:
            return
        key = f"idempotency:{tenant_id}:{event_id}"
        try:
            r = get_redis_client()
            await r.set(key, "completed", ex=ttl_seconds)
        except Exception as e:
            logger.warning(f"Failed to update idempotency status for {key}: {e}")
