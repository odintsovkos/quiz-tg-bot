"""single screen: anchor message and session message registry

Revision ID: 9b1c4d2a7f10
Revises: 4e7319ee48f6
Create Date: 2026-09-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '9b1c4d2a7f10'
down_revision: str | None = '4e7319ee48f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('anchor_message_id', sa.BigInteger(), nullable=True))

    op.create_table('session_messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('chat_id', sa.BigInteger(), nullable=False),
    sa.Column('message_id', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['quiz_sessions.id'], name=op.f('fk_session_messages_session_id'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_session_messages')),
    sa.UniqueConstraint('session_id', 'message_id', name=op.f('uq_session_messages_session_id_message_id'))
    )
    with op.batch_alter_table('session_messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_session_messages_session_id'), ['session_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('session_messages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_session_messages_session_id'))

    op.drop_table('session_messages')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('anchor_message_id')
