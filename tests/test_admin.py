"""Кабинет администратора: меню, чаты, расписание, вопросы, лимиты, сводка."""

from __future__ import annotations

from datetime import UTC, datetime, time

import pytest

from app.bot.callbacks import AdminCallback
from app.bot.handlers.admin import (
    SLOTS_SHOWN,
    WindowOrderError,
    parse_interval,
    parse_window,
    render_chat,
    render_limits,
    render_schedule,
    render_settings,
    render_slots,
    render_summary,
)
from app.bot.handlers.admin_questions import (
    EmptyCategorySelection,
    apply_field,
    chat_categories,
    draft_from_form,
    parse_options,
    render_question,
    toggle_chat_category,
)
from app.bot.handlers.admin_users import render_admins
from app.bot.keyboards.admin import root as admin_root
from app.models import AnswerSource, Chat, LimitMode, Question, UserRole
from app.services.admin import (
    AdminQuestionService,
    QuestionValidationError,
    draft_from,
)
from app.services.settings import SettingsService, SettingsValidationError
from app.services.stats.scoring import ScoringService
from app.services.users import UserService
from tests.conftest import make_question

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
DEV = "Разработчик · Глава 8"
ADMIN_CAT = "Администратор · Глава 2"


def sections(role: UserRole) -> set[str]:
    return {
        AdminCallback.unpack(button.callback_data).section
        for row in admin_root(role).inline_keyboard
        for button in row
    }


async def add_chat(session, chat_id: int = -100) -> Chat:
    chat = Chat(
        id=chat_id,
        title="Чат 1С",
        is_active=True,
        interval_minutes=180,
        window_start=time(9, 0),
        window_end=time(21, 0),
        timezone="Europe/Moscow",
        round_number=1,
        connected_at=MOMENT,
        connected_by=1,
    )
    session.add(chat)
    await session.flush()
    return chat


# --- вход и меню ---------------------------------------------------------


def test_admin_sees_every_section_but_the_admins_one():
    assert "admins" not in sections(UserRole.ADMIN)
    assert {"chats", "questions", "limits", "settings", "summary"} <= sections(
        UserRole.ADMIN
    )


def test_owner_also_sees_the_admins_section():
    assert "admins" in sections(UserRole.OWNER)


# --- чаты ----------------------------------------------------------------


async def test_chat_card_shows_state_and_schedule(session):
    chat = await add_chat(session)

    text = render_chat(chat)

    assert "Чат 1С" in text
    assert "активен" in text
    assert "раз в 180 мин" in text
    assert "09:00–21:00" in text
    assert "все" in text


async def test_paused_chat_card_says_so(session):
    chat = await add_chat(session)
    chat.is_active = False

    assert "приостановлен" in render_chat(chat)


# --- расписание ----------------------------------------------------------


#: Границы по умолчанию: `MIN_INTERVAL_MINUTES` и `MAX_INTERVAL_MINUTES`.
BOUNDS = (5, 24 * 60)


def test_interval_is_parsed_within_bounds():
    assert parse_interval(" 45 ", *BOUNDS) == 45


@pytest.mark.parametrize("raw", ["0", "1", "2000", "не число", ""])
def test_bad_interval_is_rejected(raw):
    with pytest.raises(ValueError):
        parse_interval(raw, *BOUNDS)


def test_interval_bounds_come_from_the_arguments():
    """Границы приходят из конфигурации, а не из констант кода."""
    assert parse_interval("30", 15, 120) == 30

    with pytest.raises(ValueError):
        parse_interval("30", 60, 120)


def test_window_is_parsed():
    assert parse_window("09:00-21:00") == (time(9, 0), time(21, 0))


def test_window_with_start_after_end_is_rejected():
    with pytest.raises(WindowOrderError):
        parse_window("22:00-06:00")


@pytest.mark.parametrize("raw", ["09:00", "не время-21:00", ""])
def test_malformed_window_is_rejected(raw):
    with pytest.raises(ValueError):
        parse_window(raw)


async def test_chat_categories_offer_only_those_with_active_questions(session):
    session.add(make_question("dev.001", DEV))
    session.add(make_question("adm.001", ADMIN_CAT, is_active=False))
    await session.flush()

    assert await chat_categories(session) == [DEV]


async def test_toggling_a_category_saves_it(session):
    session.add(make_question("dev.001", DEV))
    chat = await add_chat(session)

    assert await toggle_chat_category(session, chat, 0) == [DEV]
    assert await toggle_chat_category(session, chat, 0) == []


async def test_category_without_active_questions_is_rejected(session):
    session.add(make_question("dev.001", DEV))
    chat = await add_chat(session)

    with pytest.raises(EmptyCategorySelection):
        await toggle_chat_category(session, chat, 5)


# --- вопросы -------------------------------------------------------------


async def test_question_list_is_paginated(session):
    for index in range(7):
        session.add(make_question(f"q.{index:03d}", DEV))
    await session.flush()
    service = AdminQuestionService(session)

    first = await service.page(0)
    second = await service.page(1)

    assert (first.pages, first.total) == (2, 7)
    assert len(first.items) == 5
    assert len(second.items) == 2


