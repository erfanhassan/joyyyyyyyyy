import logging
from typing import Optional, Dict, Any, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
import uuid
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db.models import Tenant, TenantIntegration, Order, User
from app.core.security import encrypt_token, decrypt_token
from app.core.config import settings
from app.services.telephony_service import TelephonyService, OutboundCallingUnavailable
import httpx
import time

logger = logging.getLogger("joy.routes.tenant")
router = APIRouter(prefix="/tenant", tags=["Tenant & Store Management"])


# ==========================================
# Pydantic Schemas
# ==========================================
class TenantUpdate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, description="Business or storefront name")
    currency: Optional[str] = Field("BDT", max_length=10)
    timezone: Optional[str] = Field("Asia/Dhaka", max_length=50)
    domain: Optional[str] = Field(None, max_length=255)


class IntegrationConnectRequest(BaseModel):
    provider: str = Field(..., description="Provider identifier: 'meta', 'shopify', 'woocommerce', 'widget'")
    access_token: str = Field(..., min_length=1, description="Raw access token or secret to be AES-256 encrypted")
    refresh_token: Optional[str] = None
    settings: Dict[str, Any] = Field(default_factory=dict, description="Provider specific metadata")


from app.services.meta_api import MetaAPIClient

class IntegrationTestRequest(BaseModel):
    provider: str
    sample_payload: Optional[Dict[str, Any]] = None


class MetaOAuthExchangeRequest(BaseModel):
    code: Optional[str] = None
    access_token: Optional[str] = None


class WhatsAppEmbeddedSignupRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=4096)
    waba_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[0-9]+$")
    phone_number_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[0-9]+$")


class MetaSelectPageRequest(BaseModel):
    page_id: str
    page_name: str
    page_access_token: str
    instagram_account_id: Optional[str] = None
    instagram_username: Optional[str] = None


class OnboardRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, description="Business or storefront name")
    currency: Optional[str] = Field("BDT", max_length=10)
    timezone: Optional[str] = Field("Asia/Dhaka", max_length=50)
    domain: Optional[str] = Field(None, max_length=255)


# ==========================================
# Tenant Workspace Resolution & Profile
# ==========================================
@router.get("/me")
async def get_my_workspace(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Dynamically resolves or provisions the workspace for the authenticated merchant/operator.
    Falls back to the default storefront in local/offline development.
    """
    from app.services.workspaces import workspace_for
    tenant, role = await workspace_for(request, db)

    int_stmt = select(TenantIntegration).where(
        TenantIntegration.tenant_id == tenant.id,
        TenantIntegration.is_active == True,
    )
    int_res = await db.execute(int_stmt)
    active_integrations = int_res.scalars().all()

    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "currency": getattr(tenant, "currency", "BDT") or "BDT",
        "timezone": getattr(tenant, "timezone", "Asia/Dhaka") or "Asia/Dhaka",
        "domain": getattr(tenant, "domain", None),
        "settings": getattr(tenant, "settings", {}) or {},
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
        "active_integrations_count": len(active_integrations),
        "configured_providers": [i.provider for i in active_integrations],
        "role": role,
    }


@router.post("/onboard")
async def onboard_merchant_workspace(
    payload: OnboardRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Provisions a brand new isolated business workspace for an onboarding merchant.
    """
    from app.services.workspaces import actor, bind
    from app.db.models import WorkspaceIdentity
    from sqlalchemy import text
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    user_id, email, _ = actor(request)
    try:
        ZoneInfo(payload.timezone or "Asia/Dhaka")
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(400, "Choose a valid IANA timezone.") from None
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:subject))"), {"subject": user_id})
    existing = (await db.execute(select(WorkspaceIdentity).where(
        WorkspaceIdentity.clerk_user_id == user_id))).scalar_one_or_none()
    if existing:
        return {"status": "already_created", "id": str(existing.tenant_id)}

    new_tenant = Tenant(
        name=payload.name.strip(),
        currency=(payload.currency or "BDT").strip().upper(),
        timezone=(payload.timezone or "Asia/Dhaka").strip(),
        domain=payload.domain.strip() if payload.domain else None,
    )
    db.add(new_tenant)
    await db.flush()

    await bind(db, user_id, email, new_tenant)
    await db.refresh(new_tenant)

    return {
        "status": "success",
        "id": str(new_tenant.id),
        "name": new_tenant.name,
        "currency": new_tenant.currency,
        "timezone": new_tenant.timezone,
        "domain": new_tenant.domain,
        "message": "Business workspace created successfully.",
    }


