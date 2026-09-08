"""Общие фикстуры: чистая БД на каждый тест, без сети и без Telegram."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.db import SessionFactory, create_engine, create_session_factory
from app.models import Base, Question, QuestionOption, User, UserRole
from app.services.settings import SettingsService


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Кэш настроек общий для процесса — между тестами его надо сбрасывать."""
    SettingsService.reset_cache()
    yield
    SettingsService.reset_cache()


@pytest.fixture
async def engine(tmp_path) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.sqlite3'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> SessionFactory:
    return create_session_factory(engine)


@pytest.fixture
async def session(session_factory: SessionFactory):
    async with session_factory() as session:
        yield session


def make_user(user_id: int = 1, role: UserRole = UserRole.USER, name: str = "Иван") -> User:
    moment = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
    return User(
        id=user_id,
        role=role,
        display_name=name,
        username=None,
        first_seen_at=moment,
        last_seen_at=moment,
    )


def make_question(
    question_id: str = "dev.ch08.001",
    category: str = "Разработчик · Глава 8",
    *,
    is_active: bool = True,
    correct_index: int = 0,
    option_count: int = 4,
) -> Question:
    return Question(
        id=question_id,
        text=f"Вопрос {question_id}?",
        category=category,
        is_active=is_active,
        explanation="Пояснение",
        reference="8.1. Раздел",
        options=[
            QuestionOption(
                position=index,
                text=f"Вариант {index}",
                is_correct=index == correct_index,
            )
            for index in range(option_count)
        ],
    )
