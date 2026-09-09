"""Отрисовка личных режимов: обратная связь, итог, лимиты, меню, темы."""

from __future__ import annotations

from datetime import UTC, datetime

from app.bot import texts
from app.bot.callbacks import MenuCallback, RandomActionCallback, TopicCallback
from app.bot.handlers.quiz import (
    feedback_text,
    handle_topic_button,
    render_limits,
    render_session_result,
)
from app.bot.keyboards.common import main_menu
from app.bot.keyboards.quiz import TOPICS_PAGE_SIZE, topic_chapters, topic_groups
from app.models import LimitMode, Question
from app.services.quiz.limits import KIND_QUIZ, KIND_RANDOM, LimitService
from app.services.quiz.session import QuizSessionService
from app.services.quiz.topics import TopicPreferenceService, group_topics
from app.services.settings import SettingsService
from app.services.stats.scoring import RecordedAnswer
from app.services.users import UserService
from tests.conftest import make_question
from tests.screen import ScreenBot, query

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
DEV = "Разработчик · Глава 8"


async def setup(session, questions: int = 4):
    for index in range(questions):
        session.add(make_question(f"q.{index:03d}", DEV))
    user = await UserService(session).register(7, "Иван", now=MOMENT)
    await session.flush()
    return user


# --- обратная связь по ответу --------------------------------------------


async def test_wrong_answer_shows_the_correct_option_and_explanation(session):
    await setup(session, 1)
    question = await session.get(Question, "q.000")

    text = feedback_text(
        RecordedAnswer(accepted=True, counted=True, is_correct=False, points=0),
        question,
    )

    assert "Неверно" in text
    assert question.options[question.correct_index].text in text
    assert "Пояснение" in text
    assert "8.1. Раздел" in text


async def test_correct_answer_confirms_and_shows_the_explanation(session):
    await setup(session, 1)
    question = await session.get(Question, "q.000")

    text = feedback_text(
        RecordedAnswer(accepted=True, counted=True, is_correct=True, points=1),
        question,
    )

    assert "Верно" in text
    assert "Пояснение" in text


# --- итог сессии ---------------------------------------------------------


async def test_session_result_shows_counts_points_and_updated_totals(session):
    user = await setup(session)
    await SettingsService(session).set_session_size(2)
    service = QuizSessionService(session)
    quiz = (await service.start(user, now=MOMENT)).session
    for position in range(2):
        item = quiz.questions[position]
        question = await session.get(Question, item.question_id)
        recorded, _ = await service.answer(
            user, quiz, position, question.correct_index, now=MOMENT
        )

    text = await render_session_result(session, user, quiz, recorded)

    assert "✅ Верных: 2 из 2" in text
    assert "⭐ За сессию: 2" in text
    assert "100%" in text
    assert "не пошли" not in text


async def test_excluded_participant_sees_the_result_with_a_note(session):
    """Спека `scoring-and-stats`: итог показан, но в зачёт не пошёл."""
    await setup(session)
    await SettingsService(session).set_session_size(1)
    await SettingsService(session).set_limit_mode(LimitMode.DISABLED_FOR_ADMINS)
    admin = await UserService(session).grant_admin(7)
    service = QuizSessionService(session)
    quiz = (await service.start(admin, now=MOMENT)).session
    recorded, _ = await service.answer(admin, quiz, 0, 0, now=MOMENT)

    text = await render_session_result(session, admin, quiz, recorded)

    assert "Викторина завершена" in text
    assert "в общий зачёт не пошли" in text


# --- лимиты --------------------------------------------------------------


async def test_limits_screen_shows_both_remainders_and_reset_time(session):
    from app.core.time import utc_now

    user = await setup(session)
    # экран показывает текущие сутки, поэтому и списываем в них же
    await LimitService(session).consume(user, KIND_RANDOM, now=utc_now())

    text = await render_limits(session, user)

    assert "Викторины: 5 из 5" in text
    assert "Случайные вопросы: 19 из 20" in text
    assert "Обновятся в" in text


async def test_limits_screen_says_when_limits_are_off_for_everyone(session):
    user = await setup(session)
    await SettingsService(session).set_limit_mode(LimitMode.DISABLED_FOR_ALL)

    text = await render_limits(session, user)

    assert "лимиты не действуют" in text
    # в этом режиме ответы учитываются — предупреждения быть не должно
    assert "не идут в общий зачёт" not in text


async def test_admin_without_limits_is_warned_about_the_statistics(session):
    await setup(session)
    await SettingsService(session).set_limit_mode(LimitMode.DISABLED_FOR_ADMINS)
    admin = await UserService(session).grant_admin(7)

    text = await render_limits(session, admin)

    assert "лимиты не действуют" in text
    assert "не идут в общий зачёт" in text


async def test_exhausted_quiz_limit_message_names_limit_and_reset(session):
    from app.bot import texts
    from app.core.time import format_local

    user = await setup(session)
    await SettingsService(session).set_quiz_limit(1)
    service = QuizSessionService(session)
    first = await service.start(user, now=MOMENT)
    await service.abort(first.session, now=MOMENT)

    refused = (await service.start(user, now=MOMENT)).refused
    message = texts.LIMIT_QUIZ_REACHED.format(
        limit=refused.limit, reset_at=format_local(refused.reset_at)
    )

    assert "1 в сутки" in message
    assert "11.03.2026 00:00" in message


