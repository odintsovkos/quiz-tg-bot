"""Статистика ответов по вопросу и фактическая сложность.

Спека `scoring-and-stats`: требования «Статистика ответов по вопросу»
и «Фактическая сложность вопроса».
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.models import Answer, AnswerSource, Difficulty
from app.services.stats.reading import (
    DIFFICULTY_SAMPLE_THRESHOLD,
    QuestionStats,
    StatsService,
    difficulty_of,
    level_of_share,
)
from app.services.stats.scoring import ScoringService
from app.services.users import UserService
from tests.conftest import make_question

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
QUESTION = "dev.ch06.002"


# --- границы уровней и порог достоверности --------------------------------


def test_level_borders_of_share():
    assert level_of_share(0.70) is Difficulty.EASY
    assert level_of_share(0.69) is Difficulty.MEDIUM
    assert level_of_share(0.40) is Difficulty.MEDIUM
    assert level_of_share(0.39) is Difficulty.HARD


def test_measured_level_replaces_the_authored_one():
    difficulty = difficulty_of(QuestionStats(answers=40, correct=9), Difficulty.MEDIUM)

    assert difficulty.is_measured
    assert difficulty.measured is Difficulty.HARD
    assert difficulty.shown is Difficulty.HARD
    # 9 из 40 — это 22,5%: округление арифметическое, а не банковское.
    assert difficulty.percent == 23
    assert difficulty.answers == 40


def test_below_the_threshold_the_authored_level_is_shown():
    difficulty = difficulty_of(
        QuestionStats(answers=DIFFICULTY_SAMPLE_THRESHOLD - 1, correct=0),
        Difficulty.MEDIUM,
    )

    assert not difficulty.is_measured
    assert difficulty.share is None
    assert difficulty.shown is Difficulty.MEDIUM
    assert difficulty.answers == DIFFICULTY_SAMPLE_THRESHOLD - 1


def test_below_the_threshold_without_authored_level_nothing_is_known():
    difficulty = difficulty_of(
        QuestionStats(answers=DIFFICULTY_SAMPLE_THRESHOLD - 1, correct=5), None
    )

    assert difficulty.shown is None
    assert difficulty.share is None


def test_at_the_threshold_the_level_becomes_measured():
    difficulty = difficulty_of(
        QuestionStats(answers=DIFFICULTY_SAMPLE_THRESHOLD, correct=20), None
    )

    assert difficulty.is_measured
    assert difficulty.shown is Difficulty.EASY


def test_question_without_answers_and_without_authored_level():
    difficulty = difficulty_of(QuestionStats(0, 0), None)

    assert (difficulty.shown, difficulty.share, difficulty.answers) == (None, None, 0)


# --- агрегат по вопросу --------------------------------------------------


async def test_answers_from_both_modes_add_up(session):
    session.add(make_question(QUESTION))
    users = UserService(session)
    from_group = await users.register(1, "Иван", now=MOMENT)
    from_private = await users.register(2, "Пётр", now=MOMENT)
    await session.flush()

    scoring = ScoringService(session)
    await scoring.record_answer(
        from_group,
        QUESTION,
        is_correct=True,
        source=AnswerSource.GROUP,
        chat_id=-100,
        poll_id="poll-1",
        now=MOMENT,
    )
    await scoring.record_answer(
        from_private,
        QUESTION,
        is_correct=False,
        source=AnswerSource.PRIVATE,
        session_id=None,
        now=MOMENT,
    )

    stats = await StatsService(session).question(QUESTION)
    assert (stats.answers, stats.correct) == (2, 1)


async def test_uncounted_answer_stays_out_of_question_stats(session):
    session.add(make_question(QUESTION))
    user = await UserService(session).register(3, "Админ", now=MOMENT)
    await session.flush()
    session.add(
        Answer(
            user_id=user.id,
            question_id=QUESTION,
            source=AnswerSource.PRIVATE,
            is_correct=True,
            counted=False,
            answered_at=MOMENT,
            quiz_date=MOMENT.date(),
        )
    )
    await session.flush()

    stats = await StatsService(session).question(QUESTION)
    assert (stats.answers, stats.correct) == (0, 0)


async def test_editing_the_question_keeps_its_stats(session):
    question = make_question(QUESTION)
    session.add(question)
    user = await UserService(session).register(4, "Иван", now=MOMENT)
    await session.flush()
    await ScoringService(session).record_answer(
        user, QUESTION, is_correct=True, source=AnswerSource.PRIVATE, now=MOMENT
    )

    question.text = "Другая формулировка того же вопроса?"
    await session.flush()

    stats = await StatsService(session).question(QUESTION)
    assert (stats.answers, stats.correct) == (1, 1)


async def test_question_difficulty_combines_stats_and_authored_level(session):
    session.add(make_question(QUESTION, difficulty=Difficulty.HARD))
    user = await UserService(session).register(5, "Иван", now=MOMENT)
    await session.flush()
    await ScoringService(session).record_answer(
        user, QUESTION, is_correct=True, source=AnswerSource.PRIVATE, now=MOMENT
    )

    difficulty = await StatsService(session).question_difficulty(
        QUESTION, Difficulty.HARD
    )

    assert difficulty.authored is Difficulty.HARD
    assert not difficulty.is_measured
    assert difficulty.answers == 1
