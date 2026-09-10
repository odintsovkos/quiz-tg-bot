"""Кабинет администратора: меню, чаты, расписание, лимиты, настройки, сводка."""

from __future__ import annotations

from datetime import time

from aiogram import Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from apscheduler.schedulers.base import BaseScheduler
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import replies, texts, texts_admin
from app.bot.callbacks import AdminCallback, AdminChatCallback, AdminLimitCallback
from app.bot.handlers.admin_questions import (
    EmptyCategorySelection,
    show_chat_categories,
    show_questions,
    toggle_chat_category,
)
from app.bot.handlers.admin_users import show_admins
from app.bot.keyboards import admin as keyboards
from app.bot.routers import private_admin
from app.bot.states import EditLimits, EditSchedule, EditSettings
from app.core.config import Settings
from app.core.db import SessionFactory
from app.core.time import publication_slots
from app.models import Chat, LimitMode, User
from app.repositories.chats import ChatRepository
from app.repositories.questions import QuestionRepository
from app.services.admin import SummaryService
from app.services.quiz.group import GroupQuizService
from app.services.quiz.schedule import ScheduleService
from app.services.settings import SettingsService, SettingsValidationError

# --- корневое меню -------------------------------------------------------


@private_admin.message(Command("admin"))
async def handle_admin(
    message: Message, session: AsyncSession, user: User
) -> None:
    await replies.show(
        message, session, user, texts_admin.MENU_TITLE, keyboards.root(user.role)
    )


