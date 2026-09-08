"""Единственный экран личной переписки.

В личке бот держит один экран-якорь: смена режима меняет текст и клавиатуру
того же сообщения. Весь личный интерфейс проходит через `show`, поэтому новый
режим нельзя добавить в обход модели.

Осознанное исключение — лента сессии викторины: её сообщения отправляются
отдельно (`send_feed`), учитываются в реестре и убираются `cleanup`, как
только участник ушёл на любой экран вне сессии.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import QuizSession, User
from app.repositories.sessions import SessionRepository
from app.repositories.users import UserRepository

logger = get_logger(__name__)

Sender = Message | CallbackQuery

#: `deleteMessages` принимает не больше ста сообщений за вызов.
DELETE_BATCH = 100

#: Правка идентичного содержимого — не ошибка: два быстрых нажатия по одному
#: якорю приводят ко второй правке тем же текстом.
_NOT_MODIFIED = "message is not modified"


def accessible(query: CallbackQuery) -> Message | None:
    """Сообщение кнопки, если Telegram отдал его тело."""
    return query.message if isinstance(query.message, Message) else None


def _bot_of(target: Sender) -> Bot | None:
    bot: Bot | None = getattr(target, "bot", None)
    return bot


def _chat_of(target: Sender, user: User) -> int:
    """Чат экрана. В личке он совпадает с идентификатором участника."""
    chat = getattr(target, "chat", None)
    if chat is None:
        chat = getattr(getattr(target, "message", None), "chat", None)
    chat_id = getattr(chat, "id", None)
    return int(chat_id) if chat_id is not None else user.id


async def show(
    target: Sender,
    session: AsyncSession,
    user: User,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message | None:
    """Показать экран: убрать след сессии и заменить содержимое якоря.

    Возвращает новое сообщение, если экран пришлось отправить заново, и `None`,
    если он заменён правкой на месте.

    Правка на месте — ответ на нажатие кнопки: экран у участника перед глазами.
    На набранную команду экран переезжает вниз переписки новым сообщением,
    а прежний якорь удаляется: правка старого сообщения выше по ленте
    участнику не видна, и команда выглядела бы оставшейся без ответа.
    """
    bot = _bot_of(target)
    if bot is None:  # pragma: no cover - вне диспетчера не бывает
        return None
    chat_id = _chat_of(target, user)

    await cleanup(bot, session, user, chat_id=chat_id)

    anchor = user.anchor_message_id
    if anchor is not None and not _is_typed(target):
        edited = await _edit(bot, chat_id, anchor, text, reply_markup)
        if edited:
            return None

    sent = await _send_anchor(bot, session, user, chat_id, text, reply_markup)
    if anchor is not None and sent is not None and anchor != sent.message_id:
        await delete_quietly(bot, chat_id, anchor)
    return sent


def _is_typed(target: Sender) -> bool:
    """Событие от набранного участником сообщения, а не от нажатия кнопки."""
    return getattr(target, "message_id", None) is not None


async def _edit(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> bool:
    """Правка якоря «по возможности»: неудача не всплывает участнику."""
    try:
        await bot.edit_message_text(
            text, chat_id=chat_id, message_id=message_id, reply_markup=reply_markup
        )
    except TelegramBadRequest as error:
        if _NOT_MODIFIED in str(error).lower():
            return True
        logger.info(
            "anchor could not be edited",
            extra={"chat_id": chat_id, "message_id": message_id},
        )
        return False
    except Exception:  # pragma: no cover - сетевые сбои Telegram
        logger.warning("anchor edit failed", extra={"chat_id": chat_id})
        return False
    return True


async def _send_anchor(
    bot: Bot,
    session: AsyncSession,
    user: User,
    chat_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> Message | None:
    """Запасной путь: новое сообщение становится якорем."""
    sent = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    await UserRepository(session).set_anchor(user, sent.message_id)
    return sent


async def adopt(session: AsyncSession, user: User, message: Message) -> None:
    """Считать якорем уже отправленное сообщение."""
    await UserRepository(session).set_anchor(user, message.message_id)


async def send_feed(
    target: Sender,
    session: AsyncSession,
    user: User,
    quiz: QuizSession,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message | None:
    """Отправить сообщение ленты сессии и учесть его в реестре."""
    bot = _bot_of(target)
    if bot is None:  # pragma: no cover - вне диспетчера не бывает
        return None
    chat_id = _chat_of(target, user)
    sent = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    await SessionRepository(session).add_message(quiz.id, chat_id, sent.message_id)
    return sent


async def track(
    session: AsyncSession, quiz: QuizSession, chat_id: int, message_id: int
) -> None:
    """Учесть в реестре чужое сообщение — например, команду запуска."""
    await SessionRepository(session).add_message(quiz.id, chat_id, message_id)


async def send_plain(
    target: Sender,
    user: User,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message | None:
    """Обычное сообщение вне модели якоря.

    Единственный потребитель — пошаговый мастер добавления вопроса: он ведёт
    диалог текстовым вводом и в единственный экран не укладывается.
    """
    bot = _bot_of(target)
    if bot is None:  # pragma: no cover - вне диспетчера не бывает
        return None
    return await bot.send_message(_chat_of(target, user), text, reply_markup=reply_markup)


async def cleanup(
    bot: Bot, session: AsyncSession, user: User, *, chat_id: int | None = None
) -> None:
    """Убрать ленту сессий участника, если реестр непуст."""
    repository = SessionRepository(session)
    tracked = await repository.user_messages(user.id)
    if not tracked:
        return

    by_chat: dict[int, list[int]] = {}
    for item in tracked:
        by_chat.setdefault(item.chat_id or (chat_id or user.id), []).append(
            item.message_id
        )
    for target_chat, message_ids in by_chat.items():
        for start in range(0, len(message_ids), DELETE_BATCH):
            await _delete_batch(bot, target_chat, message_ids[start : start + DELETE_BATCH])

    await repository.clear_user_messages(user.id)


async def _delete_batch(bot: Bot, chat_id: int, message_ids: list[int]) -> None:
    """Пачка до ста сообщений; неудаляемые пропускаются поштучно."""
    try:
        await bot.delete_messages(chat_id, message_ids)
        return
    except Exception:
        logger.info(
            "batch delete refused, falling back to one by one",
            extra={"chat_id": chat_id, "count": len(message_ids)},
        )
    for message_id in message_ids:
        await delete_quietly(bot, chat_id, message_id)


async def delete_quietly(bot: Bot, chat_id: int, message_id: int) -> None:
    """Удалить сообщение «по возможности»: отказ Telegram только в лог."""
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        logger.info(
            "message could not be deleted",
            extra={"chat_id": chat_id, "message_id": message_id},
        )
