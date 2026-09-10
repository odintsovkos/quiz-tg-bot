"""Ветка публикации подключённого чата: хранение, привязка, публикация."""

from __future__ import annotations

from datetime import UTC, datetime, time

import pytest
from aiogram.types import Chat as TgChat
from aiogram.types import ForumTopicCreated, Message

from app.bot.handlers.group import handle_topic
from app.models import Chat
from app.repositories.chats import ChatRepository
from app.services.quiz.group import (
    ChatUnavailableError,
    GroupQuizService,
    is_topic_unavailable,
)
from tests.conftest import make_question
from tests.screen import ScreenBot

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
GROUP = -1002895411698


def make_chat(chat_id: int = GROUP, **overrides) -> Chat:
    values = {
        "id": chat_id,
        "title": "Чат 1С",
        "is_active": True,
        "interval_minutes": 180,
        "window_start": time(9, 0),
        "window_end": time(21, 0),
        "timezone": "Europe/Moscow",
        "round_number": 1,
        "connected_at": MOMENT,
        "connected_by": 1,
    }
    values.update(overrides)
    return Chat(**values)


# --- 1.1, 1.3 хранение ветки ---------------------------------------------


async def test_a_new_chat_publishes_to_the_general_feed(session):
    chat = await ChatRepository(session).add(make_chat())

    assert chat.topic_id is None
    assert chat.topic_title is None


async def test_the_topic_is_stored_with_its_title(session):
    chats = ChatRepository(session)
    chat = await chats.add(make_chat())

    await chats.set_topic(chat, 42, "Викторина")

    stored = await chats.get(GROUP)
    assert stored.topic_id == 42
    assert stored.topic_title == "Викторина"


async def test_clearing_the_topic_returns_the_chat_to_the_general_feed(session):
    chats = ChatRepository(session)
    chat = await chats.add(make_chat())
    await chats.set_topic(chat, 42, "Викторина")

    await chats.clear_topic(chat)

    stored = await chats.get(GROUP)
    assert stored.topic_id is None
    assert stored.topic_title is None


async def test_a_topic_without_an_id_carries_no_title(session):
    """Общая лента не бывает именованной — название снимается вместе с веткой."""
    chats = ChatRepository(session)
    chat = await chats.add(make_chat())

    await chats.set_topic(chat, None, "Викторина")

    assert chat.topic_id is None
    assert chat.topic_title is None


# --- 2. привязка ветки командой ------------------------------------------


def incoming(bot, *, thread_id=None, topic_name=None, chat_id=GROUP):
    """Сообщение в группе: в теме либо в общей ленте."""
    reply = None
    if topic_name is not None:
        reply = Message.model_construct(
            message_id=1,
            date=MOMENT,
            chat=TgChat(id=chat_id, type="supergroup"),
            forum_topic_created=ForumTopicCreated(name=topic_name, icon_color=0),
        )
    message = Message.model_construct(
        message_id=10,
        date=MOMENT,
        chat=TgChat(id=chat_id, type="supergroup", title="Чат 1С"),
        message_thread_id=thread_id,
        is_topic_message=thread_id is not None,
        reply_to_message=reply,
    )
    return message.as_(bot)


async def test_the_command_inside_a_topic_binds_it(session):
    chat = await ChatRepository(session).add(make_chat())
    bot = ScreenBot()

    await handle_topic(incoming(bot, thread_id=42), session)

    assert chat.topic_id == 42
    assert "тема №42" in bot.sent[-1][1]


async def test_the_command_picks_up_the_topic_name_when_it_is_there(session):
    chat = await ChatRepository(session).add(make_chat())
    bot = ScreenBot()

    await handle_topic(incoming(bot, thread_id=42, topic_name="Викторина"), session)

    assert chat.topic_title == "Викторина"
    assert "«Викторина»" in bot.sent[-1][1]


async def test_the_command_outside_a_topic_clears_the_branch(session):
    chats = ChatRepository(session)
    chat = await chats.add(make_chat(topic_id=42, topic_title="Викторина"))
    bot = ScreenBot()

    await handle_topic(incoming(bot), session)

    assert chat.topic_id is None
    assert chat.topic_title is None
    assert "общую ленту" in bot.sent[-1][1]


async def test_the_command_in_an_unconnected_chat_is_refused(session):
    bot = ScreenBot()

    await handle_topic(incoming(bot, thread_id=42), session)

    assert "не подключён" in bot.sent[-1][1]


# --- 4, 5. публикация в ветку и её потеря --------------------------------


async def publishable(session):
    """Подключённый чат и один активный вопрос в банке."""
    session.add(make_question("dev.ch17.021", "Разработчик · Глава 17"))
    await session.flush()


async def test_a_poll_goes_to_the_branch(session):
    chat = await ChatRepository(session).add(make_chat(topic_id=42))
    await publishable(session)
    bot = ScreenBot()

    outcome = await GroupQuizService(session).publish(bot, chat, now=MOMENT)

    assert outcome.poll is not None
    assert bot.polls[-1]["message_thread_id"] == 42


async def test_a_poll_without_a_branch_goes_to_the_general_feed(session):
    chat = await ChatRepository(session).add(make_chat())
    await publishable(session)
    bot = ScreenBot()

    await GroupQuizService(session).publish(bot, chat, now=MOMENT)

    assert bot.polls[-1]["message_thread_id"] is None


