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
    order_id: UUID
    tenant_id: UUID
    call_id: str
    transcript: str
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
        f"[Telephony Webhook] Processing completion for Order {payload.order_id} "
        f"(confirmed={payload.order_confirmed}, flagged={payload.flagged_for_review})"
    )

    # 1. Fetch Order Record
    stmt = select(Order).where(Order.id == payload.order_id, Order.tenant_id == payload.tenant_id)
    res = await db.execute(stmt)
    order = res.scalars().first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    # 2. Determine new status
    if payload.flagged_for_review or not payload.order_confirmed:
        new_status = "flagged_for_review"
    else:
        new_status = "confirmed"

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
