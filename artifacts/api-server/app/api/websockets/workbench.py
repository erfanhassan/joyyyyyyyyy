import asyncio
import json
import logging
from typing import Dict, Set, Optional, List
from uuid import UUID
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db, AsyncSessionLocal
from app.db.models import Conversation, InteractionLog
from app.services.idempotency import get_redis_client
from app.services.hitl_orchestrator import HITLOrchestrator

logger = logging.getLogger("joy.websockets.workbench")
router = APIRouter(tags=["Operator Workbench & WebSockets"])


class ConnectionManager:
    """
    Manages active WebSocket connections for Operator Workbench.
    Bridges Redis Pub/Sub channels to connected browsers in real-time.
    """

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.pubsub_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, tenant_id: str):
        await websocket.accept()
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = set()
        self.active_connections[tenant_id].add(websocket)
        logger.info(f"WebSocket client connected for tenant {tenant_id}. Total: {len(self.active_connections[tenant_id])}")

        # Start Redis subscriber for this tenant if not running
        if tenant_id not in self.pubsub_tasks or self.pubsub_tasks[tenant_id].done():
            self.pubsub_tasks[tenant_id] = asyncio.create_task(self._listen_redis_pubsub(tenant_id))

    def disconnect(self, websocket: WebSocket, tenant_id: str):
        if tenant_id in self.active_connections:
            self.active_connections[tenant_id].discard(websocket)
            if not self.active_connections[tenant_id]:
                del self.active_connections[tenant_id]
                # Cancel background pubsub task if no active connections
                if tenant_id in self.pubsub_tasks:
                    self.pubsub_tasks[tenant_id].cancel()
                    del self.pubsub_tasks[tenant_id]
        logger.info(f"WebSocket client disconnected for tenant {tenant_id}")

    async def broadcast_to_tenant(self, tenant_id: str, message: dict):
        connections = self.active_connections.get(tenant_id, set()).copy()
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to client: {e}")
                self.disconnect(connection, tenant_id)

    async def _listen_redis_pubsub(self, tenant_id: str):
        """Background task listening on Redis Pub/Sub channel and forwarding to connected sockets."""
        channel_name = f"joy:workbench:{tenant_id}"
        try:
            r = get_redis_client()
            pubsub = r.pubsub()
            await pubsub.subscribe(channel_name)
            logger.info(f"Subscribed to Redis channel: {channel_name}")

            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        raw_data = message["data"]
                        try:
                            data = json.loads(raw_data)
                            await self.broadcast_to_tenant(tenant_id, data)
                        except Exception as e:
                            logger.error(f"Error parsing pubsub message: {e}")
            except asyncio.CancelledError:
                logger.info(f"Pubsub listener for {channel_name} cancelled")
            finally:
                try:
                    await pubsub.unsubscribe(channel_name)
                    await pubsub.close()
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Could not connect Redis Pub/Sub listener for {channel_name}: {e}")


manager = ConnectionManager()


