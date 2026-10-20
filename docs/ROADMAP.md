# Project Joy: Engineering &amp; Implementation Roadmap

## Phase 1 Execution Timeline (4 Sprints / 20 Days)

### Sprint 1 (Days 1–5): Foundation, Multi-Tenancy &amp; Envelope Encryption
- Scaffold FastAPI backend, PostgreSQL 16 schema with `pgvector` &amp; `tsvector` GIN index, and Redis cluster in Docker Compose.
- Implement PostgreSQL Row-Level Security (RLS) policies scoped by `tenant_id` across all tables including `users`.
- Build HMAC-SHA256 middleware and Redis `SETNX` 24h deduplication pipeline.
- Implement Envelope Encryption service (KMS master key wrapping AES-256-GCM data encryption keys) for OAuth tokens.

### Sprint 2 (Days 6–10): Employee #1 (Social Sales Specialist) &amp; Hybrid RAG
- Build LangGraph state machine powered by DeepSeek API (`deepseek-chat`).
- Implement Meta Graph API client with **Comment-to-DM Handshake CTA** to open 24-hour customer messaging windows compliant with Meta policy.
- Build Hybrid RAG engine combining PostgreSQL full-text search (`tsvector` BM25) and `pgvector` HNSW cosine similarity.
- Integrate Model Context Protocol (MCP) tools for catalog lookup, stock checks, and capped discount code generation.
- Build the Universal JavaScript Web Embed Widget (`widget.js`) with pure white aesthetic.

### Sprint 3 (Days 11–15): Employee #2 (Voice Confirmation Specialist) &amp; LiveKit Stack
- Deploy **LiveKit Agents WebRTC + SIP trunking** architecture (Deepgram Nova-2 streaming STT, Cartesia Sonic / ElevenLabs Flash streaming TTS, Silero VAD turn detection) ensuring sustained **sub-800ms** latency and human-like voice delivery.
- Ingest Shopify/WooCommerce `orders/create` webhooks.
- Implement Timezone Gating (strictly blocking calls between 9 PM and 8 AM customer local time).
- Build automated **Omnichannel Fallback Pipeline**: dispatches 1-click confirmation links via WhatsApp Cloud API or SMS if calls are unanswered, busy, or during blackout hours.
- Update storefront order statuses to `confirmed` or `flagged_for_review`.

### Sprint 4 (Days 16–20): Non-Technical White Minimal Dashboard &amp; Meta Review
- Build Next.js 14 dashboard views with **pure white minimal aesthetic (zero blue/purple)** and non-technical staff-management UI:
  - Store Connections (Integration Hub)
  - Employee Training (Knowledge Brain)
  - Digital Employee Roster (Staff Cards &amp; Sliders)
  - Operator Desk (Unified Inbox &amp; 1-Click Crimson Takeover)
- Connect Operator Desk to backend WebSockets for real-time risk alerts and live draft editing.
- Execute E2E integration test suite (`pytest`).
- Record unedited screen capture demonstration showcasing the human-in-the-loop takeover and submit Meta App Review package for `instagram_manage_messages` and `pages_read_engagement`.
