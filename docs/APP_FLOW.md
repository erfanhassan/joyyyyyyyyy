# Project Joy: End-to-End Application Flow Architecture

## Flow 1: Merchant Onboarding &amp; Setup (&lt;10 Min TTV, Non-Technical)
1. **Simple Merchant Signup:** Merchant signs up via Next.js dashboard using Clerk/Supabase Auth JWT.
2. **1-Click Store Connections:**
   - Clicks green "Connect Facebook &amp; Instagram" button &rarr; Completes Meta Embedded Signup popup &rarr; System stores encrypted Page &amp; IG tokens in `tenant_integrations` via envelope encryption.
   - Connects Storefront &rarr; Authenticates Shopify OAuth or pastes WooCommerce API keys.
3. **Product Catalog Import (Employee Training):**
   - Merchant pastes their website URL or drops a product PDF/CSV catalog into the Knowledge Brain.
   - Background worker parses items, builds both PostgreSQL `tsvector` keywords and 1536-dim vector embeddings, and stores them in `document_chunks` with HNSW indexing.
4. **Digital Employee Activation:**
   - Merchant sets discount caps (e.g., maximum 10%), tone, and operating hours using simple sliders.
   - System sends automated test ping &rarr; Digital employees activated for 24/7 duty.

## Flow 2: Social Commerce Lead-to-Sale Funnel (Employee #1)
1. **Customer Trigger:** Customer leaves an Instagram/Facebook comment, sends a DM, or engages on the website live chat widget.
2. **Ingestion &amp; Deduplication:** FastAPI Ingestion Gateway verifies HMAC-SHA256 signature and performs Redis `SETNX` idempotency check (`idempotency:{tenant_id}:{event_id}`).
3. **Intent Recognition:** LangGraph Agent State Machine + DeepSeek API parses customer intent.
4. **Meta Comment-to-DM Handshake:**
   - If inquiry is on a public post/Reels comment, the agent posts a brief public reply (*"Just sent you a DM with details!"*) AND calls Meta Private Replies API with an interactive CTA (e.g., *"Tap here to claim 10% off &amp; check available sizes"*).
   - When the customer taps or replies, Meta's 24-hour standard messaging window opens for full multi-turn sales interaction.
5. **Hybrid Catalog RAG &amp; Inventory Check:** DeepSeek runs hybrid search (BM25 keyword + pgvector HNSW) on `document_chunks` and triggers MCP tools `catalog.lookup` and `stock.check`.
6. **Capped Discount &amp; Direct Checkout:** If customer negotiates price, agent verifies `agent_configs.max_discount_pct` &rarr; Calls `discount.generate` &rarr; Sends personalized checkout link directly into the DM/Chat.

## Flow 3: Outbound Voice Order Confirmation &amp; Fallback (Employee #2)
1. **Order Placed:** Customer completes purchase on Shopify/WooCommerce &rarr; Fires `orders/create` webhook.
2. **Timezone Gating Check:** FastAPI evaluates customer phone location and merchant operating hours:
   - **Allowed Window (8 AM – 9 PM customer local time):** Initiates outbound phone call.
   - **Blackout Window (9 PM – 8 AM customer local time):** Bypasses voice call and triggers automated WhatsApp / SMS fallback verification link immediately.
3. **LiveKit Streaming Voice Loop (Sub-800ms Latency):**
   - Telephony bridge dials customer phone over SIP trunk.
   - LiveKit WebRTC pipeline streams caller audio into Deepgram Nova-2 STT (~150ms).
   - DeepSeek streams response tokens directly to Cartesia Sonic / ElevenLabs Flash TTS (~120ms).
   - Natural human voice confirms order items and delivery address; Silero VAD handles seamless customer barge-in.
4. **Answering Machine / No-Answer Omnichannel Fallback:**
   - If call is busy, reaches voicemail, or goes unanswered after 2 attempts, the system automatically dispatches an interactive confirmation link via WhatsApp Cloud API or SMS: *"Hi [Name], please verify your delivery address for Order #[ID]: [Link]"*.
5. **Status Update:** Upon customer confirmation (via phone or fallback link), order status updates to `confirmed` or `flagged_for_review` in both Project Joy and the storefront.

## Flow 4: Operator Workbench &amp; HITL Sentiment Takeover
1. **Real-Time Sentiment Monitoring:** Sentiment evaluator analyzes every message in the conversation stream.
2. **Risk Threshold Breach:** If sentiment score drops below threshold (`risk > 0.70` or anger/cancellation keywords):
   - LangGraph pauses autonomous agent execution (`is_paused_for_human = true`).
   - State checkpoint is safely stored in PostgreSQL via `PostgreSQLSaver`.
3. **WebSocket Alert Broadcast:** Redis pub/sub emits an alert event to the Next.js Operator Workbench, highlighting the conversation with a prominent red badge.
4. **1-Click Human Takeover:** The human operator reviews the live transcript, edits the AI draft, or clicks the prominent red "Take Over Conversation" toggle to handle the customer directly. Once resolved, operator clicks "Resume Employee" to restore autonomous AI mode.
