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
    Normalizes WooCommerce payload, persists Order to PostgreSQL, and triggers
    Employee #2 (Voice Confirmation Specialist) with timezone gating.
    """
    logger.info(f"[WooCommerce Background Worker] Processing topic '{topic}' for order {payload.get('id')} (Tenant: {tenant_id})")
    from uuid import UUID
    import uuid as uuid_pkg
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.db.models import Order, TenantIntegration, Tenant
    from app.agents.voice_confirmation import VoiceConfirmationAgent

    async with AsyncSessionLocal() as db:
        try:
            # 1. Resolve Tenant UUID
            tenant_uuid = None
            if tenant_id and tenant_id != "default":
                try:
                    tenant_uuid = UUID(tenant_id)
                except ValueError:
                    pass

            if not tenant_uuid:
                # Find active WooCommerce integration
                int_stmt = select(TenantIntegration).where(
                    TenantIntegration.provider == "woocommerce",
                    TenantIntegration.is_active == True,
                ).limit(1)
                res = await db.execute(int_stmt)
                item = res.scalars().first()
                if item:
                    tenant_uuid = item.tenant_id
                else:
                    t_stmt = select(Tenant.id).limit(1)
                    t_res = await db.execute(t_stmt)
                    tenant_uuid = t_res.scalar_one_or_none()

            if not tenant_uuid:
                logger.error(f"Cannot resolve tenant for WooCommerce order {payload.get('id')}")
                return

            # 2. Normalize WooCommerce Order Data
            ext_order_id = str(payload.get("id") or event_id)
            billing = payload.get("billing") or {}
            shipping = payload.get("shipping") or {}

            first_name = billing.get("first_name") or shipping.get("first_name") or ""
            last_name = billing.get("last_name") or shipping.get("last_name") or ""
            customer_name = f"{first_name} {last_name}".strip() or "WooCommerce Customer"

            phone = billing.get("phone") or shipping.get("phone") or "+8801700000000"

            address_parts = [
                shipping.get("address_1") or billing.get("address_1"),
                shipping.get("city") or billing.get("city"),
                shipping.get("state") or billing.get("state"),
                shipping.get("country") or billing.get("country"),
            ]
            shipping_address = ", ".join([p for p in address_parts if p]) or "Shipping Address in WooCommerce"

            try:
                total_val = float(payload.get("total") or 0.0)
            except (ValueError, TypeError):
                total_val = 0.0

            # 3. Check for existing order
            stmt = select(Order).where(
                Order.tenant_id == tenant_uuid,
                Order.external_order_id == ext_order_id,
            )
            order_res = await db.execute(stmt)
            order = order_res.scalars().first()

            if not order:
                order = Order(
                    id=uuid_pkg.uuid4(),
                    tenant_id=tenant_uuid,
                    external_order_id=ext_order_id,
                    storefront_provider="woocommerce",
                    customer_name=customer_name,
                    customer_phone=phone,
                    shipping_address=shipping_address,
                    order_total=total_val,
                    status="pending_verification",
                )
                db.add(order)
                await db.commit()
                await db.refresh(order)
                logger.info(f"Persisted new WooCommerce order {order.id} (ext: {ext_order_id}) in database")

            # 4. Trigger Voice Confirmation Workflow
            confirm_res = await VoiceConfirmationAgent.process_order_confirmation(
                order_id=order.id,
                tenant_id=tenant_uuid,
                db=db,
            )
            logger.info(f"WooCommerce order {order.id} confirmation result: {confirm_res}")

            # 5. Mark Event Completed
            await IdempotencyService.mark_event_completed(str(tenant_uuid), event_id)

        except Exception as e:
            logger.error(f"Error processing WooCommerce order webhook {event_id}: {e}", exc_info=True)
            if tenant_uuid:
                await IdempotencyService.release_event_lock(str(tenant_uuid), event_id)


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
