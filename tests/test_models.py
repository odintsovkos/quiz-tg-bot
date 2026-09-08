from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Answer,
    AnswerSource,
    Chat,
    Question,
    QuestionOption,
    QuizSession,
    SessionMessage,
    SessionQuestion,
    UserDailyLimits,
    UserDailyStats,
)
from tests.conftest import make_question, make_user

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
DAY = date(2026, 3, 10)


async def test_options_are_deleted_with_the_question(session):
    session.add(make_question())
    await session.commit()

    question = await session.get(Question, "dev.ch08.001")
    await session.delete(question)
    await session.commit()

    remaining = await session.scalar(select(func.count()).select_from(QuestionOption))
    assert remaining == 0


async def test_correct_index_points_at_the_correct_option(session):
    session.add(make_question(correct_index=2))
    await session.commit()

    question = await session.get(Question, "dev.ch08.001")
    assert question.correct_index == 2


async def test_poll_and_user_pair_is_unique(session):
    session.add_all([make_user(), make_question()])
    await session.commit()

    def answer() -> Answer:
        return Answer(
            user_id=1,
            question_id="dev.ch08.001",
            source=AnswerSource.GROUP,
            chat_id=-100,
            poll_id="poll-1",
            is_correct=True,
            answered_at=MOMENT,
            quiz_date=DAY,
        )

    session.add(answer())
    await session.commit()

    session.add(answer())
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_session_and_question_pair_is_unique(session):
    session.add_all([make_user(), make_question()])
    await session.commit()
    quiz = QuizSession(
        user_id=1, total_questions=1, started_at=MOMENT, last_activity_at=MOMENT
    )
    session.add(quiz)
    await session.commit()

    session.add(SessionQuestion(session_id=quiz.id, question_id="dev.ch08.001", position=0))
    await session.commit()

    session.add(SessionQuestion(session_id=quiz.id, question_id="dev.ch08.001", position=1))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_group_answers_of_different_users_coexist(session):
    session.add_all([make_user(1), make_user(2, name="Пётр"), make_question()])
    await session.commit()

    for user_id in (1, 2):
        session.add(
            Answer(
                user_id=user_id,
                question_id="dev.ch08.001",
                source=AnswerSource.GROUP,
                poll_id="poll-1",
                is_correct=True,
                answered_at=MOMENT,
                quiz_date=DAY,
            )
        )
    await session.commit()

    total = await session.scalar(select(func.count()).select_from(Answer))
    assert total == 2


async def test_daily_stats_pair_is_unique(session):
    session.add(make_user())
    await session.commit()

    session.add(UserDailyStats(user_id=1, quiz_date=DAY))
    await session.commit()

    session.add(UserDailyStats(user_id=1, quiz_date=DAY))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_daily_limits_pair_is_unique(session):
    session.add(make_user())
    await session.commit()

    session.add(UserDailyLimits(user_id=1, quiz_date=DAY))
    await session.commit()

    session.add(UserDailyLimits(user_id=1, quiz_date=DAY))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_chat_categories_round_trip(session):
    chat = Chat(id=-100, title="Чат", connected_at=MOMENT, connected_by=1)
    chat.set_categories(["Разработчик · Глава 8", "Администратор · Глава 2"])
    session.add(chat)
    await session.commit()

    stored = await session.get(Chat, -100)
    assert stored.category_list == ["Разработчик · Глава 8", "Администратор · Глава 2"]

    stored.set_categories([])
    await session.commit()
    assert stored.category_list == []


async def test_session_messages_are_deleted_with_the_session(session):
    session.add(make_user())
    await session.commit()
    quiz = QuizSession(
        user_id=1, total_questions=1, started_at=MOMENT, last_activity_at=MOMENT
    )
    session.add(quiz)
    await session.commit()
    session.add_all(
        [
            SessionMessage(session_id=quiz.id, chat_id=1, message_id=100),
            SessionMessage(session_id=quiz.id, chat_id=1, message_id=101),
        ]
    )
    await session.commit()

    await session.delete(quiz)
    await session.commit()

    remaining = await session.scalar(select(func.count()).select_from(SessionMessage))
    assert remaining == 0
