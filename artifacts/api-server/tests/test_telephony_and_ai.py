import pytest
from uuid import UUID
import uuid
from app.core.config import settings
from app.services.embedding_service import EmbeddingService
from app.services.telephony_service import TelephonyService, OutboundCallingUnavailable
from app.db.session import AsyncSessionLocal
from app.db.models import Order


@pytest.mark.asyncio
async def test_openai_embedding_generation():
    """Verify OpenAI 1536-dim embedding generation."""
    assert settings.OPENAI_API_KEY.startswith("sk-")
    vector = await EmbeddingService.get_embedding("Silk Panjabi in Emerald Green")
    assert len(vector) == 1536
    assert isinstance(vector[0], float)


@pytest.mark.asyncio
async def test_livekit_and_amberit_diagnostics(monkeypatch):
    """Missing credentials never imply a verified SIP trunk or calling readiness."""
    monkeypatch.setattr(settings, "LIVEKIT_API_KEY", "")
    status_res = await TelephonyService.test_telephony_status()
    assert status_res["status"] == "setup_required"
    assert status_res["calling_available"] is False
    diag = status_res["diagnostics"]
    assert diag["livekit"]["connected"] is False
    assert diag["amberit"]["connected"] is False


@pytest.mark.asyncio
async def test_outbound_telephony_dispatch(monkeypatch):
    """Missing telephony credentials must raise OutboundCallingUnavailable."""
    monkeypatch.setattr(settings, "LIVEKIT_API_KEY", "")
    tenant_id = UUID("a1e6f58d-b575-420e-b4d6-1fef0064e746")
    order_id = uuid.uuid4()

    with pytest.raises(OutboundCallingUnavailable):
        await TelephonyService.initiate_outbound_call(
            order_id=order_id, customer_phone="+8801700000000",
            customer_name="Test Customer", shipping_address="Test address",
            order_items="Test item", order_total=100.00, tenant_id=tenant_id,
        )
