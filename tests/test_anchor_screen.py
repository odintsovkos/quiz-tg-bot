"""Единственный экран: правка якоря, запасной путь, уборка ленты сессии."""

from datetime import UTC, datetime

from app.bot import replies
from app.models import QuizSession
from app.repositories.sessions import SessionRepository
from tests.conftest import make_user
from tests.screen import ScreenBot, message, query

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


async def _user(session):
    user = make_user(7)
    session.add(user)
    await session.flush()
    return user


async def _quiz(session, user) -> QuizSession:
    quiz = QuizSession(
        user_id=user.id, total_questions=3, started_at=MOMENT, last_activity_at=MOMENT
    )
    session.add(quiz)
    await session.flush()
    return quiz


# --- 2.1 показ экрана ----------------------------------------------------


async def test_first_screen_is_sent_and_remembered(session):
    user = await _user(session)
    bot = ScreenBot()

    await replies.show(message(bot), session, user, "Меню")

    assert bot.sent == [(7, "Меню")]
    assert user.anchor_message_id == 101


async def test_next_screen_edits_the_anchor(session):
    user = await _user(session)
    bot = ScreenBot()
    await replies.show(message(bot), session, user, "Меню")

    await replies.show(query(bot), session, user, "Темы")

    assert bot.edits == [(7, 101, "Темы")]
    assert len(bot.sent) == 1
    assert user.anchor_message_id == 101


async def test_a_typed_command_moves_the_screen_down_the_chat(session):
    """Правка старого сообщения выше по ленте участнику не видна."""
    user = await _user(session)
    bot = ScreenBot()
    await replies.show(message(bot), session, user, "Меню")

    await replies.show(message(bot), session, user, "Справка")

    assert bot.edits == []
    assert bot.sent == [(7, "Меню"), (7, "Справка")]
    assert user.anchor_message_id == 102


async def test_the_previous_anchor_is_removed_when_the_screen_moves(session):
    user = await _user(session)
    bot = ScreenBot()
    await replies.show(message(bot), session, user, "Меню")

    await replies.show(message(bot), session, user, "Справка")

    assert bot.deleted == [101]


async def test_a_stale_anchor_from_a_previous_run_does_not_swallow_a_command(session):
    """Якорь пережил перезапуск, но команда всё равно получает свежий экран."""
    user = await _user(session)
    user.anchor_message_id = 55
    bot = ScreenBot()

    await replies.show(message(bot), session, user, "Меню")

    assert bot.sent == [(7, "Меню")]
    assert user.anchor_message_id == 101


# --- 2.2 запасной путь ---------------------------------------------------


async def test_unavailable_anchor_falls_back_to_a_new_message(session):
    user = await _user(session)
    user.anchor_message_id = 55
    bot = ScreenBot(edit_error="Bad Request: message to edit not found")

    await replies.show(query(bot), session, user, "Меню")

    assert bot.sent == [(7, "Меню")]
    assert user.anchor_message_id == 101


# --- 2.3 правка тем же содержимым ----------------------------------------


async def test_identical_edit_counts_as_success(session):
    user = await _user(session)
    user.anchor_message_id = 55
    bot = ScreenBot(edit_error="Bad Request: message is not modified")

    await replies.show(query(bot), session, user, "Меню")

    assert bot.sent == []
    assert user.anchor_message_id == 55


# --- 2.4 уборка при показе экрана ----------------------------------------


async def test_showing_a_screen_clears_the_session_feed(session):
    user = await _user(session)
    quiz = await _quiz(session, user)
    repository = SessionRepository(session)
    for message_id in (10, 11, 12):
        await repository.add_message(quiz.id, 7, message_id)
    bot = ScreenBot()

    await replies.show(message(bot), session, user, "Меню")

    assert bot.deleted == [10, 11, 12]
    assert await repository.list_messages(quiz.id) == []


async def test_showing_a_screen_without_a_feed_deletes_nothing(session):
    user = await _user(session)
    bot = ScreenBot()

    await replies.show(message(bot), session, user, "Меню")

    assert bot.delete_calls == []


# --- 5.2, 5.3 пачки и неудаляемые сообщения ------------------------------


async def test_feed_is_deleted_in_batches_of_a_hundred(session):
    user = await _user(session)
    quiz = await _quiz(session, user)
    repository = SessionRepository(session)
    for message_id in range(10, 10 + 150):
        await repository.add_message(quiz.id, 7, message_id)
    bot = ScreenBot()

    await replies.cleanup(bot, session, user)

    assert [len(call) for call in bot.delete_calls] == [100, 50]
    assert len(bot.deleted) == 150


async def test_undeletable_messages_are_skipped(session):
    user = await _user(session)
    quiz = await _quiz(session, user)
    repository = SessionRepository(session)
    for message_id in (10, 11, 12):
        await repository.add_message(quiz.id, 7, message_id)
    bot = ScreenBot(undeletable={11})

    await replies.cleanup(bot, session, user)

    assert bot.deleted == [10, 12]
    assert await repository.list_messages(quiz.id) == []


# --- лента сессии --------------------------------------------------------


async def test_feed_message_is_recorded_in_the_registry(session):
    user = await _user(session)
    quiz = await _quiz(session, user)
    bot = ScreenBot()

    await replies.send_feed(message(bot), session, user, quiz, "Вопрос 1")

    stored = await SessionRepository(session).list_messages(quiz.id)
    assert [item.message_id for item in stored] == [101]
