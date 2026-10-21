"""Meta credential failures stop automatic delivery and expose safe recovery state."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.meta_api import MetaAPIClient
from app.services.meta_credentials import (
    MetaCredentialError,
    credential_error,
    mark_reconnect_required,
)
from app.services.whatsapp import WhatsAppService


@pytest.mark.parametrize("code,subcode", [
    (190, None),
    (190, 463),
    (102, None),
    (10, None),
    (200, None),
])
def test_meta_oauth_and_permission_errors_require_reconnect(code, subcode):
    error = {"code": code, "message": "private provider detail"}
    if subcode is not None:
        error["error_subcode"] = subcode
    result = credential_error({"error": error}, "Instagram")
    assert isinstance(result, MetaCredentialError)
    assert result.channel == "Instagram"
    assert "private provider detail" not in str(result)


def test_unrelated_meta_provider_errors_remain_retryable():
    assert credential_error({"error": {"code": 2, "message": "temporary failure"}}, "Facebook") is None


@pytest.mark.asyncio
async def test_meta_send_surfaces_safe_reconnect_error(monkeypatch):
    real_client = httpx.AsyncClient

    async def upstream(_request):
        return httpx.Response(400, json={
            "error": {"code": 190, "message": "token value must not be exposed"},
        })

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(upstream), **kwargs,
    ))
    with pytest.raises(MetaCredentialError, match="Instagram") as error:
        await MetaAPIClient.send_instagram_dm("customer", "hello", "access-token")
    assert "token value" not in str(error.value)


@pytest.mark.asyncio
async def test_whatsapp_api_detects_revoked_permissions(monkeypatch):
    real_client = httpx.AsyncClient

    async def upstream(_request):
        return httpx.Response(403, json={
            "error": {"code": 10, "message": "sensitive provider response"},
        })

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(upstream), **kwargs,
    ))
    with pytest.raises(MetaCredentialError, match="WhatsApp") as error:
        await WhatsAppService.api("access-token", "POST", "123/messages", json={})
    assert "sensitive provider response" not in str(error.value)


def test_reconnect_state_is_safe_and_idempotent():
    integration = SimpleNamespace(settings={"page_id": "123", "page_name": "Store"})
    mark_reconnect_required(integration, "Instagram")
    first_detected_at = integration.settings["attention_detected_at"]
    mark_reconnect_required(integration, "Facebook")
    assert integration.settings["connection_status"] == "needs_reconnect"
    assert integration.settings["attention_channel"] == "Instagram"
    assert integration.settings["attention_detected_at"] == first_detected_at
    assert integration.settings["page_id"] == "123"


@pytest.mark.asyncio
async def test_manual_review_delivery_failure_is_terminal(monkeypatch):
    from app.services import webhook_jobs

    job = SimpleNamespace(
        id="job-id", provider="meta", payload={}, tenant_id="tenant-id",
        event_id="event-id", status="pending", attempts=0,
        lease_until=None, available_at=None, last_error=None,
    )

    class FakeSession:
        info = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, *_args, **_kwargs):
            return SimpleNamespace(scalar_one_or_none=lambda: job)

        async def commit(self):
            return None

    async def fail_with_manual_review(*_args):
        raise webhook_jobs.ManualReviewRequired("Review before resending.")

    monkeypatch.setattr(webhook_jobs, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr("app.api.webhooks.meta.process_meta_background", fail_with_manual_review)
    assert await webhook_jobs.run_once() is True
    assert job.status == "dead"
    assert job.last_error == "ManualReviewRequired"
    assert job.attempts == 1
