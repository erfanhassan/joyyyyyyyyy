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
        "sip": {
            "admin": True,
            "call": True,
        },
    }
    h_str = b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    c_str = b64url(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    sig = b64url(hmac.new(api_secret.encode("utf-8"), f"{h_str}.{c_str}".encode("utf-8"), hashlib.sha256).digest())
    return f"{h_str}.{c_str}.{sig}"


class TelephonyService:
    """LiveKit connectivity diagnostics and outbound SIP/agent execution."""

    @staticmethod
    def require_outbound_calling() -> None:
        if not (settings.LIVEKIT_URL and settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET):
            raise OutboundCallingUnavailable("LiveKit Cloud credentials (URL, API Key, API Secret) are not configured.")
        if not (settings.TELEPHONY_PHONE_NUMBER):
            raise OutboundCallingUnavailable("Telephony phone number is not configured.")
        if not settings.LIVEKIT_SIP_TRUNK_ID:
            raise OutboundCallingUnavailable("LiveKit SIP outbound trunk ID is not configured.")
        if not settings.OPENAI_API_KEY:
            raise OutboundCallingUnavailable("OpenAI voice processing is not configured.")

    @staticmethod
    async def test_telephony_status() -> Dict[str, Any]:
        """
        Checks LiveKit API access, SIP registration, and outbound trunk status.
        """
        results = {
            "livekit": {"connected": False, "status": "unconfigured"},
            "amberit": {
                "connected": False,
                "status": "not_verified",
                "message": "SIP authentication or outbound trunk not yet verified.",
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

                    # Check LiveKit SIP Outbound Trunk
                    try:
                        sip_resp = await client.post(
                            f"{livekit_url}/twirp/livekit.SIP/ListSIPOutboundTrunk",
                            headers={
                                "Authorization": f"Bearer {token}",
                                "Content-Type": "application/json",
                            },
                            json={},
                        )
                        if sip_resp.status_code == 200:
                            trunks = sip_resp.json().get("items", [])
                            if trunks:
                                active_trunk = trunks[0]
                                results["amberit"] = {
                                    "connected": True,
                                    "status": "healthy",
                                    "trunk_id": active_trunk.get("sip_trunk_id"),
                                    "trunk_name": active_trunk.get("name"),
                                    "caller_id": settings.TELEPHONY_PHONE_NUMBER,
                                    "sip_server": settings.AMBERIT_SIP_SERVER,
                                }
                            else:
                                results["amberit"] = {
                                    "connected": False,
                                    "status": "unconfigured",
                                    "message": "No outbound SIP trunks found in LiveKit.",
                                }
                    except Exception as e:
                        logger.warning(f"Error checking LiveKit SIP Outbound Trunk: {e}")
            except Exception:
                results["livekit"] = {
                    "connected": False, "status": "error",
                    "message": "Could not reach LiveKit. Check its configuration and network access.",
                }

        is_connected = results["livekit"].get("connected", False) and results["amberit"].get("connected", False)
        return {
            "status": "healthy" if is_connected else "setup_required",
            "provider": "telephony",
            "connected": is_connected,
            "calling_available": is_connected,
            "diagnostics": results,
            "message": "LiveKit Cloud WebRTC and Amber IT Bangladesh SIP Trunk are operational." if is_connected else CALLING_SETUP_MESSAGE,
            "overall_status": "LiveKit Cloud WebRTC and Amber IT Bangladesh SIP Trunk are operational." if is_connected else CALLING_SETUP_MESSAGE,
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
        TelephonyService.require_outbound_calling()

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
                    logger.error("LiveKit CreateRoom returned HTTP %s.", room_resp.status_code)
                    raise OutboundCallingUnavailable("LiveKit could not create a call room.")
            except Exception as e:
                if isinstance(e, OutboundCallingUnavailable):
                    raise
                logger.error(f"Failed to communicate with LiveKit RoomService: {e}")
                raise OutboundCallingUnavailable(f"Could not reach LiveKit: {e}")

            # 2.5 Dispatch AI Voice Agent into the Room
            try:
                agent_dispatch_resp = await client.post(
                    f"{livekit_url}/twirp/livekit.AgentDispatchService/CreateDispatch",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "room": room_name,
                        "agent_name": "joy-voice-agent",
                        "metadata": json.dumps(metadata_dict),
                    },
                )
                if agent_dispatch_resp.status_code == 200:
                    logger.info(f"Dispatched AI Agent 'joy-voice-agent' to room {room_name}")
                else:
                    logger.error("LiveKit agent dispatch returned HTTP %s.", agent_dispatch_resp.status_code)
                    raise OutboundCallingUnavailable("The voice agent could not be dispatched; no phone call was placed.")
            except Exception as e:
                if isinstance(e, OutboundCallingUnavailable):
                    raise
                logger.warning(f"Could not dispatch agent via AgentDispatchService: {e}")
                raise OutboundCallingUnavailable("The voice agent could not be dispatched; no phone call was placed.") from None

            # 3. Create SIP Outbound Participant
            trunk_id = settings.LIVEKIT_SIP_TRUNK_ID
            sip_call_id = f"sip_{order_id}"
            try:
                sip_resp = await client.post(
                    f"{livekit_url}/twirp/livekit.SIP/CreateSIPParticipant",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "sip_trunk_id": trunk_id,
                        "sip_call_to": customer_phone,
                        "sip_number": settings.TELEPHONY_PHONE_NUMBER,
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
