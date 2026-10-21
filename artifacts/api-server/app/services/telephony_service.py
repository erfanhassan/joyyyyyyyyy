import json
import base64
import hmac
import hashlib
import time
import logging
from typing import Dict, Any
from uuid import UUID
import httpx
from app.core.config import settings

logger = logging.getLogger("joy.telephony")
CALLING_SETUP_MESSAGE = (
    "Outbound calling is not enabled. A compatible AmberIT SIP trunk, LiveKit "
    "SIP dialing integration, and a running voice-agent worker must be configured "
    "and tested first. LiveKit room connectivity alone does not verify phone calls."
)


class OutboundCallingUnavailable(RuntimeError):
    pass


def generate_livekit_token(
    api_key: str,
    api_secret: str,
    room_name: str,
    participant_identity: str,
    participant_name: str,
    can_publish: bool = True,
    can_subscribe: bool = True,
) -> str:
    """Generates standard LiveKit JWT access token with HS256 signature."""
    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")

    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    claims = {
        "exp": now + 7200,
        "nbf": now,
        "iss": api_key,
        "sub": participant_identity,
        "name": participant_name,
        "video": {
            "room": room_name,
            "roomJoin": True,
            "canPublish": can_publish,
            "canSubscribe": can_subscribe,
            "roomAdmin": True,
            "roomList": True,
            "roomCreate": True,
        },
    }
    h_str = b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    c_str = b64url(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    sig = b64url(hmac.new(api_secret.encode("utf-8"), f"{h_str}.{c_str}".encode("utf-8"), hashlib.sha256).digest())
    return f"{h_str}.{c_str}.{sig}"


class TelephonyService:
    """LiveKit connectivity diagnostics; outbound SIP/agent execution is not implemented."""

    @staticmethod
    def require_outbound_calling() -> None:
        # Fail before creating an order, a room, or a call-attempt record.
        raise OutboundCallingUnavailable(CALLING_SETUP_MESSAGE)

    @staticmethod
    async def test_telephony_status() -> Dict[str, Any]:
        """
        Checks LiveKit API access, not SIP registration or end-to-end calling.
        """
        results = {
            "livekit": {"connected": False, "status": "unconfigured"},
            "amberit": {
                "connected": False,
                "status": "not_verified",
                "message": "SIP authentication, trunk compatibility and media have not been verified.",
            },
        }

        # 1. Test LiveKit Cloud Twirp API
        livekit_url = settings.LIVEKIT_URL.replace("wss://", "https://").replace("ws://", "http://")
        if settings.LIVEKIT_URL and settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET:
            try:
                start_t = time.time()
                token = generate_livekit_token(
                    api_key=settings.LIVEKIT_API_KEY,
                    api_secret=settings.LIVEKIT_API_SECRET,
                    room_name="test-health-room",
                    participant_identity="health-check",
                    participant_name="Joy Health Check",
                )
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.post(
                        f"{livekit_url}/twirp/livekit.RoomService/ListRooms",
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                        },
                        json={},
                    )
                    latency = round((time.time() - start_t) * 1000)
                    if resp.status_code == 200:
                        results["livekit"] = {
                            "connected": True,
                            "status": "healthy",
                            "cluster_url": settings.LIVEKIT_URL,
                            "latency_ms": latency,
                            "models": {
                                "stt": settings.LIVEKIT_STT_MODEL,
                                "llm": settings.LIVEKIT_LLM_MODEL,
                                "tts": settings.LIVEKIT_TTS_MODEL,
                                "voice": settings.OPENAI_VOICE,
                            },
                        }
                    else:
                        results["livekit"] = {
                            "connected": False,
                            "status": "error",
                            "status_code": resp.status_code,
                            "message": "LiveKit rejected the health-check request.",
                        }
            except Exception:
                results["livekit"] = {
                    "connected": False, "status": "error",
                    "message": "Could not reach LiveKit. Check its configuration and network access.",
                }

        return {
            "status": "setup_required",
            "provider": "telephony",
            "connected": False,
            "calling_available": False,
            "diagnostics": results,
            "message": CALLING_SETUP_MESSAGE,
            "overall_status": CALLING_SETUP_MESSAGE,
        }

    @staticmethod
    async def initiate_outbound_call(
        order_id: UUID,
        customer_phone: str,
        customer_name: str,
        shipping_address: str,
        order_items: str,
        order_total: float,
        tenant_id: UUID,
        merchant_name: str = "Joy Store",
    ) -> Dict[str, Any]:
        """
        Initiates outbound AI phone confirmation call via LiveKit SIP trunk.
        Provisions a LiveKit room with order context metadata and dispatches SIP dialing.
        """
        if not settings.LIVEKIT_URL or not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
            raise OutboundCallingUnavailable("LiveKit credentials (URL, API Key, API Secret) are not configured.")

        room_name = f"order-call-{order_id}"
        livekit_url = settings.LIVEKIT_URL.replace("wss://", "https://").replace("ws://", "http://")

        # 1. Generate Admin Token for Twirp APIs
        token = generate_livekit_token(
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
            room_name=room_name,
            participant_identity=f"agent-{order_id}",
            participant_name="Joy Voice Agent",
        )

        metadata_dict = {
            "order_id": str(order_id),
            "tenant_id": str(tenant_id),
            "customer_phone": customer_phone,
            "customer_name": customer_name,
            "shipping_address": shipping_address,
            "order_items": order_items,
            "order_total": order_total,
            "merchant_name": merchant_name,
        }

        # 2. Create LiveKit Room
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                room_resp = await client.post(
                    f"{livekit_url}/twirp/livekit.RoomService/CreateRoom",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "name": room_name,
                        "empty_timeout": 300,
                        "max_participants": 5,
                        "metadata": json.dumps(metadata_dict),
                    },
                )
                if room_resp.status_code != 200:
                    logger.error(f"LiveKit CreateRoom returned {room_resp.status_code}: {room_resp.text}")
                    raise OutboundCallingUnavailable(f"LiveKit CreateRoom failed ({room_resp.status_code}): {room_resp.text}")
            except Exception as e:
                if isinstance(e, OutboundCallingUnavailable):
                    raise
                logger.error(f"Failed to communicate with LiveKit RoomService: {e}")
                raise OutboundCallingUnavailable(f"Could not reach LiveKit: {e}")

            # 3. Create SIP Outbound Participant if AmberIT is configured
            if not (settings.AMBERIT_SIP_SERVER and settings.AMBERIT_SIP_PHONE):
                raise OutboundCallingUnavailable("SIP Trunk (AmberIT) credentials are not fully configured.")

            sip_call_id = f"sip_{order_id}"
            try:
                sip_resp = await client.post(
                    f"{livekit_url}/twirp/livekit.SIP/CreateSIPParticipant",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "sip_call_to": customer_phone,
                        "room_name": room_name,
                        "participant_identity": f"customer-{customer_phone}",
                        "participant_name": customer_name,
                    },
                )
                if sip_resp.status_code == 200:
                    sip_data = sip_resp.json()
                    sip_call_id = sip_data.get("participant_id") or sip_call_id
                    logger.info(f"LiveKit SIP outbound participant created: {sip_call_id}")
                else:
                    logger.error(f"LiveKit SIP dispatch returned {sip_resp.status_code}: {sip_resp.text}")
                    raise OutboundCallingUnavailable(f"LiveKit SIP dispatch failed ({sip_resp.status_code}): {sip_resp.text}")
            except Exception as e:
                if isinstance(e, OutboundCallingUnavailable):
                    raise
                logger.error(f"SIP participant dispatch attempt error: {e}")
                raise OutboundCallingUnavailable(f"SIP dispatch error: {e}")

        logger.info(f"Initiated outbound voice confirmation call {sip_call_id} for order {order_id} in room {room_name}")
        return {
            "status": "calling_initiated",
            "call_id": sip_call_id,
            "room_name": room_name,
            "provider": "livekit_amberit",
            "customer_phone": customer_phone,
        }
