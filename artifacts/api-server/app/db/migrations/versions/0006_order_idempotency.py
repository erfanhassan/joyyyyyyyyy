from alembic import op
revision = "0006_order_idempotency"
down_revision = "0005_privacy_requests"
branch_labels = depends_on = None


def upgrade():
    # Do not silently delete/merge historical orders to make this index fit.
    # A duplicate dataset must be reviewed before applying the migration.
    op.create_index("uq_orders_store_external",
        "orders", ["tenant_id", "storefront_provider", "external_order_id"], unique=True)
    op.execute("UPDATE agent_configs SET is_active = false WHERE agent_type <> 'social_sales'")


def downgrade():
    op.drop_index("uq_orders_store_external", table_name="orders")
