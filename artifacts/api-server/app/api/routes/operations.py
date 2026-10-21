from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from app.db.session import get_db
from app.db.models import WebhookJob, CheckoutRequest, DeliveryReceipt, TenantIntegration
from app.core.config import settings

router = APIRouter(prefix="/tenant", tags=["Operational Readiness"])


@router.get("/{tenant_id}/operations")
async def operations(tenant_id: UUID, db=Depends(get_db)):
    records = (await db.execute(select(TenantIntegration).where(
        TenantIntegration.tenant_id == tenant_id, TenantIntegration.is_active.is_(True)))).scalars().all()
    providers = {r.provider for r in records}
    rows = (await db.execute(select(WebhookJob).where(
        WebhookJob.tenant_id == tenant_id, WebhookJob.status.in_(["pending", "retry", "dead", "processing"]))
        .order_by(WebhookJob.created_at.desc()).limit(50))).scalars().all()
    checkouts = (await db.execute(select(func.count()).select_from(CheckoutRequest).where(
        CheckoutRequest.tenant_id == tenant_id, CheckoutRequest.status == "needs_review"))).scalar_one()
    deliveries = (await db.execute(select(func.count()).select_from(DeliveryReceipt).where(
        DeliveryReceipt.tenant_id == tenant_id, DeliveryReceipt.status == "needs_review"))).scalar_one()
    blockers = []
    if not providers.intersection({"shopify", "woocommerce"}):
        blockers.append("No authoritative store connected: live inventory and checkout are unavailable.")
    if len([r for r in records if r.provider in ("shopify", "woocommerce")]) > 1:
        blockers.append("Multiple stores are connected. Disconnect all but one authoritative store before using automated checkout.")
    if not providers.intersection({"meta", "whatsapp"}):
        blockers.append("No social channel connected and verified.")
    if any(r.status == "dead" for r in rows) or checkouts or deliveries:
        blockers.append("External operations require review before retrying.")
    return {
        "public_onboarding_enabled": settings.ALLOW_PUBLIC_SIGNUPS,
        "phone_available": False,
        "phone_reason": "A deployed voice worker and provider-approved SIP trunk must be verified before activation.",
        "whatsapp_available": "whatsapp" in providers,
        "whatsapp_limit": "Customer-initiated text replies only; approved outbound templates are not enabled.",
        "provider_acceptance_test_required": True,
        "blockers": blockers,
        "checkout_reviews": checkouts, "delivery_reviews": deliveries,
        "jobs": [{"id": str(r.id), "provider": r.provider, "status": r.status,
                  "attempts": r.attempts, "error": r.last_error} for r in rows],
    }
