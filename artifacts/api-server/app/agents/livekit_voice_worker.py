import os
import asyncio
import json
import logging
import time
import hmac
import hashlib
from typing import Optional, Dict, Any
from uuid import UUID

import dotenv
dotenv.load_dotenv()

from app.core.config import settings

# Ensure critical environment variables are propagated to os.environ for livekit-agents C-bindings
if settings.LIVEKIT_URL:
    os.environ["LIVEKIT_URL"] = settings.LIVEKIT_URL
if settings.LIVEKIT_API_KEY:
    os.environ["LIVEKIT_API_KEY"] = settings.LIVEKIT_API_KEY
if settings.LIVEKIT_API_SECRET:
    os.environ["LIVEKIT_API_SECRET"] = settings.LIVEKIT_API_SECRET
if settings.OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY

import httpx
from livekit import rtc
from livekit.agents import (
    JobContext,
    WorkerOptions,
    cli,
    voice,
    llm,
    function_tool,
)
from livekit.plugins import openai, silero

logger = logging.getLogger("joy.voice_worker")


async def post_telephony_completion(
    order_id: str,
    tenant_id: str,
    call_id: str,
    transcript: str,
    customer_phone: str,
    order_confirmed: bool,
    flagged_for_review: bool = False,
    updated_shipping_address: Optional[str] = None,
):
    """Dispatches cryptographically signed completion payload to JOY telephony webhook."""
    domain = settings.DOMAIN or "joy.sonictch.com"
    proto = "https" if "sonictch" in domain else "http"
    url = f"{proto}://{domain}/api/v1/webhooks/telephony/completion"

    payload_dict = {
        "order_id": order_id,
        "tenant_id": tenant_id,
        "call_id": call_id,
        "transcript": transcript,
        "customer_phone": customer_phone,
        "sentiment_score": 1.0 if order_confirmed else 0.5,
        "order_confirmed": order_confirmed,
        "flagged_for_review": flagged_for_review,
        "updated_shipping_address": updated_shipping_address,
    }
    body_bytes = json.dumps(payload_dict).encode("utf-8")
    stamp = str(int(time.time()))
    secret = settings.LIVEKIT_API_SECRET.encode("utf-8")
    signature = hmac.new(secret, stamp.encode("utf-8") + b"." + body_bytes, hashlib.sha256).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "x-joy-timestamp": stamp,
        "x-joy-signature": signature,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(url, headers=headers, content=body_bytes)
            logger.info(f"[Voice Worker] Posted call completion for order {order_id}: {resp.status_code}")
        except Exception as e:
            logger.error(f"[Voice Worker] Error posting completion: {e}")


class ConfirmationAgent(voice.Agent):
    def __init__(self, instructions: str, metadata: Dict[str, Any], call_id: str):
        super().__init__(instructions=instructions)
        self.meta = metadata
        self.call_id = call_id
        self.order_confirmed = False
        self.updated_address = None
        self.decision_made = False

    @function_tool(description="Call this function when the customer confirms, cancels, or updates their order.")
    async def record_order_decision(
        self,
        confirmed: bool,
        notes: str = "",
        updated_address: str = "",
    ):
        """Records customer decision during the live confirmation call."""
        self.decision_made = True
        self.order_confirmed = confirmed
        if updated_address:
            self.updated_address = updated_address
        logger.info(f"[Agent Tool] Decision: confirmed={confirmed}, address={updated_address}, notes={notes}")
        return "Decision recorded successfully."


