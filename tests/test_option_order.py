"""Порядок показа вариантов: перестановка, устойчивость, текст и клавиатуры."""

from __future__ import annotations

from app.bot import texts
from app.bot.callbacks import RandomAnswerCallback, SessionAnswerCallback
from app.bot.keyboards.quiz import random_question, session_question
from app.services.quiz.options import (
    OPTION_LABELS,
    display_order,
    labelled_order,
    shuffled_order,
)
from tests.conftest import make_question


def test_display_order_is_a_permutation():
    for count in range(2, 11):
        assert sorted(display_order(count, ("s", 1))) == list(range(count))


def test_display_order_is_stable_for_the_same_key():
    first = display_order(4, (7, 2))
    assert all(display_order(4, (7, 2)) == first for _ in range(5))


def test_display_order_differs_between_keys():
    orders = {tuple(display_order(4, (1, position))) for position in range(20)}
    assert len(orders) > 1


def test_shuffled_order_is_a_permutation_and_varies():
    orders = {tuple(shuffled_order(4)) for _ in range(50)}
    assert len(orders) > 1
    for order in orders:
        assert sorted(order) == [0, 1, 2, 3]


def test_labelled_order_pairs_every_option_with_its_letter():
    order = labelled_order(4, (7, 2))

    assert [label for label, _ in order] == list(OPTION_LABELS[:4])
    assert sorted(index for _, index in order) == [0, 1, 2, 3]


def test_labelled_order_is_stable_for_the_same_key():
    first = labelled_order(4, (7, 2))
    assert all(labelled_order(4, (7, 2)) == first for _ in range(5))


def test_labelled_order_differs_between_keys():
    orders = {tuple(labelled_order(4, (1, position))) for position in range(20)}
    assert len(orders) > 1


# --- список вариантов в тексте сообщения ---------------------------------


def _option_lines(text: str) -> dict[str, str]:
    """Строки списка вариантов из тела сообщения: буква → текст варианта."""
    return {
        line[3]: line.split(".</b> ", 1)[1]
        for line in text.splitlines()
        if line.startswith("<b>") and ".</b> " in line
    }


def test_option_block_prints_every_option_on_its_own_line():
    question = make_question()
    order = labelled_order(4, (5, 3))

    lines = texts.option_block(
        order, [option.text for option in question.options]
    ).splitlines()

    assert len(lines) == 4
    for line, (label, index) in zip(lines, order, strict=True):
        assert line == f"<b>{label}.</b> {question.options[index].text}"


def test_option_block_makes_only_the_letter_bold():
    """Жирная буква цепляется взглядом за ту же букву на кнопке."""
    order = labelled_order(1, (1,))

    assert texts.option_block(order, ["Обычный текст"]) == "<b>А.</b> Обычный текст"


def test_option_block_escapes_markup_in_the_option_text():
    order = labelled_order(1, (1,))

    block = texts.option_block(order, ["<b>1 & 2</b>"])

    assert block == "<b>А.</b> &lt;b&gt;1 &amp; 2&lt;/b&gt;"


def test_question_screens_quote_the_question_above_the_options():
    options = "<b>А.</b> Раз\n<b>Б.</b> Два"
    quiz = texts.quiz_question_screen(1, 3, "Вопрос?", options)
    single = texts.random_question_screen("Вопрос?", options)

    for rendered in (quiz, single):
        assert "<blockquote>Вопрос?</blockquote>" in rendered
        assert rendered.endswith(f"</blockquote>\n\n{options}")


def test_question_screens_escape_the_question_text():
    quiz = texts.quiz_question_screen(1, 3, "Что делает <b> и & ?", "")
    single = texts.random_question_screen("Что делает <b> и & ?", "")

    for rendered in (quiz, single):
        assert "<blockquote>Что делает &lt;b&gt; и &amp; ?</blockquote>" in rendered


# --- разбор ответа -------------------------------------------------------


def test_feedback_separates_the_verdict_from_the_correct_option():
    text = texts.answer_feedback("Регистр накопления", "")

    verdict, _, correct = text.partition("\n\n")
    assert "Неверно" in verdict
    assert correct == "Верный ответ: <b>Регистр накопления</b>"


def test_feedback_quotes_the_explanation_after_the_verdict():
    text = texts.answer_feedback(None, "Потому что так")

    assert text.startswith("✅ <b>Верно!</b>")
    assert text.endswith("<blockquote>Потому что так</blockquote>")


