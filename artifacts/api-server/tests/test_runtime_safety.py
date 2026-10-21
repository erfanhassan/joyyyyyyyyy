"""Regression coverage for audited launch failures; never contacts providers."""
import asyncio
import base64
import hashlib
import hmac
import json
import socket
import subprocess
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from app.core.config import settings
from app.core.safety import public_url, redact, visitor_token, verify_visitor
from app.core.deployment_guard import is_public_route
from app.core.hmac_middleware import verify_meta_signature, verify_shopify_signature, verify_woocommerce_signature
from app.services.widget_api import WidgetAPIService
from app.services.commerce import CommerceService, CommerceUnavailable
from app.services.mcp_catalog import MCPCatalogService
from app.agents.social_sales import SocialSalesAgent, SocialSalesState
from app.api.webhooks.meta_privacy import signed_identity
from app.services.operating_hours import within_hours


def test_generated_widget_parses_as_javascript_and_uses_safe_dom():
    script = WidgetAPIService.generate_embed_script("https://app.example")
    result = subprocess.run(["node", "--check", "-"], input=script, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "agentBubble.innerHTML" not in script
    assert "document.createTextNode" in script
    assert "/api/v1/widget/messages" in script
    assert "data-tenant-id" in script


def test_signed_visitors_cannot_switch_business_or_identity(monkeypatch):
    monkeypatch.setattr(settings, "ENCRYPTION_KEY_SECRET", "offline-test-secret-material-" * 2)
    token = visitor_token("business-a", "visitor-a")
    assert verify_visitor(token, "business-a", "visitor-a")["visitor"] == "visitor-a"
    for business, visitor in [("business-b", "visitor-a"), ("business-a", "visitor-b")]:
        with pytest.raises(HTTPException) as error:
            verify_visitor(token, business, visitor)
        assert error.value.status_code == 401
    with pytest.raises(HTTPException):
        verify_visitor(visitor_token("business-a", "visitor-a", int(time.time()) - 1), "business-a")


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["http://example.com", "https://127.0.0.1", "https://169.254.169.254", "https://example.com:8443"])
async def test_crawler_rejects_nonpublic_destinations(monkeypatch, url):
    async def private_dns(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", private_dns)
    with pytest.raises(HTTPException):
        await public_url(url)


@pytest.mark.parametrize("verify", [verify_meta_signature, verify_shopify_signature, verify_woocommerce_signature])
def test_missing_signing_secret_never_authenticates(verify):
    assert verify(b"{}", "pretend-signature", "") is False


def test_widget_preflight_is_public_but_call_completion_is_not():
    assert is_public_route("/api/v1/widget/chat", "OPTIONS")
    assert is_public_route("/api/v1/widget/session", "POST")
    assert is_public_route("/api/v1/widget/messages", "GET")
    assert not is_public_route("/api/v1/webhooks/telephony/completion", "POST")
    assert not is_public_route("/api/v1/webhooks/meta-privacy/requests/123/complete", "POST")
    assert not is_public_route("/api/v1/webhooks/meta-privacy/requests", "GET")


def test_credential_redaction_is_recursive():
    value = redact({"page_access_token": "not-real", "nested": {"consumer_key": "not-real", "name": "Shop"}})
    assert value["page_access_token"] == "[REDACTED]"
    assert value["nested"] == {"consumer_key": "[REDACTED]", "name": "Shop"}
    assert "page_access_token" not in SocialSalesState.__annotations__


@pytest.mark.asyncio
async def test_unknown_inventory_is_not_inferred_from_documents(monkeypatch):
    monkeypatch.setattr(CommerceService, "stock", AsyncMock(side_effect=CommerceUnavailable("No store connected")))
    result = await MCPCatalogService.stock_check(None, uuid4(), "not available; available colours blue")
    assert result["in_stock"] is False
    assert result["status"] == "unverified_inventory"


@pytest.mark.asyncio
async def test_out_of_stock_never_becomes_an_available_fallback():
    agent = object.__new__(SocialSalesAgent)
    result = await agent._generate_sales_reply_node({
        "message_text": "Buy this", "stock_info": {"status": "verified", "in_stock": False, "item": "Test item"},
        "catalog_results": [], "discount_code": "old-code", "checkout_url": "https://old.example"})
    assert "currently unavailable" in result["reply_text"]
    assert "old-code" not in result["reply_text"]
    assert "https://" not in result["reply_text"]


@pytest.mark.asyncio
async def test_agent_configuration_failure_is_closed():
    agent = object.__new__(SocialSalesAgent)
    agent.db = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("Offline")))
    result = await agent._parse_intent_node({"tenant_id": str(uuid4()), "message_text": "Hello"})
    assert result["agent_active"] is False


