"""WhatsApp Cloud API: verified phone bindings, replies, and approved templates."""
import re
import time
from uuid import UUID
import httpx
from sqlalchemy import select
from app.core.security import decrypt_token
from app.db.models import Conversation, InteractionLog, TenantIntegration
from app.db.session import AsyncSessionLocal
from app.services.meta_credentials import MetaCredentialError, credential_error, mark_reconnect_required


class WhatsAppService:
    @staticmethod
    async def integration(db, tenant_id):
        record = (await db.execute(select(TenantIntegration).where(
            TenantIntegration.tenant_id == tenant_id,
            TenantIntegration.provider == "whatsapp",
            TenantIntegration.is_active.is_(True)))).scalar_one_or_none()
        if not record:
            raise RuntimeError("WhatsApp is disconnected.")
        if (record.settings or {}).get("connection_status") == "needs_reconnect":
            from app.services.webhook_jobs import ManualReviewRequired
            raise ManualReviewRequired("WhatsApp needs reconnection before another message can be sent.")
        return record

    @staticmethod
    def template_layout(template):
        """Return supported text-parameter locations in WhatsApp send order."""
        components = template.get("components") or []
        layout = []
        supported = True
        for component in components:
            kind = str(component.get("type", "")).lower()
            if kind == "header":
                if component.get("format", "TEXT").upper() != "TEXT":
                    supported = False
                    continue
                text = component.get("text") or ""
                count = len(re.findall(r"\{\{\s*\d+\s*\}\}", text))
                if count:
                    layout.append({"type": "header", "count": count})
            elif kind == "body":
                text = component.get("text") or ""
                count = len(re.findall(r"\{\{\s*\d+\s*\}\}", text))
                if count:
                    layout.append({"type": "body", "count": count})
            elif kind == "buttons":
                for index, button in enumerate(component.get("buttons") or []):
                    if str(button.get("type", "")).upper() == "URL":
                        count = len(re.findall(r"\{\{\s*\d+\s*\}\}", button.get("url") or ""))
                        if count:
                            layout.append({"type": "button", "index": str(index), "count": count})
        return layout, supported

    @staticmethod
    def template_variables_count(template):
        layout, _ = WhatsAppService.template_layout(template)
        return sum(item["count"] for item in layout)

    @staticmethod
    def template_components(layout, variables):
        if len(variables) != sum(item["count"] for item in layout):
            raise ValueError(f"This template requires exactly {sum(item['count'] for item in layout)} variable(s).")
        if any(not isinstance(value, str) or not value.strip() for value in variables):
            raise ValueError("Every required template variable must have a value.")
        result = []
        offset = 0
        for item in layout:
            params = [
                {"type": "text", "text": str(value).strip()}
                for value in variables[offset:offset + item["count"]]
            ]
            offset += item["count"]
            if item["type"] == "button":
                result.append({
                    "type": "button", "sub_type": "url", "index": item["index"],
                    "parameters": params,
                })
            else:
                result.append({"type": item["type"], "parameters": params})
        return result

    @staticmethod
    async def approved_templates(db, tenant_id):
        record = await WhatsAppService.integration(db, tenant_id)
        token = decrypt_token(record.access_token_encrypted)
        try:
            templates = await WhatsAppService.api(
                token, "GET", f"{record.settings['waba_id']}/message_templates",
                params={"fields": "name,status,language,category,components", "limit": 100},
            )
        except MetaCredentialError as error:
            mark_reconnect_required(record, error.channel)
            raise
        return [
            {
                "name": item["name"],
                "language": item.get("language", "en"),
                "category": item.get("category"),
                "variable_count": WhatsAppService.template_variables_count(item),
                "supported": WhatsAppService.template_layout(item)[1],
            }
            for item in templates.get("data", [])
            if item.get("status") == "APPROVED" and item.get("name") and item.get("language")
        ]

    @staticmethod
    async def api(token, method, path, **kwargs):
        if not path or any(part in path for part in ("..", "://", "?")):
            raise ValueError("Invalid WhatsApp resource.")
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            result = await client.request(method, f"https://graph.facebook.com/v26.0/{path}",
                headers={"Authorization": f"Bearer {token}"}, **kwargs)
            data = result.json()
            if result.status_code >= 300 or data.get("error"):
                reconnect_error = credential_error(data, "WhatsApp")
                if reconnect_error:
                    raise reconnect_error
                raise RuntimeError("WhatsApp rejected the operation. Check number ownership, app permissions and token expiry.")
            return data

    @staticmethod
    async def verify_connection(token, config):
        phone, waba = str(config.get("phone_number_id", "")), str(config.get("waba_id", ""))
        if not phone.isdigit() or not waba.isdigit():
            raise ValueError("Enter numeric WhatsApp Business Account and phone-number IDs.")
        owned = await WhatsAppService.api(token, "GET", f"{waba}/phone_numbers")
        if phone not in {str(p["id"]) for p in owned.get("data", [])}:
            raise ValueError("This phone number does not belong to the supplied WhatsApp Business Account.")
        identity = await WhatsAppService.api(token, "GET", phone, params={"fields": "id,display_phone_number,verified_name"})
        from app.services.meta_identity import token_owner
        owner = await token_owner(token)
        subscription = await WhatsAppService.api(token, "POST", f"{waba}/subscribed_apps")
        if not subscription.get("success"):
            raise RuntimeError("WhatsApp webhook subscription was not confirmed.")
        return {"phone_number_id": phone, "waba_id": waba, "display_phone_number": identity.get("display_phone_number"),
                "verified_name": identity.get("verified_name"), "meta_user_id": owner}

    @staticmethod
    async def send(db, conversation, text, integration_id=None):
        record = (await db.execute(select(TenantIntegration).where(
            TenantIntegration.tenant_id == conversation.tenant_id,
            TenantIntegration.provider == "whatsapp",
            TenantIntegration.is_active.is_(True)))).scalar_one_or_none()
        if not record or (integration_id and str(record.id) != integration_id):
            raise RuntimeError("WhatsApp is disconnected.")
        if (record.settings or {}).get("connection_status") == "needs_reconnect":
            from app.services.webhook_jobs import ManualReviewRequired
            raise ManualReviewRequired("WhatsApp needs reconnection before another reply can be sent.")
        incoming = (await db.execute(select(InteractionLog).where(
            InteractionLog.conversation_id == conversation.id,
            InteractionLog.tenant_id == conversation.tenant_id,
            InteractionLog.sender_type == "customer")
            .order_by(InteractionLog.created_at.desc()).limit(1))).scalar_one_or_none()
        timestamp = (incoming.raw_payload or {}).get("provider_timestamp") if incoming else None
        if not timestamp or time.time() - float(timestamp) >= 86400:
            raise RuntimeError("The WhatsApp reply window has closed. An approved message template and opt-in are required.")
        try:
            result = await WhatsAppService.api(decrypt_token(record.access_token_encrypted), "POST",
                f"{record.settings['phone_number_id']}/messages", json={
                    "messaging_product": "whatsapp", "recipient_type": "individual",
                    "to": conversation.customer_identifier, "type": "text",
                    "text": {"preview_url": False, "body": text[:4096]}})
        except MetaCredentialError as error:
            mark_reconnect_required(record, error.channel)
            raise
        if not result.get("messages", [{}])[0].get("id"):
            raise RuntimeError("WhatsApp did not confirm message acceptance.")
        return result

    @staticmethod
    async def send_template(db, conversation, name, language, variables):
        if conversation.whatsapp_opt_in is not True:
            raise PermissionError("A recorded customer WhatsApp opt-in is required before sending a template.")
        record = await WhatsAppService.integration(db, conversation.tenant_id)
        token = decrypt_token(record.access_token_encrypted)
        approved = await WhatsAppService.api(
            token, "GET", f"{record.settings['waba_id']}/message_templates",
            params={"fields": "name,status,language,category,components", "name": name, "limit": 100},
        )
        template = next((item for item in approved.get("data", [])
                         if item.get("name") == name and item.get("language") == language
                         and item.get("status") == "APPROVED"), None)
        if not template:
            raise PermissionError("This WhatsApp template is not currently approved for this language.")
        layout, supported = WhatsAppService.template_layout(template)
        if not supported:
            raise ValueError("This template uses a media header, which is not supported for sending here.")
        components = WhatsAppService.template_components(layout, variables)
        try:
            result = await WhatsAppService.api(token, "POST",
                f"{record.settings['phone_number_id']}/messages", json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": conversation.customer_identifier,
                    "type": "template",
                    "template": {
                        "name": name,
                        "language": {"code": language},
                        "components": components,
                    },
                })
        except MetaCredentialError as error:
            mark_reconnect_required(record, error.channel)
            raise
        if not result.get("messages", [{}])[0].get("id"):
            raise RuntimeError("WhatsApp did not confirm template message acceptance.")
        return result, template


