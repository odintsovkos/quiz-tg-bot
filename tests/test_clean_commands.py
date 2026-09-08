"""Удаление команд участника в личке и неприкосновенность группы."""

from datetime import UTC, datetime

import pytest
from aiogram.types import Chat, Message

from app.bot import routers
from app.bot.factory import create_dispatcher
from app.bot.middlewares import CleanCommandsMiddleware
from app.core.db import create_engine, create_session_factory
from app.models import QuizSession
from app.repositories.sessions import SessionRepository
from tests.conftest import make_user
from tests.screen import ScreenBot

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


def Incoming(bot, chat_id: int = 7, chat_type: str = "private") -> Message:
    """Входящее сообщение с подменённым ботом."""
    message = Message.model_construct(
        message_id=42, date=MOMENT, chat=Chat(id=chat_id, type=chat_type)
    )
    return message.as_(bot)


@pytest.fixture
def clean() -> CleanCommandsMiddleware:
    return CleanCommandsMiddleware()


async def _handle(middleware, event, session=None):
    calls = []

    async def handler(_event, _data):
        calls.append(_event)
        return "ответ"

    data = {} if session is None else {"session": session}
    result = await middleware(handler, event, data)
    return calls, result


async def test_private_command_is_deleted_after_the_handler(clean):
    bot = ScreenBot()
    event = Incoming(bot)

    calls, result = await _handle(clean, event)

    assert calls and result == "ответ"
    assert bot.deleted == [42]


async def test_failed_deletion_is_silent(clean):
    bot = ScreenBot(undeletable={42})
    event = Incoming(bot)

    calls, result = await _handle(clean, event)

    assert calls and result == "ответ"
    assert bot.deleted == []


async def test_group_message_is_not_deleted(clean):
    bot = ScreenBot()
    event = Incoming(bot, chat_id=-100, chat_type="supergroup")

    await _handle(clean, event)

    assert bot.deleted == []


async def test_launch_command_stays_for_the_feed_cleanup(clean, session):
    """Команда запуска сессии уже в реестре — её уберёт уборка ленты."""
    user = make_user(7)
    session.add(user)
    await session.flush()
    quiz = QuizSession(
        user_id=7, total_questions=3, started_at=MOMENT, last_activity_at=MOMENT
    )
    session.add(quiz)
    await session.flush()
    await SessionRepository(session).add_message(quiz.id, 7, 42)
    bot = ScreenBot()

    await _handle(clean, Incoming(bot), session)

    assert bot.deleted == []


def test_middleware_is_not_attached_to_the_group_router():
    factory = create_session_factory(create_engine("sqlite+aiosqlite:///:memory:"))
    create_dispatcher(factory)

    attached = [type(item).__name__ for item in routers.group.message.middleware]
    assert "CleanCommandsMiddleware" not in attached
    private = [type(item).__name__ for item in routers.private_user.message.middleware]
    assert private.count("CleanCommandsMiddleware") == 1
