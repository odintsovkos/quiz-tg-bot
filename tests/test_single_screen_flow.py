"""Лента сессии, её уборка, разбор и цепочка случайных вопросов."""

from __future__ import annotations

from datetime import UTC, datetime

from aiogram.types import Chat as TgChat
from aiogram.types import Message

from app.bot import review
from app.bot.callbacks import (
    MenuCallback,
    RandomActionCallback,
    RandomAnswerCallback,
    ReviewCallback,
    SessionActionCallback,
    SessionAnswerCallback,
)
from app.bot.handlers.quiz import (
    handle_menu_button,
    handle_quiz_command,
    handle_random_answer,
    handle_random_next,
    handle_review,
    handle_session_action,
    handle_session_answer,
    send_random,
)
from app.models import Question, SessionStatus
from app.repositories.sessions import SessionRepository
from app.services.quiz.review import ReviewService
from app.services.quiz.session import QuizSessionService
from app.services.settings import SettingsService
from app.services.users import UserService
from tests.conftest import make_question
from tests.screen import ScreenBot, query

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
DEV = "Разработчик · Глава 8"


async def setup(session, *, questions: int = 12, size: int = 3):
    for index in range(questions):
        session.add(make_question(f"q.{index:03d}", DEV, correct_index=index % 4))
    user = await UserService(session).register(7, "Иван", now=MOMENT)
    await SettingsService(session).set_session_size(size)
    await session.flush()
    return user


def command(bot: ScreenBot, message_id: int = 1) -> Message:
    return Message.model_construct(
        message_id=message_id, date=MOMENT, chat=TgChat(id=7, type="private")
    ).as_(bot)


async def current_option(session, quiz, *, correct: bool) -> tuple[int, int]:
    """Позиция текущего вопроса и номер верного либо неверного варианта."""
    item = await QuizSessionService(session).current_question(quiz)
    question = await session.get(Question, item.question_id)
    index = question.correct_index
    if not correct:
        index = (index + 1) % len(question.options)
    return item.position, index


async def play(session, user, bot, quiz, *, answers: int, correct: bool = True):
    for _ in range(answers):
        position, option = await current_option(session, quiz, correct=correct)
        await handle_session_answer(
            query(bot),
            SessionAnswerCallback(session_id=quiz.id, position=position, option=option),
            session,
            user,
        )


# --- 5.1 реестр ленты ----------------------------------------------------


async def test_registry_holds_every_message_of_the_session(session):
    user = await setup(session, size=3)
    bot = ScreenBot()

    await handle_quiz_command(command(bot, message_id=5), session, user)
    quiz = await SessionRepository(session).active_for(user.id)
    await play(session, user, bot, quiz, answers=2)

    stored = await SessionRepository(session).list_messages(quiz.id)
    # команда запуска, три вопроса и два разбора ответа
    assert len(stored) == 6
    assert 5 in [item.message_id for item in stored]


# --- 5.4 уборка при завершении -------------------------------------------


async def test_finishing_a_session_clears_its_feed_and_leaves_the_result(session):
    user = await setup(session, size=3)
    bot = ScreenBot()
    await handle_quiz_command(command(bot), session, user)
    quiz = await SessionRepository(session).active_for(user.id)

    await play(session, user, bot, quiz, answers=3)

    assert await SessionRepository(session).list_messages(quiz.id) == []
    assert quiz.status is SessionStatus.COMPLETED
    assert user.anchor_message_id is not None
    # Итог отправлен последним, лента удалена целиком.
    assert len(bot.deleted) == 6


async def test_the_result_offers_the_review(session):
    user = await setup(session, size=1)
    bot = ScreenBot()
    await handle_quiz_command(command(bot), session, user)
    quiz = await SessionRepository(session).active_for(user.id)

    await play(session, user, bot, quiz, answers=1)

    markup = bot.markups[-1]
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert any("Разбор" in label for label in labels)


# --- 5.5 уборка при прерывании -------------------------------------------


