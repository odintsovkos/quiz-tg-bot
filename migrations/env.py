"""Окружение Alembic: схема берётся из ORM-моделей, URL — из конфигурации."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from app.core.db import create_engine
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    """URL из `-x url=...`, затем из окружения, затем из `alembic.ini`."""
    from_argument = context.get_x_argument(as_dictionary=True).get("url")
    if from_argument:
        return str(from_argument)
    db_path = os.environ.get("DB_PATH")
    if db_path:
        return f"sqlite+aiosqlite:///{db_path}"
    configured = config.get_main_option("sqlalchemy.url", "")
    return configured or "sqlite+aiosqlite:///data/quiz.sqlite3"


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite не умеет ALTER — batch-режим пересоздаёт таблицу
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_engine(database_url())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
