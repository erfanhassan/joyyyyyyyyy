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

    if tenant_id == "default":
        raise RuntimeError("A verified store-to-workspace mapping is required.")
    async with AsyncSessionLocal() as db:
        db.info["tenant_id"] = tenant_id
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

            phone = billing.get("phone") or shipping.get("phone") or ""

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
                Order.storefront_provider == "woocommerce",
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

            if order.status == "pending_verification":
                order.customer_name = customer_name
                order.customer_phone = phone
                order.shipping_address = shipping_address
                order.order_total = total_val
                await db.commit()

            # 5. Mark Event Completed
            # Durable inbox completion is recorded by the worker.

        except Exception as e:
            logger.error(f"Error processing WooCommerce order webhook {event_id}: {e}", exc_info=True)
            raise


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
    from app.services.store_webhooks import authenticate_store
    verified_tenant_id = await authenticate_store(
        request, "woocommerce", tenant_id, raw_body, x_wc_webhook_signature)

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

    from app.db.session import AsyncSessionLocal
    from app.services.webhook_jobs import resolve_integration, enqueue
    async with AsyncSessionLocal() as db:
        created = await enqueue(db, "woocommerce", verified_tenant_id, event_id, payload, x_wc_webhook_topic)

    # 6. Immediate Response (<1500ms)
    return {"status": "received" if created else "duplicate_ignored", "event_id": event_id, "topic": x_wc_webhook_topic, "tenant_id": str(verified_tenant_id)}
