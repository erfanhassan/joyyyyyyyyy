import logging
import html
import uuid
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy import update
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


@router.post("/livekit")
async def handle_livekit_cloud_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Native LiveKit Cloud Webhook Receiver:
    Validates Authorization header signed by LiveKit Cloud using livekit.api.WebhookReceiver.
    Handles events:
    - participant_joined
    - participant_left
    - room_finished
    """
    from livekit.api import WebhookReceiver
    from app.core.config import settings

    auth_header = request.headers.get("Authorization", "")
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")

    receiver = WebhookReceiver(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
    try:
        event = receiver.receive(body_str, auth_header)
    except Exception as e:
        logger.warning("LiveKit Cloud webhook signature rejected.")
        raise HTTPException(401, "Invalid LiveKit webhook token.") from None

    event_name = getattr(event, "event", "unknown")
    room_name = getattr(getattr(event, "room", None), "name", "")
    logger.info(f"LiveKit Cloud Webhook Event received: {event_name} for room '{room_name}'")
    return {"status": "received", "event": event_name, "room": room_name}


@router.post("/completion")
async def handle_telephony_completion(
    payload: TelephonyCompletionPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Webhook receiver for telephony call completion.
    Stores audio transcript, updates order status to 'confirmed' or 'flagged_for_review',
    and syncs verification tags to Shopify/WooCommerce.
    """
    import time, hmac, hashlib
    from app.core.config import settings
    stamp = request.headers.get("x-joy-timestamp", "")
    signature = request.headers.get("x-joy-signature", "")
    try:
        fresh = abs(time.time() - int(stamp)) <= 300
    except ValueError:
        fresh = False
    expected = hmac.new(settings.LIVEKIT_API_SECRET.encode(),
                        stamp.encode() + b"." + await request.body(), hashlib.sha256).hexdigest()
    if not settings.LIVEKIT_API_SECRET or not fresh or not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "Invalid signed telephony callback.")
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
        raise HTTPException(404, "Callback does not match an existing order; no synthetic order was created.")

    # Claim the first confirmation atomically so a duplicate callback cannot create
    # a second courier shipment.
    first_confirmation = False
    if new_status == "confirmed":
        confirmation_update = await db.execute(
            update(Order)
            .where(Order.id == order.id, Order.tenant_id == payload.tenant_id, Order.status != "confirmed")
            .values(status="confirmed", call_transcript=payload.transcript, confirmation_channel="voice",
                    shipping_address=payload.updated_shipping_address or order.shipping_address)
            .returning(Order.id)
        )
        first_confirmation = confirmation_update.scalar_one_or_none() is not None
        await db.refresh(order)
    else:
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

    # 5. Delivery Partner Auto-Dispatch (Steadfast / Pathao)
    courier_result = None
    if first_confirmation:
        try:
            from app.db.models import TenantIntegration
            from app.services.courier_service import CourierService

            int_stmt = select(TenantIntegration).where(
                TenantIntegration.tenant_id == payload.tenant_id,
                TenantIntegration.provider.in_(["steadfast", "pathao", "courier"]),
                TenantIntegration.is_active == True,
            )
            int_res = await db.execute(int_stmt)
            courier_int = int_res.scalars().first()
            if courier_int:
                from app.core.safety import open_credentials
                courier_settings = open_credentials(courier_int.settings or {})
                courier_pref = courier_settings.get("provider", courier_int.provider)
                courier_result = await CourierService.dispatch_to_delivery_partner(
                    tenant_id=payload.tenant_id,
                    invoice=order.external_order_id,
                    recipient_name=order.customer_name,
                    recipient_phone=order.customer_phone,
                    recipient_address=order.shipping_address,
                    cod_amount=float(order.order_total),
                    courier_pref=courier_pref,
                    tenant_courier_settings=courier_settings,
                )
            else:
                courier_result = {"status": "unconfigured", "message": "No active courier is configured."}
            logger.info("Courier dispatch result status: %s.", (courier_result or {}).get("status", "unknown"))
        except Exception as e:
            logger.error(f"[Telephony Callback] Courier auto-dispatch error: {e}")

    # 6. Google Sheets Two-Way Sync
    sheet_result = None
    try:
        from app.db.models import TenantIntegration
        from app.services.google_sheets_service import GoogleSheetsService

        sheet_stmt = select(TenantIntegration).where(
            TenantIntegration.tenant_id == payload.tenant_id,
            TenantIntegration.provider == "google_sheets",
            TenantIntegration.is_active == True,
        )
        sheet_res = await db.execute(sheet_stmt)
        sheet_int = sheet_res.scalars().first()
        if sheet_int and sheet_int.settings:
            from app.core.safety import open_credentials
            sheet_settings = open_credentials(sheet_int.settings)
        else:
            sheet_settings = {}
        if sheet_settings.get("webhook_url"):
            tracking = courier_result.get("tracking_code") if courier_result else None
            courier_name = courier_result.get("courier") if courier_result else None
            sheet_updated = await GoogleSheetsService.update_order_via_apps_script(
                webhook_url=sheet_settings["webhook_url"],
                order_id=order.external_order_id,
                status=new_status,
                tracking_code=tracking,
                courier=courier_name,
                notes=f"Voice Confirmation Call: Confirmed={payload.order_confirmed}. {payload.transcript[:150]}",
            )
            sheet_result = {"updated": sheet_updated}
    except Exception as e:
        logger.error(f"[Telephony Callback] Google sheets sync error: {e}")

    # 7. Sync to Storefront (Shopify / WooCommerce)
    storefront_url = None
    storefront_token = None
    try:
        from app.db.models import TenantIntegration
        from app.core.security import decrypt_token
        from app.core.safety import open_credentials
        store_stmt = select(TenantIntegration).where(
            TenantIntegration.tenant_id == payload.tenant_id,
            TenantIntegration.provider == order.storefront_provider,
            TenantIntegration.is_active.is_(True),
        )
        store_int = (await db.execute(store_stmt)).scalars().first()
        if store_int:
            store_settings = open_credentials(store_int.settings or {})
            storefront_token = decrypt_token(store_int.access_token_encrypted)
            if order.storefront_provider == "shopify":
                shop_domain = str(store_settings.get("shop_domain") or "").removeprefix("https://").rstrip("/")
                storefront_url = f"https://{shop_domain}" if shop_domain else None
            elif order.storefront_provider == "woocommerce":
                storefront_url = store_settings.get("store_url")
                consumer_key = store_settings.get("consumer_key")
                if consumer_key:
                    storefront_token = f"{consumer_key}:{storefront_token}"
    except Exception as exc:
        logger.warning("Could not load storefront credentials (%s).", type(exc).__name__)

    sync_result = await OrderSyncService.sync_order_status(
        tenant_id=payload.tenant_id,
        external_order_id=order.external_order_id,
        storefront_provider=order.storefront_provider,
        new_status=new_status,
        transcript_summary=payload.transcript[:200],
        updated_address=payload.updated_shipping_address,
        storefront_api_url=storefront_url,
        access_token=storefront_token,
    )

    return {
        "status": "success",
        "order_id": str(order.id),
        "new_order_status": new_status,
        "storefront_sync": sync_result,
        "courier_dispatch": courier_result,
        "google_sheets_sync": sheet_result,
    }