async def test_question_list_filters_by_category_and_activity(session):
    session.add(make_question("dev.001", DEV))
    session.add(make_question("dev.002", DEV, is_active=False))
    session.add(make_question("adm.001", ADMIN_CAT))
    await session.flush()
    service = AdminQuestionService(session)

    by_category = await service.page(0, category=DEV)
    inactive = await service.page(0, is_active=False)

    assert {item.id for item in by_category.items} == {"dev.001", "dev.002"}
    assert {item.id for item in inactive.items} == {"dev.002"}


async def test_question_card_shows_options_and_edit_trace(session):
    session.add(make_question("dev.001", DEV))
    await session.flush()
    admin = await UserService(session).register(7, "Иван", now=MOMENT)
    service = AdminQuestionService(session)
    question = await service.get("dev.001")

    await service.save(
        apply_field(draft_from(question), "text", "Новая формулировка?"),
        editor_id=admin.id,
        now=MOMENT,
    )
    text = render_question(await service.get("dev.001"))

    assert "Новая формулировка?" in text
    assert "✅" in text
    assert "Правил: 7" in text


async def test_editing_keeps_statistics_and_records_the_editor(session):
    session.add(make_question("dev.001", DEV))
    user = await UserService(session).register(7, "Иван", now=MOMENT)
    await session.flush()
    await ScoringService(session).record_answer(
        user, "dev.001", is_correct=True, source=AnswerSource.PRIVATE, now=MOMENT
    )
    service = AdminQuestionService(session)

    question = await service.get("dev.001")
    await service.save(
        apply_field(draft_from(question), "text", "Изменённый текст?"),
        editor_id=7,
        now=MOMENT,
    )

    updated = await service.get("dev.001")
    assert updated.text == "Изменённый текст?"
    assert (updated.updated_by, updated.updated_at) == (7, MOMENT)
    from app.services.stats.reading import StatsService

    assert (await StatsService(session).total(7)).attempts == 1


async def test_invalid_edit_is_rejected_and_the_previous_version_stays(session):
    session.add(make_question("dev.001", DEV))
    await session.flush()
    service = AdminQuestionService(session)
    question = await service.get("dev.001")
    original = question.text

    with pytest.raises(QuestionValidationError) as error:
        await service.save(
            apply_field(draft_from(question), "options", "*Единственный вариант"),
            editor_id=7,
        )

    assert "вариантов 1" in str(error.value)
    assert (await service.get("dev.001")).text == original


async def test_deactivation_keeps_the_question_in_the_bank(session):
    session.add(make_question("dev.001", DEV))
    await session.flush()
    service = AdminQuestionService(session)
    question = await service.get("dev.001")

    await service.set_active(question, False, editor_id=7)

    assert (await service.get("dev.001")) is not None
    assert question.is_active is False
    assert question.updated_by == 7


def test_options_are_parsed_with_the_correct_mark():
    options = parse_options("*Верный\nНеверный\n\n Другой ")

    assert [option.text for option in options] == ["Верный", "Неверный", "Другой"]
    assert [option.is_correct for option in options] == [True, False, False]


async def test_step_by_step_form_creates_an_active_question(session):
    await UserService(session).register(7, "Иван", now=MOMENT)
    form = {
        "identifier": "dev.ch08.500",
        "text": "Что делает слово РАЗЛИЧНЫЕ?",
        "options": "*Убирает дубли\nСортирует\nГруппирует\nОграничивает",
        "category": DEV,
        "difficulty": "medium",
        "explanation": "-",
    }

    question = await AdminQuestionService(session).save(
        draft_from_form(form), editor_id=7, now=MOMENT
    )

    assert question.is_active is True
    assert question.explanation is None
    stored = await session.get(Question, "dev.ch08.500")
    assert stored.correct_index == 0
    # сразу доступен для выдачи
    from app.repositories.questions import QuestionRepository

    assert await QuestionRepository(session).count_active([DEV]) == 1


# --- лимиты --------------------------------------------------------------


async def test_limits_screen_shows_mode_and_both_values(session):
    text = await render_limits(session)

    assert "включены для всех" in text
    assert "Запусков викторины в сутки: 5" in text
    assert "Случайных вопросов в сутки: 20" in text


async def test_mode_switch_is_saved_and_applies_at_once(session):
    await SettingsService(session).set_limit_mode(LimitMode.DISABLED_FOR_ALL)

    assert "отключены для всех" in await render_limits(session)
    settings = await SettingsService(session).get()
    assert settings.limit_mode is LimitMode.DISABLED_FOR_ALL


async def test_admin_mode_warning_text_mentions_statistics():
    from app.bot import texts_admin

    assert "не будут учитываться" in texts_admin.LIMITS_ADMIN_WARNING or (
        "перестанут учитываться" in texts_admin.LIMITS_ADMIN_WARNING
    )


async def test_limit_value_is_saved(session):
    await SettingsService(session).set_random_limit(7)

    assert "Случайных вопросов в сутки: 7" in await render_limits(session)