@pytest.mark.asyncio
async def test_takeover_is_checked_immediately_before_dispatch(monkeypatch):
    agent = object.__new__(SocialSalesAgent)
    records = [SimpleNamespace(is_active=True, operational_hours={"start":"00:00","end":"23:59","timezone":"UTC"}),
               SimpleNamespace(is_paused_for_human=True)]
    agent.db = SimpleNamespace(execute=AsyncMock(side_effect=[
        SimpleNamespace(scalars=lambda r=r: SimpleNamespace(first=lambda:r)) for r in records]))
    result = await agent._dispatch_channel_reply_node({
        "tenant_id":str(uuid4()),"customer_id":"offline","channel":"web_widget","reply_text":"Must not send"})
    assert result["dispatch_status"] == "paused_before_dispatch"
    assert result["reply_text"] == ""


@pytest.mark.asyncio
async def test_woocommerce_creates_a_real_coupon_not_an_empty_order(monkeypatch):
    record = SimpleNamespace(id=uuid4(), provider="woocommerce", settings={"store_url":"https://merchant.example"})
    monkeypatch.setattr(CommerceService, "integration", AsyncMock(return_value=record))
    calls = []
    async def request(record, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return [] if method == "GET" else {"id": "real-provider-id"}
    monkeypatch.setattr(CommerceService, "request", request)
    result = await CommerceService._create_checkout(None, uuid4(),
        {"in_stock":True,"status":"verified","integration_id":str(record.id),"variant_id":42}, 10, "offline-request")
    assert any(method == "POST" and path == "coupons" for method,path,_ in calls)
    assert not any(path == "orders" for _,path,_ in calls)
    assert "add-to-cart=42" in result["checkout_url"]
    assert result["discount_code"]


def test_meta_privacy_callback_requires_a_real_signature(monkeypatch):
    monkeypatch.setattr(settings, "META_APP_SECRET", "offline-app-secret")
    body = base64.urlsafe_b64encode(json.dumps({"algorithm":"HMAC-SHA256","user_id":"123"}).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(hmac.new(b"offline-app-secret",body.encode(),hashlib.sha256).digest()).decode().rstrip("=")
    assert signed_identity(f"{sig}.{body}") == "123"
    with pytest.raises(HTTPException):
        signed_identity(f"invalid.{body}")


def test_invalid_operating_hours_fail_closed():
    assert not within_hours({"start":"08:00","end":"20:00","timezone":"invalid/zone"})


def test_legacy_discount_calculation_never_fabricates_a_coupon():
    result = MCPCatalogService.discount_generate(uuid4(),40,10)
    assert result["approved_pct"] == 10
    assert result["discount_code"] is None and result["checkout_url"] is None


@pytest.mark.asyncio
async def test_live_stock_does_not_require_uploaded_knowledge(monkeypatch):
    agent = object.__new__(SocialSalesAgent)
    agent.db = None
    monkeypatch.setattr(MCPCatalogService, "catalog_lookup", AsyncMock(return_value=[]))
    stock = AsyncMock(return_value={"status":"verified","in_stock":True})
    monkeypatch.setattr(MCPCatalogService, "stock_check", stock)
    result = await agent._query_mcp_catalog_node({"tenant_id":str(uuid4()),"message_text":"SKU-1"})
    assert result["stock_info"]["in_stock"] is True
    stock.assert_awaited_once()


@pytest.mark.asyncio
async def test_followup_purchase_refreshes_previously_selected_product(monkeypatch):
    agent = object.__new__(SocialSalesAgent)
    agent.db = None
    monkeypatch.setattr(MCPCatalogService, "catalog_lookup", AsyncMock(return_value=[]))
    stock = AsyncMock(return_value={"status":"verified","in_stock":False})
    monkeypatch.setattr(MCPCatalogService, "stock_check", stock)
    result = await agent._query_mcp_catalog_node({
        "tenant_id":str(uuid4()), "message_text":"buy it",
        "stock_info":{"status":"verified","in_stock":True,"sku":"SKU-1"}})
    assert result["stock_info"]["in_stock"] is False
    assert stock.await_args.kwargs["sku_or_title"] == "SKU-1"


@pytest.mark.asyncio
async def test_scoped_queries_hide_other_workspaces_even_for_db_owner():
    from sqlalchemy import select, delete
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.db.session import async_engine
    test_engine = create_async_engine(async_engine.url, poolclass=NullPool)
    AsyncSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)
    from app.db.models import Tenant, Conversation, DeliveryReceipt, PrivacyRequest
    own, other, conversation = uuid4(), uuid4(), uuid4()
    async with AsyncSessionLocal() as db:
        db.add_all([Tenant(id=own,name="Isolation fixture A"),Tenant(id=other,name="Isolation fixture B")])
        await db.flush()
        db.add(Conversation(id=conversation,tenant_id=other,channel="web_widget",customer_identifier="offline"))
        await db.commit()
        db.info["tenant_id"] = str(own)
        assert (await db.execute(select(Conversation).where(Conversation.id == conversation))).scalar_one_or_none() is None
        db.info.clear()
        assert (await db.execute(select(Conversation).where(Conversation.id == conversation))).scalar_one_or_none() is not None
        # All new safety tables must actually exist in the migrated dev schema.
        await db.execute(select(DeliveryReceipt).limit(0))
        await db.execute(select(PrivacyRequest).limit(0))
        await db.execute(delete(Tenant).where(Tenant.id.in_([own,other])))
        await db.commit()
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_body_limits_reject_chunked_payloads_before_parsing():
    from app.core.request_limits import RequestLimitsMiddleware
    called = False
    async def target(scope, receive, send):
        nonlocal called
        called = True
    chunks = iter([{"type":"http.request","body":b"a" * 600000,"more_body":True},
                   {"type":"http.request","body":b"b" * 600000,"more_body":False}])
    async def receive(): return next(chunks)
    output = []
    async def send(message): output.append(message)
    await RequestLimitsMiddleware(target)({"type":"http","path":"/api/v1/widget/chat","headers":[]}, receive, send)
    assert not called
    assert output[0]["status"] == 413


@pytest.mark.asyncio
async def test_checkpoint_identity_cannot_be_overridden_by_caller():
    agent = object.__new__(SocialSalesAgent)
    agent.graph = SimpleNamespace(ainvoke=AsyncMock(return_value={}))
    await agent.execute({"tenant_id":"business-a","channel":"web_widget",
                         "customer_id":"signed-visitor","page_access_token":"must-not-persist"},
                        thread_id="somebody-elses-session")
    state = agent.graph.ainvoke.await_args.args[0]
    config = agent.graph.ainvoke.await_args.kwargs["config"]
    assert config["configurable"]["thread_id"] == "business-a:web_widget:signed-visitor"
    assert "page_access_token" not in state


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["send_facebook_messenger_dm","send_instagram_dm"])
async def test_meta_never_simulates_delivery_even_in_preview(method):
    from app.services.meta_api import MetaAPIClient
    with pytest.raises(RuntimeError):
        await getattr(MetaAPIClient, method)("123", "Offline test", "test_fake_token")


