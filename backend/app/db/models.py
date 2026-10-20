import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    Float,
    Integer,
    Numeric,
    DateTime,
    ForeignKey,
    Index,
    Computed,
    LargeBinary,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from sqlalchemy.orm import declarative_base, relationship
from pgvector.sqlalchemy import Vector

Base = declarative_base()


def get_utc_now():
    return datetime.now(timezone.utc)


# ==========================================
# 1. Tenants, Users & Organization Members
# ==========================================
class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_utc_now)

    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    integrations = relationship("TenantIntegration", back_populates="tenant", cascade="all, delete-orphan")
    agent_configs = relationship("AgentConfig", back_populates="tenant", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="tenant", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="tenant", cascade="all, delete-orphan")
    knowledge_documents = relationship("KnowledgeDocument", back_populates="tenant", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=True)
    role = Column(String(50), default="operator")  # 'owner', 'admin', 'operator'
    created_at = Column(DateTime(timezone=True), default=get_utc_now)

    tenant = relationship("Tenant", back_populates="users")
    memberships = relationship("OrganizationMember", back_populates="user", cascade="all, delete-orphan")


class OrganizationMember(Base):
    __tablename__ = "organization_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), default="operator")
    created_at = Column(DateTime(timezone=True), default=get_utc_now)

    user = relationship("User", back_populates="memberships")


# ==========================================
# 2. Integrations & Encrypted Credential Vault
# ==========================================
class TenantIntegration(Base):
    __tablename__ = "tenant_integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), nullable=False)  # 'meta', 'shopify', 'woocommerce', 'widget', 'whatsapp'
    kms_key_id = Column(String(255), nullable=True)  # Envelope encryption master key identifier
    access_token_encrypted = Column(Text, nullable=False)  # AES-256 encrypted
    refresh_token_encrypted = Column(Text, nullable=True)
    settings = Column(JSONB, default=dict)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=get_utc_now)

    tenant = relationship("Tenant", back_populates="integrations")


# ==========================================
# 3. Digital Employee Roster Configuration
# ==========================================
class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_type = Column(String(50), nullable=False)  # 'social_sales', 'voice_confirmation', 'custom'
    name = Column(String(255), nullable=False)
    system_prompt = Column(Text, nullable=False)
    tone_settings = Column(JSONB, default=lambda: {"formality": 0.5, "enthusiasm": 0.8})
    max_discount_pct = Column(Integer, default=10)
    operational_hours = Column(JSONB, default=lambda: {"start": "08:00", "end": "20:00", "timezone": "UTC"})
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=get_utc_now)

    tenant = relationship("Tenant", back_populates="agent_configs")


# ==========================================
# 4. Multi-Channel Messaging & Interactivity
# ==========================================
class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String(50), nullable=False)  # 'instagram', 'facebook', 'web_widget', 'phone', 'whatsapp'
    customer_identifier = Column(String(255), nullable=False, index=True)
    customer_name = Column(String(255), nullable=True)
    sentiment_score = Column(Float, default=1.0)
    risk_score = Column(Float, default=0.0)
    is_paused_for_human = Column(Boolean, default=False)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now)

    tenant = relationship("Tenant", back_populates="conversations")
    interaction_logs = relationship("InteractionLog", back_populates="conversation", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="conversation")


class InteractionLog(Base):
    __tablename__ = "interaction_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_type = Column(String(20), nullable=False)  # 'customer', 'agent', 'human_operator'
    message_text = Column(Text, nullable=False)
    raw_payload = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=get_utc_now)

    conversation = relationship("Conversation", back_populates="interaction_logs")


# ==========================================
# 5. Storefront Orders & Telephony Calls
# ==========================================
class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    external_order_id = Column(String(255), nullable=False, index=True)
    storefront_provider = Column(String(50), nullable=False)  # 'shopify', 'woocommerce'
    customer_name = Column(String(255), nullable=False)
    customer_phone = Column(String(50), nullable=False, index=True)
    shipping_address = Column(Text, nullable=False)
    order_total = Column(Numeric(10, 2), nullable=False)
    status = Column(String(50), default="pending_confirmation")  # 'confirmed', 'flagged_for_review', 'cancelled'
    confirmation_channel = Column(String(20), default="voice")  # 'voice', 'whatsapp', 'sms'
    fallback_status = Column(String(50), default="none")  # 'none', 'dispatched', 'confirmed', 'expired'
    fallback_dispatched_at = Column(DateTime(timezone=True), nullable=True)
    call_attempts = Column(Integer, default=0)
    call_transcript = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=get_utc_now)

    tenant = relationship("Tenant", back_populates="orders")
    conversation = relationship("Conversation", back_populates="orders")


# ==========================================
# 6. Knowledge Brain & Hybrid Vector Storage
# ==========================================
class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(50), nullable=False)  # 'pdf', 'csv', 'web_crawl'
    source_url = Column(Text, nullable=True)
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_utc_now)

    tenant = relationship("Tenant", back_populates="knowledge_documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    tsv = Column(TSVECTOR, Computed("to_tsvector('english', content)", persisted=True))
    embedding = Column(Vector(1536), nullable=True)

    document = relationship("KnowledgeDocument", back_populates="chunks")

    __table_args__ = (
        Index(
            "idx_document_chunks_vector",
            embedding,
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("idx_document_chunks_tsv", tsv, postgresql_using="gin"),
    )


# ==========================================
# 7. Model Context Protocol (MCP) Registry
# ==========================================
class MCPToolRegistry(Base):
    __tablename__ = "mcp_tools_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False)
    endpoint_url = Column(Text, nullable=False)
    is_enabled = Column(Boolean, default=True)


class MCPToolExecutionLog(Base):
    __tablename__ = "mcp_tool_execution_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False, index=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    input_payload = Column(JSONB, default=dict)
    output_payload = Column(JSONB, default=dict)
    status = Column(String(50), default="success")  # 'success', 'error', 'timeout'
    execution_time_ms = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=get_utc_now)


# ==========================================
# 8. LangGraph PostgreSQL Checkpointer
# ==========================================
class CheckpointModel(Base):
    __tablename__ = "checkpoints"

    thread_id = Column(String(255), primary_key=True)
    checkpoint_ns = Column(String(255), primary_key=True, default="")
    checkpoint_id = Column(String(255), primary_key=True)
    parent_checkpoint_id = Column(String(255), nullable=True)
    type = Column(String(50), nullable=False)
    checkpoint_blob = Column(LargeBinary, nullable=False)
    metadata_type = Column(String(50), nullable=False)
    metadata_blob = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_utc_now)


class CheckpointBlobModel(Base):
    __tablename__ = "checkpoint_blobs"

    thread_id = Column(String(255), primary_key=True)
    checkpoint_ns = Column(String(255), primary_key=True, default="")
    channel = Column(String(255), primary_key=True)
    version = Column(String(255), primary_key=True)
    type = Column(String(50), nullable=False)
    blob = Column(LargeBinary, nullable=True)


class CheckpointWriteModel(Base):
    __tablename__ = "checkpoint_writes"

    thread_id = Column(String(255), primary_key=True)
    checkpoint_ns = Column(String(255), primary_key=True, default="")
    checkpoint_id = Column(String(255), primary_key=True)
    task_id = Column(String(255), primary_key=True)
    idx = Column(Integer, primary_key=True)
    channel = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)
    blob = Column(LargeBinary, nullable=True)
    task_path = Column(String(255), nullable=False, default="")