async def test_an_unavailable_topic_falls_back_to_the_general_feed(session):
    chat = await ChatRepository(session).add(make_chat(topic_id=42, topic_title="Т"))
    await publishable(session)
    bot = ScreenBot(topic_error="Bad Request: message thread not found")

    outcome = await GroupQuizService(session).publish(bot, chat, now=MOMENT)

    assert outcome.poll is not None, "вопрос должен быть опубликован, а не потерян"
    assert outcome.topic_lost is True
    assert chat.topic_id is None and chat.topic_title is None
    assert chat.is_active is True, "чат жив — недоступна была только тема"
    assert bot.polls[-1]["message_thread_id"] is None


async def test_an_unrecognised_failure_still_marks_the_chat_unavailable(session):
    chat = await ChatRepository(session).add(make_chat(topic_id=42))
    await publishable(session)
    bot = ScreenBot(topic_error="Forbidden: bot was kicked from the group chat")

    with pytest.raises(ChatUnavailableError):
        await GroupQuizService(session).publish(bot, chat, now=MOMENT)

    assert chat.topic_id == 42, "ветка снимается только при отказе именно по теме"


def test_topic_failures_are_told_apart_from_other_errors():
    assert is_topic_unavailable(Exception("Bad Request: message thread not found"))
    assert is_topic_unavailable(Exception("Bad Request: TOPIC_CLOSED"))
    assert not is_topic_unavailable(Exception("Forbidden: bot was kicked"))
    assert not is_topic_unavailable(Exception("Bad Request: chat not found"))


# --- 3. подключение перенимает тему --------------------------------------


async def connect(bot, session, message):
    from app.bot.handlers.group import handle_connect
    from app.core.config import Settings

    settings = Settings.model_construct(
        bot_token="1:test", owner_id=1, default_timezone="Europe/Moscow"
    )
    await handle_connect(
        message,
        bot,
        session,
        await _owner(session),
        settings,
        _scheduler(),
        None,
    )


async def _owner(session):
    from app.services.users import UserService

    return await UserService(session).ensure_owner(1)


def _scheduler():
    class Noop:
        def get_job(self, job_id):
            return None

        def get_jobs(self):
            return []

        def add_job(self, *args, **kwargs):
            return None

    return Noop()


async def test_connecting_inside_a_topic_binds_it(session):
    bot = ScreenBot()

    await connect(bot, session, incoming(bot, thread_id=42, topic_name="Викторина"))

    chat = await ChatRepository(session).get(GROUP)
    assert chat.topic_id == 42
    assert chat.topic_title == "Викторина"


async def test_connecting_outside_a_topic_leaves_the_general_feed(session):
    bot = ScreenBot()

    await connect(bot, session, incoming(bot))

    chat = await ChatRepository(session).get(GROUP)
    assert chat.topic_id is None


# --- 5.3 уведомление о снятой ветке --------------------------------------


async def test_admins_are_told_when_the_branch_is_lost(session_factory):
    from app.core.db import session_scope
    from app.services.quiz.schedule import ScheduleService

    async with session_scope(session_factory) as db:
        await _owner(db)
        await ChatRepository(db).add(make_chat(topic_id=42, topic_title="Т"))
        db.add(make_question("dev.ch17.021", "Разработчик · Глава 17"))
    bot = ScreenBot(topic_error="Bad Request: message thread not found")

    published = await ScheduleService(_scheduler(), session_factory, bot).publish_now(
        GROUP, now=MOMENT
    )

    assert published is True
    assert any("стала недоступна" in text for _, text in bot.sent)


# --- 6. кабинет ----------------------------------------------------------


def test_the_chat_card_shows_the_branch():
    from app.bot.handlers.admin import render_chat

    named = render_chat(make_chat(topic_id=42, topic_title="Викторина"), 0)
    numbered = render_chat(make_chat(topic_id=42), 0)
    general = render_chat(make_chat(), 0)

    assert "тема «Викторина»" in named
    assert "тема №42" in numbered
    assert "общая лента чата" in general


def test_the_card_explains_that_a_branch_is_set_from_the_topic():
    from app.bot.handlers.admin import render_chat

    text = render_chat(make_chat(), 0)

    assert "/topic" in text
    assert "не отдаёт список тем" in text


def test_the_reset_button_appears_only_with_a_branch():
    from app.bot.keyboards.admin import chat_actions

    def labels(chat):
        markup = chat_actions(chat)
        return [b.text for row in markup.inline_keyboard for b in row]

    assert any("общую ленту" in label for label in labels(make_chat(topic_id=42)))
    assert not any("общую ленту" in label for label in labels(make_chat()))


async def test_scheduled_publication_uses_the_chat_branch(session_factory):
    """Задача расписания идёт тем же путём, что и ручной запуск."""
    from app.core.db import session_scope
    from app.services.quiz.schedule import ScheduleService

    async with session_scope(session_factory) as db:
        await ChatRepository(db).add(make_chat(topic_id=42))
        db.add(make_question("dev.ch17.021", "Разработчик · Глава 17"))
    bot = ScreenBot()

    # 12:00 UTC — 15:00 MSK, внутри окна активности чата.
    published = await ScheduleService(
        _scheduler(), session_factory, bot
    ).publish_scheduled(GROUP, now=MOMENT)

    assert published is True
    assert bot.polls[-1]["message_thread_id"] == 42
