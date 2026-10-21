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
    Manages lease-based idempotency locks with Redis and PostgreSQL fallback.
    Uses short leases (300s) for in-flight processing to ensure provider retries
    are NOT discarded if an unhandled failure occurs, and 24h TTL for completed events.
    """

    @staticmethod
    async def check_and_set_event(
        tenant_id: str,
        event_id: str,
        processing_lease_seconds: int = 300,
    ) -> bool:
        """
        Attempts to acquire a processing lease for (tenant_id, event_id).
        Key pattern: idempotency:{tenant_id}:{event_id}

        Returns:
            True: If the event is NEW or an expired lease (proceed with processing).
            False: If the event is already COMPLETED or currently being processed under an active lease.
        """
        if not event_id:
            return True

        key = f"idempotency:{tenant_id}:{event_id}"
        import time
        now = time.time()

        try:
            r = get_redis_client()
            current_status = await r.get(key)
            if current_status == "completed":
                logger.info(f"Event already successfully processed. Dropping duplicate: {key}")
                return False
            if current_status == "processing":
                logger.info(f"Event currently processing under active lease. Dropping duplicate: {key}")
                return False

            # Acquire processing lease
            is_new = await r.set(key, "processing", ex=processing_lease_seconds, nx=True)
            if not is_new:
                return False
            return True
        except Exception as e:
            logger.debug(f"Redis unavailable for idempotency key {key}: {e}. Using in-memory fallback.")
            if key in _in_memory_cache:
                entry = _in_memory_cache[key]
                if isinstance(entry, dict):
                    status = entry.get("status")
                    expires_at = entry.get("expires_at", 0)
                    if status == "completed" and now < expires_at:
                        return False
                    if status == "processing" and now < expires_at:
                        return False

            _in_memory_cache[key] = {
                "status": "processing",
                "expires_at": now + processing_lease_seconds,
            }
            return True

    @staticmethod
    async def mark_event_completed(
        tenant_id: str,
        event_id: str,
        ttl_seconds: int = 86400,
    ) -> None:
        """Update event status to 'completed' with full 24-hour deduplication TTL."""
        if not event_id:
            return
        key = f"idempotency:{tenant_id}:{event_id}"
        import time
        try:
            r = get_redis_client()
            await r.set(key, "completed", ex=ttl_seconds)
        except Exception as e:
            logger.warning(f"Failed to update idempotency status for {key}: {e}")
        _in_memory_cache[key] = {
            "status": "completed",
            "expires_at": time.time() + ttl_seconds,
        }

    @staticmethod
    async def release_event_lock(
        tenant_id: str,
        event_id: str,
    ) -> None:
        """
        Releases the processing lock if an unhandled failure occurred,
        allowing external provider webhook retries to be re-processed.
        """
        if not event_id:
            return
        key = f"idempotency:{tenant_id}:{event_id}"
        try:
            r = get_redis_client()
            val = await r.get(key)
            if val == "processing":
                await r.delete(key)
        except Exception as e:
            logger.debug(f"Failed to release processing lock for {key}: {e}")

        if key in _in_memory_cache:
            entry = _in_memory_cache[key]
            if isinstance(entry, dict) and entry.get("status") == "processing":
                _in_memory_cache.pop(key, None)
