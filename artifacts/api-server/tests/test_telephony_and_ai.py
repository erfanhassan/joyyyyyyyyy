import pytest
from uuid import UUID
import uuid
from app.core.config import settings
from app.services.embedding_service import EmbeddingService
from app.services.telephony_service import TelephonyService, generate_livekit_token
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
async def test_livekit_and_amberit_diagnostics():
    """Verify live connectivity to LiveKit Cloud and Amber IT PABX SIP gateway."""
    status_res = await TelephonyService.test_telephony_status()
    assert status_res["status"] in ("healthy", "partial")
    diag = status_res["diagnostics"]
    
    # LiveKit Cloud
    assert diag["livekit"]["connected"] is True
    assert "livekit.cloud" in diag["livekit"]["cluster_url"]
    assert diag["livekit"]["models"]["llm"] == "deepseek-ai/deepseek-v3"

    # Amber IT Bangladesh PABX
    assert diag["amberit"]["connected"] is True
    assert diag["amberit"]["phone_number"] == "+8809611901539"
    assert diag["amberit"]["extension"] == "524851"


@pytest.mark.asyncio
async def test_outbound_telephony_dispatch():
    """Verify outbound confirmation call generation and LiveKit room token creation."""
    tenant_id = UUID("a1e6f58d-b575-420e-b4d6-1fef0064e746")
    order_id = uuid.uuid4()

    dispatch = await TelephonyService.initiate_outbound_call(
        order_id=order_id,
        customer_phone="+8801712345678",
        customer_name="Tahmid Rahman",
        shipping_address="House 42, Road 11, Banani, Dhaka",
        order_items="Silk Panjabi (Size 42)",
        order_total=4500.00,
        tenant_id=tenant_id,
        merchant_name="Joy Luxury Store",
    )

    assert dispatch["status"] == "initiated"
    assert dispatch["sip_caller_id"] == "+8809611901539"
    assert dispatch["sip_extension"] == "524851"
    assert dispatch["livekit_room_created"] is True
    assert dispatch["livekit_token"] is not None
