from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision = "0005_privacy_requests"
down_revision = "0004_runtime_safety"
branch_labels = depends_on = None


def upgrade():
    op.create_table("privacy_requests",
        sa.Column("code", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))


def downgrade():
    op.drop_table("privacy_requests")
