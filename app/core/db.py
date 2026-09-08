"""Движок и сессии SQLAlchemy поверх aiosqlite.

SQLite допускает одного писателя, поэтому включаем WAL и `busy_timeout`,
а транзакции держим короткими (см. `design.md`, «SQLite: WAL и короткие транзакции»).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

BUSY_TIMEOUT_MS = 5000

SessionFactory = async_sessionmaker[AsyncSession]


def _apply_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Создать движок и повесить установку PRAGMA на каждое соединение."""
    if database_url.startswith("sqlite+aiosqlite:///"):
        raw_path = database_url.removeprefix("sqlite+aiosqlite:///")
        if raw_path and raw_path != ":memory:":
            parent = Path(raw_path).parent
            if str(parent) not in ("", "."):
                parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(database_url, echo=echo, future=True)
    event.listen(engine.sync_engine, "connect", _apply_pragmas)
    return engine


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def session_scope(factory: SessionFactory) -> AsyncIterator[AsyncSession]:
    """Одна короткая транзакция: коммит при успехе, откат при исключении."""
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()


async def dispose_engine(engine: AsyncEngine) -> None:
    await engine.dispose()
