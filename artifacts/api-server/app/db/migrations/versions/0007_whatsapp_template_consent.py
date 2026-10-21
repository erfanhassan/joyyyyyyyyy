from alembic import op
import sqlalchemy as sa

revision = "0007_whatsapp_template_consent"
down_revision = "0006_order_idempotency"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    conv_cols = [c["name"] for c in inspector.get_columns("conversations")]
    if "whatsapp_opt_in" not in conv_cols:
        op.add_column("conversations", sa.Column(
            "whatsapp_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()))
        op.alter_column("conversations", "whatsapp_opt_in", server_default=None)
    if "whatsapp_opt_in_updated_at" not in conv_cols:
        op.add_column("conversations", sa.Column(
            "whatsapp_opt_in_updated_at", sa.DateTime(timezone=True), nullable=True))
    if "whatsapp_opt_in_source" not in conv_cols:
        op.add_column("conversations", sa.Column(
            "whatsapp_opt_in_source", sa.String(255), nullable=True))


def downgrade():
    op.drop_column("conversations", "whatsapp_opt_in_source")
    op.drop_column("conversations", "whatsapp_opt_in_updated_at")
    op.drop_column("conversations", "whatsapp_opt_in")
