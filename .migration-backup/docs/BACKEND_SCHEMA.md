# Project Joy: Multi-Tenant Backend Schema &amp; Data Architecture

## 1. PostgreSQL 16 DDL &amp; Row-Level Security (RLS)

```sql
-- Enable Required Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 1. Tenants &amp; Core Users
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'operator', -- 'owner', 'admin', 'operator'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Integrations &amp; Envelope-Encrypted Credential Vault
CREATE TABLE tenant_integrations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL, -- 'meta', 'shopify', 'woocommerce', 'widget', 'whatsapp'
    kms_key_id VARCHAR(255), -- Envelope Encryption Master Key ID
    access_token_encrypted TEXT NOT NULL, -- AES-256-GCM Encrypted DEK
    refresh_token_encrypted TEXT,
    settings JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Digital Employee Roster Configuration
CREATE TABLE agent_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_type VARCHAR(50) NOT NULL, -- 'social_sales', 'voice_confirmation', 'custom'
    name VARCHAR(255) NOT NULL,
    system_prompt TEXT NOT NULL,
    tone_settings JSONB DEFAULT '{"formality": 0.5, "enthusiasm": 0.8}'::jsonb,
    max_discount_pct INT DEFAULT 10,
    operational_hours JSONB DEFAULT '{"start": "08:00", "end": "20:00", "timezone": "UTC"}'::jsonb,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Multi-Channel Conversations &amp; Messages
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    channel VARCHAR(50) NOT NULL, -- 'instagram', 'facebook', 'web_widget', 'phone', 'whatsapp'
    customer_identifier VARCHAR(255) NOT NULL,
    customer_name VARCHAR(255),
    sentiment_score FLOAT DEFAULT 1.0, -- 1.0 (positive) to 0.0 (negative)
    risk_score FLOAT DEFAULT 0.0, -- Calculated as (1.0 - sentiment_score); triggers HITL if > 0.70
    is_paused_for_human BOOLEAN DEFAULT false,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE interaction_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sender_type VARCHAR(20) NOT NULL, -- 'customer', 'agent', 'human_operator'
    message_text TEXT NOT NULL,
    raw_payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Storefront Orders, Telephony &amp; Fallback Dispatch
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL, -- Links call/chat to Operator Workbench
    external_order_id VARCHAR(255) NOT NULL,
    storefront_provider VARCHAR(50) NOT NULL, -- 'shopify', 'woocommerce'
    customer_name VARCHAR(255) NOT NULL,
    customer_phone VARCHAR(50) NOT NULL,
    shipping_address TEXT NOT NULL,
    order_total NUMERIC(10, 2) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending_confirmation', -- 'confirmed', 'flagged_for_review'
    confirmation_channel VARCHAR(20) DEFAULT 'voice', -- 'voice', 'whatsapp', 'sms'
    fallback_status VARCHAR(50) DEFAULT 'none', -- 'none', 'dispatched', 'confirmed', 'expired'
    fallback_dispatched_at TIMESTAMP WITH TIME ZONE,
    call_attempts INT DEFAULT 0,
    call_transcript TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. Knowledge Brain &amp; Hybrid Search (BM25 + pgvector HNSW)
CREATE TABLE knowledge_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    source_type VARCHAR(50) NOT NULL, -- 'pdf', 'csv', 'web_crawl'
    source_url TEXT,
    title VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    document_id UUID REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    embedding vector(1536)
);

-- pgvector HNSW Index for Semantic Cosine Search
CREATE INDEX idx_document_chunks_vector ON document_chunks 
USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- GIN Index for Fast BM25 Keyword Search
CREATE INDEX idx_document_chunks_tsv ON document_chunks USING gin(tsv);

-- 7. Model Context Protocol (MCP) Registry
CREATE TABLE mcp_tools_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    tool_name VARCHAR(100) NOT NULL,
    endpoint_url TEXT NOT NULL,
    is_enabled BOOLEAN DEFAULT true
);

-- Enable Row-Level Security (RLS) Across ALL Operational Tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE interaction_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE mcp_tools_registry ENABLE ROW LEVEL SECURITY;

-- RLS Policies Scoped by app.current_tenant_id
CREATE POLICY tenant_isolation_policy ON users
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

CREATE POLICY tenant_isolation_policy ON tenant_integrations
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

CREATE POLICY tenant_isolation_policy ON agent_configs
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

CREATE POLICY tenant_isolation_policy ON conversations
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

CREATE POLICY tenant_isolation_policy ON interaction_logs
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

CREATE POLICY tenant_isolation_policy ON orders
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

CREATE POLICY tenant_isolation_policy ON knowledge_documents
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

CREATE POLICY tenant_isolation_policy ON document_chunks
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

CREATE POLICY tenant_isolation_policy ON mcp_tools_registry
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

## 2. Redis Data Architecture &amp; In-Memory Models

### 1. Webhook Ingestion Deduplication (24h TTL)
- **Key Pattern:** `idempotency:{tenant_id}:{event_id}`
- **Data Type:** String (`SETNX`)
- **TTL:** 86,400 seconds (24 hours)
- **Purpose:** Enforces strict idempotency and at-most-once processing across Meta, Shopify, and WooCommerce webhook deliveries.
- **Example Command:**
  ```redis
  SET idempotency:8e83344d-1763-4927-b86a-74ec9e9a59cf:evt_shopify_10293847 "processing" EX 86400 NX
  ```

### 2. Live Agent Session &amp; Context State
- **Key Pattern:** `session:{tenant_id}:{conversation_id}`
- **Data Type:** Hash / JSON
- **TTL:** 3,600 seconds (1 hour sliding)
- **Purpose:** Stores active LangGraph state, intermediate tool scratchpad, and short-term dialogue context for sub-800ms conversational replies.

### 3. Operator Workbench Real-Time Event Bus
- **Channel Pattern:** `channel:tenant:{tenant_id}:workbench`
- **Data Type:** Pub/Sub Channel
- **Purpose:** Broadcasts sentiment alerts (`risk > 0.70`), takeover requests, and live transcript streaming to operator frontends over WebSockets.
- **Message Payload Example:**
  ```json
  {
    "event": "sentiment_alert",
    "conversation_id": "96b6ad0d-c7da-44a6-9811-37d4cf4492db",
    "sentiment_score": 0.22,
    "risk_score": 0.78,
    "is_paused_for_human": true,
    "customer_name": "Sarah Connor",
    "last_message": "Where is my delivery? Cancel it right now!"
  }
  ```

### 4. Telephony Outbound Concurrency Lock
- **Key Pattern:** `lock:telephony:call:{order_id}`
- **Data Type:** String (Distributed Mutex)
- **TTL:** 300 seconds (5 minutes)
- **Purpose:** Guarantees that only a single outbound confirmation phone call is placed per storefront order at any given time.
