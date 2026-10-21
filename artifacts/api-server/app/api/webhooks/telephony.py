import logging
import uuid
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db.models import Order, Conversation, InteractionLog
from app.services.order_sync import OrderSyncService

logger = logging.getLogger("joy.webhooks.telephony")
router = APIRouter(prefix="/telephony", tags=["Telephony Webhooks"])


class TelephonyCompletionPayload(BaseModel):
    order_id: Optional[UUID] = None
    tenant_id: UUID
    call_id: str
    transcript: str
    customer_phone: Optional[str] = None
    sentiment_score: float = 1.0
    order_confirmed: bool = True
    flagged_for_review: bool = False
    updated_shipping_address: Optional[str] = None


@router.post("/completion")
async def handle_telephony_completion(
    payload: TelephonyCompletionPayload,
    db: AsyncSession = Depends(get_db),
):
    """
    Webhook receiver for telephony call completion.
    Stores audio transcript, updates order status to 'confirmed' or 'flagged_for_review',
    and syncs verification tags to Shopify/WooCommerce.
    """
    logger.info(
        f"[Telephony Webhook] Processing completion for Order {payload.order_id or payload.call_id} "
        f"(confirmed={payload.order_confirmed}, flagged={payload.flagged_for_review})"
    )

    # 1. Determine new status
    if payload.flagged_for_review or not payload.order_confirmed:
        new_status = "flagged_for_review"
    else:
        new_status = "confirmed"

    # 2. Fetch or create Order Record
    order = None
    if payload.order_id:
        stmt = select(Order).where(Order.id == payload.order_id, Order.tenant_id == payload.tenant_id)
        res = await db.execute(stmt)
        order = res.scalars().first()

    if not order and payload.customer_phone:
        stmt = (
            select(Order)
            .where(Order.customer_phone == payload.customer_phone, Order.tenant_id == payload.tenant_id)
            .order_by(Order.created_at.desc())
        )
        res = await db.execute(stmt)
        order = res.scalars().first()

    if not order:
        order = Order(
            id=payload.order_id or uuid.uuid4(),
            tenant_id=payload.tenant_id,
            external_order_id=payload.call_id[:12],
            storefront_provider="custom",
            customer_name="Customer",
            customer_phone=payload.customer_phone or "+8801700000000",
            shipping_address=payload.updated_shipping_address or "Dhaka, Bangladesh",
            order_total=2500.0,
            status=new_status,
        )
        db.add(order)
        await db.flush()

    # 3. Update Order
    order.status = new_status
    order.call_transcript = payload.transcript
    order.confirmation_channel = "voice"
    if payload.updated_shipping_address:
        order.shipping_address = payload.updated_shipping_address

    # 4. Link/Update Conversation record for Operator Workbench
    if not order.conversation_id:
        conv = Conversation(
            id=uuid.uuid4(),
            tenant_id=payload.tenant_id,
            channel="phone",
            customer_identifier=order.customer_phone,
            customer_name=order.customer_name,
            sentiment_score=payload.sentiment_score,
            risk_score=round(1.0 - payload.sentiment_score, 2),
            is_paused_for_human=payload.flagged_for_review,
        )
        db.add(conv)
        await db.flush()
        order.conversation_id = conv.id

        # Log transcript to interaction logs
        log = InteractionLog(
            id=uuid.uuid4(),
            tenant_id=payload.tenant_id,
            conversation_id=conv.id,
            sender_type="agent",
            message_text=f"[Voice Confirmation Call Transcript]\n{payload.transcript}",
            raw_payload={
                "call_id": payload.call_id,
                "confirmed": payload.order_confirmed,
                "status": new_status,
            },
        )
        db.add(log)

    db.add(order)
    await db.commit()

    # 5. Sync to Storefront (Shopify / WooCommerce)
    sync_result = await OrderSyncService.sync_order_status(
        tenant_id=payload.tenant_id,
        external_order_id=order.external_order_id,
        storefront_provider=order.storefront_provider,
        new_status=new_status,
        transcript_summary=payload.transcript[:200],
        updated_address=payload.updated_shipping_address,
    )

    return {
        "status": "success",
        "order_id": str(order.id),
        "new_order_status": new_status,
        "storefront_sync": sync_result,
    }