async def test_aborting_a_session_clears_its_feed(session):
    user = await setup(session, size=3)
    bot = ScreenBot()
    await handle_quiz_command(command(bot), session, user)
    quiz = await SessionRepository(session).active_for(user.id)
    await play(session, user, bot, quiz, answers=1)

    await handle_session_action(
        query(bot),
        SessionActionCallback(action="abort", session_id=quiz.id),
        session,
        user,
    )

    assert await SessionRepository(session).list_messages(quiz.id) == []
    assert quiz.status is SessionStatus.ABORTED


# --- 5.6 уход на экран и возврат в сессию --------------------------------


async def test_leaving_for_the_menu_clears_the_feed_and_keeps_the_session(session):
    user = await setup(session, size=3)
    bot = ScreenBot()
    await handle_quiz_command(command(bot), session, user)
    quiz = await SessionRepository(session).active_for(user.id)
    await play(session, user, bot, quiz, answers=1)

    await handle_menu_button(query(bot), MenuCallback(action="root"), session, user)

    assert await SessionRepository(session).list_messages(quiz.id) == []
    assert quiz.status is SessionStatus.ACTIVE


async def test_continuing_reissues_the_question_on_an_empty_registry(session):
    user = await setup(session, size=3)
    bot = ScreenBot()
    await handle_quiz_command(command(bot), session, user)
    quiz = await SessionRepository(session).active_for(user.id)
    await play(session, user, bot, quiz, answers=1)
    await handle_menu_button(query(bot), MenuCallback(action="root"), session, user)

    await handle_session_action(
        query(bot),
        SessionActionCallback(action="continue", session_id=quiz.id),
        session,
        user,
    )

    stored = await SessionRepository(session).list_messages(quiz.id)
    assert len(stored) == 1
    assert "Вопрос 2 из 3" in bot.sent[-1][1]
    # Прогресс сохранён: один ответ уже засчитан.
    assert sum(1 for item in quiz.questions if item.answered) == 1


# --- 6.1 данные разбора --------------------------------------------------


async def test_review_marks_correct_and_wrong_answers(session):
    user = await setup(session, size=2)
    bot = ScreenBot()
    await handle_quiz_command(command(bot), session, user)
    quiz = await SessionRepository(session).active_for(user.id)
    await play(session, user, bot, quiz, answers=1, correct=True)
    await play(session, user, bot, quiz, answers=1, correct=False)

    items = await ReviewService(session).build(quiz)

    assert [item.number for item in items] == [1, 2]
    assert [item.is_correct for item in items] == [True, False]
    # Верный ответ у обоих, выбранный — тот, что участник действительно нажал.
    assert items[0].chosen == items[0].correct
    assert items[1].chosen is not None and items[1].chosen != items[1].correct
    assert all(item.explanation == "Пояснение" for item in items)
    assert all(item.reference == "8.1. Раздел" for item in items)
    assert all(item.answered for item in items)


# --- 6.2 постраничный разбор ---------------------------------------------


def test_long_review_is_split_into_pages():
    from app.services.quiz.review import ReviewItem

    items = [
        ReviewItem(
            number=index + 1,
            text="Вопрос " + "я" * 200,
            correct="Вариант",
            chosen="Другой вариант",
            explanation="Пояснение " + "ю" * 800,
            reference="8.1. Раздел",
            answered=True,
            is_correct=index % 2 == 0,
        )
        for index in range(10)
    ]

    pages = review.paginate(items)
    text, _page, total = review.render(items, 0)

    assert total > 1 and len(pages) == total
    assert all(len(", ".join(block)) <= review.PAGE_LIMIT * 2 for block in pages)
    assert "стр. 1 из" in text


def test_empty_review_reports_it_on_a_single_page():
    text, page, pages = review.render([], 0)

    assert pages == 1 and page == 0
    assert "Разбирать нечего" in text


# --- 6.3 экран разбора ---------------------------------------------------


async def test_review_opens_and_returns_to_the_result(session):
    user = await setup(session, size=2)
    bot = ScreenBot()
    await handle_quiz_command(command(bot), session, user)
    quiz = await SessionRepository(session).active_for(user.id)
    await play(session, user, bot, quiz, answers=2)
    sent_before = len(bot.sent)

    await handle_review(
        query(bot), ReviewCallback(session_id=quiz.id, page=0), session, user
    )
    assert "Разбор викторины" in bot.edits[-1][2]

    await handle_review(
        query(bot),
        ReviewCallback(session_id=quiz.id, action="result"),
        session,
        user,
    )

    assert "Викторина завершена" in bot.edits[-1][2]
    assert len(bot.sent) == sent_before


