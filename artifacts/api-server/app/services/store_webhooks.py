import base64
import hashlib
import hmac
from fastapi import HTTPException
from app.db.session import AsyncSessionLocal
from app.services.webhook_jobs import resolve_integration
from app.services.commerce import CommerceService
from app.core.config import settings


async def authenticate_store(request, provider, tenant_id, body, signature):
    source = request.headers.get("x-shopify-shop-domain" if provider == "shopify" else "x-wc-webhook-source", "")
    if not source or not signature:
        raise HTTPException(401, "Missing verified store identity or signature.")
    async with AsyncSessionLocal() as db:
        try:
            record = await resolve_integration(db, provider, source, tenant_id)
        except HTTPException:
            raise HTTPException(401, "Store identity or signature is invalid.") from None
        configured = (record.settings or {}).get("webhook_secret")
        secret = CommerceService.credential(configured) if configured else (
            settings.SHOPIFY_API_SECRET if provider == "shopify" else settings.WOOCOMMERCE_WEBHOOK_SECRET)
        if not secret:
            raise HTTPException(503, "Configure this store's webhook signing secret.")
        expected = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(401, "Store identity or signature is invalid.")
        return record.tenant_id
