"""Offline integration checks: no provider messages, phone calls, or database writes."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.api.routes import tenant as routes
from app.core.config import settings
from app.services.meta_api import MetaAPIClient
from app.services.telephony_service import TelephonyService


@pytest.mark.asyncio
async def test_phone_endpoint_rejects_before_saving_an_order():
    db = SimpleNamespace(add=Mock(), commit=AsyncMock())
    with pytest.raises(HTTPException) as error:
        await routes.trigger_test_call(uuid4(), routes.OutboundCallRequest(), db)
    assert error.value.status_code == 503
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_telephony_diagnostics_do_not_require_a_fake_integration_record(monkeypatch):
    monkeypatch.setattr(settings, "LIVEKIT_API_KEY", "")
    db = SimpleNamespace(execute=AsyncMock())
    result = await routes.test_integration_connection(uuid4(), "telephony", db)
    assert result["status"] == "setup_required"
    assert result["connected"] is False
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_healthy_livekit_does_not_mean_sip_is_ready(monkeypatch):
    monkeypatch.setattr(settings, "LIVEKIT_URL", "wss://voice.example.test")
    monkeypatch.setattr(settings, "LIVEKIT_API_KEY", "test-only-key")
    monkeypatch.setattr(settings, "LIVEKIT_API_SECRET", "test-only-secret")
    real_client = httpx.AsyncClient
    calls = []

    async def upstream(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"rooms": []})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(upstream), **kwargs,
    ))
    result = await TelephonyService.test_telephony_status()
    assert calls == ["/twirp/livekit.RoomService/ListRooms"]
    assert result["diagnostics"]["livekit"]["connected"] is True
    assert result["diagnostics"]["amberit"]["connected"] is False
    assert result["calling_available"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["shopify", "woocommerce", "custom"])
async def test_stored_credentials_are_not_falsely_verified(monkeypatch, provider):
    monkeypatch.setattr(routes, "decrypt_token", lambda _token: "real-token-placeholder")
    record = SimpleNamespace(is_active=True, access_token_encrypted="ciphertext", settings={})
    db = SimpleNamespace(execute=AsyncMock(return_value=Mock(scalar_one_or_none=lambda: record)))
    result = await routes.test_integration_connection(uuid4(), provider, db)
    assert result["connected"] is False
    assert result["status"] == "not_verified"
    assert "latency_ms" not in result


@pytest.mark.asyncio
async def test_meta_cannot_save_a_fake_page(monkeypatch):
    with pytest.raises(HTTPException):
        await MetaAPIClient.get_page_identity("123", "EAAG_simulated_token")


@pytest.mark.asyncio
async def test_meta_requires_successful_webhook_subscription(monkeypatch):
    monkeypatch.setattr(MetaAPIClient, "get_page_identity", AsyncMock(
        return_value={"id": "123", "name": "Test Page"},
    ))
    monkeypatch.setattr(MetaAPIClient, "subscribe_page_to_webhooks", AsyncMock(
        return_value={"success": False},
    ))
    monkeypatch.setattr(routes, "encrypt_token", lambda _value: "ciphertext")
    db = SimpleNamespace(
        execute=AsyncMock(return_value=Mock(scalar_one_or_none=lambda: object())),
        add=Mock(), commit=AsyncMock(),
    )
    with pytest.raises(HTTPException) as error:
        await routes.meta_select_page(
            uuid4(),
            routes.MetaSelectPageRequest(page_id="123", page_name="Test", page_access_token="placeholder"),
            db,
        )
    assert error.value.status_code == 400
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("method,kwargs", [
    ("send_facebook_messenger_dm", {"recipient_id": "test", "message_text": "Test"}),
    ("send_instagram_dm", {"recipient_id": "test", "message_text": "Test"}),
    ("reply_public_comment", {"comment_id": "test", "message_text": "Test"}),
    ("send_comment_to_dm_handshake", {"comment_id": "test", "private_message_text": "Test"}),
])
async def test_production_never_reports_simulated_delivery(monkeypatch, method, kwargs):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="did not confirm delivery"):
        await getattr(MetaAPIClient, method)(**kwargs)
