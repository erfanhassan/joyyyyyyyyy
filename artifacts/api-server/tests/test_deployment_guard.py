"""Offline safety checks; never call AI, storefronts, or phone services."""
import gzip
import pytest
import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.main import app
from app import main as main_module
from app.core import deployment_guard
from app.core.config import settings
from app.core.security import encrypt_token, decrypt_token


@pytest.fixture
def production_client(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "META_APP_SECRET", "")
    monkeypatch.setattr(settings, "SHOPIFY_API_SECRET", "")
    monkeypatch.setattr(settings, "WOOCOMMERCE_WEBHOOK_SECRET", "")
    monkeypatch.setattr(settings, "ENCRYPTION_KEY_SECRET", "")
    monkeypatch.setattr(settings, "META_VERIFY_TOKEN", "joy_meta_verify_token_default")
    monkeypatch.setattr(settings, "CLERK_SECRET_KEY", "")
    monkeypatch.setattr(settings, "CLERK_PUBLISHABLE_KEY", "")
    monkeypatch.setattr(settings, "JOY_INITIAL_ADMIN_EMAIL", "")
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("path", [
    "/api/v1/tenant/a1e6f58d-b575-420e-b4d6-1fef0064e746",
    "/api/v1/tenant/a1e6f58d-b575-420e-b4d6-1fef0064e746/integrations",
    "/api/tenant/a1e6f58d-b575-420e-b4d6-1fef0064e746",
    "/api/v1/workbench/takeover",
    "/api/v1/knowledge/query",
    "/api/v1/webhooks/telephony/completion",
    "/api/webhooks/telephony/completion",
])
@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE"])
def test_public_administration_is_closed(production_client, path, method):
    assert production_client.request(method, path).status_code == 403


def test_public_websocket_is_closed(production_client):
    with pytest.raises(WebSocketDisconnect):
        with production_client.websocket_connect(
            "/ws/workbench/a1e6f58d-b575-420e-b4d6-1fef0064e746"
        ):
            pytest.fail("An unauthenticated production socket was accepted")


def test_health_and_public_widget_remain_available(production_client):
    health = production_client.get("/api/healthz")
    assert health.status_code == 200
    assert health.json()["administration_available"] is False
    assert production_client.get("/api/v1/widget/widget.js").status_code == 200


def test_clerk_proxy_is_public_but_fails_closed_when_not_configured(production_client):
    response = production_client.get("/api/__clerk/v1/environment")
    assert response.status_code == 503
    assert response.json()["detail"] == "Sign-in proxy is not configured."


