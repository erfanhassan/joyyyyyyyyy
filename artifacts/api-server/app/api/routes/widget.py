import logging
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services.widget_api import WidgetAPIService
from app.agents.social_sales import SocialSalesAgent

logger = logging.getLogger("joy.routes.widget")
router = APIRouter(prefix="/widget", tags=["Web Widget"])


class WidgetChatRequest(BaseModel):
    tenant_id: str
    customer_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=4000)
    visitor_token: str = Field(min_length=1, max_length=1000)
    request_id: str = Field(min_length=1, max_length=100)
    customer_name: Optional[str] = Field(default="Web Visitor", max_length=150)


async def authorize_origin(request, db, tenant_id):
    from sqlalchemy import select
    from app.db.models import Tenant
    from urllib.parse import urlsplit
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if not tenant:
        raise HTTPException(404, "Storefront not found.")
    configured = [tenant.domain] + list((tenant.settings or {}).get("widget_origins", []))
    origin = request.headers.get("origin", "")
    if not origin and request.method in ("GET", "HEAD"):
        # Same-origin GET fetches may omit Origin. Normalize Referer rather
        # than comparing a full page URL; the signed visitor is still required.
        referer = urlsplit(request.headers.get("referer", ""))
        if referer.scheme == "https" and referer.netloc and not referer.username and not referer.password:
            origin = f"https://{referer.netloc}"
        elif request.headers.get("sec-fetch-site") == "same-origin":
            origin = f"{request.url.scheme}://{request.url.netloc}"
    allowed = set()
    from app.core.config import settings
    allowed.update(settings.BACKEND_CORS_ORIGINS)
    for value in configured:
        if value:
            parsed = urlsplit(value if "://" in value else f"https://{value}")
            if parsed.scheme == "https" and parsed.netloc:
                allowed.add(f"https://{parsed.netloc.lower()}")
    if origin.rstrip("/").lower() not in allowed:
        raise HTTPException(403, "This website is not authorized to embed this storefront.")
    return tenant


class SessionRequest(BaseModel):
    tenant_id: UUID


@router.post("/session")
async def create_widget_session(req: SessionRequest, request: Request, db: AsyncSession = Depends(get_db)):
    from uuid import uuid4
    from app.core.safety import visitor_token
    from app.services.quotas import consume
    await authorize_origin(request, db, req.tenant_id)
    peer = request.client.host if request.client else "unknown"
    await consume(db, "widget-session", f"{req.tenant_id}:{peer}", 10)
    visitor = str(uuid4())
    return {"customer_id": visitor, "token": visitor_token(str(req.tenant_id), visitor)}


