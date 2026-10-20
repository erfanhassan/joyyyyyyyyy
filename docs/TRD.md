# Project Joy: Technical Requirements Document (TRD)

## 1. System Architecture &amp; Tech Stack
- **Backend Framework:** FastAPI (Python 3.12) with asynchronous ASGI event handling.
- **Frontend Framework:** Next.js 14 (App Router, Tailwind CSS, Shadcn UI, WebSockets) with pure white minimal design and zero blue/purple palette.
- **Primary Database:** PostgreSQL 16 with `pgvector` extension for vector embeddings, `tsvector` for BM25 full-text catalog search, and Row-Level Security (RLS).
- **In-Memory Cache &amp; Event Bus:** Redis Cluster for session memory, `SETNX` idempotency keys, and WebSocket pub/sub messaging.
- **Agent Orchestration Engine:** LangGraph state machine with `PostgreSQLSaver` persistence checkpointer.

## 2. Dual LLM, Telephony &amp; Voice Architecture
- **Primary LLM Reasoning Core:** DeepSeek API (`deepseek-chat`) for multi-turn conversational sales, intent classification, and MCP tool orchestration.
- **Fallback &amp; Embeddings Engine:** ChatGPT API (`gpt-4o-mini` / `text-embedding-3-small`) for structured JSON validation and 1536-dimensional catalog vector embeddings.
- **Ultra-Low Latency Voice Stack (LiveKit Agents + SIP):**
  - **The Latency Solution:** Replaces legacy sequential HTTP pipelines (which cause 7–8s delays) with a bi-directional streaming WebRTC audio loop managed by the **LiveKit Agents** framework and SIP trunking (Local Bangladeshi SIP providers like AmberIT, or standard RFC 3261 SIP trunks) to standard PSTN phone lines.
  - **Speech-to-Text (STT):** Deepgram Nova-2 streaming WebSocket (~150ms latency).
  - **Turn Detection &amp; Interruption:** Silero VAD (300ms silence detection) and LiveKit turn detection for instant barge-in support.
  - **LLM Token Streaming:** DeepSeek streaming chunk generation piped directly to speech synthesis.
  - **Text-to-Speech (TTS):** Cartesia Sonic / ElevenLabs Flash streaming WebSocket (~120ms time-to-first-byte audio), delivering expressive, natural, human-like voice quality.
  - **Total Latency:** Sustained **sub-800ms** conversational round-trip time.

## 3. Universal Integration Layer &amp; Channel Gateways
- **Social Channel APIs:** Meta Graph API (Messenger, Instagram Messaging API, Webhooks).
  - **Meta 24-Hour Policy Engine:** For public post comments, dispatches a single high-conversion private reply with interactive quick-replies (Handshake CTA) to prompt the user to reply and unlock the full 24-hour multi-turn sales window.
- **Storefront Integrations:** Shopify REST/GraphQL APIs, WooCommerce REST API, and Model Context Protocol (MCP) server endpoints (`catalog.lookup`, `stock.check`, `discount.generate`).
- **Omnichannel Voice Fallback:** WhatsApp Cloud API &amp; Twilio/Telnyx SMS gateway dispatching secure 1-click verification URLs when phone calls are unanswered or restricted by timezone hours.
- **Web Live Chat:** Universal JavaScript widget snippet (`widget.js`) serving live chat sessions via FastAPI WebSockets.

## 4. Knowledge Brain &amp; Hybrid Catalog Search
- **Hybrid Search Engine:** Combines PostgreSQL native `tsvector` full-text search (BM25 exact SKU and keyword matching) with `pgvector` HNSW cosine similarity (`vector(1536)`).
- **Reciprocal Rank Fusion (RRF):** Blends keyword and semantic ranking to prevent hallucinations on model numbers or specific variant queries while preserving descriptive intent search.

## 5. Security, Compliance &amp; Multi-Tenant Guardrails
- **Merchant Authentication:** Clerk or Supabase Auth JWT verification middleware on all protected API routes, resolving and injecting `tenant_id` into the database session context.
- **Data Isolation:** Mandatory `tenant_id` on all database tables with PostgreSQL Row-Level Security policies (`current_setting('app.current_tenant_id')`).
- **Envelope Encryption Vault:** Master Key Encryption Key (KEK) managed in cloud KMS (AWS KMS / GCP KMS / Vault); individual Data Encryption Keys (DEKs) encrypt OAuth tokens in `tenant_integrations` with AES-256-GCM.
- **Ingestion Security:** HMAC-SHA256 signature verification middleware on all incoming webhooks.
- **Deduplication:** Redis `SETNX` keys (`idempotency:{tenant_id}:{event_id}`) with 24-hour TTL.
- **Meta App Review Compliance:** Full auditing logs, clear operator takeover controls, and human-in-the-loop escalation safeguards documented for review submission.
- **Living Specs Rule:** Enforce `.antigravity/rules.md` for bi-directional spec-code updates.
