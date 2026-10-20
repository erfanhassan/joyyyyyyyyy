import json
import logging
from typing import Optional
from fastapi import APIRouter, Request, Header, HTTPException, BackgroundTasks, status
from app.core.config import settings
from app.core.hmac_middleware import verify_shopify_signature
from app.services.idempotency import IdempotencyService

logger = logging.getLogger("joy.webhooks.shopify")
router = APIRouter(prefix="/shopify", tags=["Shopify Webhooks"])


async def process_shopify_background(payload: dict, topic: str, tenant_id: str, event_id: str):
    """
    Asynchronous background handler for Shopify order webhooks.
    Triggers Employee #2: Voice Confirmation Specialist.
    """
    logger.info(f"[Shopify Background Worker] Processing topic '{topic}' for order {payload.get('id')} (Tenant: {tenant_id})")
    # Voice Confirmation & Timezone Gating trigger point
    await IdempotencyService.mark_event_completed(tenant_id, event_id)


@router.post("")
@router.post("/{tenant_id}")
async def receive_shopify_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    tenant_id: str = "default",
    x_shopify_hmac_sha256: Optional[str] = Header(None, alias="X-Shopify-Hmac-Sha256"),
    x_shopify_topic: Optional[str] = Header("orders/create", alias="X-Shopify-Topic"),
    x_shopify_webhook_id: Optional[str] = Header(None, alias="X-Shopify-Webhook-Id"),
):
    """
    Ingests Shopify webhooks (e.g. orders/create, orders/updated).
    Validates HMAC signature using SHOPIFY_API_SECRET and drops duplicates via Redis SETNX.
    """
    raw_body = await request.body()

    # 1. HMAC-SHA256 Signature Verification
    if settings.SHOPIFY_API_SECRET:
        is_valid = verify_shopify_signature(raw_body, x_shopify_hmac_sha256, settings.SHOPIFY_API_SECRET)
        if not is_valid:
            logger.warning(f"Invalid Shopify HMAC signature for tenant {tenant_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Shopify HMAC signature",
            )

    # 2. Parse Payload
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse Shopify JSON payload: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON")

    # 3. Determine Event ID for Deduplication
    order_id = payload.get("id") or payload.get("order_number")
    event_id = x_shopify_webhook_id or (f"shopify_{x_shopify_topic.replace('/', '_')}_{order_id}" if order_id else None)
    if not event_id:
        import hashlib
        event_id = hashlib.sha256(raw_body).hexdigest()[:16]

    # 4. Redis SETNX 24-Hour Deduplication
    is_new = await IdempotencyService.check_and_set_event(tenant_id, event_id)
    if not is_new:
        return {"status": "duplicate_ignored", "event_id": event_id}

    # 5. Dispatch to Background Worker
    background_tasks.add_task(process_shopify_background, payload, x_shopify_topic, tenant_id, event_id)

    # 6. Immediate Response (<1500ms)
    return {"status": "received", "event_id": event_id, "topic": x_shopify_topic, "tenant_id": tenant_id}