@router.get("/verify-order")
async def verify_order_via_link(
    order_id: UUID,
    tenant_id: UUID,
    exp: int,
    sig: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Public customer verification endpoint for omnichannel WhatsApp / SMS links.
    Validates HMAC signature and timestamp expiry.
    """
    import time
    import hmac
    import hashlib
    from fastapi.responses import HTMLResponse
    from app.core.config import settings

    # 1. Validate Expiry
    now = int(time.time())
    if now > exp:
        return HTMLResponse(
            status_code=400,
            content="""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Link Expired</title><style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f9fafb}.card{background:white;padding:32px;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.08);text-align:center;max-width:400px}h2{color:#b91c1c;margin-top:0}</style></head><body><div class="card"><h2>Link Expired</h2><p>This verification link has expired. Our support staff will contact you to confirm your order.</p></div></body></html>""",
        )

    # 2. Validate HMAC Signature
    secret = settings.ENCRYPTION_KEY_SECRET or "joy_order_verify_secret_2026"
    expected_sig = hmac.new(secret.encode(), f"{order_id}:{exp}".encode(), hashlib.sha256).hexdigest()[:16]

    if not hmac.compare_digest(sig, expected_sig):
        return HTMLResponse(
            status_code=403,
            content="""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Invalid Signature</title><style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f9fafb}.card{background:white;padding:32px;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.08);text-align:center;max-width:400px}h2{color:#b91c1c;margin-top:0}</style></head><body><div class="card"><h2>Invalid Verification Link</h2><p>This verification link is invalid or corrupted.</p></div></body></html>""",
        )

    # 3. Find and update order
    stmt = select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id)
    res = await db.execute(stmt)
    order = res.scalars().first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = "confirmed"
    order.confirmation_channel = "whatsapp_link"
    db.add(order)
    await db.commit()

    # 4. Sync status back to Shopify / WooCommerce
    await OrderSyncService.sync_order_status(
        tenant_id=tenant_id,
        external_order_id=order.external_order_id,
        storefront_provider=order.storefront_provider,
        new_status="confirmed",
        transcript_summary="Customer confirmed delivery via signed WhatsApp link.",
        updated_address=order.shipping_address,
    )

    return HTMLResponse(
        status_code=200,
        content=f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Order Confirmed | JOY</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; background: #f4f4f5; }}
    .card {{ background: #ffffff; padding: 40px; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); text-align: center; max-width: 440px; border: 1px solid #e4e4e7; }}
    .badge {{ display: inline-flex; align-items: center; justify-content: center; width: 56px; height: 56px; border-radius: 28px; background: #ecfdf5; color: #059669; margin-bottom: 20px; }}
    h1 {{ font-size: 20px; color: #18181b; margin: 0 0 8px 0; }}
    p {{ font-size: 14px; color: #71717a; line-height: 1.5; margin: 0 0 20px 0; }}
    .details {{ background: #fafafa; border: 1px solid #e4e4e7; border-radius: 10px; padding: 14px; text-align: left; font-size: 13px; color: #3f3f46; margin-bottom: 24px; }}
    .row {{ display: flex; justify-content: space-between; margin-bottom: 6px; }}
    .row:last-child {{ margin-bottom: 0; }}
    .label {{ color: #71717a; }}
    .value {{ font-weight: 600; color: #18181b; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>
    </div>
    <h1>Order Confirmed!</h1>
    <p>Thank you, {order.customer_name}. Your delivery has been verified and is now being prepared for shipping.</p>
    <div class="details">
      <div class="row"><span class="label">Order ID:</span><span class="value">#{order.external_order_id}</span></div>
      <div class="row"><span class="label">Total:</span><span class="value">BDT {order.order_total:,.2f}</span></div>
      <div class="row"><span class="label">Destination:</span><span class="value">{order.shipping_address}</span></div>
    </div>
  </div>
</body>
</html>""",
    )
