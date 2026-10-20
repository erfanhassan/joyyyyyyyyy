"""0002_langgraph_checkpoints

Revision ID: 0002_langgraph_checkpoints
Revises: 0001_initial_schema
Create Date: 2026-10-20 04:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0002_langgraph_checkpoints'
down_revision: Union[str, None] = '0001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Checkpoints Table
    op.create_table(
        'checkpoints',
        sa.Column('thread_id', sa.String(length=255), nullable=False),
        sa.Column('checkpoint_ns', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('checkpoint_id', sa.String(length=255), nullable=False),
        sa.Column('parent_checkpoint_id', sa.String(length=255), nullable=True),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('checkpoint_blob', sa.LargeBinary(), nullable=False),
        sa.Column('metadata_type', sa.String(length=50), nullable=False),
        sa.Column('metadata_blob', sa.LargeBinary(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('thread_id', 'checkpoint_ns', 'checkpoint_id'),
    )

    # 2. Checkpoint Blobs Table
    op.create_table(
        'checkpoint_blobs',
        sa.Column('thread_id', sa.String(length=255), nullable=False),
        sa.Column('checkpoint_ns', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('channel', sa.String(length=255), nullable=False),
        sa.Column('version', sa.String(length=255), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('blob', sa.LargeBinary(), nullable=True),
        sa.PrimaryKeyConstraint('thread_id', 'checkpoint_ns', 'channel', 'version'),
    )

    # 3. Checkpoint Writes Table
    op.create_table(
        'checkpoint_writes',
        sa.Column('thread_id', sa.String(length=255), nullable=False),
        sa.Column('checkpoint_ns', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('checkpoint_id', sa.String(length=255), nullable=False),
        sa.Column('task_id', sa.String(length=255), nullable=False),
        sa.Column('idx', sa.Integer(), nullable=False),
        sa.Column('channel', sa.String(length=255), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('blob', sa.LargeBinary(), nullable=True),
        sa.Column('task_path', sa.String(length=255), nullable=False, server_default=''),
        sa.PrimaryKeyConstraint('thread_id', 'checkpoint_ns', 'checkpoint_id', 'task_id', 'idx'),
    )


def downgrade() -> None:
    op.drop_table('checkpoint_writes')
    op.drop_table('checkpoint_blobs')
    op.drop_table('checkpoints')
