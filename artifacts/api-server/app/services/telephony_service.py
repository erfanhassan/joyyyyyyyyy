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
        """Never report an initiated call when no SIP participant was dialed."""
        TelephonyService.require_outbound_calling()