@router.get("/verify-order")
async def verify_order_via_link(
    order_id: UUID,
    tenant_id: UUID,
    exp: int,
    sig: str,
    db: AsyncSession = Depends(get_db),
):
    """Show a confirmation form only; link scanners must not mutate order state."""
    import time
    from fastapi.responses import HTMLResponse
    from app.agents.voice_confirmation import VoiceConfirmationAgent

    if exp < int(time.time()) or exp > int(time.time()) + 86400:
        return HTMLResponse(status_code=400, content="This order confirmation link has expired.")
    if not VoiceConfirmationAgent.verify_signed_verification_link(order_id, tenant_id, exp, sig):
        return HTMLResponse(status_code=403, content="This order confirmation link is invalid.")
    stmt = select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id)
    res = await db.execute(stmt)
    order = res.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order_id_value = html.escape(str(order.external_order_id))
    customer_name = html.escape(order.customer_name or "there")
    total = html.escape(f"{order.order_total:,.2f}")
    token_fields = (
        f'<input type="hidden" name="order_id" value="{order.id}">'
        f'<input type="hidden" name="tenant_id" value="{tenant_id}">'
        f'<input type="hidden" name="exp" value="{exp}">'
        f'<input type="hidden" name="sig" value="{html.escape(sig, quote=True)}">'
    )
    if order.status == "confirmed":
        content = f"<h1>Already confirmed</h1><p>Order #{order_id_value} has already been confirmed.</p>"
    else:
        content = (
            f"<h1>Confirm your order</h1><p>Hello {customer_name}. "
            f"Confirm order #{order_id_value} for BDT {total}.</p>"
            f'<form method="post" action="/api/v1/telephony/verify-order/confirm">'
            f'{token_fields}<button type="submit">Confirm order</button></form>'
        )
    response = HTMLResponse(
        status_code=200,
        content=(
            '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" '
            'content="width=device-width, initial-scale=1"><title>Order confirmation | JOY</title>'
            '<style>body{font:16px system-ui;background:#f4f4f5;display:grid;place-items:center;'
            'min-height:100vh;margin:0}.card{background:white;padding:32px;border-radius:16px;'
            'max-width:420px;box-shadow:0 8px 24px #0001}button{background:#111;color:#fff;border:0;'
            'border-radius:8px;padding:12px 18px;font-size:16px;cursor:pointer}</style></head>'
            f'<body><main class="card">{content}</main></body></html>'
        ),
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@router.post("/verify-order/confirm")
async def confirm_order_via_link(
    order_id: UUID,
    tenant_id: UUID,
    exp: int,
    sig: str,
    db: AsyncSession = Depends(get_db),
):
    """Apply the signed customer confirmation only after an explicit POST."""
    import time
    from fastapi.responses import HTMLResponse
    from app.agents.voice_confirmation import VoiceConfirmationAgent

    if exp < int(time.time()) or exp > int(time.time()) + 86400:
        return HTMLResponse(status_code=400, content="This order confirmation link has expired.")
    if not VoiceConfirmationAgent.verify_signed_verification_link(order_id, tenant_id, exp, sig):
        return HTMLResponse(status_code=403, content="This order confirmation link is invalid.")

    stmt = select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id)
    order = (await db.execute(stmt)).scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "confirmed":
        order.status = "confirmed"
        order.confirmation_channel = "signed_link"
        db.add(order)
        await db.commit()

    response = HTMLResponse(
        status_code=200,
        content=f"<h1>Order confirmed</h1><p>Thank you. Order #{html.escape(order.external_order_id)} is confirmed.</p>",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