# ==========================================
# WebSocket Endpoint
# ==========================================
@router.websocket("/ws/workbench/{tenant_id}")
async def operator_workbench_ws(websocket: WebSocket, tenant_id: str):
    """
    Real-time Operator Workbench WebSocket:
    - Streams live customer sentiment, risk alerts, and message feeds.
    - Receives human operator takeover commands and message overrides.
    """
    await manager.connect(websocket, tenant_id)
    try:
        # Send initial connection acknowledgment & conversation snapshot
        conv_snapshot = []
        try:
            tenant_uuid = UUID(tenant_id)
            async with AsyncSessionLocal() as db:
                stmt = (
                    select(Conversation)
                    .where(Conversation.tenant_id == tenant_uuid)
                    .order_by(desc(Conversation.updated_at))
                    .limit(20)
                )
                res = await db.execute(stmt)
                conversations = res.scalars().all()

                conv_snapshot = [
                    {
                        "id": str(c.id),
                        "channel": c.channel,
                        "customer_name": c.customer_name or "Anonymous Customer",
                        "customer_identifier": c.customer_identifier,
                        "sentiment_score": c.sentiment_score,
                        "risk_score": c.risk_score,
                        "is_paused_for_human": c.is_paused_for_human,
                        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                    }
                    for c in conversations
                ]
        except Exception as e:
            logger.debug(f"Initial conversation snapshot skipped: {e}")

        await websocket.send_json({
            "type": "connected",
            "tenant_id": tenant_id,
            "conversations": conv_snapshot,
            "message": "Connected to JOY Operator Workbench real-time stream.",
        })

        # Listen for messages from client
        while True:
            raw_text = await websocket.receive_text()
            try:
                msg = json.loads(raw_text)
                action = msg.get("action")

                # Resolve tenant UUID safely
                t_uuid = None
                try:
                    t_uuid = UUID(msg.get("tenant_id")) if msg.get("tenant_id") else UUID(tenant_id)
                except (ValueError, TypeError):
                    t_uuid = None

                if action == "ping":
                    await websocket.send_json({"type": "pong"})

                elif action == "takeover":
                    # 1-Click Human Takeover Toggle
                    conv_id = UUID(msg["conversation_id"])
                    take_over = bool(msg.get("take_over", True))
                    operator_name = msg.get("operator_name", "Operator")
                    result = await HITLOrchestrator.toggle_human_takeover(
                        tenant_id=t_uuid or conv_id,
                        conversation_id=conv_id,
                        take_over=take_over,
                        operator_name=operator_name,
                    )
                    await websocket.send_json({"type": "takeover_ack", "result": result})

                elif action == "send_reply":
                    # Human Operator Message Overwrite
                    conv_id = UUID(msg["conversation_id"])
                    text = msg.get("text", "")
                    operator_name = msg.get("operator_name", "Operator")
                    result = await HITLOrchestrator.submit_human_reply(
                        tenant_id=t_uuid or conv_id,
                        conversation_id=conv_id,
                        message_text=text,
                        operator_name=operator_name,
                    )
                    await websocket.send_json({"type": "reply_ack", "result": result})

                elif action == "edit_draft":
                    # Live Draft Editing
                    conv_id = UUID(msg["conversation_id"])
                    draft = msg.get("draft", "")
                    result = await HITLOrchestrator.update_ai_draft(
                        tenant_id=t_uuid or conv_id,
                        conversation_id=conv_id,
                        draft_text=draft,
                    )
                    await websocket.send_json({"type": "draft_ack", "result": result})

                elif action == "get_conversations":
                    conv_list = []
                    if t_uuid:
                        try:
                            async with AsyncSessionLocal() as db:
                                stmt = (
                                    select(Conversation)
                                    .where(Conversation.tenant_id == t_uuid)
                                    .order_by(desc(Conversation.updated_at))
                                    .limit(20)
                                )
                                res = await db.execute(stmt)
                                convs = res.scalars().all()
                                conv_list = [
                                    {
                                        "id": str(c.id),
                                        "channel": c.channel,
                                        "customer_name": c.customer_name,
                                        "customer_identifier": c.customer_identifier,
                                        "sentiment_score": c.sentiment_score,
                                        "risk_score": c.risk_score,
                                        "is_paused_for_human": c.is_paused_for_human,
                                        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                                    }
                                    for c in convs
                                ]
                        except Exception as e:
                            logger.debug(f"get_conversations error: {e}")
                    await websocket.send_json({"type": "conversation_list", "conversations": conv_list})

            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON format."})
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}", exc_info=True)
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        manager.disconnect(websocket, tenant_id)


# ==========================================
# REST Endpoints for Operator Desk
# ==========================================
class TakeoverRequest(BaseModel):
    tenant_id: UUID
    conversation_id: UUID
    take_over: bool
    operator_name: Optional[str] = "Operator"


class HumanReplyRequest(BaseModel):
    tenant_id: UUID
    conversation_id: UUID
    message_text: str
    operator_name: Optional[str] = "Operator"


class WhatsAppConsentRequest(BaseModel):
    tenant_id: UUID
    conversation_id: UUID
    opted_in: bool
    source: Optional[str] = Field(None, max_length=255)


class WhatsAppTemplateSendRequest(BaseModel):
    tenant_id: UUID
    conversation_id: UUID
    name: str = Field(..., min_length=1, max_length=512)
    language: str = Field(..., min_length=1, max_length=32)
    variables: List[str] = Field(default_factory=list, max_length=20)


class SimulateRiskRequest(BaseModel):
    tenant_id: UUID
    customer_message: str
    channel: Optional[str] = "instagram"
    customer_name: Optional[str] = "Angry Customer"
    customer_identifier: Optional[str] = "user_999"


