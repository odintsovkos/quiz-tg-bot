"""Миграции на непустой базе: данные должны переживать пересоздание таблиц.

SQLite не умеет ALTER, поэтому batch-режим alembic пересоздаёт таблицу —
копия, `DROP TABLE`, переименование. Приложение держит
`PRAGMA foreign_keys=ON`, и такой `DROP` уносит каскадом всё, что ссылается
на строку: варианты ответа, ответы участников, ленту сессий, опросы.
Один раз это уже случилось на рабочей базе, поэтому проверяется отдельно.
"""

from __future__ import annotations

import sqlite3

import pytest
from alembic import command
from alembic.config import Config

PREVIOUS = "d5e2b8c37a91"
QUESTION = "dev.ch21.008"


def alembic_config(db_path) -> Config:
    config = Config("alembic.ini")
    config.cmd_opts = None
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    return config


def fill(db_path) -> None:
    """Вопрос с вариантами, участник и его ответ — то, что нельзя потерять."""
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO questions (id, text, category, difficulty, is_active) "
            "VALUES (?, 'Вопрос?', 'Разработчик · Глава 21', 'medium', 1)",
            (QUESTION,),
        )
        connection.executemany(
            "INSERT INTO question_options (question_id, position, text, is_correct) "
            "VALUES (?, ?, ?, ?)",
            [(QUESTION, index, f"Вариант {index}", index == 0) for index in range(4)],
        )
        connection.execute(
            "INSERT INTO users (id, role, display_name, first_seen_at, last_seen_at) "
            "VALUES (7, 'user', 'Иван', '2026-09-01', '2026-09-01')"
        )
        connection.execute(
            "INSERT INTO answers "
            "(user_id, question_id, source, is_correct, counted, answered_at, quiz_date) "
            "VALUES (7, ?, 'private', 1, 1, '2026-09-01', '2026-09-01')",
            (QUESTION,),
        )
        connection.commit()
    finally:
        connection.close()


def counts(db_path) -> dict[str, int]:
    connection = sqlite3.connect(db_path)
    try:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("questions", "question_options", "answers")
        }
    finally:
        connection.close()


@pytest.fixture
def filled_db(tmp_path):
    """База на предыдущей ревизии с данными, которые ссылаются на вопрос."""
    db_path = tmp_path / "quiz.sqlite3"
    config = alembic_config(db_path)
    command.upgrade(config, PREVIOUS)
    fill(db_path)
    assert counts(db_path) == {"questions": 1, "question_options": 4, "answers": 1}
    return db_path, config


def test_upgrade_keeps_rows_that_reference_a_question(filled_db):
    db_path, config = filled_db

    command.upgrade(config, "head")

    assert counts(db_path) == {"questions": 1, "question_options": 4, "answers": 1}


def test_upgrade_leaves_referential_integrity_intact(filled_db):
    db_path, config = filled_db

    command.upgrade(config, "head")

    connection = sqlite3.connect(db_path)
    try:
        assert list(connection.execute("PRAGMA foreign_key_check")) == []
    finally:
        connection.close()


def test_downgrade_and_upgrade_again_keep_the_data(filled_db):
    db_path, config = filled_db

    command.upgrade(config, "head")
    command.downgrade(config, PREVIOUS)
    command.upgrade(config, "head")

    assert counts(db_path) == {"questions": 1, "question_options": 4, "answers": 1}


def test_difficulty_becomes_nullable(filled_db):
    db_path, config = filled_db

    command.upgrade(config, "head")

    connection = sqlite3.connect(db_path)
    try:
        notnull = [
            row[3]
            for row in connection.execute("PRAGMA table_info(questions)")
            if row[1] == "difficulty"
        ]
        assert notnull == [0]
        connection.execute(
            "INSERT INTO questions (id, text, category, is_active) "
            "VALUES ('x.001', 'Без сложности?', 'Тема', 1)"
        )
        connection.commit()
    finally:
        connection.close()
