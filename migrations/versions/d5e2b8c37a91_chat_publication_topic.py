"""group topic: publication branch of a connected chat

Revision ID: d5e2b8c37a91
Revises: c3a9f1b6d204
Create Date: 2026-09-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd5e2b8c37a91'
down_revision: str | None = 'c3a9f1b6d204'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('chats', schema=None) as batch_op:
        batch_op.add_column(sa.Column('topic_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('topic_title', sa.String(length=256), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('chats', schema=None) as batch_op:
        batch_op.drop_column('topic_title')
        batch_op.drop_column('topic_id')
