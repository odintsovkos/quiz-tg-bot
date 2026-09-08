"""Хранение якоря личной переписки и реестра сообщений сессии."""

from datetime import UTC, datetime

from app.models import QuizSession
from app.repositories.sessions import SessionRepository
from app.repositories.users import UserRepository
from tests.conftest import make_user

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


async def _quiz(session) -> QuizSession:
    session.add(make_user())
    await session.flush()
    quiz = QuizSession(
        user_id=1, total_questions=3, started_at=MOMENT, last_activity_at=MOMENT
    )
    session.add(quiz)
    await session.flush()
    return quiz


async def test_anchor_is_stored_and_read_back(session):
    users = UserRepository(session)
    user = await users.add(make_user())

    await users.set_anchor(user, 555)

    assert await users.anchor_of(1) == 555


async def test_anchor_is_empty_for_a_new_user(session):
    users = UserRepository(session)
    await users.add(make_user())

    assert await users.anchor_of(1) is None


async def test_anchor_can_be_cleared(session):
    users = UserRepository(session)
    user = await users.add(make_user())
    await users.set_anchor(user, 555)

    await users.set_anchor(user, None)

    assert await users.anchor_of(1) is None


async def test_registry_keeps_messages_in_order(session):
    quiz = await _quiz(session)
    sessions = SessionRepository(session)

    for message_id in (10, 11, 12):
        await sessions.add_message(quiz.id, chat_id=1, message_id=message_id)

    stored = await sessions.list_messages(quiz.id)
    assert [item.message_id for item in stored] == [10, 11, 12]


async def test_registry_ignores_a_repeated_message(session):
    quiz = await _quiz(session)
    sessions = SessionRepository(session)

    await sessions.add_message(quiz.id, chat_id=1, message_id=10)
    await sessions.add_message(quiz.id, chat_id=1, message_id=10)

    assert len(await sessions.list_messages(quiz.id)) == 1


async def test_registry_is_cleared(session):
    quiz = await _quiz(session)
    sessions = SessionRepository(session)
    await sessions.add_message(quiz.id, chat_id=1, message_id=10)

    await sessions.clear_messages(quiz.id)

    assert await sessions.list_messages(quiz.id) == []
