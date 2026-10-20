"""0001_initial_schema_with_rls

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-10-20 03:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
import pgvector.sqlalchemy

# revision identifiers, used by Alembic.
revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OPERATIONAL_TABLES = [
    "users",
    "organization_members",
    "tenant_integrations",
    "agent_configs",
    "conversations",
    "interaction_logs",
    "orders",
    "knowledge_documents",
    "document_chunks",
    "mcp_tools_registry",
    "mcp_tool_execution_logs",
]


def upgrade() -> None:
    # 0. Enable Required Extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector";')

    # 1. Tenants Table
    op.create_table(
        'tenants',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # 2. Users Table
    op.create_table(
        'users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(length=255), unique=True, nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('role', sa.String(length=50), server_default='operator'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_users_tenant_id', 'users', ['tenant_id'])
    op.create_index('ix_users_email', 'users', ['email'])

    # 3. Organization Members Table
    op.create_table(
        'organization_members',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(length=50), server_default='operator'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_org_members_tenant_id', 'organization_members', ['tenant_id'])
    op.create_index('ix_org_members_user_id', 'organization_members', ['user_id'])

    # 4. Integrations Vault Table
    op.create_table(
        'tenant_integrations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('kms_key_id', sa.String(length=255), nullable=True),
        sa.Column('access_token_encrypted', sa.Text(), nullable=False),
        sa.Column('refresh_token_encrypted', sa.Text(), nullable=True),
        sa.Column('settings', JSONB(), server_default='{}'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_integrations_tenant_id', 'tenant_integrations', ['tenant_id'])

    # 5. Agent Configs (Employee Roster) Table
    op.create_table(
        'agent_configs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_type', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('system_prompt', sa.Text(), nullable=False),
        sa.Column('tone_settings', JSONB(), server_default='{"formality": 0.5, "enthusiasm": 0.8}'),
        sa.Column('max_discount_pct', sa.Integer(), server_default='10'),
        sa.Column('operational_hours', JSONB(), server_default='{"start": "08:00", "end": "20:00", "timezone": "UTC"}'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_agent_configs_tenant_id', 'agent_configs', ['tenant_id'])

    # 6. Conversations Table
    op.create_table(
        'conversations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel', sa.String(length=50), nullable=False),
        sa.Column('customer_identifier', sa.String(length=255), nullable=False),
        sa.Column('customer_name', sa.String(length=255), nullable=True),
        sa.Column('sentiment_score', sa.Float(), server_default='1.0'),
        sa.Column('risk_score', sa.Float(), server_default='0.0'),
        sa.Column('is_paused_for_human', sa.Boolean(), server_default='false'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_conversations_tenant_id', 'conversations', ['tenant_id'])
    op.create_index('ix_conversations_cust_id', 'conversations', ['customer_identifier'])

    # 7. Interaction Logs Table
    op.create_table(
        'interaction_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('conversation_id', UUID(as_uuid=True), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sender_type', sa.String(length=20), nullable=False),
        sa.Column('message_text', sa.Text(), nullable=False),
        sa.Column('raw_payload', JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_interaction_logs_tenant_id', 'interaction_logs', ['tenant_id'])
    op.create_index('ix_interaction_logs_conv_id', 'interaction_logs', ['conversation_id'])

    # 8. Storefront Orders Table
    op.create_table(
        'orders',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('conversation_id', UUID(as_uuid=True), sa.ForeignKey('conversations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('external_order_id', sa.String(length=255), nullable=False),
        sa.Column('storefront_provider', sa.String(length=50), nullable=False),
        sa.Column('customer_name', sa.String(length=255), nullable=False),
        sa.Column('customer_phone', sa.String(length=50), nullable=False),
        sa.Column('shipping_address', sa.Text(), nullable=False),
        sa.Column('order_total', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='pending_confirmation'),
        sa.Column('confirmation_channel', sa.String(length=20), server_default='voice'),
        sa.Column('fallback_status', sa.String(length=50), server_default='none'),
        sa.Column('fallback_dispatched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('call_attempts', sa.Integer(), server_default='0'),
        sa.Column('call_transcript', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_orders_tenant_id', 'orders', ['tenant_id'])
    op.create_index('ix_orders_ext_id', 'orders', ['external_order_id'])
    op.create_index('ix_orders_cust_phone', 'orders', ['customer_phone'])

    # 9. Knowledge Documents Table
    op.create_table(
        'knowledge_documents',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source_type', sa.String(length=50), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_knowledge_docs_tenant_id', 'knowledge_documents', ['tenant_id'])

    # 10. Document Chunks Table with Vector and TSVector
    op.create_table(
        'document_chunks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('knowledge_documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('tsv', TSVECTOR, sa.Computed("to_tsvector('english', content)", persisted=True)),
        sa.Column('embedding', pgvector.sqlalchemy.Vector(1536), nullable=True),
    )
    op.create_index('ix_doc_chunks_tenant_id', 'document_chunks', ['tenant_id'])
    op.create_index('ix_doc_chunks_doc_id', 'document_chunks', ['document_id'])

    # Vector HNSW Index (Cosine Ops)
    op.execute(
        """
        CREATE INDEX idx_document_chunks_vector ON document_chunks 
        USING hnsw (embedding vector_cosine_ops) 
        WITH (m = 16, ef_construction = 64);
        """
    )

    # Full-Text GIN Index for Hybrid Search
    op.execute("CREATE INDEX idx_document_chunks_tsv ON document_chunks USING gin (tsv);")

    # 11. MCP Tool Registry & Execution Logs Table
    op.create_table(
        'mcp_tools_registry',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('endpoint_url', sa.Text(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), server_default='true'),
    )
    op.create_index('ix_mcp_registry_tenant_id', 'mcp_tools_registry', ['tenant_id'])

    op.create_table(
        'mcp_tool_execution_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('conversation_id', UUID(as_uuid=True), sa.ForeignKey('conversations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('input_payload', JSONB(), server_default='{}'),
        sa.Column('output_payload', JSONB(), server_default='{}'),
        sa.Column('status', sa.String(length=50), server_default='success'),
        sa.Column('execution_time_ms', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_mcp_logs_tenant_id', 'mcp_tool_execution_logs', ['tenant_id'])
    op.create_index('ix_mcp_logs_conv_id', 'mcp_tool_execution_logs', ['conversation_id'])

    # ==========================================
    # Enable PostgreSQL Row-Level Security (RLS)
    # ==========================================
    for table in OPERATIONAL_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_policy ON {table}
            FOR ALL
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
            """
        )


def downgrade() -> None:
    # Drop RLS Policies and Disable RLS
    for table in reversed(OPERATIONAL_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    # Drop Tables in Reverse Dependency Order
    op.drop_table('mcp_tool_execution_logs')
    op.drop_table('mcp_tools_registry')
    op.drop_table('document_chunks')
    op.drop_table('knowledge_documents')
    op.drop_table('orders')
    op.drop_table('interaction_logs')
    op.drop_table('conversations')
    op.drop_table('agent_configs')
    op.drop_table('tenant_integrations')
    op.drop_table('organization_members')
    op.drop_table('users')
    op.drop_table('tenants')