async def entrypoint(ctx: JobContext):
    """
    LiveKit Agent Job Entrypoint:
    Runs when an outbound or inbound call room is dispatched.
    """
    logger.info(f"[Voice Worker] Connected to room {ctx.room.name}")
    await ctx.connect()

    # Parse order context metadata passed during room creation
    meta: Dict[str, Any] = {}
    if ctx.room.metadata:
        try:
            meta = json.loads(ctx.room.metadata)
        except Exception:
            pass

    customer_name = meta.get("customer_name") or "গ্রাহক"
    customer_phone = meta.get("customer_phone") or ""
    order_id = meta.get("order_id") or ctx.room.name
    items = meta.get("order_items") or "পণ্য"
    total = meta.get("order_total") or "নির্ধারিত মূল্য"
    store_name = meta.get("merchant_name") or "JOY Store"
    tenant_id = meta.get("tenant_id") or ""
    shipping_address = meta.get("shipping_address") or "আপনার ঠিকানা"

    system_prompt = f"""You are the friendly, polite voice confirmation specialist calling from {store_name} in Bangladesh.
Your goal is to quickly confirm the customer's order over the telephone:
- Customer Name: {customer_name}
- Order items: {items}
- Total COD amount: {total} BDT
- Delivery address: {shipping_address}

Guidelines:
1. Greet the customer respectfully in Bangla (or friendly Banglish/English as appropriate):
   "আসসালামু আলাইকুম {customer_name}, আমি {store_name} থেকে বলছি আপনার অর্ডারটি কনফার্ম করার জন্য।"
2. State the items ({items}) and total amount ({total} টাকা).
3. Ask if they want to confirm the delivery: "অর্ডারটি কি কনফার্ম করে ডেলিভারির জন্য পাঠিয়ে দেব?"
4. If customer says yes/confirm ("হ্যাঁ", "হাঁ", "ঠিক আছে", "কনফার্ম", "yes"):
   Call record_order_decision(confirmed=True).
   Say: "ধন্যবাদ! আপনার অর্ডারটি কনফার্ম করা হয়েছে এবং শীঘ্রই পাঠিয়ে দেওয়া হবে। ভালো থাকবেন।"
5. If customer says cancel/no ("না", "বাতিল", "দরকার নেই", "cancel"):
   Call record_order_decision(confirmed=False).
   Say: "ঠিক আছে, আপনার অনুরোধ অনুযায়ী অর্ডারটি বাতিল করা হলো। ধন্যবাদ।"
6. If customer wants to change delivery address:
   Ask for the new address, call record_order_decision(confirmed=True, updated_address=new_address).
7. Speak warmly, clearly, and keep responses concise for telephone audio.
"""

    # Initialize AI Components
    openai_key = settings.OPENAI_API_KEY
    agent_instance = ConfirmationAgent(
        instructions=system_prompt,
        metadata=meta,
        call_id=ctx.room.name,
    )

    session = voice.AgentSession(
        stt=openai.STT(api_key=openai_key),
        vad=silero.VAD.load(),
        llm=openai.LLM(model="gpt-4o-mini", api_key=openai_key),
        tts=openai.TTS(voice=settings.OPENAI_VOICE or "alloy", api_key=openai_key),
    )

    # Start the voice session in the room
    await session.start(agent_instance, room=ctx.room)

    # Initial greeting to the customer
    greeting = f"আসসালামু আলাইকুম {customer_name}! আমি {store_name} থেকে কল করেছি আপনার অর্ডারটি কনফার্ম করার জন্য।"
    await session.say(greeting)

    # Wait until room closes or conversation ends
    while ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
        await asyncio.sleep(1.0)
        # Check if call finished
        remote_participants = list(ctx.room.remote_participants.values())
        if not remote_participants and session.user_state != "speaking":
            break

    # Build transcript
    transcript_lines = []
    for item in session.history.messages:
        role = "Customer" if item.role == "user" else "Agent"
        text = getattr(item, "text_content", None) or str(item.content)
        transcript_lines.append(f"{role}: {text}")
    full_transcript = "\n".join(transcript_lines) or "Call completed."

    # Post completion back to JOY backend
    if tenant_id and order_id:
        await post_telephony_completion(
            order_id=order_id,
            tenant_id=tenant_id,
            call_id=ctx.room.name,
            transcript=full_transcript,
            customer_phone=customer_phone,
            order_confirmed=agent_instance.order_confirmed,
            updated_shipping_address=agent_instance.updated_address,
        )


def start_worker():
    """CLI starter for the background LiveKit worker."""
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="joy-voice-agent",
            ws_url=settings.LIVEKIT_URL,
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
        )
    )


if __name__ == "__main__":
    start_worker()
