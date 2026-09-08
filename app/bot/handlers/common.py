"""Стартовые команды и общая обработка ошибок."""

from __future__ import annotations

from aiogram import Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, BotCommandScopeDefault, ErrorEvent, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import replies, texts
from app.bot.keyboards.common import back_to_menu, main_menu
from app.bot.routers import private_user
from app.core.logging import get_logger
from app.models import User

logger = get_logger(__name__)


@private_user.message(CommandStart())
async def handle_start(
    message: Message, session: AsyncSession, user: User
) -> None:
    await replies.show(
        message,
        session,
        user,
        texts.START.format(name=user.display_name),
        main_menu(),
    )


@private_user.message(Command("help"))
async def handle_help(message: Message, session: AsyncSession, user: User) -> None:
    """Состав справки зависит от роли вызвавшего."""
    await replies.show(message, session, user, help_text(user), back_to_menu())


def help_text(user: User) -> str:
    if user.role.is_admin:
        return texts.HELP_USER + texts.HELP_ADMIN_EXTRA
    return texts.HELP_USER


async def register_commands(bot: Bot) -> None:
    """Зарегистрировать список команд, чтобы он был виден в меню клиента."""
    await bot.set_my_commands(
        [
            BotCommand(command=name, description=description)
            for name, description in texts.COMMAND_DESCRIPTIONS.items()
        ],
        scope=BotCommandScopeDefault(),
    )


async def handle_error(event: ErrorEvent) -> bool:
    """Единая обработка необработанных исключений.

    Спека `bot-core`: участник получает нейтральное сообщение, а трассировка,
    SQL и содержимое исключения остаются в логе.
    """
    update = event.update
    message = getattr(update, "message", None)
    callback = getattr(update, "callback_query", None)
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    user = getattr(message or callback, "from_user", None)

    logger.exception(
        "handler failed",
        extra={
            "update_type": type(update).__name__,
            "event_type": event.update.event_type,
            "chat_id": chat_id,
            "user_id": getattr(user, "id", None),
        },
    )

    try:
        if callback is not None:
            await callback.answer(texts.ERROR_GENERIC, show_alert=True)
        elif message is not None:
            await message.answer(texts.ERROR_GENERIC)
    except Exception:  # pragma: no cover - ответить не всегда возможно
        logger.warning("could not notify the user about the error")
    return True
