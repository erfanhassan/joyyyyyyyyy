"""Atomic PostgreSQL quotas, shared across replicas; no fail-open fallback."""
import hashlib
import time
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert
from app.db.models import PublicRateCounter


async def consume(db, scope: str, identity: str, maximum: int, seconds: int = 60):
    window = int(time.time()) // seconds
    digest = hashlib.sha256(identity.encode()).hexdigest()
    key = f"{scope}:{digest}:{window}"
    statement = insert(PublicRateCounter).values(
        key=key, count=1,
        expires_at=datetime.fromtimestamp((window + 2) * seconds, timezone.utc))
    statement = statement.on_conflict_do_update(
        index_elements=["key"], set_={"count": PublicRateCounter.count + 1}).returning(PublicRateCounter.count)
    try:
        count = (await db.execute(statement)).scalar_one()
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(503, "Chat capacity cannot be verified. Please try again later.") from None
    if count > maximum:
        raise HTTPException(429, "Chat limit reached. Please try again later.",
                            headers={"Retry-After": str(seconds)})
