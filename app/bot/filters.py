"""Фильтры роутеров.

Права проверяются фильтром на уровне роутера, а не проверкой внутри каждого
хендлера: так требование «проверка роли в момент выполнения» закрывается разом
для всех административных экранов, включая нажатия по старым сообщениям
(см. `design.md`, «Роутеры aiogram по зонам»).
"""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from app.core.logging import get_logger
from app.models import User, UserRole
from app.repositories.chats import ChatRepository

logger = get_logger(__name__)


class RoleFilter(BaseFilter):
    """Пропустить событие, только если роль участника в списке допустимых.

    Роль читается из профиля, положенного `UserMiddleware`, то есть из БД
    на момент нажатия, а не из данных кнопки.
    """

    def __init__(self, *roles: UserRole) -> None:
        self.roles = frozenset(roles)

    async def __call__(self, event: TelegramObject, user: User | None = None) -> bool:
        allowed = user is not None and user.role in self.roles
        if not allowed:
            # Отказ по роли иначе не оставляет никакого следа: событие просто
            # не доходит до хендлера, и со стороны это неотличимо от того,
            # что бот вообще не получил сообщение.
            logger.debug(
                "role filter rejected the event",
                extra={
                    "user_id": getattr(user, "id", None),
                    "role": getattr(getattr(user, "role", None), "value", None),
                    "expected": sorted(role.value for role in self.roles),
                },
            )
        return allowed


class IsAdmin(RoleFilter):
    """Администратор или владелец."""

    def __init__(self) -> None:
        super().__init__(UserRole.ADMIN, UserRole.OWNER)


class IsOwner(RoleFilter):
    """Только владелец — например, раздел управления администраторами."""

    def __init__(self) -> None:
        super().__init__(UserRole.OWNER)


class ConnectedChat(BaseFilter):
    """Пропустить событие только в подключённом администратором чате.

    Спека `bot-core`: в неподключённом групповом чате бот молчит.
    """

    async def __call__(self, event: TelegramObject, **data: object) -> bool:
        chat = getattr(event, "chat", None)
        chat_id = getattr(chat, "id", None)
        session = data.get("session")
        if chat_id is None or session is None:
            return False
        stored = await ChatRepository(session).get(int(chat_id))  # type: ignore[arg-type]
        return stored is not None
