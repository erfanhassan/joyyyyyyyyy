import json
import logging
from typing import Optional
from fastapi import APIRouter, Request, Header, HTTPException, Query, BackgroundTasks, Response, status
from app.core.config import settings
from app.core.hmac_middleware import verify_meta_signature
from app.services.idempotency import IdempotencyService

logger = logging.getLogger("joy.webhooks.meta")
router = APIRouter(prefix="/meta", tags=["Meta Webhooks"])


async def get_or_create_meta_conversation(db, tenant_uuid, customer_id: str, channel: str, customer_name=None):
    """Resolve a channel-specific conversation for an incoming Meta message or comment."""
    from uuid import uuid4
    from sqlalchemy import select
    from app.db.models import Conversation

    customer_id = str(customer_id)
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.tenant_id == tenant_uuid,
            Conversation.customer_identifier == customer_id,
            Conversation.channel == channel,
        )
        .order_by(Conversation.updated_at.desc())
        .limit(1)
    )
    conversation = result.scalars().first()
    if conversation:
        if customer_name and not conversation.customer_name:
            conversation.customer_name = customer_name
        return conversation

    conversation = Conversation(
        id=uuid4(),
        tenant_id=tenant_uuid,
        channel=channel,
        customer_identifier=customer_id,
        customer_name=customer_name or f"Customer ({customer_id[:6]})",
        sentiment_score=1.0,
        risk_score=0.0,
        is_paused_for_human=False,
    )
    db.add(conversation)
    await db.flush()
    return conversation