@private_admin.callback_query(AdminCallback.filter())
async def handle_admin_section(
    query: CallbackQuery,
    callback_data: AdminCallback,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    section = callback_data.section

    if section == "root":
        await replies.show(
            query, session, user, texts_admin.MENU_TITLE, keyboards.root(user.role)
        )
    elif section == "chats":
        await _show_chats(query, session, user)
    elif section == "questions":
        await show_questions(query, session, user, callback_data, state)
    elif section == "limits":
        await _show_limits(query, session, user)
    elif section == "settings":
        await _show_settings(query, session, user, callback_data, state)
    elif section == "summary":
        await _show_summary(query, session, user)
    elif section == "admins":
        await show_admins(query, session, user)
    elif section == "schedule":
        await _show_chats(query, session, user)
    await query.answer()


# --- чаты ----------------------------------------------------------------


def render_topic(chat: Chat) -> str:
    """Куда чат публикует: имя темы, её номер либо общая лента."""
    if chat.topic_id is None:
        return texts_admin.CHAT_TOPIC_GENERAL
    if chat.topic_title:
        return texts_admin.CHAT_TOPIC_NAMED.format(title=chat.topic_title)
    return texts_admin.CHAT_TOPIC_NUMBERED.format(id=chat.topic_id)


def render_chat(chat: Chat) -> str:
    return texts_admin.CHAT_LINE.format(
        title=chat.title,
        state=(
            texts_admin.CHAT_STATE_ACTIVE
            if chat.is_active
            else texts_admin.CHAT_STATE_PAUSED
        ),
        interval=chat.interval_minutes,
        window_start=texts.format_time(chat.window_start),
        window_end=texts.format_time(chat.window_end),
        topic=render_topic(chat),
        categories=", ".join(chat.category_list) or texts_admin.CHAT_CATEGORIES_ALL,
    ) + texts_admin.CHAT_TOPIC_HINT


async def _show_chats(
    target: replies.Sender, session: AsyncSession, user: User
) -> None:
    """Список чатов одним экраном: карточка каждого открывается кнопкой.

    Прежде карточки шли отдельными сообщениями; в модели единственного экрана
    список стал уровнем навигации над карточкой чата.
    """
    chats = await ChatRepository(session).list_all()
    if not chats:
        await replies.show(
            target, session, user, texts_admin.CHATS_EMPTY, keyboards.back()
        )
        return

    await replies.show(
        target, session, user, texts_admin.CHATS_TITLE, keyboards.chat_list(chats)
    )


async def _show_chat(
    target: replies.Sender, session: AsyncSession, user: User, chat: Chat
) -> None:
    await replies.show(
        target, session, user, render_chat(chat), keyboards.chat_actions(chat)
    )


@private_admin.callback_query(AdminChatCallback.filter())
async def handle_chat_action(
    query: CallbackQuery,
    callback_data: AdminChatCallback,
    session: AsyncSession,
    user: User,
    bot: Bot,
    scheduler: BaseScheduler,
    session_factory: SessionFactory,
    state: FSMContext,
    settings: Settings,
) -> None:
    chats = ChatRepository(session)
    chat = await chats.get(callback_data.chat_id)
    if chat is None:
        await query.answer(texts_admin.CHAT_UNKNOWN, show_alert=True)
        return

    schedule = ScheduleService(scheduler, session_factory, bot)
    action = callback_data.action

    if action == "open":
        await _show_chat(query, session, user, chat)
        await query.answer()
        return

    if action in {"pause", "resume"}:
        await GroupQuizService(session).set_active(chat, action == "resume")
        schedule.apply(chat)
        await _show_chat(query, session, user, chat)
        await query.answer(
            texts_admin.CHAT_RESUMED if chat.is_active else texts_admin.CHAT_PAUSED
        )
        return

    if action == "publish":
        # Расписание не сдвигается: задача продолжает срабатывать по-своему.
        # Сессия события передаётся внутрь: вторая сессия на том же файле
        # SQLite встала бы в очередь за блокировкой этой транзакции.
        published = await schedule.publish_now(chat.id, session=session)
        await query.answer(
            texts_admin.CHAT_PUBLISHED if published else texts_admin.CHAT_PUBLISH_FAILED,
            show_alert=not published,
        )
        return

    if action == "remove":
        await GroupQuizService(session).disconnect(chat.id)
        schedule.remove(chat.id)
        await replies.show(
            query, session, user, texts_admin.CHAT_REMOVED, keyboards.back()
        )
        await query.answer()
        return

    if action == "schedule":
        await _show_schedule(query, session, user, chat)
        await query.answer()
        return

    if action == "set_interval":
        await state.set_state(EditSchedule.interval)
        await state.update_data(chat_id=chat.id)
        await replies.show(
            query,
            session,
            user,
            texts_admin.SCHEDULE_ASK_INTERVAL.format(
                minimum=settings.min_interval_minutes,
                maximum=settings.max_interval_minutes,
            ),
            keyboards.back(),
        )
        await query.answer()
        return

    if action == "set_window":
        await state.set_state(EditSchedule.window)
        await state.update_data(chat_id=chat.id)
        await replies.show(
            query, session, user, texts_admin.SCHEDULE_ASK_WINDOW, keyboards.back()
        )
        await query.answer()
        return

    if action == "set_categories":
        await show_chat_categories(query, session, user, chat)
        await query.answer()
        return

    if action == "topic_clear":
        # Задать ветку отсюда нечем: message_thread_id есть только
        # у сообщения, отправленного в самой теме.
        if chat.topic_id is None:
            await query.answer(texts_admin.CHAT_TOPIC_ALREADY_GENERAL, show_alert=True)
            return
        await GroupQuizService(session).set_topic(chat, None)
        await _show_chat(query, session, user, chat)
        await query.answer(texts_admin.CHAT_TOPIC_CLEARED)
        return

    if action == "cat_noop":  # счётчик страниц — подпись, а не кнопка
        await query.answer()
        return

    if action == "cat_page":
        await show_chat_categories(query, session, user, chat, callback_data.page)
        await query.answer()
        return

    if action == "cat_all":
        chat.set_categories([])
        await session.flush()
        await show_chat_categories(query, session, user, chat, callback_data.page)
        await query.answer(texts_admin.SCHEDULE_CATEGORIES_SAVED)
        return

    if action.startswith("cat"):
        try:
            await toggle_chat_category(session, chat, int(action.removeprefix("cat")))
        except (EmptyCategorySelection, ValueError):
            await query.answer(texts_admin.SCHEDULE_EMPTY_CATEGORIES, show_alert=True)
            return
        # Переключение категории не уводит со страницы.
        await show_chat_categories(query, session, user, chat, callback_data.page)
        await query.answer(texts_admin.SCHEDULE_CATEGORIES_SAVED)


async def _show_schedule(
    target: replies.Sender, session: AsyncSession, user: User, chat: Chat
) -> None:
    await replies.show(
        target,
        session,
        user,
        texts_admin.SCHEDULE_TITLE.format(
            title=chat.title,
            interval=chat.interval_minutes,
            window_start=texts.format_time(chat.window_start),
            window_end=texts.format_time(chat.window_end),
            slots=render_slots(chat),
            categories=", ".join(chat.category_list) or texts_admin.CHAT_CATEGORIES_ALL,
        ),
        reply_markup=keyboards.schedule_actions(chat.id),
    )


#: Сколько моментов публикации показывать на экране расписания. При нижней
#: границе периодичности их бывают сотни, а сообщение Telegram не резиновое.
SLOTS_SHOWN = 12


def render_slots(chat: Chat) -> str:
    """Моменты публикации чата строкой — то, что видно в кабинете.

    Считаются той же функцией, что и расписание в планировщике, поэтому
    экран не может разойтись с тем, когда бот на самом деле публикует.
    """
    slots = publication_slots(
        chat.window_start, chat.window_end, chat.interval_minutes
    )
    shown = ", ".join(texts.format_time(slot) for slot in slots[:SLOTS_SHOWN])
    if len(slots) <= SLOTS_SHOWN:
        return shown
    return f"{shown} {texts_admin.SCHEDULE_SLOTS_TAIL.format(total=len(slots))}"


def parse_interval(raw: str, minimum: int, maximum: int) -> int:
    """Разобрать периодичность; вне границ — отказ, прежнее значение остаётся.

    Границы приходят из конфигурации развёртывания, а не из констант кода:
    их подбирают под чат, а верхняя вдобавок гарантирует, что вопрос уходит
    хотя бы раз в сутки.
    """
    value = int(raw.strip())
    if not minimum <= value <= maximum:
        raise ValueError(value)
    return value


def parse_window(raw: str) -> tuple[time, time]:
    """Разобрать окно вида `09:00-21:00`."""
    parts = raw.replace(" ", "").split("-")
    if len(parts) != 2:
        raise ValueError(raw)
    start, end = (time.fromisoformat(part) for part in parts)
    if start >= end:
        raise WindowOrderError(raw)
    return start, end


class WindowOrderError(ValueError):
    """Начало окна не раньше окончания."""


@private_admin.message(EditSchedule.interval)
async def handle_interval_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
    scheduler: BaseScheduler,
    session_factory: SessionFactory,
    settings: Settings,
) -> None:
    try:
        interval = parse_interval(
            message.text or "",
            settings.min_interval_minutes,
            settings.max_interval_minutes,
        )
    except ValueError:
        await replies.show(
            message,
            session,
            user,
            texts_admin.SCHEDULE_BAD_INTERVAL.format(
                minimum=settings.min_interval_minutes,
                maximum=settings.max_interval_minutes,
            ),
            keyboards.back(),
        )
        return

    data = await state.get_data()
    chat = await ChatRepository(session).get(int(data["chat_id"]))
    if chat is None:
        await state.clear()
        await replies.show(
            message, session, user, texts_admin.CHAT_UNKNOWN, keyboards.back()
        )
        return

    chat.interval_minutes = interval
    await session.flush()
    ScheduleService(scheduler, session_factory, bot).apply(chat)
    await state.clear()
    await _show_schedule(message, session, user, chat)