def test_configured_production_admin_requires_a_verified_session(
    production_client, monkeypatch
):
    monkeypatch.setattr(settings, "CLERK_SECRET_KEY", "test-only-secret-key")
    monkeypatch.setattr(settings, "CLERK_PUBLISHABLE_KEY", "test-only-publishable-key")
    monkeypatch.setattr(settings, "JOY_INITIAL_ADMIN_EMAIL", "owner@example.test")
    monkeypatch.delenv("REPLIT_DOMAINS", raising=False)

    response = production_client.get(
        "/api/v1/tenant/a1e6f58d-b575-420e-b4d6-1fef0064e746"
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Sign in to continue."


def test_verified_owner_can_reach_protected_auth_endpoint(production_client, monkeypatch):
    monkeypatch.setattr(settings, "CLERK_SECRET_KEY", "test-only-secret-key")
    monkeypatch.setattr(settings, "CLERK_PUBLISHABLE_KEY", "test-only-publishable-key")
    monkeypatch.setattr(settings, "JOY_INITIAL_ADMIN_EMAIL", "owner@example.test")
    monkeypatch.setattr(settings, "META_APP_ID", "test-meta-app-id")

    async def owner(_scope):
        return {"user_id": "user_test"}

    monkeypatch.setattr(deployment_guard, "authenticate_owner", owner)
    response = production_client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == {
        "authenticated": True,
        "role": "owner",
        "meta_app_id": "test-meta-app-id",
        "meta_login_config_id": "",
        "whatsapp_embedded_signup_config_id": "",
    }


def test_clerk_proxy_forwards_required_headers_and_cookie(production_client, monkeypatch):
    monkeypatch.setattr(settings, "CLERK_SECRET_KEY", "test-only-clerk-secret")
    monkeypatch.setenv("REPLIT_DOMAINS", "joy.example.test")
    calls = []

    real_client = httpx.AsyncClient

    async def upstream(request):
        calls.append((request.method, str(request.url), request.headers, request.content))
        return httpx.Response(
            200,
            headers={
                "content-type": "application/json",
                "set-cookie": "clerk-session=test; Path=/; Secure; HttpOnly",
            },
            stream=httpx.ByteStream(b'{"ok":true}'),
        )

    monkeypatch.setattr(
        main_module.httpx, "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(upstream), **kwargs),
    )
    response = production_client.post(
        "/api/__clerk/v1/client?test=1",
        content=b"request-body",
        headers={
            "host": "testserver",
            "x-forwarded-host": "joy.example.test",
            "x-forwarded-proto": "https",
            "cookie": "__client_uat=1",
        },
    )

    assert response.status_code == 200
    assert response.content == b'{"ok":true}'
    assert response.headers["set-cookie"].startswith("clerk-session=test")
    method, url, headers, body = calls[0]
    assert method == "POST"
    assert url == "https://frontend-api.clerk.dev/v1/client?test=1"
    assert headers["Clerk-Proxy-Url"] == "https://joy.example.test/api/__clerk"
    assert headers["Clerk-Secret-Key"] == "test-only-clerk-secret"
    assert headers["cookie"] == "__client_uat=1"
    assert body == b"request-body"


@pytest.mark.parametrize("encoding", ["gzip", "br", "zstd"])
def test_clerk_proxy_preserves_encoded_wire_bytes(production_client, monkeypatch, encoding):
    monkeypatch.setattr(settings, "CLERK_SECRET_KEY", "test-only-clerk-secret")
    source = b'console.log("Clerk script loads");'
    wire = gzip.compress(source) if encoding == "gzip" else b"\x5b\x54\xec\x14compressed"
    real_client = httpx.AsyncClient

    async def upstream(_request):
        return httpx.Response(
            200,
            headers={"content-type": "application/javascript", "content-encoding": encoding},
            stream=httpx.ByteStream(wire),
        )

    monkeypatch.setattr(
        main_module.httpx, "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(upstream), **kwargs),
    )
    # Capture ASGI messages directly: a test HTTP client may itself decode the
    # body, hiding the exact compressed-byte regression that broke production.
    import asyncio
    messages = []

    async def capture(message):
        messages.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http", "method": "GET", "path": "/api/__clerk/npm/clerk.js",
        "query_string": b"", "headers": [(b"host", b"joy.example.test")],
        "scheme": "https", "server": ("joy.example.test", 443), "client": ("127.0.0.1", 1),
        "http_version": "1.1",
    }
    asyncio.run(app(scope, receive, capture))
    headers = dict(messages[0]["headers"])
    assert messages[0]["status"] == 200
    assert headers[b"content-encoding"] == encoding.encode()
    assert headers[b"content-length"] == str(len(wire)).encode()
    assert b"".join(item.get("body", b"") for item in messages[1:]) == wire


@pytest.mark.parametrize("provider", ["meta", "shopify", "woocommerce", "custom"])
def test_unconfigured_webhooks_are_closed(production_client, provider):
    assert production_client.post(f"/api/v1/webhooks/{provider}", json={}).status_code in (401, 403)


def test_configured_webhook_still_requires_signature(production_client, monkeypatch):
    monkeypatch.setattr(settings, "META_APP_SECRET", "test-only-signature-key")
    assert production_client.post("/api/v1/webhooks/meta", json={}).status_code == 401


@pytest.mark.parametrize("key", ["", "short", "joy_master_aes256_secret_key_change_in_production_32b"])
def test_provider_credentials_reject_missing_or_public_keys(monkeypatch, key):
    monkeypatch.setattr(settings, "ENCRYPTION_KEY_SECRET", key)
    with pytest.raises(HTTPException) as error:
        encrypt_token("test-only-provider-token")
    assert error.value.status_code == 503


def test_private_provider_encryption_round_trip():
    key = "test-only-private-key-material-at-least-32-characters"
    encrypted = encrypt_token("test-only-provider-token", key)
    assert encrypted != "test-only-provider-token"
    assert decrypt_token(encrypted, key) == "test-only-provider-token"
