"""optional question difficulty and per-question answer lookup

Revision ID: f1b07c4a92de
Revises: d5e2b8c37a91
Create Date: 2026-09-12 00:00:00.000000
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import sqlalchemy as sa
from alembic import op

revision: str = 'f1b07c4a92de'
down_revision: str | None = 'd5e2b8c37a91'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


@contextmanager
def foreign_keys_off() -> Iterator[None]:
    """Снять проверку внешних ключей на время пересоздания таблицы.

    SQLite не умеет ALTER, поэтому batch-режим пересоздаёт таблицу: копия,
    `DROP TABLE questions`, переименование. Приложение держит
    `PRAGMA foreign_keys=ON`, и этот `DROP` уносит каскадом всё, что ссылается
    на вопрос, — варианты ответа, ответы участников, ленту сессий, опросы
    и историю заданных вопросов. Проверку надо снимать именно здесь.

    `PRAGMA foreign_keys` внутри транзакции ничего не делает, поэтому оба
    переключения идут вне транзакции миграции.
    """
    with op.get_context().autocommit_block():
        op.execute('PRAGMA foreign_keys=OFF')
    try:
        yield
    finally:
        with op.get_context().autocommit_block():
            op.execute('PRAGMA foreign_keys=ON')


def upgrade() -> None:
    # Сложность вопроса становится необязательной: её отсутствие больше не
    # подменяется «средней». Значения существующих вопросов не меняются.
    with foreign_keys_off():
        with op.batch_alter_table('questions', schema=None) as batch_op:
            batch_op.alter_column(
                'difficulty',
                existing_type=sa.String(length=16),
                nullable=True,
            )

    # Под агрегат «сколько ответов на этот вопрос и сколько из них верных»:
    # внешний ключ в SQLite индекса не создаёт, без него это полный просмотр
    # таблицы ответов. Индекс добавляется без пересоздания таблицы.
    with op.batch_alter_table('answers', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_answers_question_id'), ['question_id'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('answers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_answers_question_id'))

    # Обратная миграция вернёт NOT NULL: вопросы без сложности, если они
    # появились, надо заполнить до отката — иначе ограничение не пройдёт.
    with foreign_keys_off():
        with op.batch_alter_table('questions', schema=None) as batch_op:
            batch_op.alter_column(
                'difficulty',
                existing_type=sa.String(length=16),
                nullable=False,
            )