@router.get("/workbench/conversations/{tenant_id}")
async def list_workbench_conversations(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Fetches active conversations with sentiment and takeover indicators."""
    stmt = (
        select(Conversation)
        .where(Conversation.tenant_id == tenant_id)
        .order_by(desc(Conversation.updated_at))
        .limit(50)
    )
    res = await db.execute(stmt)
    convs = res.scalars().all()

    items = []
    for c in convs:
        # Determine color badge per DESIGN_BRIEF.md
        if c.risk_score > 0.70:
            badge = "crimson_alert"   # #E11D48
        elif c.risk_score >= 0.40:
            badge = "yellow_warning"  # #F59E0B
        else:
            badge = "green_safe"      # #059669

        items.append({
            "id": str(c.id),
            "tenant_id": str(c.tenant_id),
            "channel": c.channel,
            "customer_name": c.customer_name or "Anonymous",
            "customer_identifier": c.customer_identifier,
            "sentiment_score": c.sentiment_score,
            "risk_score": c.risk_score,
            "risk_badge": badge,
            "is_paused_for_human": c.is_paused_for_human,
            "whatsapp_opt_in": c.whatsapp_opt_in,
            "whatsapp_opt_in_updated_at": c.whatsapp_opt_in_updated_at.isoformat()
            if c.whatsapp_opt_in_updated_at else None,
            "whatsapp_opt_in_source": c.whatsapp_opt_in_source,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        })
    return {"conversations": items}


@router.get("/workbench/conversations/{tenant_id}/{conversation_id}/logs")
async def get_conversation_logs(
    tenant_id: UUID,
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Fetches full interaction message logs for a specific conversation."""
    stmt = (
        select(InteractionLog)
        .where(
            InteractionLog.tenant_id == tenant_id,
            InteractionLog.conversation_id == conversation_id,
        )
        .order_by(InteractionLog.created_at.asc())
    )
    res = await db.execute(stmt)
    logs = res.scalars().all()
    return {
        "conversation_id": str(conversation_id),
        "messages": [
            {
                "id": str(l.id),
                "sender_type": l.sender_type,
                "message_text": l.message_text,
                "created_at": l.created_at.isoformat() if l.created_at else None,
                "raw_payload": l.raw_payload,
            }
            for l in logs
        ],
    }


@router.post("/workbench/takeover")
async def execute_takeover(
    req: TakeoverRequest,
    db: AsyncSession = Depends(get_db),
):
    """1-Click Crimson Takeover toggle endpoint."""
    return await HITLOrchestrator.toggle_human_takeover(
        tenant_id=req.tenant_id,
        conversation_id=req.conversation_id,
        take_over=req.take_over,
        operator_name=req.operator_name or "Operator",
        db=db,
    )


@router.post("/workbench/reply")
async def send_human_reply(
    req: HumanReplyRequest,
    db: AsyncSession = Depends(get_db),
):
    """Submits human operator reply and transmits it to customer channel."""
    return await HITLOrchestrator.submit_human_reply(
        tenant_id=req.tenant_id,
        conversation_id=req.conversation_id,
        message_text=req.message_text,
        operator_name=req.operator_name or "Operator",
        db=db,
    )


@router.post("/workbench/whatsapp/consent")
async def update_whatsapp_consent(
    req: WhatsAppConsentRequest,
    db: AsyncSession = Depends(get_db),
):
    """Record or revoke a workspace operator's recorded customer opt-in."""
    from datetime import datetime, timezone

    if req.opted_in and not (req.source and req.source.strip()):
        raise HTTPException(400, "Record where the customer gave opt-in before enabling template messages.")
    conversation = (await db.execute(select(Conversation).where(
        Conversation.tenant_id == req.tenant_id,
        Conversation.id == req.conversation_id,
        Conversation.channel == "whatsapp",
    ))).scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "WhatsApp conversation not found.")

    source = req.source.strip()[:255] if req.opted_in and req.source else None
    conversation.whatsapp_opt_in = req.opted_in
    conversation.whatsapp_opt_in_updated_at = datetime.now(timezone.utc)
    conversation.whatsapp_opt_in_source = source
    consent_log = InteractionLog(
        tenant_id=req.tenant_id,
        conversation_id=conversation.id,
        sender_type="human_operator",
        message_text=("WhatsApp customer opt-in recorded" if req.opted_in
                      else "WhatsApp customer opt-in revoked"),
        raw_payload={
            "event_type": "whatsapp_consent",
            "opted_in": req.opted_in,
            "source": source,
        },
    )
    db.add(consent_log)
    await db.flush()
    message_id = str(consent_log.id)
    await db.commit()
    await HITLOrchestrator.broadcast_workbench_event(req.tenant_id, {
        "type": "new_message",
        "tenant_id": str(req.tenant_id),
        "conversation_id": str(conversation.id),
        "sender_type": "human_operator",
        "message_text": ("WhatsApp customer opt-in recorded" if req.opted_in
                         else "WhatsApp customer opt-in revoked"),
        "message_id": message_id,
    })
    return {
        "opted_in": conversation.whatsapp_opt_in,
        "updated_at": conversation.whatsapp_opt_in_updated_at.isoformat(),
        "source": conversation.whatsapp_opt_in_source,
        "message_id": message_id,
    }


