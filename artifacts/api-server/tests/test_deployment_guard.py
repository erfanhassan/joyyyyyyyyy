"""Offline safety checks; never call AI, storefronts, or phone services."""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.main import app
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


@pytest.mark.parametrize("provider", ["meta", "shopify", "woocommerce", "custom"])
def test_unconfigured_webhooks_are_closed(production_client, provider):
    assert production_client.post(f"/api/v1/webhooks/{provider}", json={}).status_code == 403


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
