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
    Normalizes order payload, persists Order record to PostgreSQL, and triggers
    Employee #2 (Voice Confirmation Specialist) with timezone gating.
    """
    logger.info(f"[Shopify Background Worker] Processing topic '{topic}' for order {payload.get('id')} (Tenant: {tenant_id})")
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
                # Find active Shopify integration
                int_stmt = select(TenantIntegration).where(
                    TenantIntegration.provider == "shopify",
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
                logger.error(f"Cannot resolve tenant for Shopify order {payload.get('id')}")
                return

            # 2. Normalize Shopify Order Data
            ext_order_id = str(payload.get("id") or payload.get("order_number") or event_id)
            customer = payload.get("customer") or {}
            shipping = payload.get("shipping_address") or {}
            billing = payload.get("billing_address") or {}

            first_name = customer.get("first_name") or shipping.get("first_name") or billing.get("first_name") or ""
            last_name = customer.get("last_name") or shipping.get("last_name") or billing.get("last_name") or ""
            customer_name = f"{first_name} {last_name}".strip() or "Shopify Customer"

            phone = (
                shipping.get("phone")
                or billing.get("phone")
                or customer.get("phone")
                or payload.get("phone")
                or ""
            )

            address_parts = [
                shipping.get("address1"),
                shipping.get("address2"),
                shipping.get("city"),
                shipping.get("country"),
            ]
            shipping_address = ", ".join([p for p in address_parts if p]) or "Shipping Address provided in Shopify"

            try:
                total_val = float(payload.get("total_price") or payload.get("current_total_price") or 0.0)
            except (ValueError, TypeError):
                total_val = 0.0

            line_items = payload.get("line_items") or []
            items_desc = ", ".join([f"{li.get('title')} (x{li.get('quantity', 1)})" for li in line_items]) or "Catalog Items"

            # 3. Check for existing order
            stmt = select(Order).where(
                Order.tenant_id == tenant_uuid,
                Order.external_order_id == ext_order_id,
                Order.storefront_provider == "shopify",
            )
            order_res = await db.execute(stmt)
            order = order_res.scalars().first()

            if not order:
                order = Order(
                    id=uuid_pkg.uuid4(),
                    tenant_id=tenant_uuid,
                    external_order_id=ext_order_id,
                    storefront_provider="shopify",
                    customer_name=customer_name,
                    customer_phone=phone,
                    shipping_address=shipping_address,
                    order_total=total_val,
                    status="pending_verification",
                )
                db.add(order)
                await db.commit()
                await db.refresh(order)
                logger.info(f"Persisted new Shopify order {order.id} (ext: {ext_order_id}) in database")

            # Incoming order notifications do not grant consent to call.
            if order.status == "pending_verification":
                order.customer_name = customer_name
                order.customer_phone = phone
                order.shipping_address = shipping_address
                order.order_total = total_val
                await db.commit()

            # Durable inbox completion is recorded by the worker.

        except Exception as e:
            logger.error(f"Error processing Shopify order webhook {event_id}: {e}", exc_info=True)
            raise


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
    from app.services.store_webhooks import authenticate_store
    verified_tenant_id = await authenticate_store(
        request, "shopify", tenant_id, raw_body, x_shopify_hmac_sha256)

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

    from app.db.session import AsyncSessionLocal
    from app.services.webhook_jobs import resolve_integration, enqueue
    async with AsyncSessionLocal() as db:
        created = await enqueue(db, "shopify", verified_tenant_id, event_id, payload, x_shopify_topic)

    # 6. Immediate Response (<1500ms)
    return {"status": "received" if created else "duplicate_ignored", "event_id": event_id, "topic": x_shopify_topic, "tenant_id": str(verified_tenant_id)}
