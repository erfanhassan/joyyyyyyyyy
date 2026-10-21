"""0003_tenant_settings_and_multi_merchant

Revision ID: 0003_tenant_settings_and_multi_merchant
Revises: 0002_langgraph_checkpoints
Create Date: 2026-10-21 04:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '0003_tenant_settings'
down_revision: Union[str, None] = '0002_langgraph_checkpoints'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add currency, timezone, domain, settings to tenants table
    op.add_column('tenants', sa.Column('currency', sa.String(length=10), server_default='BDT', nullable=True))
    op.add_column('tenants', sa.Column('timezone', sa.String(length=50), server_default='Asia/Dhaka', nullable=True))
    op.add_column('tenants', sa.Column('domain', sa.String(length=255), nullable=True))
    op.add_column('tenants', sa.Column('settings', JSONB, server_default='{}', nullable=True))


def downgrade() -> None:
    op.drop_column('tenants', 'settings')
    op.drop_column('tenants', 'domain')
    op.drop_column('tenants', 'timezone')
    op.drop_column('tenants', 'currency')