@pytest.mark.asyncio
async def test_instagram_asset_must_belong_to_verified_facebook_page(monkeypatch):
    from app.api.routes.tenant import meta_select_page
    from app.services.meta_api import MetaAPIClient
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: object())))
    monkeypatch.setattr(MetaAPIClient, "get_page_identity", AsyncMock(return_value={
        "id":"123","name":"Offline","instagram_business_account":{"id":"500"}}))
    subscription = AsyncMock()
    monkeypatch.setattr(MetaAPIClient, "subscribe_page_to_webhooks", subscription)
    with pytest.raises(HTTPException) as error:
        await meta_select_page(uuid4(),SimpleNamespace(page_id="123",page_access_token="opaque",
                                                      instagram_account_id="600"),db)
    assert error.value.status_code == 400
    subscription.assert_not_awaited()


def test_nested_credentials_are_sealed_not_just_redacted(monkeypatch):
    from app.core.safety import seal_credentials
    monkeypatch.setattr("app.core.security.encrypt_token",lambda value:f"sealed-{value}")
    result=seal_credentials({"label":"Store","nested":[{"api_key":"offline","password":"enc:existing"}]})
    assert result == {"label":"Store","nested":[{"api_key":"enc:sealed-offline","password":"enc:existing"}]}


@pytest.mark.asyncio
async def test_published_simulators_do_not_run(monkeypatch):
    from app.core.request_limits import RequestLimitsMiddleware
    monkeypatch.setattr(settings,"ENVIRONMENT","production")
    target=AsyncMock()
    output=[]
    async def send(message): output.append(message)
    await RequestLimitsMiddleware(target)({"type":"http","path":"/api/v1/workbench/simulate-order"},None,send)
    target.assert_not_awaited()
    assert output[0]["status"] == 409


