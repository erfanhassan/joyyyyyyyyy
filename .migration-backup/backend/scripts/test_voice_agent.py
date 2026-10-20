import asyncio
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models import Tenant, Order, AgentConfig, Conversation, InteractionLog
from app.agents.voice_confirmation import VoiceConfirmationAgent, is_within_calling_hours
from app.services.order_sync import OrderSyncService
from app.api.webhooks.telephony import TelephonyCompletionPayload, handle_telephony_completion

async def run_tests():
    print("--- [TEST 1: Timezone & Calling Hours Rules] ---")
    # Test Bangladesh daytime vs nighttime
    # Note: customer timezone logic
    allowed_dhaka, msg_dhaka = is_within_calling_hours("+8801712345678")
    print(f"Customer (+8801712345678): allowed={allowed_dhaka}, reason='{msg_dhaka}'")

    # Test merchant custom operating hours
    test_merchant_hours = {"start": "09:00", "end": "18:00"}
    allowed_custom, msg_custom = is_within_calling_hours("+8801712345678", test_merchant_hours)
    print(f"Customer with custom merchant hours: allowed={allowed_custom}, reason='{msg_custom}'")

    print("\n--- [TEST 2: End-to-End Order Creation & Voice Agent Pipeline] ---")
    async with AsyncSessionLocal() as db:
        # Get or create tenant
        tenant_stmt = select(Tenant).limit(1)
        res = await db.execute(tenant_stmt)
        tenant = res.scalars().first()
        if not tenant:
            tenant = Tenant(
                id=uuid.uuid4(),
                name="Gulshan Luxury Boutique",
                slug=f"gulshan-{uuid.uuid4().hex[:6]}",
                business_phone="+8801812345678",
                primary_currency="BDT",
            )
            db.add(tenant)
            await db.commit()
            await db.refresh(tenant)

        # Configure Employee #2 (Voice Confirmation Agent)
        cfg_stmt = select(AgentConfig).where(
            AgentConfig.tenant_id == tenant.id,
            AgentConfig.agent_type == "voice_confirmation"
        )
        cfg_res = await db.execute(cfg_stmt)
        agent_cfg = cfg_res.scalars().first()
        if not agent_cfg:
            agent_cfg = AgentConfig(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                agent_type="voice_confirmation",
                name="Voice Confirmation Specialist",
                system_prompt="You are Joy, the Voice Confirmation Specialist.",
                operational_hours={"start": "00:00", "end": "23:59"}, # wide open for testing
                max_discount_pct=0.10,
            )
            db.add(agent_cfg)
            await db.commit()

        # Create sample Order
        test_order = Order(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            external_order_id=f"TEST-{uuid.uuid4().hex[:6]}",
            storefront_provider="shopify",
            customer_name="Rahim Chowdhury",
            customer_phone="+8801712345678",
            shipping_address="Road 11, House 42, Banani, Dhaka 1213",
            order_total=Decimal("4500.00"),
            status="pending_confirmation",
            call_attempts=0,
        )
        db.add(test_order)
        await db.commit()
        await db.refresh(test_order)
        print(f"Created Test Order: {test_order.id} (Status: {test_order.status})")

        # Test A: Order processing under test bypass (initiates call)
        res_call = await VoiceConfirmationAgent.process_order_confirmation(
            order_id=test_order.id,
            tenant_id=tenant.id,
            db=db,
            bypass_timezone_for_test=True,
        )
        print("Voice Agent Call Dispatch Result:", res_call)
        assert res_call["status"] == "call_dispatched", f"Expected call_dispatched, got {res_call}"

        # Test B: Telephony Completion Webhook
        print("\n--- [TEST 3: Telephony Webhook Completion] ---")
        webhook_payload = TelephonyCompletionPayload(
            order_id=test_order.id,
            tenant_id=tenant.id,
            call_id=res_call["call_id"],
            transcript="Agent: Hello, calling from Joy Store for Rahim Chowdhury. Rahim: Yes, that is me. Agent: Confirming delivery to Road 11, House 42, Banani. Rahim: Yes, correct, please send it.",
            sentiment_score=0.95,
            order_confirmed=True,
            flagged_for_review=False,
            updated_shipping_address="Road 11, House 42, Banani, Dhaka 1213 (Confirmed)",
        )

        webhook_result = await handle_telephony_completion(payload=webhook_payload, db=db)
        print("Webhook Handling Result:", webhook_result)
        assert webhook_result["status"] == "success"
        assert webhook_result["new_order_status"] == "confirmed"

        # Verify updated DB state
        order_verify_stmt = select(Order).where(Order.id == test_order.id)
        verify_res = await db.execute(order_verify_stmt)
        updated_order = verify_res.scalars().first()
        print(f"\nFinal Order DB State:")
        print(f"  - Status: {updated_order.status}")
        print(f"  - Channel: {updated_order.confirmation_channel}")
        print(f"  - Address: {updated_order.shipping_address}")
        print(f"  - Transcript: {updated_order.call_transcript[:60]}...")
        print(f"  - Linked Conversation ID: {updated_order.conversation_id}")
        assert updated_order.status == "confirmed"
        assert updated_order.conversation_id is not None
        assert "Confirmed" in updated_order.shipping_address

    print("\nALL VOICE CONFIRMATION AGENT ACCEPTANCE TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(run_tests())