@router.get("/{tenant_id}")
async def get_tenant_profile(tenant_id: UUID, db: AsyncSession = Depends(get_db)):
    """Fetches real-time tenant profile, currency, and integration counts from PostgreSQL."""
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found in database.",
        )

    int_stmt = select(TenantIntegration).where(
        TenantIntegration.tenant_id == tenant_id,
        TenantIntegration.is_active == True,
    )
    int_res = await db.execute(int_stmt)
    active_integrations = int_res.scalars().all()

    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "currency": getattr(tenant, "currency", "BDT") or "BDT",
        "timezone": getattr(tenant, "timezone", "Asia/Dhaka") or "Asia/Dhaka",
        "domain": getattr(tenant, "domain", None),
        "settings": getattr(tenant, "settings", {}) or {},
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
        "active_integrations_count": len(active_integrations),
        "configured_providers": [i.provider for i in active_integrations],
    }


class WidgetOriginUpdate(BaseModel):
    domain: str = Field(min_length=1, max_length=255)


@router.patch("/{tenant_id}/widget-origin")
async def update_widget_origin(tenant_id: UUID, payload: WidgetOriginUpdate, db: AsyncSession = Depends(get_db)):
    from urllib.parse import urlsplit
    try:
        parsed=urlsplit(payload.domain.strip())
        if (parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.port not in (None,443) or parsed.query or parsed.fragment or parsed.path not in ("","/")):
            raise ValueError()
        host=parsed.hostname.encode("idna").decode().lower()
        origin=f"https://{'['+host+']' if ':' in host else host}"
    except (ValueError,UnicodeError):
        raise HTTPException(400,"Use an exact HTTPS website origin without credentials, a path, or a custom port.") from None
    tenant=(await db.execute(select(Tenant).where(Tenant.id==tenant_id))).scalar_one_or_none()
    if not tenant:
        raise HTTPException(404,"Workspace not found.")
    tenant.domain=origin
    await db.commit()
    return {"status":"success","domain":origin}


@router.put("/{tenant_id}")
async def update_tenant_profile(
    tenant_id: UUID,
    payload: TenantUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Updates the merchant's real business name, currency, domain, and operational timezone."""
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found.",
        )

    tenant.name = payload.name.strip()
    if payload.currency:
        tenant.currency = payload.currency.strip().upper()
    if payload.timezone:
        tenant.timezone = payload.timezone.strip()
    if payload.domain is not None:
        tenant.domain = payload.domain.strip() if payload.domain else None

    await db.commit()
    await db.refresh(tenant)

    logger.info(f"Updated tenant {tenant_id} settings: name={tenant.name}, currency={tenant.currency}, tz={tenant.timezone}, domain={tenant.domain}")
    return {
        "status": "success",
        "id": str(tenant.id),
        "name": tenant.name,
        "currency": tenant.currency,
        "timezone": tenant.timezone,
        "domain": tenant.domain,
        "message": "Store profile updated successfully.",
    }