@pytest.mark.asyncio
async def test_widget_origin_updates_do_not_require_or_replace_profile_fields():
    from app.api.routes.tenant import update_widget_origin, WidgetOriginUpdate
    tenant=SimpleNamespace(domain=None,name="Keep business name",currency="BDT")
    db=SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda:tenant)),commit=AsyncMock())
    result=await update_widget_origin(uuid4(),WidgetOriginUpdate(domain="https://qa.example"),db)
    assert result["domain"]=="https://qa.example"
    assert tenant.name=="Keep business name" and tenant.currency=="BDT"
    with pytest.raises(HTTPException):
        await update_widget_origin(uuid4(),WidgetOriginUpdate(domain="http://qa.example"),db)


@pytest.mark.asyncio
async def test_websocket_members_cannot_select_another_business(monkeypatch):
    from app.core.deployment_guard import member_websocket_allowed
    own,other=uuid4(),uuid4()
    class FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def execute(self,statement):
            values=statement.compile().params.values()
            match=own in values and "verified-subject" in values
            return SimpleNamespace(scalar_one_or_none=lambda:object() if match else None)
    monkeypatch.setattr("app.db.session.AsyncSessionLocal",FakeSession)
    assert await member_websocket_allowed(f"/ws/workbench/{own}","verified-subject")
    assert not await member_websocket_allowed(f"/ws/workbench/{other}","verified-subject")
    assert not await member_websocket_allowed(f"/ws/workbench/{own}","someone-else")


@pytest.mark.asyncio
@pytest.mark.parametrize("headers,allowed",[
    ({"referer":"https://qa.example/dashboard/integration-hub"},True),
    ({"sec-fetch-site":"same-origin"},True),
    ({"referer":"https://attacker.example/"},False),
    ({"origin":"https://attacker.example","referer":"https://qa.example/"},False),
])
async def test_widget_polling_accepts_same_origin_get_without_weakening_cross_origin_check(headers,allowed):
    from app.api.routes.widget import authorize_origin
    tenant=SimpleNamespace(domain="https://qa.example",settings={})
    db=SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda:tenant)))
    request=SimpleNamespace(method="GET",headers=headers,url=SimpleNamespace(scheme="https",netloc="qa.example"))
    if allowed:
        assert await authorize_origin(request,db,uuid4()) is tenant
    else:
        with pytest.raises(HTTPException) as error:
            await authorize_origin(request,db,uuid4())
        assert error.value.status_code==403
