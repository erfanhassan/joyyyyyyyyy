# Project Joy: Product Requirements Document (PRD)

## 1. Executive Summary &amp; Product Vision
- **Mission:** Empower e-commerce and social commerce merchants with plug-and-play digital employees ("agents as employees") that autonomously manage sales, customer inquiries, and post-purchase order verification.
- **Business Model:** "Digital Employees as Hirable Staff" — merchants hire specialized autonomous employees on a modular subscription or per-seat basis (e.g., Social Sales Specialist, Order Confirmation Specialist) without adding human payroll.
- **Core Value Proposition:** Eliminates response bottlenecks on social media (Facebook, Instagram) and storefronts (Shopify, WooCommerce, custom sites), driving higher lead conversion while safeguarding brand reputation with real-time human-in-the-loop (HITL) sentiment controls.
- **Target Usability:** Frictionless plug-and-play design tailored for non-technical retail merchants (including localized retail hubs like Dhaka, Bangladesh and emerging global markets) with under 10 minutes Time-to-Value (TTV) and zero AI jargon.

## 2. User Personas &amp; Target Audience
- **Primary Persona:** E-commerce Business Owner / Merchant seeking automated 24/7 social sales and phone order verification without scaling headcount or dealing with complex technical setups.
- **Secondary Persona:** End Customer interacting via social comments, DMs, live website chat, or receiving automated outbound confirmation phone calls and fallback SMS/WhatsApp verification links.
- **Tertiary Persona:** Store Operator / Support Representative overseeing AI conversations on the Operator Workbench with 1-click human takeover capability.

## 3. Digital Employee Roster Specifications (Phase 1 Scope)

### Employee #1: Social Sales Specialist
- **Multi-Channel Reach:**
  - Meta Social Ecosystem: Facebook Pages API, Messenger API, Instagram Graph API (post comments, Reels comments, ad comments, DMs, and automated private DM replies to public comments).
  - Web &amp; Storefront Live Chat: Universal JavaScript Web Embed Widget (`widget.js`) embeddable on Shopify, WooCommerce, BigCommerce, Wix, Squarespace, Webflow, or custom React/HTML sites.
- **Conversational Capabilities &amp; Meta 24-Hour Policy Compliance:**
  - Hybrid RAG-powered catalog search combining exact keyword matching (BM25) with semantic vector retrieval.
  - Real-time stock checks, dynamic discount code generation (strictly capped by merchant settings), and direct checkout link dispatch.
  - **Meta Comment-to-DM Handshake:** Adheres to Meta's 7-day single private reply limit by sending an engaging, one-click interactive CTA (e.g., *"Tap to claim your 10% coupon &amp; view sizes"*) to prompt the customer's DM response, unlocking the full 24-hour conversational sales window.
- **Model Context Protocol (MCP) Tools:** `catalog.lookup`, `stock.check`, `discount.generate`.

### Employee #2: Outbound Voice Confirmation Specialist
- **Trigger Mechanics:** Automated ingestion of `orders/create` (Shopify) or `woocommerce_new_order` (WooCommerce) webhooks.
- **Timezone &amp; Operating Hours Gating:** Evaluates customer phone number timezone and merchant operating hours (strictly blocks calls between 9 PM and 8 AM customer local time).
- **Sub-800ms Streaming Voice Pipeline (LiveKit + SIP):**
  - Full-duplex WebRTC streaming speech-to-speech loop via LiveKit Agents and SIP telephony trunking (Local Bangladeshi SIP providers like AmberIT, or standard RFC 3261 SIP trunks).
  - Eliminates the multi-second latency of legacy batch HTTP chains by running streaming STT (Deepgram Nova-2, ~150ms), streaming LLM tokens (DeepSeek), and ultra-fast streaming TTS (Cartesia Sonic / ElevenLabs Flash, ~120ms) with Silero VAD turn detection.
  - Verifies shipping address, order items, flags anomalies, and updates storefront order status to `confirmed` or `flagged_for_review`.
- **Automated Omnichannel Fallback (SMS / WhatsApp):**
  - If the customer does not answer after 2 call attempts, or if the order is placed during the late-night blackout window, the system automatically dispatches an interactive confirmation link via WhatsApp Cloud API or SMS: *"Hi [Name], please verify your delivery address for Order #[ID] here: [Link]"*, boosting confirmation rates above 90%.

### Extensible Digital Employee Framework
- **Future Employee Roster Builder:** Extensible database schemas and UI layout allowing merchants to configure and deploy future specialized digital employees (e.g., Returns &amp; Exchanges Specialist, VIP Retention Specialist, Abandoned Cart Recoverer) without altering core platform code.

## 4. Platform Core Modules
- **Integration Hub:** 1-click Meta Embedded Signup modal (Facebook Page &amp; IG Business binding), Shopify/WooCommerce OAuth connectors, and Universal JS Widget snippet generator.
- **Knowledge Brain (Hybrid RAG):** Automated storefront URL crawler, drag-and-drop PDF/CSV catalog parser, PostgreSQL full-text search (`tsvector` BM25), and pgvector HNSW indexing with Reciprocal Rank Fusion for high SKU precision.
- **Operator Workbench (HITL &amp; Meta Review Safeguards):** Unified multi-channel inbox, automated sentiment risk scoring (halts AI autonomy if risk > 0.70), live draft editor, and 1-click human takeover switch. Serves as primary compliance proof for Meta App Review.

## 5. Functional Requirements &amp; Acceptance Criteria
- Zero cross-tenant data leakage via PostgreSQL Row-Level Security (`tenant_id`).
- 100% adherence to merchant discount caps (`max_discount_pct`).
- Webhook ingestion responding with HTTP 200 within 1,500ms and Redis 24h deduplication.
- Envelope encryption protecting OAuth tokens with master KMS Key Encryption Keys (KEK).
- End-to-end voice latency strictly below 800ms time-to-speech.