def test_feedback_does_not_repeat_the_section():
    """Раздел показан в шапке вопроса до ответа, в разборе его нет."""
    text = texts.answer_feedback(None, "Потому что так")

    assert "Источник" not in text


def test_feedback_without_explanation_is_just_the_verdict():
    assert texts.answer_feedback(None, "") == texts.ANSWER_CORRECT


def test_feedback_escapes_everything_that_comes_from_the_bank():
    text = texts.answer_feedback("1 < 2", "A & B")

    assert "1 &lt; 2" in text
    assert "A &amp; B" in text


# --- клавиатуры ----------------------------------------------------------


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_session_keyboard_keeps_the_original_option_index():
    order = labelled_order(4, (5, 3))
    buttons = _buttons(session_question(order, session_id=5, position=3))[:4]

    for button, (label, index) in zip(buttons, order, strict=True):
        assert button.text == label
        assert SessionAnswerCallback.unpack(button.callback_data).option == index


def test_random_keyboard_keeps_the_original_option_index():
    order = labelled_order(4, (11,))
    buttons = _buttons(random_question(order, issue_id=11))

    for button, (label, index) in zip(buttons, order, strict=True):
        assert button.text == label
        assert RandomAnswerCallback.unpack(button.callback_data).option == index


def test_session_keyboard_puts_the_letters_in_one_row():
    markup = session_question(labelled_order(4, (5, 3)), session_id=5, position=3)

    letters, abort = markup.inline_keyboard
    assert [button.text for button in letters] == list(OPTION_LABELS[:4])
    assert len(abort) == 1 and abort[0].text.endswith("Прервать")


def test_random_keyboard_puts_the_letters_in_one_row():
    markup = random_question(labelled_order(4, (11,)), issue_id=11)

    (letters,) = markup.inline_keyboard
    assert [button.text for button in letters] == list(OPTION_LABELS[:4])


def test_correct_option_is_not_always_first_in_private():
    """У всех вопросов банка верный вариант записан первым."""
    first_shown = {labelled_order(4, (5, position))[0][1] for position in range(20)}

    assert len(first_shown) > 1


# --- сквозная проверка ---------------------------------------------------


async def test_answer_by_shown_button_is_scored_and_reviewed(session):
    """Ответ по букве учитывается по тексту варианта, а не по позиции."""
    from app.models import Question
    from app.services.quiz.review import ReviewService
    from app.services.quiz.session import QuizSessionService
    from app.services.settings import SettingsService
    from app.services.users import UserService

    for index in range(5):
        session.add(make_question(f"q.{index:03d}", correct_index=0))
    user = await UserService(session).register(7, "Иван", now=None)
    await session.flush()
    await SettingsService(session).set_session_size(3)

    service = QuizSessionService(session)
    quiz = (await service.start(user)).session
    for position in range(3):
        item = await service.current_question(quiz)
        question = await session.get(Question, item.question_id)
        order = labelled_order(len(question.options), (quiz.id, position))
        lines = _option_lines(
            texts.option_block(order, [option.text for option in question.options])
        )
        buttons = _buttons(session_question(order, quiz.id, position))[:4]

        # Участник читает верный вариант в тексте и жмёт кнопку с его буквой.
        correct_text = question.options[question.correct_index].text
        letter = next(key for key, value in lines.items() if value == correct_text)
        chosen = next(button for button in buttons if button.text == letter)
        option = SessionAnswerCallback.unpack(chosen.callback_data).option

        recorded, _ = await service.answer(user, quiz, position, option)
        assert recorded.is_correct

    items = await ReviewService(session).build(quiz)
    assert len(items) == 3
    for item in items:
        assert item.is_correct and item.chosen == item.correct


def test_admin_card_keeps_the_storage_order():
    """В кабинете список вариантов — редактируемый источник, его не мешаем."""
    from app.bot.handlers.admin_questions import render_question
    from app.services.stats.reading import QuestionStats, difficulty_of

    question = make_question()
    card = render_question(question, difficulty_of(QuestionStats(0, 0), None))
    shown = [line for line in card.splitlines() if line.startswith(("✅", "▫️"))]

    assert [line.split()[-1] for line in shown] == ["0", "1", "2", "3"]
    assert shown[0].startswith("✅")