async def enqueue_whatsapp(payload, route_tenant):
    from app.services.webhook_jobs import resolve_integration, enqueue
    count = 0
    async with AsyncSessionLocal() as db:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                phone = value.get("metadata", {}).get("phone_number_id")
                if not value.get("messages"):
                    continue  # Delivery/read receipts must never trigger another AI message.
                record = await resolve_integration(db, "whatsapp", phone, route_tenant)
                if str(record.settings.get("waba_id")) != str(entry.get("id")):
                    raise ValueError("WhatsApp Business Account does not match the connected phone.")
                for message in value["messages"]:
                    count += int(await enqueue(db, "whatsapp", record.tenant_id, message["id"],
                        {"message": message, "integration_id": str(record.id)}))
    return count


async def process_whatsapp(payload, tenant_id, event_id):
    from app.agents.social_sales import SocialSalesAgent
    from app.services.hitl_orchestrator import HITLOrchestrator
    message = payload["message"]
    async with AsyncSessionLocal() as db:
        db.info["tenant_id"] = str(tenant_id)
        tenant = UUID(str(tenant_id))
        customer = str(message["from"])
        conv = (await db.execute(select(Conversation).where(
            Conversation.tenant_id == tenant, Conversation.channel == "whatsapp",
            Conversation.customer_identifier == customer))).scalars().first()
        if not conv:
            conv = Conversation(tenant_id=tenant, channel="whatsapp", customer_identifier=customer)
            db.add(conv)
            await db.flush()
        text = message.get("text", {}).get("body") or "[Non-text WhatsApp message: human review required]"
        db.add(InteractionLog(tenant_id=tenant, conversation_id=conv.id, sender_type="customer",
            message_text=text, raw_payload={"provider_timestamp": message.get("timestamp"), "event_id": event_id}))
        if message.get("type") != "text":
            conv.is_paused_for_human = True
        await db.commit()
        await HITLOrchestrator.broadcast_workbench_event(tenant, {
            "type": "new_message", "tenant_id": str(tenant), "conversation_id": str(conv.id),
            "sender_type": "customer", "channel": "whatsapp", "message_text": text})
        if conv.is_paused_for_human or time.time() - float(message.get("timestamp", 0)) >= 86400:
            return
        state = await SocialSalesAgent(db).execute({
            "tenant_id": str(tenant), "channel": "whatsapp", "customer_id": customer,
            "customer_name": None, "message_text": text, "conversation_id": str(conv.id),
            "request_id": event_id, "integration_id": payload["integration_id"],
            "comment_id": None, "is_private_reply": False, "is_paused_for_human": False})
        if state.get("reply_text"):
            db.add(InteractionLog(tenant_id=tenant, conversation_id=conv.id,
                sender_type="agent", message_text=state["reply_text"],
                raw_payload={"dispatch_status": state.get("dispatch_status")}))
            await db.commit()
