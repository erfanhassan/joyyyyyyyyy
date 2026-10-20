import asyncio
import json
import uuid
import websockets
from sqlalchemy import select, text
from app.db.session import AsyncSessionLocal
from app.db.models import Tenant, Conversation, InteractionLog
from app.services.sentiment_service import SentimentService
from app.services.hitl_orchestrator import HITLOrchestrator
from app.services.postgres_checkpointer import PostgreSQLSaver


async def test_sentiment_service():
    print("\n--- [TEST 1: Sentiment & Risk Evaluation] ---")
    safe_msg = "Hello! Do you have the blue panjabi in size 42 in stock?"
    safe_result = await SentimentService.evaluate_sentiment(safe_msg)
    print(f"Safe message result: sentiment={safe_result['sentiment_score']}, risk={safe_result['risk_score']}, breached={safe_result['is_risk_breached']}")
    assert safe_result["risk_score"] < 0.40
    assert not safe_result["is_risk_breached"]
    assert safe_result["risk_badge"] == "green_safe"

    angry_msg = "This is a scam! You cheaters stole my money! Cancel my order and give me a full refund right now or I will sue with my lawyer!"
    angry_result = await SentimentService.evaluate_sentiment(angry_msg)
    print(f"Angry message result: sentiment={angry_result['sentiment_score']}, risk={angry_result['risk_score']}, breached={angry_result['is_risk_breached']}")
    print(f"Flagged keywords: {angry_result['flagged_keywords']}")
    assert angry_result["risk_score"] > 0.70
    assert angry_result["is_risk_breached"]
    assert angry_result["risk_badge"] == "crimson_alert"
    assert "scam" in angry_result["flagged_keywords"]
    assert "refund" in angry_result["flagged_keywords"]
    print("✓ Test 1: Sentiment & Risk Evaluator passed.")


async def test_hitl_interrupt_and_checkpointer():
    print("\n--- [TEST 2: HITL Intercept & LangGraph Checkpointer State Preservation] ---")
    async with AsyncSessionLocal() as db:
        # Get or create tenant
        t_stmt = select(Tenant).limit(1)
        res = await db.execute(t_stmt)
        tenant = res.scalars().first()
        if not tenant:
            tenant = Tenant(id=uuid.uuid4(), name="Banani Fashion Hub", slug="banani-hub")
            db.add(tenant)
            await db.commit()
            await db.refresh(tenant)

        # Create test conversation
        conv = Conversation(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            channel="instagram",
            customer_identifier="cust_insta_101",
            customer_name="Angry Shopper",
            sentiment_score=1.0,
            risk_score=0.0,
            is_paused_for_human=False,
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)

        print(f"Initial Conversation: id={conv.id}, is_paused={conv.is_paused_for_human}")

        # Inject angry customer message
        angry_msg = "I demand a refund immediately! Your product was broken and this store is a fraud!"
        intercept_res = await HITLOrchestrator.evaluate_and_intercept(
            tenant_id=tenant.id,
            conversation_id=conv.id,
            customer_message=angry_msg,
            db=db,
            pending_ai_draft="Pending manager review draft",
        )

        print("Intercept Result:", intercept_res)
        assert intercept_res["halt_ai"] is True
        assert intercept_res["risk_score"] > 0.70

        # Verify DB Conversation state
        await db.refresh(conv)
        print(f"Updated Conversation: is_paused={conv.is_paused_for_human}, risk={conv.risk_score}")
        assert conv.is_paused_for_human is True
        assert conv.risk_score > 0.70

        # Verify PostgreSQL checkpointer state
        saver = HITLOrchestrator.get_checkpointer()
        chk_tuple = saver.get_tuple({
            "configurable": {
                "thread_id": str(conv.id),
                "checkpoint_ns": "hitl_intercept",
            }
        })
        print(f"PostgreSQL Checkpoint tuple found: {chk_tuple is not None}")
        assert chk_tuple is not None
        assert chk_tuple.checkpoint["channel_values"]["is_paused_for_human"] is True
        assert "refund" in chk_tuple.checkpoint["channel_values"]["customer_message"]

    print("✓ Test 2: HITL Intercept & Checkpointer passed.")


