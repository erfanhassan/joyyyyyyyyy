from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.websockets import workbench
from app.services.whatsapp import WhatsAppService


def test_template_variables_are_counted_and_formatted_by_component():
    template = {
        "components": [
            {"type": "HEADER", "format": "TEXT", "text": "Hi {{1}}"},
            {"type": "BODY", "text": "Order {{1}} costs {{2}}"},
            {"type": "BUTTONS", "buttons": [
                {"type": "URL", "url": "https://shop.example/{{1}}"},
                {"type": "QUICK_REPLY", "text": "Help"},
            ]},
        ],
    }
    layout, supported = WhatsAppService.template_layout(template)
    assert supported
    assert WhatsAppService.template_variables_count(template) == 4
    assert WhatsAppService.template_components(layout, ["Mina", "A-12", "$5", "receipt"]) == [
        {"type": "header", "parameters": [{"type": "text", "text": "Mina"}]},
        {"type": "body", "parameters": [
            {"type": "text", "text": "A-12"},
            {"type": "text", "text": "$5"},
        ]},
        {"type": "button", "sub_type": "url", "index": "0",
         "parameters": [{"type": "text", "text": "receipt"}]},
    ]


def test_template_component_builder_rejects_missing_or_blank_variables():
    with pytest.raises(ValueError, match="exactly 1"):
        WhatsAppService.template_components([{"type": "body", "count": 1}], [])
    with pytest.raises(ValueError, match="must have a value"):
        WhatsAppService.template_components([{"type": "body", "count": 1}], [" "])


def test_media_header_template_is_marked_unsupported():
    layout, supported = WhatsAppService.template_layout({
        "components": [{"type": "HEADER", "format": "IMAGE"}],
    })
    assert layout == []
    assert not supported


@pytest.mark.asyncio
async def test_template_send_requires_recorded_opt_in_before_provider_access():
    db = SimpleNamespace(execute=AsyncMock())
    conversation = SimpleNamespace(tenant_id=uuid4(), whatsapp_opt_in=False)
    with pytest.raises(PermissionError, match="opt-in"):
        await WhatsAppService.send_template(db, conversation, "order_update", "en", [])
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_template_send_rechecks_approval_from_meta(monkeypatch):
    integration = SimpleNamespace(
        access_token_encrypted="encrypted",
        settings={"waba_id": "123", "phone_number_id": "456"},
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalar_one_or_none=lambda: integration)))
    conversation = SimpleNamespace(
        tenant_id=uuid4(), whatsapp_opt_in=True, customer_identifier="15551234567")
    monkeypatch.setattr("app.services.whatsapp.decrypt_token", lambda _token: "token")
    api = AsyncMock(return_value={"data": [{
        "name": "order_update", "language": "en", "status": "REJECTED",
        "components": [{"type": "BODY", "text": "Hello {{1}}"}],
    }]})
    monkeypatch.setattr(WhatsAppService, "api", api)

    with pytest.raises(PermissionError, match="not currently approved"):
        await WhatsAppService.send_template(db, conversation, "order_update", "en", ["Mina"])
    api.assert_awaited_once()
    assert api.await_args.args[1] == "GET"


@pytest.mark.asyncio
async def test_template_send_sends_and_uses_only_the_approved_template(monkeypatch):
    integration = SimpleNamespace(
        access_token_encrypted="encrypted",
        settings={"waba_id": "123", "phone_number_id": "456"},
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalar_one_or_none=lambda: integration)))
    conversation = SimpleNamespace(
        tenant_id=uuid4(), whatsapp_opt_in=True, customer_identifier="15551234567")
    template = {
        "name": "order_update", "language": "en", "status": "APPROVED",
        "components": [{"type": "BODY", "text": "Hello {{1}}"}],
    }
    calls = []

    async def fake_api(_token, method, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "GET":
            return {"data": [template]}
        return {"messages": [{"id": "wamid.accepted"}]}

    monkeypatch.setattr("app.services.whatsapp.decrypt_token", lambda _token: "token")
    monkeypatch.setattr(WhatsAppService, "api", fake_api)
    result, returned_template = await WhatsAppService.send_template(
        db, conversation, "order_update", "en", ["Mina"])

    assert returned_template is template
    assert result["messages"][0]["id"] == "wamid.accepted"
    assert calls[1][0:2] == ("POST", "456/messages")
    assert calls[1][2]["json"]["template"]["components"] == [{
        "type": "body", "parameters": [{"type": "text", "text": "Mina"}],
    }]


@pytest.mark.asyncio
async def test_consent_endpoint_records_source_and_audit_log(monkeypatch):
    conversation = SimpleNamespace(
        id=uuid4(), tenant_id=uuid4(), channel="whatsapp",
        whatsapp_opt_in=False, whatsapp_opt_in_updated_at=None, whatsapp_opt_in_source=None)
    logs = []

    class FakeDb:
        async def execute(self, _statement):
            return SimpleNamespace(scalar_one_or_none=lambda: conversation)

        def add(self, value):
            logs.append(value)

        async def flush(self):
            if logs:
                logs[-1].id = uuid4()

        async def commit(self):
            return None

    monkeypatch.setattr(workbench.HITLOrchestrator, "broadcast_workbench_event", AsyncMock())
    result = await workbench.update_whatsapp_consent(
        workbench.WhatsAppConsentRequest(
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            opted_in=True,
            source="Customer checkout form",
        ),
        FakeDb(),
    )
    assert result["opted_in"] is True
    assert result["source"] == "Customer checkout form"
    assert logs[0].raw_payload == {
        "event_type": "whatsapp_consent",
        "opted_in": True,
        "source": "Customer checkout form",
    }


@pytest.mark.asyncio
async def test_consent_endpoint_requires_source_to_record_opt_in():
    with pytest.raises(HTTPException) as error:
        await workbench.update_whatsapp_consent(
            workbench.WhatsAppConsentRequest(
                tenant_id=uuid4(), conversation_id=uuid4(), opted_in=True, source=" "),
            SimpleNamespace(),
        )
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_template_endpoint_logs_delivery_in_the_selected_conversation(monkeypatch):
    conversation = SimpleNamespace(id=uuid4(), tenant_id=uuid4(), channel="whatsapp")
    added = []

    class FakeDb:
        async def execute(self, _statement):
            return SimpleNamespace(scalar_one_or_none=lambda: conversation)

        def add(self, value):
            value.id = uuid4()
            added.append(value)

        async def commit(self):
            return None

    template = {"name": "order_update", "language": "en"}
    monkeypatch.setattr(WhatsAppService, "send_template", AsyncMock(return_value=(
        {"messages": [{"id": "wamid.accepted"}]}, template)))
    monkeypatch.setattr(workbench.HITLOrchestrator, "broadcast_workbench_event", AsyncMock())

    response = await workbench.send_whatsapp_template(
        workbench.WhatsAppTemplateSendRequest(
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            name="order_update",
            language="en",
            variables=["A-12"],
        ),
        FakeDb(),
    )

    assert response["status"] == "accepted"
    assert added[0].conversation_id == conversation.id
    assert added[0].raw_payload["dispatch_status"] == "dispatched_whatsapp_template"
    assert added[0].raw_payload["provider_message_id"] == "wamid.accepted"