@router.get("/workbench/conversations/{tenant_id}/{conversation_id}/whatsapp/templates")
async def list_whatsapp_templates(
    tenant_id: UUID,
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    conversation = (await db.execute(select(Conversation).where(
        Conversation.tenant_id == tenant_id,
        Conversation.id == conversation_id,
        Conversation.channel == "whatsapp",
    ))).scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "WhatsApp conversation not found.")
    from app.services.whatsapp import WhatsAppService
    from app.services.meta_credentials import MetaCredentialError
    try:
        templates = await WhatsAppService.approved_templates(db, tenant_id)
    except MetaCredentialError as error:
        await db.commit()
        raise HTTPException(502, str(error)) from None
    except Exception as error:
        raise HTTPException(502, str(error)) from None
    return {"templates": templates}


@router.post("/workbench/whatsapp/template")
async def send_whatsapp_template(
    req: WhatsAppTemplateSendRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a freshly verified, approved template only after recorded customer opt-in."""
    conversation = (await db.execute(select(Conversation).where(
        Conversation.tenant_id == req.tenant_id,
        Conversation.id == req.conversation_id,
        Conversation.channel == "whatsapp",
    ))).scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "WhatsApp conversation not found.")

    from app.services.whatsapp import WhatsAppService
    from app.services.meta_credentials import MetaCredentialError
    try:
        result, template = await WhatsAppService.send_template(
            db, conversation, req.name, req.language, req.variables)
    except PermissionError as error:
        raise HTTPException(403, str(error)) from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    except MetaCredentialError as error:
        await db.commit()
        raise HTTPException(502, str(error)) from None
    except Exception as error:
        raise HTTPException(502, str(error)) from None

    provider_message_id = result["messages"][0]["id"]
    summary = f"WhatsApp template sent: {template['name']} ({template['language']})"
    log_entry = InteractionLog(
        tenant_id=req.tenant_id,
        conversation_id=conversation.id,
        sender_type="human_operator",
        message_text=summary,
        raw_payload={
            "dispatch_status": "dispatched_whatsapp_template",
            "provider_message_id": provider_message_id,
            "template_name": template["name"],
            "template_language": template["language"],
            "template_variables": req.variables,
        },
    )
    db.add(log_entry)
    await db.commit()
    await HITLOrchestrator.broadcast_workbench_event(req.tenant_id, {
        "type": "new_message",
        "tenant_id": str(req.tenant_id),
        "conversation_id": str(conversation.id),
        "sender_type": "human_operator",
        "message_text": summary,
        "message_id": str(log_entry.id),
    })
    return {
        "status": "accepted",
        "provider_message_id": provider_message_id,
        "message_id": str(log_entry.id),
        "message_text": summary,
    }


@router.post("/workbench/simulate-sentiment-alert")
async def simulate_sentiment_alert(
    req: SimulateRiskRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Test/Simulation endpoint to verify HITL interrupt, state pausing,
    and Redis Pub/Sub broadcast for angry customer inputs.
    """
    # 1. Create or fetch conversation
    conv_stmt = select(Conversation).where(
        Conversation.tenant_id == req.tenant_id,
        Conversation.customer_identifier == req.customer_identifier,
    )
    conv_res = await db.execute(conv_stmt)
    conv = conv_res.scalars().first()
    if not conv:
        conv = Conversation(
            tenant_id=req.tenant_id,
            channel=req.channel,
            customer_name=req.customer_name,
            customer_identifier=req.customer_identifier,
            sentiment_score=1.0,
            risk_score=0.0,
            is_paused_for_human=False,
        )
        db.add(conv)
        await db.flush()

    # 2. Evaluate and Intercept
    result = await HITLOrchestrator.evaluate_and_intercept(
        tenant_id=req.tenant_id,
        conversation_id=conv.id,
        customer_message=req.customer_message,
        db=db,
    )

    return {
        "conversation_id": str(conv.id),
        "evaluation": result,
    }