async def test_websocket_workbench_live():
    print("\n--- [TEST 3: Live WebSocket Broadcast, 1-Click Crimson Takeover & Human Overwrite] ---")
    async with AsyncSessionLocal() as db:
        t_stmt = select(Tenant).limit(1)
        res = await db.execute(t_stmt)
        tenant = res.scalars().first()

        # Create a fresh conversation for live WS testing
        conv = Conversation(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            channel="web_widget",
            customer_identifier="visitor_ws_888",
            customer_name="Shuvo Mallik",
            sentiment_score=0.8,
            risk_score=0.2,
            is_paused_for_human=False,
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)

    ws_url = f"ws://localhost:8000/ws/workbench/{tenant.id}"
    print(f"Connecting to WebSocket: {ws_url}")

    async with websockets.connect(ws_url) as ws:
        # 1. Receive connected welcome payload
        init_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
        init_data = json.loads(init_raw)
        print("Received WS Initial Frame:", init_data["type"], f"(Active convs: {len(init_data.get('conversations', []))})")
        assert init_data["type"] == "connected"

        # 2. Inject angry message in another task to trigger real-time broadcast
        async def inject_angry():
            await asyncio.sleep(0.5)
            async with AsyncSessionLocal() as session:
                await HITLOrchestrator.evaluate_and_intercept(
                    tenant_id=tenant.id,
                    conversation_id=conv.id,
                    customer_message="Fraud alert! Cancel my order or I will report you to the police!",
                    db=session,
                )

        asyncio.create_task(inject_angry())

        # 3. WebSocket client should receive 'hitl_alert' event
        alert_raw = await asyncio.wait_for(ws.recv(), timeout=6.0)
        alert_data = json.loads(alert_raw)
        print("Received WS Event:", alert_data.get("type"), f"risk_score={alert_data.get('risk_score')}, badge={alert_data.get('risk_badge')}")
        assert alert_data.get("type") == "hitl_alert"
        assert alert_data.get("conversation_id") == str(conv.id)
        assert alert_data.get("risk_badge") == "crimson_alert"

        # 4. Human Operator initiates 1-Click Takeover
        print("\nSending Takeover Command via WebSocket...")
        await ws.send(json.dumps({
            "action": "takeover",
            "conversation_id": str(conv.id),
            "take_over": True,
            "operator_name": "Operations Lead (Tanvir)",
        }))

        # Receive takeover ack or takeover_toggled event
        ack_1 = await asyncio.wait_for(ws.recv(), timeout=5.0)
        ack_1_data = json.loads(ack_1)
        print("Received WS Frame after Takeover:", ack_1_data.get("type"))

        # 5. Human Operator sends custom message overwrite
        print("\nSending Human Message Overwrite via WebSocket...")
        human_msg = "Hello Shuvo, this is Tanvir, Operations Manager. I have cancelled your order and processed a 100% refund immediately."
        await ws.send(json.dumps({
            "action": "send_reply",
            "conversation_id": str(conv.id),
            "text": human_msg,
            "operator_name": "Operations Lead (Tanvir)",
        }))

        ack_2 = await asyncio.wait_for(ws.recv(), timeout=5.0)
        ack_2_data = json.loads(ack_2)
        print("Received WS Frame after Human Reply:", ack_2_data.get("type"))

        # Verify DB logs for human operator message
        async with AsyncSessionLocal() as verify_db:
            logs_stmt = select(InteractionLog).where(
                InteractionLog.conversation_id == conv.id,
                InteractionLog.sender_type == "human_operator"
            )
            logs_res = await verify_db.execute(logs_stmt)
            logs = logs_res.scalars().all()
            print(f"Found {len(logs)} Human Operator logs in database:")
            for l in logs:
                print(f"  - [{l.sender_type}] {l.message_text}")
            assert len(logs) >= 1
            assert any(human_msg in l.message_text for l in logs)

    print("✓ Test 3: Live WebSocket Broadcast, Takeover & Overwrites passed.")


async def main():
    await test_sentiment_service()
    await test_hitl_interrupt_and_checkpointer()
    await test_websocket_workbench_live()
    print("\n=======================================================")
    print("ALL HITL SENTIMENT INTERRUPT & WORKBENCH TESTS PASSED!")
    print("=======================================================")


if __name__ == "__main__":
    asyncio.run(main())
