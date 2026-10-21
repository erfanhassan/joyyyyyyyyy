import logging
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services.widget_api import WidgetAPIService
from app.agents.social_sales import SocialSalesAgent

logger = logging.getLogger("joy.routes.widget")
router = APIRouter(prefix="/widget", tags=["Web Widget"])


class WidgetChatRequest(BaseModel):
    tenant_id: str
    customer_id: str
    message: str
    customer_name: Optional[str] = "Web Visitor"


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

    # Rate limiting: max 30 messages/minute per visitor
    from app.services.idempotency import get_redis_client
    redis = await get_redis_client()
    if redis:
        try:
            rate_key = f"ratelimit:widget:{tenant_uuid}:{req.customer_id}"
            count = await redis.incr(rate_key)
            if count == 1:
                await redis.expire(rate_key, 60)
            if count > 30:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Message rate limit exceeded. Please wait a moment before sending more messages.",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Redis rate limit check skipped: {e}")

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
        "page_access_token": None,
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
    conv.is_paused_for_human = final_state.get("is_paused_for_human", False)
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