async def process_meta_background(payload: dict, tenant_id: str, event_id: str):
    """
    Asynchronous background handler for Meta webhooks (comments, DMs, private replies).
    Builds the complete production path:
    Verified webhook → identify business/Page → save event → check human takeover →
    run SocialSalesAgent → dispatch with Page credentials → record delivery result.
    """
    logger.info(f"[Meta Background Worker] Processing event {event_id} for tenant {tenant_id}")
    from uuid import UUID
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.db.models import Tenant, TenantIntegration, Conversation, InteractionLog, AgentConfig
    from app.core.security import decrypt_token
    from app.agents.social_sales import SocialSalesAgent
    from app.services.hitl_orchestrator import HITLOrchestrator

    async with AsyncSessionLocal() as db:
        if tenant_id == "default":
            raise RuntimeError("Durable processing requires a resolved workspace.")
        db.info["tenant_id"] = tenant_id
        try:
            # 1. Identify Tenant and TenantIntegration
            integration = None
            tenant_uuid = None

            if tenant_id and tenant_id != "default":
                try:
                    tenant_uuid = UUID(tenant_id)
                    int_stmt = select(TenantIntegration).where(
                        TenantIntegration.tenant_id == tenant_uuid,
                        TenantIntegration.provider == "meta",
                        TenantIntegration.is_active == True,
                    ).limit(1)
                    res = await db.execute(int_stmt)
                    integration = res.scalars().first()
                except ValueError:
                    pass

            # If not resolved via route parameter, match Page ID / Instagram ID from payload
            if not integration:
                entries = payload.get("entry", [])
                for entry in entries:
                    entry_id = str(entry.get("id", ""))
                    if entry_id:
                        int_stmt = select(TenantIntegration).where(
                            TenantIntegration.provider == "meta",
                            TenantIntegration.is_active == True,
                        )
                        res = await db.execute(int_stmt)
                        all_meta = res.scalars().all()
                        for item in all_meta:
                            settings_dict = item.settings or {}
                            if (
                                str(settings_dict.get("page_id")) == entry_id
                                or str(settings_dict.get("instagram_account_id")) == entry_id
                            ):
                                integration = item
                                tenant_uuid = item.tenant_id
                                break
                    if integration:
                        break

            from app.services.webhook_jobs import resolve_integration
            integration = await resolve_integration(db, "meta", payload.get("entry", [{}])[0].get("id"), tenant_id)
            tenant_uuid = integration.tenant_id

            if not integration or not tenant_uuid:
                raise RuntimeError("No active matching Meta integration.")

            # 2. Decrypt Page Access Token
            page_token = None
            if integration.access_token_encrypted:
                try:
                    page_token = decrypt_token(integration.access_token_encrypted)
                except Exception as e:
                    logger.error(f"Failed to decrypt Meta access token: {e}")
                    raise RuntimeError("Page credentials cannot be decrypted.") from None

            page_settings = integration.settings or {}
            ig_account_id = str(page_settings.get("instagram_account_id", ""))
            fb_page_id = str(page_settings.get("page_id", ""))

            # 3. Process Entries (Batched Payloads)
            entries = payload.get("entry", [])
            for entry in entries:
                # 3A. Handle Direct Messages (DMs)
                messaging_events = entry.get("messaging", [])
                for msg_item in messaging_events:
                    sender = msg_item.get("sender", {})
                    recipient = msg_item.get("recipient", {})
                    message = msg_item.get("message", {})

                    # Skip echo messages (messages sent by the page/agent itself)
                    if message.get("is_echo"):
                        continue

                    customer_id = sender.get("id")
                    recipient_id = recipient.get("id")
                    message_text = message.get("text")
                    if not customer_id or not message_text:
                        continue

                    channel = "instagram" if (recipient_id == ig_account_id or customer_id == ig_account_id) else "facebook"

                    conv = await get_or_create_meta_conversation(
                        db, tenant_uuid, customer_id, channel,
                    )

                    # Save incoming customer interaction log
                    cust_log = InteractionLog(
                        tenant_id=tenant_uuid,
                        conversation_id=conv.id,
                        sender_type="customer",
                        message_text=message_text,
                        raw_payload=msg_item,
                    )
                    db.add(cust_log)
                    await db.commit()

                    # Durable Takeover Check: if human has taken over, do not run AI
                    if conv.is_paused_for_human:
                        logger.info(f"Conversation {conv.id} is paused for human takeover. Skipping autonomous AI reply.")
                        await HITLOrchestrator.broadcast_workbench_event(
                            tenant_uuid,
                            {
                                "type": "new_message",
                                "conversation_id": str(conv.id),
                                "tenant_id": str(tenant_uuid),
                                "sender_type": "customer",
                                "message_text": message_text,
                                "customer_identifier": customer_id,
                                "channel": channel,
                                "is_paused_for_human": True,
                            },
                        )
                        continue

                    # Execute SocialSalesAgent
                    agent = SocialSalesAgent(db=db)
                    initial_state = {
                        "tenant_id": str(tenant_uuid),
                        "channel": channel,
                        "customer_id": customer_id,
                        "customer_name": conv.customer_name,
                        "message_text": message_text,
                        "comment_id": None,
                        "is_private_reply": False,
                        "integration_id": str(integration.id),
                        "request_id": event_id,
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

                    # Save outgoing agent interaction log
                    if final_state.get("reply_text"):
                        agent_log = InteractionLog(
                            tenant_id=tenant_uuid,
                            conversation_id=conv.id,
                            sender_type="agent",
                            message_text=final_state["reply_text"],
                            raw_payload=__import__("app.core.safety", fromlist=["redact"]).redact(final_state),
                        )
                        db.add(agent_log)
                        await db.commit()

                # 3B. Handle Feed & Post/Reel Comments
                changes_events = entry.get("changes", [])
                for change in changes_events:
                    val = change.get("value", {})
                    is_comment = (
                        change.get("field") == "comments"
                        or val.get("item") == "comment"
                    )
                    if is_comment and val.get("verb") in ("add", None):
                        comment_id = val.get("comment_id") or val.get("id")
                        comment_id = str(comment_id) if comment_id is not None else None
                        comment_msg = val.get("message") or val.get("text")
                        sender = val.get("from") or {}
                        sender_id = sender.get("id")
                        sender_id = str(sender_id) if sender_id is not None else None
                        sender_name = sender.get("name") or sender.get("username")

                        # Don't reply to comments made by the Page itself
                        if not comment_id or not comment_msg or sender_id in (fb_page_id, ig_account_id):
                            continue

                        channel = "instagram" if entry.get("id") == ig_account_id else "facebook"

                        # Comments can arrive without a DM event in the same webhook payload.
                        conv = await get_or_create_meta_conversation(
                            db, tenant_uuid, sender_id, channel, sender_name,
                        )

                        db.add(InteractionLog(
                            tenant_id=tenant_uuid,
                            conversation_id=conv.id,
                            sender_type="customer",
                            message_text=comment_msg,
                            raw_payload=change,
                        ))
                        await db.commit()

                        await HITLOrchestrator.broadcast_workbench_event(
                            tenant_uuid,
                            {
                                "type": "new_message",
                                "conversation_id": str(conv.id),
                                "tenant_id": str(tenant_uuid),
                                "sender_type": "customer",
                                "message_text": comment_msg,
                                "customer_identifier": sender_id,
                                "channel": channel,
                                "is_paused_for_human": conv.is_paused_for_human,
                                "is_comment": True,
                            },
                        )
                        if conv.is_paused_for_human:
                            continue

                        agent = SocialSalesAgent(db=db)
                        initial_state = {
                            "tenant_id": str(tenant_uuid),
                            "channel": channel,
                            "customer_id": sender_id,
                            "customer_name": sender_name,
                            "message_text": comment_msg,
                            "comment_id": comment_id,
                            "is_private_reply": True,
                            "integration_id": str(integration.id),
                            "request_id": event_id,
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
                        if final_state.get("reply_text"):
                            agent_log = InteractionLog(
                                tenant_id=tenant_uuid,
                                conversation_id=conv.id,
                                sender_type="agent",
                                message_text=final_state["reply_text"],
                                raw_payload=__import__("app.core.safety", fromlist=["redact"]).redact(final_state),
                            )
                            db.add(agent_log)
                            await db.commit()

            # Completion belongs to the durable inbox worker, not Redis.
            logger.info(f"Successfully processed Meta event {event_id} for tenant {tenant_uuid}")

        except Exception as e:
            logger.error(f"Error processing Meta background webhook {event_id}: {e}", exc_info=True)
            raise


@router.get("")
@router.get("/{tenant_id}")
async def verify_meta_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    tenant_id: str = "default",
):
    """
    Meta Webhook Hub Challenge verification endpoint.
    Used by Facebook and Instagram to verify webhook endpoint ownership.
    """
    expected_token = settings.META_VERIFY_TOKEN

    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        logger.info(f"Meta challenge verification successful for tenant {tenant_id}")
        return Response(content=hub_challenge, media_type="text/plain", status_code=200)

    logger.warning("Meta challenge verification failed")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Verification token mismatch",
    )


