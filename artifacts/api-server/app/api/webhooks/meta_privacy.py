"""Meta-signed deauthorization and data-deletion requests, with honest status."""
import base64
import hashlib
import hmac
import json
from uuid import UUID, uuid4
from urllib.parse import parse_qs
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select, delete
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models import (TenantIntegration, Conversation, PrivacyRequest, WebhookJob,
                          CheckpointModel, CheckpointBlobModel, CheckpointWriteModel)

router = APIRouter(prefix="/meta-privacy", tags=["Privacy"])


def signed_identity(value):
    try:
        signature, payload = value.split(".")
        decoded = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        expected = hmac.new(settings.META_APP_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if (not settings.META_APP_SECRET or not hmac.compare_digest(decoded, expected)
                or data.get("algorithm", "").upper() != "HMAC-SHA256"
                or not str(data.get("user_id", "")).isdigit()):
            raise ValueError()
        return str(data["user_id"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(401, "Invalid Meta signed request.") from None


@router.post("/deauthorize")
@router.post("/delete")
async def privacy_callback(request: Request):
    body = await request.body()
    if len(body) > 8192:
        raise HTTPException(413, "Privacy request exceeds the allowed size.")
    try:
        if "application/json" in request.headers.get("content-type", ""):
            value = json.loads(body).get("signed_request", "")
        else:
            value = parse_qs(body.decode()).get("signed_request", [""])[0]
    except (ValueError, AttributeError, UnicodeError):
        raise HTTPException(400, "Malformed privacy request.") from None
    user_id = signed_identity(value)
    deleting = request.url.path.endswith("/delete")
    async with AsyncSessionLocal() as db:
        records = (await db.execute(select(TenantIntegration).where(
            TenantIntegration.provider.in_(["meta", "whatsapp"])))).scalars().all()
        legacy_unknown = any(not (r.settings or {}).get("meta_user_id") for r in records)
        matched = [r for r in records if str((r.settings or {}).get("meta_user_id")) == user_id]
        for record in matched:
            # Deactivate now; review deletion after in-flight graphs stop so
            # they cannot recreate a customer's deleted history.
            record.is_active = False
            record.access_token_encrypted = ""
            record.refresh_token_encrypted = None
            from app.core.safety import redact
            record.settings = redact(record.settings or {})
        code = uuid4()
        receipt = PrivacyRequest(code=code, user_hash=hmac.new(settings.META_APP_SECRET.encode(), user_id.encode(), hashlib.sha256).hexdigest(),
            status=("delete_pending_review" if matched else "delete_legacy_review") if deleting and (matched or legacy_unknown)
                   else ("deauth_legacy_review" if legacy_unknown else "completed"))
        db.add(receipt)
        await db.commit()
    base = str(request.base_url).rstrip("/")
    return {"url": f"{base}/api/v1/webhooks/meta-privacy/status/{code}", "confirmation_code": str(code)}


@router.get("/status/{code}")
async def privacy_status(code: UUID):
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(PrivacyRequest).where(PrivacyRequest.code == code))).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Deletion request not found.")
        return {"confirmation_code": str(code), "status": row.status}


def require_privacy_admin(request):
    from app.core.deployment_guard import is_public_deployment
    if is_public_deployment() and not request.scope.get("state", {}).get("is_joy_owner"):
        raise HTTPException(403, "Only the application owner can review signed privacy requests.")


@router.get("/requests")
async def privacy_requests(request: Request):
    require_privacy_admin(request)
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(PrivacyRequest).where(PrivacyRequest.status != "completed")
            .order_by(PrivacyRequest.created_at).limit(100))).scalars().all()
        return [{"code":str(r.code),"status":r.status} for r in rows]


@router.post("/requests/{code}/complete")
async def complete_privacy_request(code: UUID, request: Request):
    require_privacy_admin(request)
    if (await request.json()).get("confirm") != "DELETE_REQUESTED_DATA":
        raise HTTPException(400, "Explicit deletion confirmation is required.")
    async with AsyncSessionLocal() as db:
        receipt = (await db.execute(select(PrivacyRequest).where(
            PrivacyRequest.code == code).with_for_update())).scalar_one_or_none()
        if not receipt:
            raise HTTPException(404, "Privacy request not found.")
        if receipt.status == "completed":
            return {"status":"completed"}
        if not receipt.status.startswith("delete_"):
            raise HTTPException(409, "This request only authorizes deauthorization, not data deletion.")
        records = (await db.execute(select(TenantIntegration).where(
            TenantIntegration.provider.in_(["meta","whatsapp"])))).scalars().all()
        matched = [r for r in records if (r.settings or {}).get("meta_user_id") and
            hmac.compare_digest(receipt.user_hash, hmac.new(settings.META_APP_SECRET.encode(),
                str(r.settings["meta_user_id"]).encode(),hashlib.sha256).hexdigest())]
        if not matched:
            raise HTTPException(409, "Legacy ownership must be verified before business data is deleted.")
        for record in matched:
            if record.is_active:
                raise HTTPException(409, "Deactivate the associated integration before deleting its data.")
            jobs = (await db.execute(select(WebhookJob).where(
                WebhookJob.tenant_id == record.tenant_id, WebhookJob.provider == record.provider)
                .with_for_update())).scalars().all()
            if any(job.status == "processing" for job in jobs):
                raise HTTPException(409, "An in-flight operation must finish or time out before deletion. Retry later.")
            channels = ["facebook","instagram"] if record.provider == "meta" else ["whatsapp"]
            await db.execute(delete(Conversation).where(
                Conversation.tenant_id == record.tenant_id,Conversation.channel.in_(channels)))
            for model in (CheckpointModel,CheckpointBlobModel,CheckpointWriteModel):
                for channel in channels:
                    await db.execute(delete(model).where(model.thread_id.like(f"{record.tenant_id}:{channel}:%")))
            await db.execute(delete(WebhookJob).where(
                WebhookJob.tenant_id == record.tenant_id, WebhookJob.provider == record.provider))
            await db.delete(record)
        receipt.status = "delete_legacy_review" if any(not (r.settings or {}).get("meta_user_id") for r in records) else "completed"
        await db.commit()
        return {"status":receipt.status}
