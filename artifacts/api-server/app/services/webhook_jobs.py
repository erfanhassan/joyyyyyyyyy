"""Durable inbox. HTTP acknowledgement follows commit, never an in-memory task."""
import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select, or_, and_
from sqlalchemy.dialects.postgresql import insert
from app.db.models import WebhookJob, TenantIntegration
from app.db.session import AsyncSessionLocal

logger = logging.getLogger("joy.jobs")


async def resolve_integration(db, provider, asset, tenant_id="default"):
    records = (await db.execute(select(TenantIntegration).where(
        TenantIntegration.provider == provider,
        TenantIntegration.is_active.is_(True)))).scalars().all()
    def matches(record):
        config = record.settings or {}
        if provider == "whatsapp":
            return str(config.get("phone_number_id", "")) == str(asset)
        if provider == "meta":
            return str(asset) in {str(config.get("page_id", "")), str(config.get("instagram_account_id", ""))}
        from urllib.parse import urlsplit
        configured = config.get("shop_domain") if provider == "shopify" else config.get("store_url")
        def host(s):
            return (urlsplit(s if "://" in s else f"https://{s}").hostname or "").lower()
        return bool(configured and asset and host(configured) == host(asset))
    matched = [r for r in records if matches(r)]
    if len(matched) != 1:
        raise HTTPException(404, "No unique active integration matches this provider asset.")
    record = matched[0]
    if tenant_id != "default" and str(record.tenant_id) != str(tenant_id):
        raise HTTPException(403, "Provider asset does not belong to this workspace.")
    return record


async def enqueue(db, provider, tenant_id, event_id, payload, topic=None):
    statement = insert(WebhookJob).values(
        id=uuid.uuid4(), provider=provider, tenant_id=tenant_id, event_id=str(event_id),
        payload=payload, topic=topic, status="pending", attempts=0)
    result = await db.execute(statement.on_conflict_do_nothing(
        index_elements=["provider", "tenant_id", "event_id"]).returning(WebhookJob.id))
    created = result.scalar_one_or_none() is not None
    await db.commit()
    return created


async def enqueue_meta(payload, route_tenant="default"):
    count = 0
    async with AsyncSessionLocal() as db:
        # Resolve each individual event. A mixed-Page batch never shares credentials.
        pending = []
        for entry in payload.get("entry", []):
            record = await resolve_integration(db, "meta", entry.get("id"), route_tenant)
            for field in ("messaging", "changes"):
                for event in entry.get(field, []):
                    normalized = {"object": payload.get("object"), "entry": [{
                        "id": entry["id"], "time": entry.get("time"), field: [event]}]}
                    event_id = event.get("message", {}).get("mid") or hashlib.sha256(
                        json.dumps(event, sort_keys=True).encode()).hexdigest()
                    pending.append((record.tenant_id, f"{entry['id']}:{event_id}", normalized))
        # Validate the entire batch before accepting any event.
        for tenant_id, event_id, event in pending:
            count += int(await enqueue(db, "meta", tenant_id, event_id, event))
    return count


async def run_once():
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        job = (await db.execute(select(WebhookJob).where(or_(
            and_(WebhookJob.status.in_(["pending", "retry"]), WebhookJob.available_at <= now),
            and_(WebhookJob.status == "processing", WebhookJob.lease_until < now)))
            .order_by(WebhookJob.available_at).with_for_update(skip_locked=True).limit(1))).scalar_one_or_none()
        if not job:
            return False
        job.status = "processing"
        job.attempts += 1
        job.lease_until = now + timedelta(minutes=5)
        await db.commit()
        try:
            if job.provider == "meta":
                from app.api.webhooks.meta import process_meta_background
                process = process_meta_background(job.payload, str(job.tenant_id), job.event_id)
            elif job.provider == "shopify":
                from app.api.webhooks.shopify import process_shopify_background
                process = process_shopify_background(job.payload, job.topic, str(job.tenant_id), job.event_id)
            elif job.provider == "woocommerce":
                from app.api.webhooks.woocommerce import process_woocommerce_background
                process = process_woocommerce_background(job.payload, job.topic, str(job.tenant_id), job.event_id)
            elif job.provider == "whatsapp":
                from app.services.whatsapp import process_whatsapp
                process = process_whatsapp(job.payload, str(job.tenant_id), job.event_id)
            else:
                raise ValueError("Unsupported provider")
            await asyncio.wait_for(process, timeout=240)
            job.status, job.last_error = "completed", None
        except Exception as error:
            # Do not persist provider bodies, phone numbers or credential-bearing errors.
            job.status = "dead" if job.attempts >= 8 or isinstance(error, ManualReviewRequired) else "retry"
            job.last_error = type(error).__name__
            job.available_at = datetime.now(timezone.utc) + timedelta(seconds=min(3600, 2 ** job.attempts * 15))
            logger.error("Webhook job %s requires attention (%s)", job.id, job.last_error)
        job.lease_until = None
        await db.commit()
        return True


class ManualReviewRequired(RuntimeError):
    """A provider may have accepted the side effect; do not automatically repeat it."""


async def worker():
    while True:
        try:
            worked = await run_once()
            if not worked:
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Webhook worker unavailable")
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(worker())