# ==========================================
# Integrations Vault Endpoints (AES-256)
# ==========================================
@router.get("/{tenant_id}/integrations")
async def list_tenant_integrations(tenant_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Returns all configured integrations from PostgreSQL with masked token representations
    and verified permission scopes.
    """
    stmt = select(TenantIntegration).where(TenantIntegration.tenant_id == tenant_id)
    result = await db.execute(stmt)
    integrations = result.scalars().all()

    items = []
    for item in integrations:
        # Decrypt token safely to build masked display (e.g. "EAAG...34fa")
        try:
            raw_token = decrypt_token(item.access_token_encrypted)
            if len(raw_token) > 8:
                masked_token = f"{raw_token[:4]}••••••••{raw_token[-4:]}"
            else:
                masked_token = "••••••••"
        except Exception:
            masked_token = "••••••••(Encrypted)"

        items.append({
            "id": str(item.id),
            "tenant_id": str(item.tenant_id),
            "provider": item.provider,
            "is_active": item.is_active,
            "masked_token": masked_token,
            "settings": __import__("app.core.safety", fromlist=["redact"]).redact(item.settings or {}),
            "created_at": item.created_at.isoformat() if item.created_at else None,
        })

    return {"tenant_id": str(tenant_id), "integrations": items}


@router.post("/{tenant_id}/integrations")
async def save_tenant_integration(
    tenant_id: UUID,
    payload: IntegrationConnectRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Encrypts access tokens via AES-256 Fernet and persists credentials in PostgreSQL
    with envelope encryption.
    """
    if any(marker in payload.access_token.lower() for marker in ("simulated", "sandbox_token")) or payload.access_token.startswith(("joy_", "mock_", "test_")):
        raise HTTPException(status_code=400, detail="Use real provider credentials. Demo tokens cannot connect an integration.")
    if payload.provider == "meta":
        return await meta_select_page(
            tenant_id,
            MetaSelectPageRequest(
                page_id=str(payload.settings.get("page_id") or ""),
                page_name=str(payload.settings.get("page_name") or ""),
                page_access_token=payload.access_token,
                instagram_account_id=payload.settings.get("instagram_account_id"),
            ),
            db,
        )

    if payload.provider == "whatsapp":
        from app.services.whatsapp import WhatsAppService
        try:
            payload.settings = await WhatsAppService.verify_connection(payload.access_token, payload.settings)
        except (ValueError, RuntimeError):
            raise HTTPException(400, "WhatsApp verification failed. Check phone/WABA ownership, permissions and token validity.") from None

    # Verify tenant exists
    tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
    t_res = await db.execute(tenant_stmt)
    if not t_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Tenant does not exist.")

    # Encrypt the token using Fernet AES-256
    if payload.provider not in ("shopify","woocommerce","whatsapp"):
        raise HTTPException(409,"This provider is not implemented. No connection was saved.")
    encrypted_token = encrypt_token(payload.access_token)
    encrypted_refresh = encrypt_token(payload.refresh_token) if payload.refresh_token else None
    from app.core.safety import seal_credentials
    safe_settings = seal_credentials(payload.settings)

    # Check if integration already exists for this provider
    if payload.provider in ("shopify","woocommerce"):
        from app.services.commerce import CommerceService
        candidate = TenantIntegration(tenant_id=tenant_id,provider=payload.provider,
            access_token_encrypted=encrypted_token,settings=safe_settings,is_active=True)
        try:
            safe_settings.update(await CommerceService.verify_read(candidate))
        except Exception:
            raise HTTPException(400,"Store verification failed. Check the canonical store URL, API credentials and required read permissions. No connection was saved.") from None

    stmt = select(TenantIntegration).where(
        TenantIntegration.tenant_id == tenant_id,
        TenantIntegration.provider == payload.provider,
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.access_token_encrypted = encrypted_token
        existing.refresh_token_encrypted = encrypted_refresh
        existing.settings = safe_settings
        existing.is_active = True
        integration_obj = existing
        action = "updated"
    else:
        integration_obj = TenantIntegration(
            tenant_id=tenant_id,
            provider=payload.provider,
            access_token_encrypted=encrypted_token,
            refresh_token_encrypted=encrypted_refresh,
            settings=safe_settings,
            is_active=True,
        )
        db.add(integration_obj)
        action = "created"

    await db.commit()
    await db.refresh(integration_obj)

    logger.info(f"Integration '{payload.provider}' {action} for tenant {tenant_id}")
    return {
        "status": "success",
        "action": action,
        "provider": payload.provider,
        "is_active": True,
        "message": f"{payload.provider.capitalize()} credentials saved and encrypted. Live provider access and webhook delivery still need verification.",
    }


@router.post("/{tenant_id}/integrations/whatsapp/embedded-signup")
async def finish_whatsapp_embedded_signup(
    tenant_id: UUID,
    payload: WhatsAppEmbeddedSignupRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange Embedded Signup's short-lived code server-side; never expose the resulting token to the browser."""
    if not settings.META_APP_ID or not settings.META_APP_SECRET:
        raise HTTPException(503, "Meta app credentials are not configured on the server.")
    try:
        token_data = await MetaAPIClient.exchange_code_for_user_token(payload.code)
        access_token = token_data.get("access_token")
        if not access_token:
            raise RuntimeError("Meta did not return an access token.")
        result = await save_tenant_integration(
            tenant_id,
            IntegrationConnectRequest(
                provider="whatsapp",
                access_token=access_token,
                settings={
                    "waba_id": payload.waba_id,
                    "phone_number_id": payload.phone_number_id,
                },
            ),
            db,
        )
        result["message"] = (
            "WhatsApp account verified and connected. Inbound delivery still depends on "
            "the JOY Meta app's webhook callback and WhatsApp fields being configured."
        )
        return result
    except HTTPException:
        raise
    except Exception:
        logger.warning("WhatsApp Embedded Signup verification failed for tenant %s", tenant_id)
        raise HTTPException(
            400,
            "WhatsApp signup could not be verified. Confirm the Meta configuration, selected WABA and phone number, and required permissions.",
        ) from None


@router.post("/{tenant_id}/integrations/meta/oauth-exchange")
async def meta_oauth_exchange(
    tenant_id: UUID,
    payload: MetaOAuthExchangeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Exchanges Meta OAuth code or token for a long-lived user access token,
    and automatically discovers all managed Facebook Pages and linked Instagram accounts.
    """
    try:
        user_token = payload.access_token
        if payload.code:
            token_data = await MetaAPIClient.exchange_code_for_user_token(
                code=payload.code,
            )
            user_token = token_data.get("access_token")

        if not user_token:
            raise HTTPException(status_code=400, detail="No code or access token provided for Meta exchange.")

        # Upgrade to long-lived user token (60-day)
        long_lived_res = await MetaAPIClient.get_long_lived_user_token(user_token)
        final_user_token = long_lived_res.get("access_token", user_token)

        # Retrieve managed Facebook Pages and linked Instagram accounts
        pages = await MetaAPIClient.get_user_pages_and_instagram(final_user_token)

        return {
            "status": "success",
            "pages": pages,
            "count": len(pages),
            "message": f"Successfully discovered {len(pages)} Facebook page(s) and connected Instagram accounts.",
        }
    except Exception as e:
        logger.error(f"Error during Meta OAuth exchange: {e}")
        # If in dev/sandbox and Meta returns error, provide actionable error or fallback
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{tenant_id}/integrations/meta/select-page")
async def meta_select_page(
    tenant_id: UUID,
    payload: MetaSelectPageRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Encrypts the selected Facebook Page Access Token with AES-256 Fernet,
    saves the integration to PostgreSQL, and subscribes the page to webhooks.
    """
    # Verify tenant
    t_res = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    if not t_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Tenant does not exist.")

    if not payload.page_id.isdigit() or not payload.page_access_token:
        raise HTTPException(status_code=400, detail="A real Facebook Page ID and Page access token are required.")
    page_identity = await MetaAPIClient.get_page_identity(
        payload.page_id, payload.page_access_token,
    )
    instagram = page_identity.get("instagram_business_account") or {}
    if payload.instagram_account_id and str(instagram.get("id", "")) != payload.instagram_account_id:
        raise HTTPException(400, "The selected Instagram account is not linked to this verified Page.")
    from app.services.meta_identity import token_owner
    try:
        meta_user_id = await token_owner(payload.page_access_token)
    except Exception:
        raise HTTPException(400, "Meta could not verify this token's app and authorizing user. Reconnect with the configured application.") from None
    encrypted_token = encrypt_token(payload.page_access_token)
    # Do not persist a successful connection unless Meta confirms subscription.
    webhook_sub_res = await MetaAPIClient.subscribe_page_to_webhooks(
        page_id=payload.page_id,
        page_access_token=payload.page_access_token,
    )
    if webhook_sub_res.get("success") is not True:
        raise HTTPException(
            status_code=400,
            detail="Meta did not approve the Page webhook subscription. Check the Page permissions and app configuration, then retry.",
        )

    stmt = select(TenantIntegration).where(
        TenantIntegration.tenant_id == tenant_id,
        TenantIntegration.provider == "meta",
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    settings_data = {
        "page_name": page_identity["name"],
        "page_id": payload.page_id,
        "instagram_account_id": str(instagram.get("id") or ""),
        "instagram_username": instagram.get("username") or "",
        "requested_permissions": [
            "pages_manage_metadata",
            "pages_show_list",
            "pages_read_engagement",
            "pages_manage_engagement",
            "pages_messaging",
            "instagram_basic",
            "instagram_manage_messages",
            "instagram_manage_comments",
        ],
    }
    settings_data["meta_user_id"] = meta_user_id

    if existing:
        existing.access_token_encrypted = encrypted_token
        existing.settings = settings_data
        existing.is_active = True
        integration_obj = existing
        action = "updated"
    else:
        integration_obj = TenantIntegration(
            tenant_id=tenant_id,
            provider="meta",
            access_token_encrypted=encrypted_token,
            settings=settings_data,
            is_active=True,
        )
        db.add(integration_obj)
        action = "created"

    await db.commit()
    await db.refresh(integration_obj)

    return {
        "status": "success",
        "action": action,
        "provider": "meta",
        "page_name": payload.page_name,
        "page_id": payload.page_id,
        "instagram_account_id": payload.instagram_account_id,
        "webhook_subscription": webhook_sub_res,
        "message": f"Facebook Page '{payload.page_name}' connected & AES-256 encrypted successfully!",
    }


@router.delete("/{tenant_id}/integrations/{provider}")
async def disconnect_tenant_integration(
    tenant_id: UUID,
    provider: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Disconnects integration, revokes/unsubscribes provider webhooks if applicable,
    and removes credentials from PostgreSQL.
    """
    # Look up existing integration first to handle provider unsubscription
    existing_stmt = select(TenantIntegration).where(
        TenantIntegration.tenant_id == tenant_id,
        TenantIntegration.provider == provider,
    )
    res_existing = await db.execute(existing_stmt)
    existing_item = res_existing.scalars().first()

    if not existing_item:
        raise HTTPException(
            status_code=404,
            detail=f"No active integration found for provider '{provider}'.",
        )

    # If Meta, cleanly unsubscribe the Page from webhooks
    if provider == "meta" and existing_item.access_token_encrypted:
        try:
            page_token = decrypt_token(existing_item.access_token_encrypted)
            page_id = (existing_item.settings or {}).get("page_id")
            if page_id and page_token:
                result = await MetaAPIClient.unsubscribe_page_from_webhooks(page_id, page_token)
                if not result.get("success"):
                    raise RuntimeError("Unsubscription was not confirmed.")
        except Exception:
            raise HTTPException(502, "Meta unsubscription failed. The encrypted connection was retained so you can retry.") from None

    if provider == "whatsapp":
        try:
            from app.services.whatsapp import WhatsAppService
            token = decrypt_token(existing_item.access_token_encrypted)
            business = (existing_item.settings or {}).get("waba_id", "")
            response = await WhatsAppService.api(token, "DELETE", f"{business}/subscribed_apps")
            if not response.get("success"):
                raise RuntimeError("Unsubscription was not confirmed.")
        except Exception:
            raise HTTPException(502, "WhatsApp unsubscription failed. The encrypted connection was retained for retry.") from None

    if provider in ("meta", "whatsapp"):
        # Retain the verified subject association for subsequent Meta deletion
        # requests, but destroy all reusable credentials after unsubscribe.
        from app.core.safety import redact
        existing_item.is_active = False
        existing_item.access_token_encrypted = ""
        existing_item.refresh_token_encrypted = None
        existing_item.settings = redact(existing_item.settings or {})
        await db.commit()
        return {"status":"success", "provider":provider,
                "message":"Webhook unsubscription confirmed and credentials removed. Privacy association retained until data deletion."}

    stmt = delete(TenantIntegration).where(
        TenantIntegration.tenant_id == tenant_id,
        TenantIntegration.provider == provider,
    )
    await db.execute(stmt)
    await db.commit()

    logger.info(f"Disconnected integration '{provider}' for tenant {tenant_id}")
    return {
        "status": "success",
        "provider": provider,
        "message": f"{provider.capitalize()} integration disconnected." + (" Webhook unsubscription confirmed." if provider in ("meta", "whatsapp") else " Remove any manually configured store webhooks in the provider dashboard."),
    }


@router.post("/{tenant_id}/integrations/{provider}/test")
async def test_integration_connection(
    tenant_id: UUID,
    provider: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Tests live communication with provider API or validates encrypted credentials.
    """
    if provider in ("telephony", "amberit", "livekit"):
        return await TelephonyService.test_telephony_status()

    stmt = select(TenantIntegration).where(
        TenantIntegration.tenant_id == tenant_id,
        TenantIntegration.provider == provider,
    )
    res = await db.execute(stmt)
    integration = res.scalar_one_or_none()

    if not integration or not integration.is_active:
        return {
            "status": "unconfigured",
            "provider": provider,
            "connected": False,
            "message": f"Provider '{provider}' has not been configured yet.",
        }

    # Verify decryption
    try:
        raw_token = decrypt_token(integration.access_token_encrypted)
        is_token_valid = len(raw_token) > 0
    except Exception:
        return {
            "status": "error",
            "provider": provider,
            "connected": False,
            "message": "Stored credentials could not be decrypted. Check the server encryption configuration.",
        }

    # Provider specific diagnostics
    if provider == "meta":
        page_name = integration.settings.get("page_name", "Facebook Page")
        page_id = integration.settings.get("page_id", "")
        ig_id = integration.settings.get("instagram_account_id", "")
        t0 = time.monotonic()
        try:
            identity = await MetaAPIClient.get_page_identity(page_id, raw_token)
            page_name = identity["name"]
        except HTTPException as exc:
            return {"status": "error", "provider": "meta", "connected": False, "message": exc.detail}
        latency = max(1, int((time.monotonic() - t0) * 1000))

        return {
            "status": "healthy",
            "provider": "meta",
            "connected": True,
            "account_name": page_name,
            "instagram_account_id": ig_id or "Not linked",
            "latency_ms": latency,
            "message": f"Page API access verified for '{page_name}'. End-to-end webhook delivery and replies require a separate message test.",
        }
    elif provider == "shopify":
        return {
            "status": "not_verified",
            "provider": "shopify",
            "connected": False,
            "shop_domain": integration.settings.get("shop_domain", "store.myshopify.com"),
            "webhook_endpoint": f"/api/v1/webhooks/shopify/{tenant_id}",
            "message": "Shopify credentials are stored. Live API access and webhook delivery have not been verified.",
        }
    elif provider == "woocommerce":
        return {
            "status": "not_verified",
            "provider": "woocommerce",
            "connected": False,
            "store_url": integration.settings.get("store_url", "https://mystore.com"),
            "webhook_endpoint": f"/api/v1/webhooks/woocommerce/{tenant_id}",
            "message": "WooCommerce credentials are stored. Live API access and webhook delivery have not been verified.",
        }
    else:
        return {
            "status": "not_verified",
            "provider": provider,
            "connected": False,
            "message": f"{provider.capitalize()} credentials are stored; no live verification is implemented.",
        }


# ==========================================
# Telephony Diagnostics & Live Test Call
# ==========================================
class OutboundCallRequest(BaseModel):
    customer_phone: str = Field(default="+8801712345678", description="Bangladeshi or international phone number")
    customer_name: str = Field(default="Tahmid Rahman")
    shipping_address: str = Field(default="House 42, Road 11, Banani, Dhaka")
    order_items: str = Field(default="Silk Jamdani Panjabi (Size L)")
    order_total: float = Field(default=3850.00)


@router.get("/{tenant_id}/telephony/status")
async def get_telephony_status(tenant_id: UUID):
    """
    Returns real-time health and diagnostics for LiveKit Cloud WebRTC and Amber IT Bangladesh PABX.
    """
    return await TelephonyService.test_telephony_status()


@router.post("/{tenant_id}/telephony/test-call")
async def trigger_test_call(
    tenant_id: UUID,
    payload: OutboundCallRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Triggers an outbound confirmation call via LiveKit Cloud & Amber IT Bangladesh PABX.
    Persists order in PostgreSQL and dispatches call over WebRTC / SIP.
    """
    try:
        TelephonyService.require_outbound_calling()
    except OutboundCallingUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None

    order_id = uuid.uuid4()
    order = Order(
        id=order_id,
        tenant_id=tenant_id,
        external_order_id=f"TEST-{uuid.uuid4().hex[:6].upper()}",
        storefront_provider="shopify",
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        shipping_address=payload.shipping_address,
        order_total=payload.order_total,
        status="pending_confirmation",
        confirmation_channel="voice",
        call_attempts=1,
    )
    db.add(order)
    await db.commit()

    # Dispatch via TelephonyService
    call_dispatch = await TelephonyService.initiate_outbound_call(
        order_id=order_id,
        customer_phone=payload.customer_phone,
        customer_name=payload.customer_name,
        shipping_address=payload.shipping_address,
        order_items=payload.order_items,
        order_total=payload.order_total,
        tenant_id=tenant_id,
    )

    return {
        "status": "success",
        "order_id": str(order_id),
        "external_order_id": order.external_order_id,
        "dispatch": call_dispatch,
        "message": f"Voice confirmation call dispatched via Amber IT (+8809611901539) to {payload.customer_phone}",
    }

