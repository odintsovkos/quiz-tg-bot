"""Начисление баллов, флаг учёта, идемпотентность, чтение статистики."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select

from app.core.db import session_scope
from app.models import Answer, AnswerSource, LimitMode, UserRole
from app.services.settings import SettingsService
from app.services.stats.reading import PERIOD_TODAY, PERIOD_TOTAL, StatsService
from app.services.stats.scoring import ScoringService, is_counted
from app.services.users import UserService
from tests.conftest import make_question

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
DAY = date(2026, 3, 10)


async def prepare(session, *, questions: int = 1):
    for index in range(questions):
        session.add(make_question(f"dev.ch08.{index:03d}"))
    user = await UserService(session).register(7, "Иван", now=MOMENT)
    await session.flush()
    return user


# --- начисление ----------------------------------------------------------


async def test_correct_answer_earns_one_point(session):
    user = await prepare(session)

    recorded = await ScoringService(session).record_answer(
        user, "dev.ch08.000", is_correct=True, source=AnswerSource.PRIVATE, now=MOMENT
    )

    assert (recorded.accepted, recorded.counted, recorded.points) == (True, True, 1)
    daily = await StatsService(session).daily(7, DAY)
    assert (daily.attempts, daily.correct, daily.points) == (1, 1, 1)


async def test_wrong_answer_earns_nothing_but_counts_as_an_attempt(session):
    user = await prepare(session)

    recorded = await ScoringService(session).record_answer(
        user, "dev.ch08.000", is_correct=False, source=AnswerSource.PRIVATE, now=MOMENT
    )

    assert recorded.points == 0
    daily = await StatsService(session).daily(7, DAY)
    assert (daily.attempts, daily.correct, daily.points) == (1, 0, 0)


async def test_both_daily_and_total_are_updated(session):
    user = await prepare(session)

    await ScoringService(session).record_answer(
        user, "dev.ch08.000", is_correct=True, source=AnswerSource.GROUP,
        poll_id="p1", now=MOMENT,
    )

    stats = StatsService(session)
    assert (await stats.daily(7, DAY)).points == 1
    assert (await stats.total(7)).points == 1


# --- идемпотентность -----------------------------------------------------


async def test_second_answer_to_the_same_poll_is_ignored(session):
    user = await prepare(session)
    service = ScoringService(session)

    first = await service.record_answer(
        user, "dev.ch08.000", is_correct=True, source=AnswerSource.GROUP,
        poll_id="p1", now=MOMENT,
    )
    second = await service.record_answer(
        user, "dev.ch08.000", is_correct=False, source=AnswerSource.GROUP,
        poll_id="p1", now=MOMENT,
    )

    assert first.accepted and not second.accepted
    assert (await StatsService(session).total(7)).attempts == 1


async def test_concurrent_answers_to_one_poll_produce_a_single_row(session_factory):
    """Две одновременные записи по паре «опрос и участник» дают одну строку."""
    async with session_scope(session_factory) as session:
        await prepare(session)

    async def record() -> bool:
        async with session_scope(session_factory) as session:
            user = await UserService(session).get(7)
            result = await ScoringService(session).record_answer(
                user, "dev.ch08.000", is_correct=True, source=AnswerSource.GROUP,
                poll_id="p1", now=MOMENT,
            )
            return result.accepted

    outcomes = await asyncio.gather(record(), record(), return_exceptions=True)
    accepted = [item for item in outcomes if item is True]

    async with session_factory() as session:
        rows = await session.scalar(
            select(func.count()).select_from(Answer).where(Answer.poll_id == "p1")
        )
    assert rows == 1
    assert len(accepted) == 1


async def test_repeated_answer_within_a_session_is_ignored(session):
    from app.models import QuizSession

    user = await prepare(session)
    quiz = QuizSession(
        user_id=7, total_questions=1, started_at=MOMENT, last_activity_at=MOMENT
    )
    session.add(quiz)
    await session.flush()
    service = ScoringService(session)

    first = await service.record_answer(
        user, "dev.ch08.000", is_correct=True, source=AnswerSource.PRIVATE,
        session_id=quiz.id, now=MOMENT,
    )
    second = await service.record_answer(
        user, "dev.ch08.000", is_correct=True, source=AnswerSource.PRIVATE,
        session_id=quiz.id, now=MOMENT,
    )

    assert first.accepted and not second.accepted
    assert (await StatsService(session).total(7)).attempts == 1


# --- флаг учёта: все четыре комбинации -----------------------------------


@pytest.mark.parametrize(
    ("role", "source", "mode", "expected"),
    [
        (UserRole.ADMIN, AnswerSource.PRIVATE, LimitMode.DISABLED_FOR_ADMINS, False),
        (UserRole.ADMIN, AnswerSource.GROUP, LimitMode.DISABLED_FOR_ADMINS, True),
        (UserRole.USER, AnswerSource.PRIVATE, LimitMode.DISABLED_FOR_ADMINS, True),
        (UserRole.USER, AnswerSource.GROUP, LimitMode.DISABLED_FOR_ADMINS, True),
        (UserRole.ADMIN, AnswerSource.PRIVATE, LimitMode.ENABLED, True),
        (UserRole.ADMIN, AnswerSource.PRIVATE, LimitMode.DISABLED_FOR_ALL, True),
        (UserRole.OWNER, AnswerSource.PRIVATE, LimitMode.DISABLED_FOR_ADMINS, False),
    ],
)
def test_counted_flag_rule(role, source, mode, expected):
    assert is_counted(role, source, mode) is expected


async def test_admin_private_answer_is_recorded_but_not_counted(session):
    user = await prepare(session)
    await SettingsService(session).set_limit_mode(LimitMode.DISABLED_FOR_ADMINS)
    admin = await UserService(session).grant_admin(7)

    recorded = await ScoringService(session).record_answer(
        admin, "dev.ch08.000", is_correct=True, source=AnswerSource.PRIVATE, now=MOMENT
    )

    assert recorded.accepted and not recorded.counted and recorded.points == 0
    assert (await StatsService(session).total(7)).attempts == 0
    stored = await session.scalar(select(Answer))
    assert stored.counted is False
    assert user.id == 7


async def test_admin_group_answer_is_counted_in_the_same_mode(session):
    await prepare(session)
    await SettingsService(session).set_limit_mode(LimitMode.DISABLED_FOR_ADMINS)
    admin = await UserService(session).grant_admin(7)

    recorded = await ScoringService(session).record_answer(
        admin, "dev.ch08.000", is_correct=True, source=AnswerSource.GROUP,
        poll_id="p1", now=MOMENT,
    )

    assert recorded.counted and recorded.points == 1
    assert (await StatsService(session).total(7)).points == 1


async def test_switching_mode_does_not_recount_the_past(session):
    await prepare(session, questions=2)
    await SettingsService(session).set_limit_mode(LimitMode.DISABLED_FOR_ADMINS)
    admin = await UserService(session).grant_admin(7)
    service = ScoringService(session)

    await service.record_answer(
        admin, "dev.ch08.000", is_correct=True, source=AnswerSource.PRIVATE, now=MOMENT
    )
    await SettingsService(session).set_limit_mode(LimitMode.ENABLED)
    await service.record_answer(
        admin, "dev.ch08.001", is_correct=True, source=AnswerSource.PRIVATE, now=MOMENT
    )

    total = await StatsService(session).total(7)
    assert (total.attempts, total.points) == (1, 1)


# --- чтение статистики ---------------------------------------------------


async def test_accuracy_is_undefined_without_attempts(session):
    await prepare(session)

    assert (await StatsService(session).daily(7, DAY)).accuracy is None
    assert (await StatsService(session).total(7)).accuracy is None


async def test_newcomer_sees_zeroes_and_no_rank(session):
    await prepare(session)
    stats = StatsService(session)

    line = await stats.total(7)

    assert (line.attempts, line.correct, line.points) == (0, 0, 0)
    assert await stats.rank(7, PERIOD_TOTAL) is None


async def test_rank_in_both_ratings(session):
    await prepare(session, questions=2)
    users = UserService(session)
    await users.register(8, "Пётр", now=MOMENT)
    first = await users.get(7)
    second = await users.get(8)
    service = ScoringService(session)

    await service.record_answer(
        first, "dev.ch08.000", is_correct=True, source=AnswerSource.GROUP,
        poll_id="p1", now=MOMENT,
    )
    await service.record_answer(
        second, "dev.ch08.000", is_correct=False, source=AnswerSource.GROUP,
        poll_id="p1", now=MOMENT,
    )

    stats = StatsService(session)
    assert await stats.rank(7, PERIOD_TODAY, DAY) == 1
    assert await stats.rank(8, PERIOD_TODAY, DAY) == 2
    assert await stats.rank(7, PERIOD_TOTAL) == 1