# --- выдача вопроса ------------------------------------------------------


def _shown(text: str, markup) -> list[tuple[str, str]]:
    """Пары «буква кнопки — текст варианта под той же буквой в списке»."""
    lines = _option_lines(text)
    return [(button.text, lines[button.text]) for button in _buttons(markup)[:4]]


async def _prepare(session, *, questions: int = 4):
    from app.services.settings import SettingsService
    from app.services.users import UserService

    for index in range(questions):
        session.add(make_question(f"q.{index:03d}", correct_index=0))
    user = await UserService(session).register(7, "Иван", now=None)
    await SettingsService(session).set_session_size(1)
    await session.flush()
    return user


def _command(bot):
    from datetime import UTC, datetime

    from aiogram.types import Chat as TgChat
    from aiogram.types import Message

    return Message.model_construct(
        message_id=1,
        date=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
        chat=TgChat(id=7, type="private"),
    ).as_(bot)


async def test_session_question_list_matches_its_buttons(session):
    from app.bot.handlers.quiz import handle_quiz_command
    from app.models import Question
    from app.repositories.sessions import SessionRepository
    from app.services.quiz.session import QuizSessionService
    from tests.screen import ScreenBot

    user = await _prepare(session)
    bot = ScreenBot()
    await handle_quiz_command(_command(bot), session, user)

    quiz = await SessionRepository(session).active_for(user.id)
    item = await QuizSessionService(session).current_question(quiz)
    question = await session.get(Question, item.question_id)

    text, markup = bot.sent[-1][1], bot.markups[-1]
    for button, (label, index) in zip(
        _buttons(markup)[:4],
        labelled_order(len(question.options), (quiz.id, item.position)),
        strict=True,
    ):
        assert button.text == label
        assert SessionAnswerCallback.unpack(button.callback_data).option == index
        assert f"<b>{label}.</b> {question.options[index].text}" in text


async def test_random_question_list_matches_its_buttons(session):
    from app.bot.handlers.quiz import send_random
    from app.models import Question, RandomQuestionIssue
    from tests.screen import ScreenBot

    user = await _prepare(session)
    bot = ScreenBot()
    await send_random(_command(bot), session, user)

    from sqlalchemy import select

    issue = await session.scalar(
        select(RandomQuestionIssue).order_by(RandomQuestionIssue.id.desc()).limit(1)
    )
    question = await session.get(Question, issue.question_id)

    text, markup = bot.sent[-1][1], bot.markups[-1]
    for button, (label, index) in zip(
        _buttons(markup),
        labelled_order(len(question.options), (issue.id,)),
        strict=True,
    ):
        assert button.text == label
        assert RandomAnswerCallback.unpack(button.callback_data).option == index
        assert f"<b>{label}.</b> {question.options[index].text}" in text


async def test_random_question_keeps_the_topics_warning_in_one_screen(session):
    from app.bot.handlers.quiz import send_random
    from app.services.quiz.topics import TopicPreferenceService
    from tests.screen import ScreenBot

    user = await _prepare(session)
    await TopicPreferenceService(session).save(7, ["Несуществующая тема"])
    bot = ScreenBot()
    await send_random(_command(bot), session, user)

    text = bot.sent[-1][1]
    assert len(bot.sent) == 1
    assert texts.TOPICS_FALLBACK_APPLIED in text
    assert len(_option_lines(text)) == 4


async def test_repeated_question_screen_keeps_the_same_letters(session):
    """Возврат к сессии перерисовывает вопрос — список и буквы те же."""
    from app.bot.callbacks import SessionActionCallback
    from app.bot.handlers.quiz import handle_quiz_command, handle_session_action
    from app.repositories.sessions import SessionRepository
    from tests.screen import ScreenBot, query

    user = await _prepare(session)
    bot = ScreenBot()
    await handle_quiz_command(_command(bot), session, user)
    first_text, first_markup = bot.sent[-1][1], bot.markups[-1]

    quiz = await SessionRepository(session).active_for(user.id)
    await handle_session_action(
        query(bot),
        SessionActionCallback(action="continue", session_id=quiz.id),
        session,
        user,
    )

    assert len(bot.sent) == 2  # вопрос действительно выдан заново
    assert _shown(bot.sent[-1][1], bot.markups[-1]) == _shown(first_text, first_markup)
