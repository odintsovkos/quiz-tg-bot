"""Сборка объектов aiogram.

Middleware и роутеры регистрируются здесь в одном месте и в фиксированном
порядке: сначала узкие зоны (владелец, кабинет), затем общие.
"""

from __future__ import annotations

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot import routers
from app.bot.handlers.common import handle_error
from app.bot.middlewares import (
    CleanCommandsMiddleware,
    DatabaseMiddleware,
    UserMiddleware,
)
from app.core.db import SessionFactory


def _detach(router: Router) -> None:
    """Отвязать зону от прежнего диспетчера.

    Роутеры зон — модульные объекты, а aiogram запрещает включать уже
    привязанный роутер во второй диспетчер. В рабочем процессе диспетчер
    один, но CLI и тесты собирают его повторно в том же процессе.
    """
    # Публичного способа отвязать роутер в aiogram нет.
    router._parent_router = None


def create_bot(token: str) -> Bot:
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(session_factory: SessionFactory) -> Dispatcher:
    """Диспетчер с хранилищем FSM в памяти.

    Состояние диалогов кабинета терять при перезапуске не страшно; состояние
    викторины лежит в БД, поэтому сессия перезапуск переживает.
    """
    # Импорт регистрирует хендлеры в роутерах их зон.
    import app.bot.handlers  # noqa: F401

    dispatcher = Dispatcher(storage=MemoryStorage())

    for observer in (
        dispatcher.message,
        dispatcher.callback_query,
        dispatcher.poll_answer,
        dispatcher.my_chat_member,
    ):
        # Именно outer: inner-middleware aiogram оборачивает вызов хендлера
        # и отрабатывает уже после фильтров, а `IsAdmin` и `ConnectedChat`
        # читают профиль и сессию из данных события в момент проверки.
        observer.outer_middleware(DatabaseMiddleware(session_factory))
        observer.outer_middleware(UserMiddleware())

    # Уборка команд — только в личных зонах: чужие сообщения в группе
    # бот удалять не вправе.
    for zone in (routers.private_owner, routers.private_admin, routers.private_user):
        # Диспетчер в тестах и CLI собирается повторно на тех же роутерах,
        # поэтому middleware не должен накапливаться.
        if not any(
            isinstance(item, CleanCommandsMiddleware)
            for item in zone.message.middleware
        ):
            zone.message.middleware(CleanCommandsMiddleware())

    zones = (
        routers.private_owner,
        routers.private_admin,
        routers.private_user,
        routers.group,
        routers.polls,
    )
    for zone in zones:
        _detach(zone)
    dispatcher.include_routers(*zones)
    dispatcher.errors.register(handle_error)
    return dispatcher
