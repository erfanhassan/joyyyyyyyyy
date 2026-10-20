import json
import logging
from typing import Optional
from fastapi import APIRouter, Request, Header, HTTPException, BackgroundTasks, status
from app.core.config import settings
from app.core.hmac_middleware import verify_woocommerce_signature
from app.services.idempotency import IdempotencyService

logger = logging.getLogger("joy.webhooks.woocommerce")
router = APIRouter(prefix="/woocommerce", tags=["WooCommerce Webhooks"])


async def process_woocommerce_background(payload: dict, topic: str, tenant_id: str, event_id: str):
    """
    Asynchronous background handler for WooCommerce order events.
    Triggers Employee #2: Voice Confirmation Specialist.
    """
    logger.info(f"[WooCommerce Background Worker] Processing topic '{topic}' for order {payload.get('id')} (Tenant: {tenant_id})")
    await IdempotencyService.mark_event_completed(tenant_id, event_id)


@router.post("")
@router.post("/{tenant_id}")
async def receive_woocommerce_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    tenant_id: str = "default",
    x_wc_webhook_signature: Optional[str] = Header(None, alias="X-WC-Webhook-Signature"),
    x_wc_webhook_topic: Optional[str] = Header("action.woocommerce_new_order", alias="X-WC-Webhook-Topic"),
    x_wc_webhook_id: Optional[str] = Header(None, alias="X-WC-Webhook-ID"),
):
    """
    Ingests WooCommerce webhooks (action.woocommerce_new_order).
    Validates HMAC signature using WOOCOMMERCE_WEBHOOK_SECRET and deduplicates via Redis SETNX.
    """
    raw_body = await request.body()

    # 1. HMAC-SHA256 Signature Verification
    if settings.WOOCOMMERCE_WEBHOOK_SECRET:
        is_valid = verify_woocommerce_signature(raw_body, x_wc_webhook_signature, settings.WOOCOMMERCE_WEBHOOK_SECRET)
        if not is_valid:
            logger.warning(f"Invalid WooCommerce HMAC signature for tenant {tenant_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid WooCommerce HMAC signature",
            )

    # 2. Parse Payload
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse WooCommerce JSON payload: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON")

    # 3. Determine Event ID for Deduplication
    order_id = payload.get("id")
    event_id = x_wc_webhook_id or (f"woo_{order_id}" if order_id else None)
    if not event_id:
        import hashlib
        event_id = hashlib.sha256(raw_body).hexdigest()[:16]

    # 4. Redis SETNX 24-Hour Deduplication
    is_new = await IdempotencyService.check_and_set_event(tenant_id, event_id)
    if not is_new:
        return {"status": "duplicate_ignored", "event_id": event_id}

    # 5. Dispatch to Background Worker
    background_tasks.add_task(process_woocommerce_background, payload, x_wc_webhook_topic, tenant_id, event_id)

    # 6. Immediate Response (<1500ms)
    return {"status": "received", "event_id": event_id, "topic": x_wc_webhook_topic, "tenant_id": tenant_id}
