"""Проход события через настоящий диспетчер.

Обработчики в остальных тестах вызываются напрямую, поэтому порядок
middleware и фильтров ими не проверяется. Здесь событие идёт полным путём
aiogram: профиль и сессия БД должны попасть в данные до фильтров, иначе
`IsAdmin` и `ConnectedChat` отвергают всё молча.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TgUser

from app.bot.callbacks import AdminChatCallback
from app.bot.factory import create_dispatcher
from app.core.db import session_scope
from app.core.scheduler import create_scheduler
from app.models import Chat as ChatModel
from app.models import UserRole
from app.services.quiz.schedule import job_id
from app.services.users import UserService
from tests.conftest import make_question
from tests.screen import ScreenBot

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
OWNER = 785656472
GROUP = -1001234567890


@pytest.fixture
async def dispatcher(session_factory):
    return create_dispatcher(session_factory)


@pytest.fixture
async def scheduler():
    """Планировщик собирается ровно как в проде: иначе тест не увидит ни
    сериализацию задачи, ни борьбу за запись в базу."""
    scheduler = create_scheduler("Europe/Moscow")
    scheduler.start(paused=True)
    try:
        yield scheduler
    finally:
        scheduler.shutdown(wait=False)


def update(text: str, *, chat_id: int, chat_type: str, user_id: int = OWNER) -> Update:
    return Update(
        update_id=1,
        message=Message(
            message_id=10,
            date=MOMENT,
            chat=Chat(id=chat_id, type=chat_type),
            from_user=TgUser(id=user_id, is_bot=False, first_name="Иван"),
            text=text,
        ),
    )


async def make_owner(session_factory) -> None:
    async with session_scope(session_factory) as session:
        await UserService(session).ensure_owner(OWNER)


async def feed(dispatcher, bot, event: Update, **data):
    return await dispatcher.feed_update(bot, event, **data)


async def test_group_connect_reaches_the_handler(
    dispatcher, scheduler, session_factory
):
    """Подключение проходит целиком: фильтр по роли, запись чата, задача."""
    await make_owner(session_factory)
    bot = ScreenBot()

    await feed(
        dispatcher,
        bot,
        update("/connect", chat_id=GROUP, chat_type="supergroup"),
        settings=_settings(),
        scheduler=scheduler,
        session_factory=session_factory,
    )

    async with session_scope(session_factory) as session:
        stored = await session.get(ChatModel, GROUP)
    assert stored is not None, "чат не подключился — событие не дошло до хендлера"
    assert scheduler.get_job(job_id(GROUP)) is not None
    assert bot.sent, "участник не получил подтверждение"


async def test_group_connect_from_a_plain_user_is_ignored(
    dispatcher, scheduler, session_factory
):
    bot = ScreenBot()

    await feed(
        dispatcher,
        bot,
        update("/connect", chat_id=GROUP, chat_type="supergroup", user_id=999),
        settings=_settings(),
        scheduler=scheduler,
        session_factory=session_factory,
    )

    async with session_scope(session_factory) as session:
        stored = await session.get(ChatModel, GROUP)
    assert stored is None


async def test_the_profile_is_available_to_filters(dispatcher, session_factory):
    """Роль читается фильтром, значит профиль уже лежит в данных события."""
    await make_owner(session_factory)
    bot = ScreenBot()

    await feed(dispatcher, bot, update("/start", chat_id=OWNER, chat_type="private"))

    async with session_scope(session_factory) as session:
        profile = await UserService(session).register(OWNER, "Иван")
        assert profile.role is UserRole.OWNER
    assert bot.sent, "личный экран не отправлен"


def _settings():
    from app.core.config import Settings

    return Settings.model_construct(
        bot_token="1:test", owner_id=OWNER, default_timezone="Europe/Moscow"
    )


async def test_admin_cabinet_opens_for_the_owner(dispatcher, session_factory):
    await make_owner(session_factory)
    bot = ScreenBot()

    await feed(dispatcher, bot, update("/admin", chat_id=OWNER, chat_type="private"))

    assert bot.sent, "кабинет не открылся"


def press(data: str, *, user_id: int = OWNER) -> Update:
    """Нажатие кнопки в личке — событие с уже открытой транзакцией события."""
    return Update(
        update_id=2,
        callback_query=CallbackQuery(
            id="cb-1",
            from_user=TgUser(id=user_id, is_bot=False, first_name="Иван"),
            chat_instance="ci-1",
            data=data,
            message=Message(
                message_id=11,
                date=MOMENT,
                chat=Chat(id=user_id, type="private"),
            ),
        ),
    )


async def test_publishing_from_the_cabinet_does_not_deadlock_the_database(
    dispatcher, scheduler, session_factory
):
    """Публикация идёт внутри транзакции события, своей сессии открывать нельзя.

    Вторая сессия на том же файле SQLite ждала бы блокировку, которую держит
    транзакция этого же события, и падала бы с `database is locked`.
    """
    await make_owner(session_factory)
    bot = ScreenBot()
    await feed(
        dispatcher,
        bot,
        update("/connect", chat_id=GROUP, chat_type="supergroup"),
        settings=_settings(),
        scheduler=scheduler,
        session_factory=session_factory,
    )
    async with session_scope(session_factory) as session:
        session.add(make_question("dev.ch17.021", "Разработчик · Глава 17"))

    await feed(
        dispatcher,
        bot,
        press(AdminChatCallback(action="publish", chat_id=GROUP).pack()),
        settings=_settings(),
        scheduler=scheduler,
        session_factory=session_factory,
    )

    assert bot.polls, "опрос не опубликован"
    async with session_scope(session_factory) as session:
        from sqlalchemy import func, select

        from app.models import GroupPoll

        stored = await session.scalar(select(func.count()).select_from(GroupPoll))
    assert stored == 1


async def test_manual_publication_uses_the_chat_branch(
    dispatcher, scheduler, session_factory
):
    """Ручной запуск из кабинета адресуется в ветку так же, как расписание."""
    await make_owner(session_factory)
    bot = ScreenBot()
    await feed(
        dispatcher,
        bot,
        update("/connect", chat_id=GROUP, chat_type="supergroup"),
        settings=_settings(),
        scheduler=scheduler,
        session_factory=session_factory,
    )
    async with session_scope(session_factory) as session:
        session.add(make_question("dev.ch17.021", "Разработчик · Глава 17"))
        chat = await session.get(ChatModel, GROUP)
        chat.topic_id = 42

    await feed(
        dispatcher,
        bot,
        press(AdminChatCallback(action="publish", chat_id=GROUP).pack()),
        settings=_settings(),
        scheduler=scheduler,
        session_factory=session_factory,
    )

    assert bot.polls[-1]["message_thread_id"] == 42