@router.post("")
@router.post("/{tenant_id}")
async def receive_meta_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    tenant_id: str = "default",
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
):
    """
    Ingest Facebook & Instagram comments, DMs, and post engagement webhooks.
    Enforces HMAC-SHA256 signature verification and Redis 24h deduplication.
    Responds within 1,500ms.
    """
    raw_body = await request.body()
    if not settings.META_APP_SECRET:
        raise HTTPException(503, "Meta webhook verification is not configured.")

    # 1. HMAC Signature Verification
    if settings.META_APP_SECRET:
        is_valid = verify_meta_signature(raw_body, x_hub_signature_256, settings.META_APP_SECRET)
        if not is_valid:
            logger.warning(f"Invalid Meta HMAC signature for tenant {tenant_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid HMAC signature",
            )

    # 2. Parse Payload
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse Meta JSON payload: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON")

    if payload.get("object") == "whatsapp_business_account":
        from app.services.whatsapp import enqueue_whatsapp
        accepted = await enqueue_whatsapp(payload, tenant_id)
        return {"status": "queued", "accepted_events": accepted}

    # 3. Extract Deduplication Event ID
    # Meta payloads typically have entry[0].id or entry[0].time or messaging[0].message.mid
    event_id = None
    entries = payload.get("entry", [])
    if entries and isinstance(entries, list):
        first_entry = entries[0]
        # Check for direct messaging MID
        messaging = first_entry.get("messaging", [])
        if messaging and isinstance(messaging, list):
            event_id = messaging[0].get("message", {}).get("mid")
        # Check for changes (comments / feeds)
        if not event_id:
            changes = first_entry.get("changes", [])
            if changes and isinstance(changes, list):
                event_id = changes[0].get("value", {}).get("comment_id") or changes[0].get("value", {}).get("post_id")
        # Fallback to entry id + timestamp
        if not event_id:
            event_id = f"{first_entry.get('id', 'evt')}_{first_entry.get('time', '0')}"
    
    if not event_id:
        import hashlib
        event_id = hashlib.sha256(raw_body).hexdigest()[:16]

    from app.services.webhook_jobs import enqueue_meta
    accepted = await enqueue_meta(payload, tenant_id)

    # 6. Immediate HTTP 200 OK
    return {
        "status": "received", "event_id": event_id, "tenant_id": tenant_id,
        "automation_status": "queued", "accepted_events": accepted,
    }