@private_admin.message(EditSchedule.window)
async def handle_window_input(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    try:
        start, end = parse_window(message.text or "")
    except WindowOrderError:
        await replies.show(
            message,
            session,
            user,
            texts_admin.SCHEDULE_WINDOW_START_AFTER_END,
            keyboards.back(),
        )
        return
    except ValueError:
        await replies.show(
            message, session, user, texts_admin.SCHEDULE_BAD_WINDOW, keyboards.back()
        )
        return

    data = await state.get_data()
    chat = await ChatRepository(session).get(int(data["chat_id"]))
    if chat is None:
        await state.clear()
        await replies.show(
            message, session, user, texts_admin.CHAT_UNKNOWN, keyboards.back()
        )
        return

    chat.window_start, chat.window_end = start, end
    await session.flush()
    await state.clear()
    await _show_schedule(message, session, user, chat)


# --- лимиты --------------------------------------------------------------


async def render_limits(session: AsyncSession) -> str:
    settings = await SettingsService(session).get()
    return texts_admin.LIMITS_TITLE.format(
        mode=texts_admin.LIMIT_MODE_NAMES[settings.limit_mode.value],
        quiz=settings.quiz_limit,
        random=settings.random_limit,
    )


async def _show_limits(
    query: CallbackQuery, session: AsyncSession, user: User
) -> None:
    settings = await SettingsService(session).get()
    await replies.show(
        query,
        session,
        user,
        await render_limits(session),
        keyboards.limits_actions(settings.limit_mode),
    )


@private_admin.callback_query(AdminLimitCallback.filter())
async def handle_limit_action(
    query: CallbackQuery,
    callback_data: AdminLimitCallback,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    service = SettingsService(session)
    action = callback_data.action

    if action == "mode":
        mode = LimitMode(callback_data.value)
        if mode is LimitMode.DISABLED_FOR_ADMINS:
            # Спека требует предупредить до применения режима.
            await replies.show(
                query,
                session,
                user,
                texts_admin.LIMITS_ADMIN_WARNING,
                keyboards.limits_confirm(mode),
            )
            await query.answer()
            return
        await service.set_limit_mode(mode)
        await _show_limits(query, session, user)
        await query.answer(
            texts_admin.LIMITS_MODE_SAVED.format(
                mode=texts_admin.LIMIT_MODE_NAMES[mode.value]
            )
        )
        return

    if action == "mode_confirm":
        mode = LimitMode(callback_data.value)
        await service.set_limit_mode(mode)
        await _show_limits(query, session, user)
        await query.answer(
            texts_admin.LIMITS_MODE_SAVED.format(
                mode=texts_admin.LIMIT_MODE_NAMES[mode.value]
            )
        )
        return

    if action in {"set_quiz", "set_random"}:
        await state.set_state(EditLimits.value)
        await state.update_data(kind=action)
        await replies.show(
            query,
            session,
            user,
            texts_admin.LIMITS_ASK_QUIZ
            if action == "set_quiz"
            else texts_admin.LIMITS_ASK_RANDOM,
            keyboards.back(),
        )
        await query.answer()


@private_admin.message(EditLimits.value)
async def handle_limit_value(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    data = await state.get_data()
    service = SettingsService(session)
    try:
        value = int((message.text or "").strip())
    except ValueError:
        await replies.show(
            message, session, user, texts_admin.INVALID_NUMBER, keyboards.back()
        )
        return

    try:
        if data["kind"] == "set_quiz":
            await service.set_quiz_limit(value)
        else:
            await service.set_random_limit(value)
    except SettingsValidationError as error:
        await replies.show(message, session, user, str(error), keyboards.back())
        return

    await state.clear()
    settings = await service.get()
    await replies.show(
        message,
        session,
        user,
        texts_admin.LIMITS_VALUE_SAVED + "\n\n" + await render_limits(session),
        keyboards.limits_actions(settings.limit_mode),
    )


# --- общие настройки -----------------------------------------------------


async def render_settings(session: AsyncSession) -> str:
    settings = await SettingsService(session).get()
    return texts_admin.SETTINGS_TITLE.format(
        session_size=settings.session_size,
        leaderboard_rows=settings.leaderboard_rows,
        timezone=settings.timezone,
    )


async def _show_settings(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
    callback_data: AdminCallback,
    state: FSMContext,
) -> None:
    prompts = {
        "session_size": texts_admin.SETTINGS_ASK_SESSION_SIZE,
        "rows": texts_admin.SETTINGS_ASK_ROWS,
        "timezone": texts_admin.SETTINGS_ASK_TIMEZONE,
    }
    if callback_data.action in prompts:
        await state.set_state(EditSettings.value)
        await state.update_data(kind=callback_data.action)
        await replies.show(
            query, session, user, prompts[callback_data.action], keyboards.back()
        )
        return

    await replies.show(
        query, session, user, await render_settings(session), keyboards.settings_actions()
    )


@private_admin.message(EditSettings.value)
async def handle_setting_value(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    data = await state.get_data()
    kind = data["kind"]
    service = SettingsService(session)
    raw = (message.text or "").strip()

    try:
        if kind == "timezone":
            await service.set_timezone(raw)
            await state.clear()
            await _saved_settings(
                message, session, user, texts_admin.SETTINGS_TIMEZONE_SAVED
            )
            return

        value = int(raw)
        if kind == "session_size":
            await service.set_session_size(value)
        else:
            await service.set_leaderboard_rows(value)
    except SettingsValidationError as error:
        await replies.show(message, session, user, str(error), keyboards.back())
        return
    except ValueError:
        await replies.show(
            message, session, user, texts_admin.INVALID_NUMBER, keyboards.back()
        )
        return

    await state.clear()
    await _saved_settings(message, session, user, texts_admin.SETTINGS_SAVED)


async def _saved_settings(
    message: Message, session: AsyncSession, user: User, notice: str
) -> None:
    """Подтверждение и текущие настройки — одним экраном."""
    await replies.show(
        message,
        session,
        user,
        notice + "\n\n" + await render_settings(session),
        keyboards.settings_actions(),
    )


# --- сводка --------------------------------------------------------------


async def render_summary(session: AsyncSession) -> str:
    summary = await SummaryService(session).build()
    return texts_admin.SUMMARY.format(
        users=summary.users,
        active_today=summary.active_today,
        answers_today=summary.answers_today,
        answers_total=summary.answers_total,
        accuracy=texts.accuracy(summary.correct_total, summary.answers_total),
        questions_total=summary.questions_total,
        questions_active=summary.questions_active,
        questions_inactive=summary.questions_inactive,
    )


async def _show_summary(
    query: CallbackQuery, session: AsyncSession, user: User
) -> None:
    await replies.show(
        query, session, user, await render_summary(session), keyboards.back()
    )


async def categories_with_active_questions(session: AsyncSession) -> list[str]:
    return await QuestionRepository(session).list_categories(only_active=True)
