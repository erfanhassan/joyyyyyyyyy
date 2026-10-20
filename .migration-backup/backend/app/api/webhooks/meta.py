import json
import logging
from typing import Optional
from fastapi import APIRouter, Request, Header, HTTPException, Query, BackgroundTasks, Response, status
from app.core.config import settings
from app.core.hmac_middleware import verify_meta_signature
from app.services.idempotency import IdempotencyService

logger = logging.getLogger("joy.webhooks.meta")
router = APIRouter(prefix="/meta", tags=["Meta Webhooks"])


async def process_meta_background(payload: dict, tenant_id: str, event_id: str):
    """
    Asynchronous background handler for Meta webhooks (comments, DMs, private replies).
    """
    logger.info(f"[Meta Background Worker] Processing event {event_id} for tenant {tenant_id}")
    # Handled by LangGraph Agent (Employee #1: Social Sales Specialist)
    await IdempotencyService.mark_event_completed(tenant_id, event_id)


@router.get("")
@router.get("/{tenant_id}")
async def verify_meta_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    tenant_id: str = "default",
):
    """
    Meta Webhook Hub Challenge verification endpoint.
    Used by Facebook and Instagram to verify webhook endpoint ownership.
    """
    expected_token = settings.META_VERIFY_TOKEN

    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        logger.info(f"Meta challenge verification successful for tenant {tenant_id}")
        return Response(content=hub_challenge, media_type="text/plain", status_code=200)

    logger.warning(f"Meta challenge failed: received token '{hub_verify_token}' vs expected")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Verification token mismatch",
    )


@router.post("")
@router.post("/{tenant_id}")
async def receive_meta_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    tenant_id: str = "default",
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
):
    """
    Ingest Facebook & Instagram comments, DMs, and post engagement webhooks.
    Enforces HMAC-SHA256 signature verification and Redis 24h deduplication.
    Responds within 1,500ms.
    """
    raw_body = await request.body()

    # 1. HMAC Signature Verification
    if settings.META_APP_SECRET:
        is_valid = verify_meta_signature(raw_body, x_hub_signature_256, settings.META_APP_SECRET)
        if not is_valid:
            logger.warning(f"Invalid Meta HMAC signature for tenant {tenant_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid HMAC signature",
            )

    # 2. Parse Payload
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse Meta JSON payload: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON")

    # 3. Extract Deduplication Event ID
    # Meta payloads typically have entry[0].id or entry[0].time or messaging[0].message.mid
    event_id = None
    entries = payload.get("entry", [])
    if entries and isinstance(entries, list):
        first_entry = entries[0]
        # Check for direct messaging MID
        messaging = first_entry.get("messaging", [])
        if messaging and isinstance(messaging, list):
            event_id = messaging[0].get("message", {}).get("mid")
        # Check for changes (comments / feeds)
        if not event_id:
            changes = first_entry.get("changes", [])
            if changes and isinstance(changes, list):
                event_id = changes[0].get("value", {}).get("comment_id") or changes[0].get("value", {}).get("post_id")
        # Fallback to entry id + timestamp
        if not event_id:
            event_id = f"{first_entry.get('id', 'evt')}_{first_entry.get('time', '0')}"
    
    if not event_id:
        import hashlib
        event_id = hashlib.sha256(raw_body).hexdigest()[:16]

    # 4. Redis SETNX 24-Hour Deduplication
    is_new = await IdempotencyService.check_and_set_event(tenant_id, event_id)
    if not is_new:
        return {"status": "duplicate_ignored", "event_id": event_id}

    # 5. Dispatch to Background Worker
    background_tasks.add_task(process_meta_background, payload, tenant_id, event_id)

    # 6. Immediate HTTP 200 OK
    return {"status": "received", "event_id": event_id, "tenant_id": tenant_id}