async def test_review_of_a_foreign_session_is_refused(session):
    user = await setup(session, size=1)
    other = await UserService(session).register(8, "Пётр", now=MOMENT)
    bot = ScreenBot()
    await handle_quiz_command(command(bot), session, user)
    quiz = await SessionRepository(session).active_for(user.id)

    target = query(bot)
    await handle_review(
        target, ReviewCallback(session_id=quiz.id, page=0), session, other
    )

    assert target.answered[-1][1] is True
    assert bot.edits == []


# --- 7.1, 7.2 случайный вопрос на якоре ----------------------------------


async def test_random_question_uses_the_anchor(session):
    user = await setup(session)
    bot = ScreenBot()
    await send_random(command(bot), session, user)
    assert len(bot.sent) == 1

    await handle_random_next(query(bot), session, user)

    assert len(bot.sent) == 1
    assert "Случайный вопрос" in bot.edits[-1][2]


async def test_three_random_questions_in_a_row_add_no_messages(session):
    user = await setup(session)
    bot = ScreenBot()
    await send_random(command(bot), session, user)

    for _ in range(3):
        issue = await _last_issue(session, user)
        question = await session.get(Question, issue.question_id)
        await handle_random_answer(
            query(bot),
            RandomAnswerCallback(issue_id=issue.id, option=question.correct_index),
            session,
            user,
        )
        await handle_random_next(query(bot), session, user)

    assert len(bot.sent) == 1
    assert len(bot.edits) == 6


async def _last_issue(session, user):
    from sqlalchemy import select

    from app.models import RandomQuestionIssue

    statement = (
        select(RandomQuestionIssue)
        .where(RandomQuestionIssue.user_id == user.id)
        .order_by(RandomQuestionIssue.id.desc())
        .limit(1)
    )
    return await session.scalar(statement)


async def test_random_next_callback_data_is_accepted(session):
    """Кнопка «ещё вопрос» приходит с данными действия, а не пустой."""
    user = await setup(session)
    bot = ScreenBot()

    await handle_random_next(query(bot), session, user)

    assert RandomActionCallback(action="next").pack()
    assert len(bot.sent) == 1


# --- разбор показывает и выбранный вариант --------------------------------


def _item(**overrides):
    from app.services.quiz.review import ReviewItem

    base = {
        "number": 1,
        "text": "Вопрос?",
        "correct": "Верный вариант",
        "chosen": "Верный вариант",
        "explanation": None,
        "reference": None,
        "answered": True,
        "is_correct": True,
    }
    base.update(overrides)
    return ReviewItem(**base)


def test_a_wrong_answer_shows_what_was_picked():
    text = review.item_text(
        _item(chosen="Ошибочный вариант", is_correct=False)
    )

    assert "<b>Верно:</b> Верный вариант" in text
    assert "<b>Вы ответили:</b> Ошибочный вариант" in text


def test_a_correct_answer_does_not_repeat_the_option():
    text = review.item_text(_item())

    assert "<b>Верно:</b> Верный вариант" in text
    assert "Вы ответили" not in text


def test_an_unanswered_question_says_so():
    text = review.item_text(_item(answered=False, is_correct=False, chosen=None))

    assert "не ответили" in text
    assert "Вы ответили" not in text


def test_an_old_session_without_a_stored_choice_still_renders():
    """Сессии, пройденные до появления поля, выбранный вариант не помнят."""
    text = review.item_text(_item(is_correct=False, chosen=None))

    assert "<b>Верно:</b> Верный вариант" in text
    assert "Вы ответили" not in text


async def test_the_review_of_a_played_session_shows_the_wrong_choice(session):
    user = await setup(session, size=1)
    bot = ScreenBot()
    await handle_quiz_command(command(bot), session, user)
    quiz = await SessionRepository(session).active_for(user.id)
    await play(session, user, bot, quiz, answers=1, correct=False)

    items = await ReviewService(session).build(quiz)
    text = review.item_text(items[0])

    assert items[0].chosen != items[0].correct
    assert "Вы ответили" in text