@router.get("/messages")
async def visitor_messages(tenant_id: UUID, request: Request, after: str = "", db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from app.core.safety import verify_visitor
    from app.db.models import Conversation, InteractionLog
    await authorize_origin(request, db, tenant_id)
    identity = verify_visitor(request.headers.get("authorization", "").removeprefix("Bearer "), str(tenant_id))
    conv = (await db.execute(select(Conversation).where(
        Conversation.tenant_id == tenant_id, Conversation.channel == "web_widget",
        Conversation.customer_identifier == identity["visitor"]))).scalars().first()
    if not conv:
        return {"messages": []}
    from app.services.quotas import consume
    await consume(db, "widget-poll", f"{tenant_id}:{identity['visitor']}", 30)
    from datetime import datetime
    statement = select(InteractionLog).where(
        InteractionLog.tenant_id == tenant_id, InteractionLog.conversation_id == conv.id,
        InteractionLog.sender_type == "human_operator")
    if after:
        try:
            timestamp = datetime.fromisoformat(after)
            if timestamp.tzinfo is None:
                raise ValueError()
        except ValueError:
            raise HTTPException(400, "Invalid message cursor.") from None
        statement = statement.where(InteractionLog.created_at > timestamp)
    rows = (await db.execute(statement.order_by(InteractionLog.created_at).limit(100))).scalars().all()
    return {"messages": [{"id": str(row.id), "text": row.message_text, "created_at": row.created_at.isoformat()} for row in rows]}


@router.get("/widget.js")
async def serve_widget_js(request: Request):
    """
    Serves the Universal JavaScript Web Embed Widget (widget.js).
    Merchants copy and paste this single script snippet into Shopify (theme.liquid),
    WooCommerce, or custom storefronts to activate Employee #1.
    """
    # Derive API base URL from incoming request
    base_url = str(request.base_url).rstrip("/")
    script_content = WidgetAPIService.generate_embed_script(base_url)

    return Response(
        content=script_content,
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post("/chat")
async def handle_widget_chat(
    req: WidgetChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Processes incoming messages from the Universal Web Embed Widget.
    Runs Employee #1 (Social Sales Agent) state machine:
    - Intent recognition
    - MCP catalog lookup
    - Capped discount generation
    - Direct checkout link dispatch
    """
    if not req.message.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be empty")

    try:
        tenant_uuid = UUID(req.tenant_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tenant_id '{req.tenant_id}'. Must be a valid UUID.",
        )

    from app.core.safety import verify_visitor
    from app.services.quotas import consume
    await authorize_origin(request, db, tenant_uuid)
    verify_visitor(req.visitor_token, str(tenant_uuid), req.customer_id)
    await consume(db, "widget-visitor", f"{tenant_uuid}:{req.customer_id}", 30)
    await consume(db, "widget-tenant", str(tenant_uuid), 300)
    await consume(db, "widget-daily", str(tenant_uuid), 3000, seconds=86400)

    # 1. Get or create conversation record
    conv = await WidgetAPIService.get_or_create_conversation(
        db=db,
        tenant_id=tenant_uuid,
        customer_identifier=req.customer_id,
        customer_name=req.customer_name,
    )

    # 2. Log customer message
    await WidgetAPIService.log_message(
        db=db,
        tenant_id=tenant_uuid,
        conversation_id=conv.id,
        sender_type="customer",
        message_text=req.message,
    )

    # 3. Durable human takeover check: If human has taken over, do not run AI
    if conv.is_paused_for_human:
        from app.services.hitl_orchestrator import HITLOrchestrator
        await HITLOrchestrator.broadcast_workbench_event(
            tenant_uuid,
            {
                "type": "new_message",
                "conversation_id": str(conv.id),
                "tenant_id": str(tenant_uuid),
                "sender_type": "customer",
                "message_text": req.message,
                "customer_identifier": req.customer_id,
                "channel": "web_widget",
                "is_paused_for_human": True,
            },
        )
        return {
            "status": "paused_for_human",
            "conversation_id": str(conv.id),
            "reply": "A customer support specialist has joined this chat and will be with you shortly.",
            "is_paused_for_human": True,
        }

    # 4. Execute Social Sales Agent
    agent = SocialSalesAgent(db=db)
    initial_state = {
        "tenant_id": str(tenant_uuid),
        "channel": "web_widget",
        "customer_id": req.customer_id,
        "customer_name": req.customer_name,
        "message_text": req.message,
        "comment_id": None,
        "is_private_reply": False,
        "request_id": req.request_id,
        "conversation_id": str(conv.id),
        "store_domain": None,
        "agent_active": True,
        "system_prompt": None,
        "tone_settings": None,
        "intent": None,
        "sentiment_score": 1.0,
        "risk_score": 0.0,
        "is_paused_for_human": False,
        "catalog_results": [],
        "stock_info": None,
        "max_discount_pct": 10,
        "requested_discount_pct": 0,
        "approved_discount_pct": 0,
        "discount_code": None,
        "checkout_url": None,
        "reply_text": "",
        "dispatch_status": "pending",
    }

    final_state = await agent.execute(initial_state)
    reply_text = final_state.get("reply_text", "Thanks for reaching out! How can I assist you further?")

    # 5. Update conversation state & log agent response
    conv.sentiment_score = final_state.get("sentiment_score", 1.0)
    conv.risk_score = final_state.get("risk_score", 0.0)
    if final_state.get("is_paused_for_human"):
        conv.is_paused_for_human = True
    db.add(conv)

    await WidgetAPIService.log_message(
        db=db,
        tenant_id=tenant_uuid,
        conversation_id=conv.id,
        sender_type="agent",
        message_text=reply_text,
        raw_payload={
            "intent": final_state.get("intent"),
            "discount_code": final_state.get("discount_code"),
            "approved_pct": final_state.get("approved_discount_pct"),
            "is_paused_for_human": final_state.get("is_paused_for_human"),
        },
    )

    return {
        "status": "success",
        "conversation_id": str(conv.id),
        "reply": reply_text,
        "discount_code": final_state.get("discount_code"),
        "checkout_url": final_state.get("checkout_url"),
        "is_paused_for_human": final_state.get("is_paused_for_human"),
    }
