import logging
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional
from uuid import UUID
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Order, AgentConfig, Conversation
from app.services.telephony_service import TelephonyService
from app.services.idempotency import get_redis_client

logger = logging.getLogger("joy.agents.voice_confirmation")


def get_customer_timezone(phone_number: str) -> str:
    """
    Infers customer timezone from international phone number dial prefix.
    """
    clean_phone = phone_number.strip().replace(" ", "").replace("-", "")

    # Bangladesh prefixes (+880, 01)
    if clean_phone.startswith("+880") or clean_phone.startswith("880") or clean_phone.startswith("01"):
        return "Asia/Dhaka"
    # United Kingdom
    elif clean_phone.startswith("+44") or clean_phone.startswith("44"):
        return "Europe/London"
    # UAE / Middle East
    elif clean_phone.startswith("+971") or clean_phone.startswith("971"):
        return "Asia/Dubai"
    # India
    elif clean_phone.startswith("+91") or clean_phone.startswith("91"):
        return "Asia/Kolkata"
    # North America
    elif clean_phone.startswith("+1") or clean_phone.startswith("1"):
        return "America/New_York"

    return "UTC"


def is_within_calling_hours(
    phone_number: str,
    merchant_hours: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """
    Validates whether an outbound call is permitted right now.
    Strict Constraint:
    - Never call between 9 PM (21:00) and 8 AM (08:00) in the customer's local timezone.
    - Also validates against merchant's configured operational hours if defined.
    """
    tz_name = get_customer_timezone(phone_number)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc

    customer_local_now = datetime.now(tz)
    current_hour = customer_local_now.hour

    # Strict blackout: 9 PM (21:00) to 8 AM (07:59)
    if current_hour >= 21 or current_hour < 8:
        return False, f"Blocked: Local time is {customer_local_now.strftime('%I:%M %p')} ({tz_name}). Gated between 9 PM and 8 AM."

    # Validate merchant operating hours if configured
    if merchant_hours:
        start_str = merchant_hours.get("start", "08:00")
        end_str = merchant_hours.get("end", "20:00")
        try:
            start_hour = int(start_str.split(":")[0])
            end_hour = int(end_str.split(":")[0])
            if current_hour < start_hour or current_hour >= end_hour:
                return False, f"Blocked: Outside merchant operating hours ({start_str} - {end_str})."
        except Exception as e:
            logger.warning(f"Error parsing merchant hours: {e}")

    return True, f"Permitted: Customer local time is {customer_local_now.strftime('%I:%M %p')} ({tz_name})."


class VoiceConfirmationAgent:
    """
    Employee #2: Outbound Voice Confirmation Specialist
    - Ingests new storefront orders
    - Validates customer timezone & operating hours
    - Initiates sub-800ms streaming speech-to-speech calls via LiveKit / SIP
    - Dispatches automated WhatsApp/SMS fallback if outside hours or unanswered
    """

    @staticmethod
    def generate_signed_verification_link(order_id: UUID, tenant_id: UUID) -> str:
        """Generates a cryptographically signed, 24-hour expiring order confirmation URL."""
        import time
        import hmac
        import hashlib
        from app.core.config import settings
        from app.core.public_urls import public_app_origin

        exp_ts = int(time.time()) + 86400  # 24 hours
        secret = settings.ENCRYPTION_KEY_SECRET
        if len(secret) < 32:
            raise RuntimeError("Secure order verification is not configured.")
        signed_value = f"{tenant_id}:{order_id}:{exp_ts}".encode()
        sig = hmac.new(secret.encode(), signed_value, hashlib.sha256).hexdigest()
        return (
            f"{public_app_origin()}/api/v1/telephony/verify-order"
            f"?order_id={order_id}&tenant_id={tenant_id}&exp={exp_ts}&sig={sig}"
        )

    @staticmethod
    def verify_signed_verification_link(order_id: UUID, tenant_id: UUID, exp: int, sig: str) -> bool:
        import hmac
        import hashlib
        from app.core.config import settings

        secret = settings.ENCRYPTION_KEY_SECRET
        if len(secret) < 32:
            return False
        current = hmac.new(
            secret.encode(),
            f"{tenant_id}:{order_id}:{exp}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(sig, current):
            return True
        # Allow old links generated before the tenant ID and full-length signature fix.
        legacy = hmac.new(
            secret.encode(),
            f"{order_id}:{exp}".encode(),
            hashlib.sha256,
        ).hexdigest()[:16]
        return hmac.compare_digest(sig, legacy)

    @staticmethod
    async def process_order_confirmation(
        order_id: UUID,
        tenant_id: UUID,
        db: AsyncSession,
        order_items: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes order verification pipeline for an incoming order:
        1. Timezone & Operating Hours gating
        2. LiveKit SIP dialing
        3. Cryptographic signed WhatsApp/SMS fallback
        """
        import time
        from app.services.telephony_service import OutboundCallingUnavailable

        # 1. Fetch Order Record
        stmt = select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id)
        res = await db.execute(stmt)
        order = res.scalars().first()
        if not order:
            logger.error(f"Order {order_id} not found for tenant {tenant_id}")
            return {"status": "error", "message": "Order not found"}

        # 2. Fetch Merchant Voice Agent Config
        cfg_stmt = select(AgentConfig).where(
            AgentConfig.tenant_id == tenant_id,
            AgentConfig.agent_type == "voice_confirmation",
        )
        cfg_res = await db.execute(cfg_stmt)
        agent_cfg = cfg_res.scalars().first()
        if not agent_cfg or not agent_cfg.is_active:
            return {"status": "agent_disabled", "message": "Voice confirmation is not enabled for this workspace."}
        merchant_hours = agent_cfg.operational_hours

        # 3. Timezone & Operating Hours Validation
        allowed, reason = is_within_calling_hours(order.customer_phone, merchant_hours)
        if not allowed:
            logger.info(f"Order {order_id} call held: {reason}. Triggering Omnichannel Fallback.")
            verification_link = VoiceConfirmationAgent.generate_signed_verification_link(order.id, tenant_id)

            order.confirmation_channel = "whatsapp"
            order.fallback_status = "link_created"
            order.fallback_dispatched_at = datetime.now(timezone.utc)
            db.add(order)
            await db.commit()

            return {
                "status": "verification_link_created",
                "channel": "not_sent",
                "reason": reason,
                "verification_link": verification_link,
            }

        # 4. Redis Distributed Lock (prevents concurrent calls to the same order)
        try:
            r = await get_redis_client()
            if r:
                lock_key = f"lock:telephony:call:{order_id}"
                acquired = await r.set(lock_key, "locked", ex=300, nx=True)
                if not acquired:
                    logger.warning(f"Outbound call already in progress for order {order_id}")
                    return {"status": "skipped", "message": "Call currently in progress"}
        except Exception as e:
            logger.warning(f"Redis lock check warning: {e}")

        # 5. Initiate Outbound Call via LiveKit Telephony Gateway
        order.call_attempts = (order.call_attempts or 0) + 1
        db.add(order)
        await db.commit()

        try:
            call_result = await TelephonyService.initiate_outbound_call(
                order_id=order.id,
                customer_phone=order.customer_phone,
                customer_name=order.customer_name,
                shipping_address=order.shipping_address,
                order_items=order_items or f"Store Order #{order.external_order_id}",
                order_total=float(order.order_total),
                tenant_id=tenant_id,
            )
            return {
                "status": "call_dispatched",
                "order_id": str(order.id),
                "call_id": call_result.get("call_id"),
                "room_name": call_result.get("room_name"),
                "reason": reason,
            }
        except OutboundCallingUnavailable as exc:
            logger.warning("Telephony unavailable (%s).", type(exc).__name__)
            try:
                verification_link = VoiceConfirmationAgent.generate_signed_verification_link(order.id, tenant_id)
            except RuntimeError:
                return {"status": "not_dispatched", "message": "Telephony and secure confirmation-link delivery are not configured."}
            order.confirmation_channel = "whatsapp"
            order.fallback_status = "telephony_unavailable_fallback"
            order.fallback_dispatched_at = datetime.now(timezone.utc)
            db.add(order)
            await db.commit()

            return {
                "status": "verification_link_created",
                "channel": "not_sent",
                "reason": "Telephony is unavailable; a signed link was created but not delivered.",
                "verification_link": verification_link,
            }
