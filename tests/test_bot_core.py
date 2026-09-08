"""Ядро бота: регистрация, роли, фильтры, справка, ошибки, лимит частоты."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TelegramUser

from app.bot.filters import ConnectedChat, IsAdmin, IsOwner
from app.bot.handlers.common import handle_error, help_text
from app.bot.middlewares import DatabaseMiddleware, UserMiddleware, display_name
from app.bot.throttling import send_with_retry
from app.models import Chat as ChatModel
from app.models import UserRole
from app.services.users import UserService

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


def telegram_user(user_id: int = 7, first: str = "Иван") -> TelegramUser:
    return TelegramUser(id=user_id, is_bot=False, first_name=first, username="ivan")


def private_message(text: str = "/help", user_id: int = 7) -> Message:
    return Message(
        message_id=1,
        date=MOMENT,
        chat=Chat(id=user_id, type="private"),
        from_user=telegram_user(user_id),
        text=text,
    )


def group_message(chat_id: int = -100) -> Message:
    return Message(
        message_id=1,
        date=MOMENT,
        chat=Chat(id=chat_id, type="supergroup", title="Чат"),
        from_user=telegram_user(),
        text="привет",
    )


def callback(data: str = "adm:chats:open:0") -> CallbackQuery:
    return CallbackQuery(
        id="1",
        from_user=telegram_user(),
        chat_instance="ci",
        data=data,
        message=private_message(),
    )


# --- middleware ----------------------------------------------------------


async def test_database_middleware_commits_after_the_handler(session_factory):
    middleware = DatabaseMiddleware(session_factory)

    async def handler(event, data):
        await UserService(data["session"]).register(7, "Иван", now=MOMENT)
        return "ok"

    assert await middleware(handler, private_message(), {}) == "ok"

    async with session_factory() as session:
        assert await UserService(session).get(7) is not None


async def test_database_middleware_rolls_back_on_error(session_factory):
    middleware = DatabaseMiddleware(session_factory)

    async def handler(event, data):
        await UserService(data["session"]).register(7, "Иван", now=MOMENT)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await middleware(handler, private_message(), {})

    async with session_factory() as session:
        assert await UserService(session).get(7) is None


async def test_user_middleware_registers_on_first_contact(session):
    captured: dict[str, object] = {}

    async def handler(event, data):
        captured.update(data)

    await UserMiddleware()(handler, private_message(), {"session": session})

    assert captured["user"].id == 7
    assert captured["user"].role is UserRole.USER


async def test_user_middleware_registers_from_a_group_message(session):
    captured: dict[str, object] = {}

    async def handler(event, data):
        captured.update(data)

    await UserMiddleware()(handler, group_message(), {"session": session})

    assert captured["user"].id == 7


def test_display_name_joins_first_and_last_name():
    user = TelegramUser(id=7, is_bot=False, first_name="Иван", last_name="Петров")
    assert display_name(user) == "Иван Петров"


# --- фильтры по роли -----------------------------------------------------


async def test_admin_filter_declines_a_plain_user(session):
    user = await UserService(session).register(7, "Иван", now=MOMENT)

    assert await IsAdmin()(private_message(), user=user) is False


async def test_admin_filter_accepts_an_admin(session):
    service = UserService(session)
    await service.register(7, "Иван", now=MOMENT)
    user = await service.grant_admin(7)

    assert await IsAdmin()(private_message(), user=user) is True


async def test_stale_admin_button_is_declined_after_revocation(session):
    """Спека `bot-core`: нажатие по старой кнопке проверяет роль заново."""
    service = UserService(session)
    await service.register(7, "Иван", now=MOMENT)
    await service.grant_admin(7)
    user = await service.revoke_admin(7)

    assert await IsAdmin()(callback(), user=user) is False


async def test_owner_filter_declines_a_mere_admin(session):
    service = UserService(session)
    await service.register(7, "Иван", now=MOMENT)
    admin = await service.grant_admin(7)

    assert await IsOwner()(private_message(), user=admin) is False
    assert await IsAdmin()(private_message(), user=admin) is True


async def test_role_filter_declines_an_event_without_a_profile():
    assert await IsAdmin()(private_message(), user=None) is False


# --- подключённые чаты ---------------------------------------------------


async def test_connected_chat_filter_stays_silent_in_an_unknown_chat(session):
    assert await ConnectedChat()(group_message(), session=session) is False


async def test_connected_chat_filter_accepts_a_connected_chat(session):
    session.add(ChatModel(id=-100, title="Чат", connected_at=MOMENT, connected_by=1))
    await session.flush()

    assert await ConnectedChat()(group_message(), session=session) is True


# --- справка -------------------------------------------------------------


async def test_help_differs_by_role(session):
    service = UserService(session)
    plain = await service.register(7, "Иван", now=MOMENT)
    plain_text = help_text(plain)

    admin = await service.grant_admin(7)
    admin_text = help_text(admin)

    assert "/admin" not in plain_text
    assert "/admin" in admin_text
    assert plain_text in admin_text


# --- ошибки --------------------------------------------------------------


class FakeMessage:
    def __init__(self) -> None:
        self.answers: list[str] = []
        self.chat = Chat(id=7, type="private")
        self.from_user = telegram_user()

    async def answer(self, text: str, **_kwargs) -> None:
        self.answers.append(text)


class FakeUpdate:
    event_type = "message"

    def __init__(self, message) -> None:
        self.message = message
        self.callback_query = None


class FakeErrorEvent:
    def __init__(self, update, exception) -> None:
        self.update = update
        self.exception = exception


async def test_handler_failure_gives_a_neutral_message(caplog):
    message = FakeMessage()
    error = ValueError("SELECT * FROM users -- внутренняя деталь")

    try:
        raise error
    except ValueError as raised:
        handled = await handle_error(FakeErrorEvent(FakeUpdate(message), raised))

    assert handled is True
    assert message.answers == ["Что-то пошло не так. Попробуйте ещё раз чуть позже."]
    assert "SELECT" not in message.answers[0]
    assert "Traceback" not in message.answers[0]


async def test_handler_failure_is_logged_with_context(caplog):
    message = FakeMessage()
    with caplog.at_level("ERROR"):
        try:
            raise RuntimeError("boom")
        except RuntimeError as raised:
            await handle_error(FakeErrorEvent(FakeUpdate(message), raised))

    record = caplog.records[-1]
    assert record.chat_id == 7
    assert record.user_id == 7
    assert record.exc_info is not None


# --- лимит частоты Telegram ---------------------------------------------


async def test_rate_limit_is_retried_after_the_named_pause():
    slept: list[float] = []
    attempts = {"count": 0}

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    async def action() -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TelegramRetryAfter(
                method=SendMessage(chat_id=1, text="x"),
                message="Too Many Requests",
                retry_after=7,
            )
        return "отправлено"

    result = await send_with_retry(action, sleep=sleep)

    assert result == "отправлено"
    assert slept == [7]
    assert attempts["count"] == 2


async def test_rate_limit_gives_up_after_the_attempt_budget():
    async def sleep(_seconds: float) -> None:
        return None

    async def action() -> str:
        raise TelegramRetryAfter(
            method=SendMessage(chat_id=1, text="x"),
            message="Too Many Requests",
            retry_after=1,
        )

    with pytest.raises(TelegramRetryAfter):
        await send_with_retry(action, max_attempts=2, sleep=sleep)
