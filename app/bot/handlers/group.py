"""Групповой чат: подключение, отключение, приём ответов на опросы."""

from __future__ import annotations

from aiogram import Bot
from aiogram.filters import Command
from aiogram.types import Message, PollAnswer
from apscheduler.schedulers.base import BaseScheduler
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.filters import IsAdmin
from app.bot.routers import group, polls
from app.core.config import Settings
from app.core.db import SessionFactory
from app.core.logging import get_logger
from app.models import User
from app.repositories.chats import ChatRepository
from app.services.quiz.group import ChatRightsError, GroupQuizService
from app.services.quiz.schedule import ScheduleService

logger = get_logger(__name__)


def message_topic(message: Message) -> tuple[int | None, str | None]:
    """Тема, в которой отправлено сообщение, и её название.

    Идентификатор есть у любого сообщения из темы. Названия у него, как
    правило, нет: Bot API отдаёт имя только со служебным сообщением о
    создании темы, которое попадает сюда, если команда была ответом на него.
    """
    thread_id = message.message_thread_id
    if thread_id is None or not message.is_topic_message:
        return None, None
    created = getattr(message.reply_to_message, "forum_topic_created", None)
    return thread_id, getattr(created, "name", None)


def topic_label(topic_id: int | None, topic_title: str | None) -> str:
    """Как назвать ветку участнику: по имени, по номеру или общей лентой."""
    if topic_id is None:
        return texts.TOPIC_LABEL_GENERAL
    if topic_title:
        return texts.TOPIC_LABEL_NAMED.format(title=topic_title)
    return texts.TOPIC_LABEL_NUMBERED.format(id=topic_id)


@group.message(Command("connect"), IsAdmin())
async def handle_connect(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    user: User,
    settings: Settings,
    scheduler: BaseScheduler,
    session_factory: SessionFactory,
) -> None:
    """Подключение выполняется из самого чата — так запоминается его id."""
    service = GroupQuizService(session)
    topic_id, topic_title = message_topic(message)
    try:
        chat, existed = await service.connect(
            bot,
            message.chat.id,
            message.chat.title or str(message.chat.id),
            user.id,
            timezone=settings.default_timezone,
        )
    except ChatRightsError as error:
        text = (
            texts.CHAT_NO_POLL_RIGHTS
            if error.missing == "polls"
            else texts.CHAT_NO_MESSAGE_RIGHTS
        )
        await message.answer(text)
        return

    # Подключение изнутри темы сразу задаёт ветку: иначе типовой сценарий
    # требовал бы двух команд подряд в одном и том же месте.
    if topic_id is not None:
        await service.set_topic(chat, topic_id, topic_title)

    ScheduleService(scheduler, session_factory, bot).apply(chat)

    if existed:
        await message.answer(texts.CHAT_ALREADY_CONNECTED)
        return
    await message.answer(
        texts.CHAT_CONNECTED.format(
            interval=chat.interval_minutes,
            window_start=texts.format_time(chat.window_start),
            window_end=texts.format_time(chat.window_end),
        )
    )


@group.message(Command("topic"), IsAdmin())
async def handle_topic(message: Message, session: AsyncSession) -> None:
    """Привязать ветку публикации к теме, из которой отправлена команда.

    Та же команда вне темы возвращает чат на общую ленту: отдельная команда
    сброса не нужна, потому что место отправки уже всё говорит.
    """
    service = GroupQuizService(session)
    chat = await ChatRepository(session).get(message.chat.id)
    if chat is None:
        await message.answer(texts.CHAT_NOT_CONNECTED)
        return

    topic_id, topic_title = message_topic(message)
    await service.set_topic(chat, topic_id, topic_title)

    if topic_id is None:
        await message.answer(texts.TOPIC_CLEARED)
        return
    await message.answer(
        texts.TOPIC_BOUND.format(topic=topic_label(topic_id, topic_title))
    )


@group.message(Command("disconnect"), IsAdmin())
async def handle_disconnect(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    scheduler: BaseScheduler,
    session_factory: SessionFactory,
) -> None:
    removed = await GroupQuizService(session).disconnect(message.chat.id)
    if not removed:
        await message.answer(texts.CHAT_NOT_CONNECTED)
        return
    ScheduleService(scheduler, session_factory, bot).remove(message.chat.id)
    await message.answer(texts.CHAT_DISCONNECTED)


@polls.poll_answer()
async def handle_poll_answer(
    poll_answer: PollAnswer, session: AsyncSession, user: User
) -> None:
    """Ответ на опрос: неизвестный опрос игнорируется без ошибки."""
    recorded = await GroupQuizService(session).accept_poll_answer(
        user, poll_answer.poll_id, list(poll_answer.option_ids)
    )
    if recorded is None:
        logger.debug("poll answer ignored", extra={"poll_id": poll_answer.poll_id})
