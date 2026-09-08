"""Middleware диспетчера.

Сессия БД и профиль участника кладутся в данные события один раз, до вызова
фильтров, — поэтому фильтры по роли работают на актуальной роли, а не на той,
что была при отрисовке кнопки.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, User

from app.bot import replies
from app.core.db import SessionFactory
from app.core.logging import get_logger
from app.repositories.sessions import SessionRepository
from app.services.users import UserService

logger = get_logger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class DatabaseMiddleware(BaseMiddleware):
    """Открыть сессию БД на время обработки одного события.

    Транзакция короткая — ровно одно событие: держать её открытой на время
    сетевых вызовов Telegram нельзя, единственный писатель заблокирует всё.
    """

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def __call__(
        self, handler: Handler, event: TelegramObject, data: dict[str, Any]
    ) -> Any:
        async with self._session_factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
            except Exception:
                await session.rollback()
                raise
            await session.commit()
            return result


def event_user(event: TelegramObject) -> User | None:
    """Автор события, если он вообще есть (у служебных обновлений его нет)."""
    for attribute in ("from_user", "user"):
        candidate = getattr(event, attribute, None)
        if isinstance(candidate, User):
            return candidate
    return None


def display_name(user: User) -> str:
    parts = [user.first_name, user.last_name]
    return " ".join(part for part in parts if part) or str(user.id)


class UserMiddleware(BaseMiddleware):
    """Зарегистрировать участника при любом взаимодействии.

    Спека `bot-core`: профиль создаётся и при первом ответе в группе, а имя
    для отображения обновляется каждый раз.
    """

    async def __call__(
        self, handler: Handler, event: TelegramObject, data: dict[str, Any]
    ) -> Any:
        telegram_user = event_user(event)
        if telegram_user is None or telegram_user.is_bot:
            return await handler(event, data)

        session = data["session"]
        data["user"] = await UserService(session).register(
            telegram_user.id,
            display_name(telegram_user),
            telegram_user.username,
        )
        return await handler(event, data)


def is_private(event: TelegramObject) -> bool:
    chat = getattr(event, "chat", None)
    if chat is None:
        message = getattr(event, "message", None)
        chat = getattr(message, "chat", None)
    return getattr(chat, "type", None) == "private"


class CleanCommandsMiddleware(BaseMiddleware):
    """Убрать сообщение участника из личной переписки после обработки.

    Спека `bot-core`: на экране остаётся только якорь. Удаление идёт после
    обработчика — иначе тот не успел бы прочитать сообщение и записать его
    в реестр сессии.

    Подключается только к личным зонам: чужие сообщения в группе бот удалять
    не вправе, и спека этого прямо не допускает.
    """

    async def __call__(
        self, handler: Handler, event: TelegramObject, data: dict[str, Any]
    ) -> Any:
        result = await handler(event, data)
        if isinstance(event, Message) and is_private(event):
            await self._delete(event, data)
        return result

    async def _delete(self, message: Message, data: dict[str, Any]) -> None:
        """Неудача удаления остаётся в логе и участнику не показывается."""
        bot = message.bot
        if bot is None:  # pragma: no cover - вне диспетчера не бывает
            return
        session = data.get("session")
        if session is not None and await SessionRepository(session).is_tracked(
            message.chat.id, message.message_id
        ):
            # Команда запуска сессии уйдёт вместе с её лентой.
            return
        await replies.delete_quietly(bot, message.chat.id, message.message_id)
