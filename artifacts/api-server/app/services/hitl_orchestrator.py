import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Conversation, InteractionLog
from app.services.idempotency import get_redis_client
from app.services.sentiment_service import SentimentService
from app.services.postgres_checkpointer import PostgreSQLSaver
from app.services.meta_api import MetaAPIClient

logger = logging.getLogger("joy.services.hitl")


class HITLOrchestrator:
    """
    Human-In-The-Loop (HITL) Sentiment Interrupt & Takeover Orchestrator:
    - Automatically halts AI autonomy if customer sentiment risk score R > 0.70 or anger keywords detected.
    - Preserves complete conversational state in PostgreSQL checkpointer.
    - Emits real-time alerts over Redis Pub/Sub to the Operator Workbench WebSocket.
    - Facilitates 1-click human operator takeover and live draft editing / message overwrites.
    """

    _checkpointer: Optional[PostgreSQLSaver] = None

    @classmethod
    def get_checkpointer(cls) -> PostgreSQLSaver:
        if cls._checkpointer is None:
            cls._checkpointer = PostgreSQLSaver()
        return cls._checkpointer

    @classmethod
    async def evaluate_and_intercept(
        cls,
        tenant_id: UUID,
        conversation_id: UUID,
        customer_message: str,
        db: Optional[AsyncSession] = None,
        pending_ai_draft: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluates incoming customer message for risk.
        If risk > 0.70 or critical anger/refund keywords detected:
        1. Halts AI generation.
        2. Sets is_paused_for_human = True on Conversation.
        3. Preserves state in PostgreSQL checkpointer.
        4. Broadcasts WebSocket alert over Redis Pub/Sub to Operator Workbench.
        """
        if db is None:
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                return await cls.evaluate_and_intercept(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    customer_message=customer_message,
                    db=session,
                    pending_ai_draft=pending_ai_draft,
                )

        # 1. Evaluate Sentiment & Risk
        analysis = await SentimentService.evaluate_sentiment(customer_message)
        sentiment_score = analysis["sentiment_score"]
        risk_score = analysis["risk_score"]
        is_breached = analysis["is_risk_breached"]

        # 2. Fetch Conversation
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
        )
        res = await db.execute(stmt)
        conversation = res.scalars().first()

        if conversation:
            conversation.sentiment_score = sentiment_score
            conversation.risk_score = risk_score
            conversation.updated_at = datetime.now(timezone.utc)

        if is_breached:
            logger.warning(
                f"[HITL Triggered] Risk threshold breached (R={risk_score} > 0.70) "
                f"for conversation {conversation_id}: {analysis['reason']}"
            )
            if conversation:
                conversation.is_paused_for_human = True

            # Save state into PostgreSQL Checkpointer
            checkpointer = cls.get_checkpointer()
            checkpoint_config = {
                "configurable": {
                    "thread_id": str(conversation_id),
                    "checkpoint_ns": "hitl_intercept",
                    "checkpoint_id": f"chk_{int(datetime.now(timezone.utc).timestamp())}",
                }
            }
            values_dict = {
                "customer_message": customer_message,
                "sentiment_score": sentiment_score,
                "risk_score": risk_score,
                "flagged_keywords": analysis["flagged_keywords"],
                "is_paused_for_human": True,
                "pending_ai_draft": pending_ai_draft,
            }
            channel_versions = {k: 1 for k in values_dict.keys()}
            checkpoint_state = {
                "id": checkpoint_config["configurable"]["checkpoint_id"],
                "v": 1,
                "ts": datetime.now(timezone.utc).isoformat(),
                "channel_values": values_dict,
                "channel_versions": channel_versions,
                "versions_seen": {},
            }
            try:
                checkpointer.put(
                    config=checkpoint_config,
                    checkpoint=checkpoint_state,  # type: ignore[arg-type]
                    metadata={"source": "hitl_interceptor", "reason": analysis["reason"]},
                    new_versions=channel_versions,
                )
            except Exception as e:
                logger.error(f"Failed to persist state in PostgreSQLSaver: {e}", exc_info=True)

            # Log customer message to DB
            cust_log = InteractionLog(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                sender_type="customer",
                message_text=customer_message,
                raw_payload={"sentiment": analysis},
            )
            db.add(cust_log)
            if conversation:
                db.add(conversation)
            await db.commit()

            # Broadcast HITL Alert via Redis Pub/Sub
            alert_payload = {
                "type": "hitl_alert",
                "conversation_id": str(conversation_id),
                "tenant_id": str(tenant_id),
                "customer_name": conversation.customer_name if conversation else "Customer",
                "customer_identifier": conversation.customer_identifier if conversation else "Unknown",
                "channel": conversation.channel if conversation else "web_widget",
                "sentiment_score": sentiment_score,
                "risk_score": risk_score,
                "risk_badge": analysis["risk_badge"],
                "flagged_keywords": analysis["flagged_keywords"],
                "customer_message": customer_message,
                "pending_ai_draft": pending_ai_draft or "Pending manager escalation review.",
                "is_paused_for_human": True,
                "reason": analysis["reason"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await cls.broadcast_workbench_event(tenant_id, alert_payload)

            handover_msg = (
                "I understand your concern and want to make sure this is handled properly. "
                "I am connecting you with one of our store managers right now."
            )
            return {
                "halt_ai": True,
                "sentiment_score": sentiment_score,
                "risk_score": risk_score,
                "risk_badge": analysis["risk_badge"],
                "flagged_keywords": analysis["flagged_keywords"],
                "reason": analysis["reason"],
                "handover_message": handover_msg,
            }

        # Safe - AI autonomy continues
        if conversation:
            db.add(conversation)
        await db.commit()

        return {
            "halt_ai": False,
            "sentiment_score": sentiment_score,
            "risk_score": risk_score,
            "risk_badge": analysis["risk_badge"],
            "flagged_keywords": [],
            "reason": analysis["reason"],
        }

    @classmethod
    async def toggle_human_takeover(
        cls,
        tenant_id: UUID,
        conversation_id: UUID,
        take_over: bool,
        operator_name: str = "Operator",
        db: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        """
        1-Click Crimson Takeover toggle:
        - If take_over is True: Halts autonomous AI, enables human direct chatting.
        - If take_over is False: Resumes autonomous AI employee.
        """
        if db is None:
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                return await cls.toggle_human_takeover(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    take_over=take_over,
                    operator_name=operator_name,
                    db=session,
                )

        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
        )
        res = await db.execute(stmt)
        conv = res.scalars().first()
        if not conv:
            return {"status": "error", "message": "Conversation not found"}

        conv.is_paused_for_human = take_over
        conv.updated_at = datetime.now(timezone.utc)
        db.add(conv)

        # Log action in interaction logs
        action_text = f"[Operator Action] {operator_name} {'took over conversation' if take_over else 'resumed autonomous AI'}."
        action_log = InteractionLog(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            sender_type="human_operator",
            message_text=action_text,
            raw_payload={"operator_name": operator_name, "take_over": take_over},
        )
        db.add(action_log)
        await db.commit()

        # Broadcast update to Redis Pub/Sub
        event = {
            "type": "takeover_toggled",
            "conversation_id": str(conversation_id),
            "tenant_id": str(tenant_id),
            "is_paused_for_human": take_over,
            "operator_name": operator_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await cls.broadcast_workbench_event(tenant_id, event)

        logger.info(f"Takeover toggled for conversation {conversation_id} to {take_over} by {operator_name}")
        return {
            "status": "success",
            "conversation_id": str(conversation_id),
            "is_paused_for_human": take_over,
            "operator_name": operator_name,
        }

    @classmethod
    async def submit_human_reply(
        cls,
        tenant_id: UUID,
        conversation_id: UUID,
        message_text: str,
        operator_name: str = "Operator",
        db: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        """
        Submits human operator reply overwriting or replacing AI output.
        Logs to database and dispatches to appropriate storefront/messaging channel.
        """
        if db is None:
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                return await cls.submit_human_reply(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    message_text=message_text,
                    operator_name=operator_name,
                    db=session,
                )

        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
        )
        res = await db.execute(stmt)
        conv = res.scalars().first()
        if not conv:
            return {"status": "error", "message": "Conversation not found"}

        # 1. Log human message
        log_entry = InteractionLog(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            sender_type="human_operator",
            message_text=message_text,
            raw_payload={"operator_name": operator_name},
        )
        db.add(log_entry)
        conv.updated_at = datetime.now(timezone.utc)
        db.add(conv)
        await db.commit()

        # 2. Resolve merchant Page credentials for Meta dispatch
        from app.db.models import TenantIntegration
        from app.core.security import decrypt_token

        page_token = None
        meta_int = None
        try:
            int_stmt = select(TenantIntegration).where(
                TenantIntegration.tenant_id == tenant_id,
                TenantIntegration.provider == "meta",
                TenantIntegration.is_active == True,
            ).limit(1)
            int_res = await db.execute(int_stmt)
            meta_int = int_res.scalars().first()
            if meta_int and meta_int.access_token_encrypted:
                page_token = decrypt_token(meta_int.access_token_encrypted)
        except Exception as e:
            logger.warning(f"Failed to load Page token for human reply: {e}")

        # 3. Dispatch to external channel
        dispatch_status = "saved_locally"
        dispatch_error = None
        provider_response = None

        if conv.channel in ("instagram", "facebook"):
            try:
                if conv.channel == "instagram":
                    provider_response = await MetaAPIClient.send_instagram_dm(
                        recipient_id=conv.customer_identifier,
                        message_text=message_text,
                        page_access_token=page_token,
                    )
                    dispatch_status = "dispatched_instagram"
                elif conv.channel == "facebook":
                    provider_response = await MetaAPIClient.send_facebook_messenger_dm(
                        recipient_id=conv.customer_identifier,
                        message_text=message_text,
                        page_access_token=page_token,
                    )
                    dispatch_status = "dispatched_facebook"
            except Exception as e:
                dispatch_status = "failed_provider"
                dispatch_error = str(e)
                from app.services.meta_credentials import MetaCredentialError, mark_reconnect_required
                if isinstance(e, MetaCredentialError) and meta_int:
                    mark_reconnect_required(meta_int, e.channel)
                logger.error(f"External channel dispatch error: {e}")
        elif conv.channel == "whatsapp":
            try:
                from app.services.whatsapp import WhatsAppService
                provider_response = await WhatsAppService.send(db, conv, message_text)
                dispatch_status = "dispatched_whatsapp"
            except Exception as error:
                dispatch_status = "failed_provider"
                dispatch_error = str(error)
        elif conv.channel == "web_widget":
            dispatch_status = "dispatched_web_widget"

        # Update log entry with real delivery outcome
        log_entry.raw_payload = {
            "operator_name": operator_name,
            "dispatch_status": dispatch_status,
            "error": dispatch_error,
            "provider_response": provider_response,
        }
        db.add(log_entry)
        await db.commit()

        # 4. Broadcast to all open workbench sockets
        event = {
            "type": "new_message",
            "conversation_id": str(conversation_id),
            "tenant_id": str(tenant_id),
            "sender_type": "human_operator",
            "message_text": message_text,
            "operator_name": operator_name,
            "dispatch_status": dispatch_status,
            "dispatch_error": dispatch_error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await cls.broadcast_workbench_event(tenant_id, event)

        return {
            "status": "success" if dispatch_status != "failed_provider" else "delivery_failed",
            "conversation_id": str(conversation_id),
            "dispatch_status": dispatch_status,
            "error": dispatch_error,
            "message_text": message_text,
        }

    @classmethod
    async def update_ai_draft(
        cls,
        tenant_id: UUID,
        conversation_id: UUID,
        draft_text: str,
    ) -> Dict[str, Any]:
        """Broadcasts real-time live edit of an AI draft to operator desks."""
        event = {
            "type": "draft_updated",
            "conversation_id": str(conversation_id),
            "tenant_id": str(tenant_id),
            "draft_text": draft_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await cls.broadcast_workbench_event(tenant_id, event)
        return {"status": "success", "draft_text": draft_text}

    @classmethod
    async def broadcast_workbench_event(cls, tenant_id: UUID, event_payload: Dict[str, Any]) -> None:
        """Publishes event to Redis Pub/Sub channel for workbench WebSocket consumers."""
        redis_published = False
        try:
            r = get_redis_client()
            channel = f"joy:workbench:{str(tenant_id)}"
            await r.publish(channel, json.dumps(event_payload))
            redis_published = True
            logger.debug(f"Broadcasted event {event_payload.get('type')} to Redis channel {channel}")
        except Exception as e:
            logger.warning(f"Redis Pub/Sub broadcast failed: {e}")

        # Direct local WebSocket broadcast fallback if Redis is unreachable
        if not redis_published:
            try:
                from app.api.websockets.workbench import manager
                await manager.broadcast_to_tenant(str(tenant_id), event_payload)
            except Exception as e:
                logger.debug(f"Direct fallback broadcast skipped: {e}")
