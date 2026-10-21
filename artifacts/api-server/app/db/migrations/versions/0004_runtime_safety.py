"""Durable ingestion, checkout request identities and public quotas."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0004_runtime_safety"
down_revision = "0003_tenant_settings"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    users_columns = [c["name"] for c in inspector.get_columns("users")]
    if "clerk_user_id" not in users_columns:
        op.add_column("users", sa.Column("clerk_user_id", sa.String(255), nullable=True))
        op.create_index("ix_users_clerk_user_id", "users", ["clerk_user_id"], unique=True)

    existing_tables = inspector.get_table_names()
    if "workspace_identities" not in existing_tables:
        op.create_table("workspace_identities",
            sa.Column("clerk_user_id", sa.String(255), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role", sa.String(30), nullable=False))
        op.create_index("ix_workspace_identities_tenant_id", "workspace_identities", ["tenant_id"])

    if "webhook_jobs" not in existing_tables:
        op.create_table("webhook_jobs",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("provider", sa.String(30), nullable=False),
            sa.Column("event_id", sa.String(255), nullable=False),
            sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("payload", JSONB, nullable=False),
            sa.Column("topic", sa.String(100)),
            sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
            sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
            sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("lease_until", sa.DateTime(timezone=True)),
            sa.Column("last_error", sa.String(255)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("provider", "tenant_id", "event_id"))
        op.create_index("ix_webhook_jobs_tenant_id", "webhook_jobs", ["tenant_id"])
        op.create_index("ix_webhook_jobs_pending", "webhook_jobs", ["status", "available_at"])

    if "public_rate_counters" not in existing_tables:
        op.create_table("public_rate_counters",
            sa.Column("key", sa.String(255), primary_key=True),
            sa.Column("count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
        op.create_index("ix_public_rate_counters_expires_at", "public_rate_counters", ["expires_at"])

    if "checkout_requests" not in existing_tables:
        op.create_table("checkout_requests",
            sa.Column("key", sa.String(64), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(30), nullable=False, server_default="creating"),
            sa.Column("result", JSONB),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        op.create_index("ix_checkout_requests_tenant_id", "checkout_requests", ["tenant_id"])

    if "delivery_receipts" not in existing_tables:
        op.create_table("delivery_receipts",
            sa.Column("key", sa.String(64), primary_key=True),
            sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(30), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        op.create_index("ix_delivery_receipts_tenant_id", "delivery_receipts", ["tenant_id"])


def downgrade():
    op.drop_table("delivery_receipts")
    op.drop_table("workspace_identities")
    op.drop_table("checkout_requests")
    op.drop_table("public_rate_counters")
    op.drop_table("webhook_jobs")
    op.drop_index("ix_users_clerk_user_id", table_name="users")
    op.drop_column("users", "clerk_user_id")
