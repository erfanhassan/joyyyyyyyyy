import asyncio
from types import SimpleNamespace

import pytest
from starlette.datastructures import Headers

from app.core import clerk_auth
from app.core.config import settings


def _scope(origin="https://joy.example.test", host="joy.example.test"):
    return {
        "type": "http",
        "headers": [
            (b"host", host.encode()),
            (b"origin", origin.encode()),
        ],
    }


def test_clerk_auth_requires_all_server_configuration(monkeypatch):
    monkeypatch.setattr(settings, "CLERK_SECRET_KEY", "server-key")
    monkeypatch.setattr(settings, "CLERK_PUBLISHABLE_KEY", "publishable-key")
    monkeypatch.setattr(settings, "JOY_INITIAL_ADMIN_EMAIL", "")
    assert not clerk_auth.clerk_auth_configured()

    monkeypatch.setattr(settings, "JOY_INITIAL_ADMIN_EMAIL", "owner@example.test")
    assert clerk_auth.clerk_auth_configured()


def test_authorized_origin_must_be_a_published_domain(monkeypatch):
    monkeypatch.setenv("REPLIT_DOMAINS", "joy.example.test,joy.replit.app")
    assert (
        clerk_auth._authorized_origin(
            Headers(scope=_scope())
        )
        == "https://joy.example.test"
    )
    assert (
        clerk_auth._authorized_origin(
            Headers(scope=_scope(origin="https://attacker.example", host="joy.example.test"))
        )
        is None
    )
    assert (
        clerk_auth._authorized_origin(
            Headers(scope=_scope(origin="http://joy.example.test"))
        )
        is None
    )


def test_authentication_accepts_only_the_configured_verified_owner(monkeypatch):
    monkeypatch.setenv("REPLIT_DOMAINS", "joy.example.test")
    monkeypatch.setattr(settings, "CLERK_SECRET_KEY", "test-secret")
    monkeypatch.setattr(settings, "JOY_INITIAL_ADMIN_EMAIL", "Owner@example.test")

    async def fake_authenticate(request, options):
        assert options.authorized_parties == ["https://joy.example.test"]
        return SimpleNamespace(is_signed_in=True, payload={"sub": "user_test"})

    async def owner_email(_user_id):
        return "owner@example.test"

    monkeypatch.setattr(clerk_auth, "authenticate_request_async", fake_authenticate)
    monkeypatch.setattr(clerk_auth, "_verified_primary_email", owner_email)

    identity = asyncio.run(clerk_auth.authenticate_owner(_scope()))
    assert identity == {"user_id": "user_test"}


def test_other_signed_in_accounts_are_denied(monkeypatch):
    monkeypatch.setenv("REPLIT_DOMAINS", "joy.example.test")
    monkeypatch.setattr(settings, "CLERK_SECRET_KEY", "test-secret")
    monkeypatch.setattr(settings, "JOY_INITIAL_ADMIN_EMAIL", "owner@example.test")

    async def fake_authenticate(_request, _options):
        return SimpleNamespace(is_signed_in=True, payload={"sub": "user_other"})

    async def other_email(_user_id):
        return "other@example.test"

    monkeypatch.setattr(clerk_auth, "authenticate_request_async", fake_authenticate)
    monkeypatch.setattr(clerk_auth, "_verified_primary_email", other_email)

    with pytest.raises(clerk_auth.ClerkAuthFailure) as failure:
        asyncio.run(clerk_auth.authenticate_owner(_scope()))
    assert failure.value.status_code == 403