async def test_limits_stay_independent_on_the_screen(session):
    user = await setup(session)
    await SettingsService(session).set_random_limit(1)
    service = LimitService(session)
    await service.consume(user, KIND_RANDOM, now=MOMENT)

    assert (await service.consume(user, KIND_RANDOM, now=MOMENT)).allowed is False
    assert (await service.consume(user, KIND_QUIZ, now=MOMENT)).allowed is True


# --- меню и клавиатуры ---------------------------------------------------


def test_main_menu_reaches_every_mode():
    actions = {
        MenuCallback.unpack(button.callback_data).action
        for row in main_menu().inline_keyboard
        for button in row
    }

    assert actions == {"quiz", "random", "topics", "stats", "top", "limits"}


def test_topics_keyboard_marks_the_selected_ones():
    groups = group_topics(["Разработчик · Тема А", "Разработчик · Тема Б"])
    markup = topic_chapters(0, groups[0], {"Разработчик · Тема Б"}, page=0)
    labels = [button.text for row in markup.inline_keyboard for button in row]

    assert labels[0].startswith("▫️")
    assert labels[1].startswith("✅")
    assert any("К руководствам" in label for label in labels)
    # Выйти в меню можно с любого экрана тем, не листая страницы назад.
    assert any("В меню" in label for label in labels)


def test_select_all_button_flips_to_clear_when_everything_is_chosen():
    available = ["Разработчик · Тема А", "Разработчик · Тема Б"]
    groups = group_topics(available)

    empty = topic_chapters(0, groups[0], set(), page=0)
    full = topic_chapters(0, groups[0], set(available), page=0)

    def label(markup):
        return next(
            button.text
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data.startswith("tp:all:")
        )

    assert label(empty) == "✅ Выбрать все"
    assert label(full) == "◻️ Снять все"


def test_topic_buttons_address_by_index_and_fit_the_limit():
    groups = group_topics(["Разработчик · Очень длинное название темы " * 5])
    markup = topic_chapters(0, groups[0], set(), page=0)
    data = markup.inline_keyboard[0][0].callback_data

    assert len(data.encode()) <= 64
    assert TopicCallback.unpack(data).index == 0


def test_group_screen_counts_the_chosen_chapters():
    groups = group_topics(["Разработчик · Тема А", "Администратор · Тема Б"])
    markup = topic_groups(groups, {"Разработчик · Тема А"})
    labels = [button.text for row in markup.inline_keyboard for button in row]

    assert "Разработчик — 1 из 1" in labels
    assert "Администратор — 0 из 1" in labels
    assert any("Все темы" in label for label in labels)
    assert any("Сбросить" in label for label in labels)


def test_all_topics_and_reset_stand_side_by_side():
    groups = group_topics(["Разработчик · Тема А"])
    row = next(
        row
        for row in topic_groups(groups, set()).inline_keyboard
        if any(button.callback_data.startswith("tp:select_all:") for button in row)
    )

    assert [TopicCallback.unpack(button.callback_data).action for button in row] == [
        "select_all",
        "reset",
    ]


async def test_all_topics_button_marks_every_topic_and_reset_clears_them(session):
    """«Все темы» отмечает банк целиком, соседняя кнопка снимает выбор."""
    user = await setup(session, 1)
    session.add(make_question("adm.001", "Администратор · Глава 2"))
    await session.flush()
    service = TopicPreferenceService(session)
    bot = ScreenBot()

    marked = query(bot)
    await handle_topic_button(marked, TopicCallback(action="select_all"), session, user)
    assert sorted(await service.selected(user.id)) == await service.available()
    assert marked.answered == [(texts.TOPICS_ALL_SELECTED, False)]

    cleared = query(bot)
    await handle_topic_button(cleared, TopicCallback(action="reset"), session, user)
    assert await service.selected(user.id) == []
    assert cleared.answered == [(texts.TOPICS_RESET, False)]


def test_long_topic_list_is_paginated_and_fits_the_markup_limit():
    """85 тем одним списком Telegram отвергает: разметка длиннее 10 КБ."""
    available = [f"Разработчик · Глава {number}" for number in range(85)]
    groups = group_topics(available)
    markup = topic_chapters(0, groups[0], set(), page=0)

    chapters = [
        button
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data.startswith("tp:toggle:")
    ]
    assert len(chapters) == TOPICS_PAGE_SIZE
    assert len(markup.model_dump_json().encode()) < 10_000
    assert any(button.text == "стр. 1 из 11" for row in markup.inline_keyboard for button in row)


def test_page_buttons_wrap_around_the_ends():
    available = [f"Разработчик · Глава {number}" for number in range(20)]
    groups = group_topics(available)
    arrows = [
        TopicCallback.unpack(button.callback_data)
        for row in topic_chapters(0, groups[0], set(), page=0).inline_keyboard
        for button in row
        if button.text in {"⬅️", "➡️"}
    ]

    assert [arrow.page for arrow in arrows] == [2, 1]


def test_random_next_button_is_typed():
    from app.bot.keyboards.quiz import random_next

    data = random_next().inline_keyboard[0][0].callback_data
    assert RandomActionCallback.unpack(data).action == "next"
