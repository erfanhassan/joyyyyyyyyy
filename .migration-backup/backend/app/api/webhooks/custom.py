import json
import logging
from typing import Optional
from fastapi import APIRouter, Request, Header, HTTPException, BackgroundTasks, status
from app.core.config import settings
from app.core.hmac_middleware import verify_custom_signature
from app.services.idempotency import IdempotencyService

logger = logging.getLogger("joy.webhooks.custom")
router = APIRouter(prefix="/custom", tags=["Custom Storefront Webhooks"])


async def process_custom_background(payload: dict, tenant_id: str, event_id: str):
    """
    Asynchronous background handler for custom e-commerce storefront webhooks.
    """
    logger.info(f"[Custom Storefront Background Worker] Processing event {event_id} for tenant {tenant_id}")
    await IdempotencyService.mark_event_completed(tenant_id, event_id)


@router.post("")
@router.post("/{tenant_id}")
async def receive_custom_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    tenant_id: str = "default",
    x_signature_sha256: Optional[str] = Header(None, alias="X-Signature-SHA256"),
    x_event_id: Optional[str] = Header(None, alias="X-Event-ID"),
):
    """
    Ingests generic REST e-commerce webhooks from custom React, Next.js, or HTML sites.
    Validates HMAC signature and prevents duplicates via Redis SETNX.
    """
    raw_body = await request.body()

    # 1. HMAC-SHA256 Signature Verification (if secret configured)
    if settings.SHOPIFY_API_SECRET or settings.ENCRYPTION_KEY_SECRET:
        secret = settings.SHOPIFY_API_SECRET or settings.ENCRYPTION_KEY_SECRET
        is_valid = verify_custom_signature(raw_body, x_signature_sha256, secret)
        if not is_valid:
            logger.warning(f"Invalid Custom HMAC signature for tenant {tenant_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid HMAC signature",
            )

    # 2. Parse Payload
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse custom JSON payload: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON")

    # 3. Determine Event ID for Deduplication
    event_id = x_event_id or payload.get("event_id") or payload.get("id")
    if not event_id:
        import hashlib
        event_id = hashlib.sha256(raw_body).hexdigest()[:16]

    # 4. Redis SETNX 24-Hour Deduplication
    is_new = await IdempotencyService.check_and_set_event(tenant_id, str(event_id))
    if not is_new:
        return {"status": "duplicate_ignored", "event_id": event_id}

    # 5. Dispatch to Background Worker
    background_tasks.add_task(process_custom_background, payload, tenant_id, str(event_id))

    # 6. Immediate Response (<1500ms)
    return {"status": "received", "event_id": event_id, "tenant_id": tenant_id}