@pytest.mark.parametrize("value", [0, -3])
async def test_non_positive_limit_is_rejected(session, value):
    service = SettingsService(session)

    with pytest.raises(SettingsValidationError):
        await service.set_random_limit(value)

    assert (await service.get()).random_limit == 20


# --- общие настройки -----------------------------------------------------


async def test_settings_screen_shows_current_values(session):
    text = await render_settings(session)

    assert "Размер сессии викторины: 10" in text
    assert "Строк в таблице результатов: 10" in text
    assert "Europe/Moscow" in text


async def test_session_size_change_affects_only_new_sessions(session):
    from app.services.quiz.session import QuizSessionService

    for index in range(12):
        session.add(make_question(f"q.{index:03d}", DEV))
    user = await UserService(session).register(7, "Иван", now=MOMENT)
    await session.flush()

    await SettingsService(session).set_session_size(3)
    quiz = QuizSessionService(session)
    running = (await quiz.start(user, now=MOMENT)).session
    await SettingsService(session).set_session_size(5)

    assert running.total_questions == 3
    restarted = (await quiz.start(user, restart=True, now=MOMENT)).session
    assert restarted.total_questions == 5


async def test_timezone_change_does_not_recompute_saved_days(session):
    from datetime import date

    from app.models import UserDailyStats

    await UserService(session).register(7, "Иван", now=MOMENT)
    session.add(
        UserDailyStats(
            user_id=7, quiz_date=date(2026, 3, 10), attempts=2, correct=1, points=1
        )
    )
    await session.flush()

    await SettingsService(session).set_timezone("Asia/Vladivostok")

    from app.services.stats.reading import StatsService

    saved = await StatsService(session).daily(7, date(2026, 3, 10))
    assert (saved.attempts, saved.points) == (2, 1)
    assert (await SettingsService(session).get()).timezone == "Asia/Vladivostok"


async def test_invalid_timezone_is_rejected(session):
    service = SettingsService(session)

    with pytest.raises(SettingsValidationError):
        await service.set_timezone("Mars/Olympus")

    assert (await service.get()).timezone == "Europe/Moscow"


# --- сводка --------------------------------------------------------------


async def test_summary_shows_every_indicator(session):
    session.add(make_question("dev.001", DEV))
    session.add(make_question("dev.002", DEV, is_active=False))
    user = await UserService(session).register(7, "Иван", now=MOMENT)
    await session.flush()
    await ScoringService(session).record_answer(
        user, "dev.001", is_correct=True, source=AnswerSource.PRIVATE
    )

    text = await render_summary(session)

    assert "Участников: 1" in text
    assert "Активных сегодня: 1" in text
    assert "Задано вопросов сегодня: 1" in text
    assert "Задано вопросов за всё время: 1" in text
    assert "Доля верных ответов: 100%" in text
    assert "Банк вопросов: 2 (1 активных, 1 деактивированных)" in text


# --- администраторы ------------------------------------------------------


async def test_admin_list_shows_the_owner_and_admins(session):
    service = UserService(session)
    await service.ensure_owner(1, now=MOMENT)
    await service.register(7, "Иван", now=MOMENT)
    await service.grant_admin(7)

    text = render_admins(await service.list_admins())

    assert "владелец" in text
    assert "Иван (id 7) — администратор" in text


async def test_admin_list_of_the_owner_alone_says_so(session):
    service = UserService(session)
    await service.ensure_owner(1, now=MOMENT)

    assert "Кроме владельца" in render_admins(await service.list_admins())


async def test_schedule_screen_shows_the_moments_of_publication(session):
    """Администратор должен видеть, когда бот публикует, а не только интервал."""
    chat = await add_chat(session)

    assert render_slots(chat) == "09:00, 12:00, 15:00, 18:00"


async def test_the_schedule_screen_renders_whole(session):
    """Экран собирается целиком: заголовок и его подстановки ходят вместе."""
    chat = await add_chat(session)

    text = render_schedule(chat)

    assert "09:00, 12:00, 15:00, 18:00" in text
    assert "180" in text


async def test_the_moments_start_at_the_window_start(session):
    chat = await add_chat(session)
    chat.window_start = time(10, 30)
    chat.interval_minutes = 240

    assert render_slots(chat) == "10:30, 14:30, 18:30"


async def test_a_long_list_of_moments_is_trimmed_with_a_total(session):
    chat = await add_chat(session)
    chat.interval_minutes = 15  # 48 момента в окне 09:00–21:00

    text = render_slots(chat)

    assert text.startswith("09:00, 09:15, 09:30")
    assert "всего 48" in text
    assert text.count(":") == SLOTS_SHOWN


async def test_a_daily_interval_shows_a_single_moment(session):
    chat = await add_chat(session)
    chat.interval_minutes = 24 * 60

    assert render_slots(chat) == "09:00"


def test_the_rejection_names_the_configured_bounds():
    from app.bot import texts_admin

    text = texts_admin.SCHEDULE_BAD_INTERVAL.format(minimum=5, maximum=24 * 60)

    assert "5" in text and "1440" in text
