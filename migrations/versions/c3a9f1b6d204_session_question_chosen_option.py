"""review: remember the option the participant picked

Revision ID: c3a9f1b6d204
Revises: 9b1c4d2a7f10
Create Date: 2026-09-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c3a9f1b6d204'
down_revision: str | None = '9b1c4d2a7f10'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('session_questions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('chosen_option', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('session_questions', schema=None) as batch_op:
        batch_op.drop_column('chosen_option')
