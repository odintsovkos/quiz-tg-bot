"""Таблица результатов и пересчёт агрегатов."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select

from app.models import UserDailyStats, UserTotalStats
from app.services.settings import SettingsService
from app.services.stats.reading import PERIOD_TODAY, PERIOD_TOTAL, StatsService
from app.services.stats.recalc import recalculate_stats
from app.services.users import UserService

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
DAY = date(2026, 3, 10)


async def add_participant(
    session, user_id: int, name: str, *, attempts: int, correct: int, points: int
):
    await UserService(session).register(user_id, name, now=MOMENT)
    session.add(
        UserDailyStats(
            user_id=user_id,
            quiz_date=DAY,
            attempts=attempts,
            correct=correct,
            points=points,
        )
    )
    session.add(
        UserTotalStats(
            user_id=user_id, attempts=attempts, correct=correct, points=points
        )
    )
    await session.flush()


async def test_sorted_by_points_then_accuracy_then_attempts(session):
    await add_participant(session, 1, "Первый", attempts=10, correct=5, points=5)
    # столько же баллов, но выше точность
    await add_participant(session, 2, "Второй", attempts=6, correct=5, points=5)
    # столько же баллов и та же точность, но меньше попыток
    await add_participant(session, 3, "Третий", attempts=5, correct=5, points=5)
    await add_participant(session, 4, "Четвёртый", attempts=20, correct=9, points=9)

    board = await StatsService(session).leaderboard(PERIOD_TODAY, day=DAY)

    assert [row.user_id for row in board.rows] == [4, 3, 2, 1]
    assert [row.rank for row in board.rows] == [1, 2, 3, 4]


async def test_participants_without_attempts_are_absent(session):
    await add_participant(session, 1, "Активный", attempts=2, correct=1, points=1)
    await add_participant(session, 2, "Молчун", attempts=0, correct=0, points=0)

    board = await StatsService(session).leaderboard(PERIOD_TODAY, day=DAY)

    assert [row.user_id for row in board.rows] == [1]


async def test_empty_period_gives_an_empty_table(session):
    await UserService(session).register(1, "Иван", now=MOMENT)

    board = await StatsService(session).leaderboard(PERIOD_TODAY, day=DAY)

    assert board.rows == ()
    assert board.self_row is None


async def test_row_count_is_limited_by_the_setting(session):
    await SettingsService(session).set_leaderboard_rows(3)
    for index in range(1, 6):
        await add_participant(
            session, index, f"№{index}", attempts=10, correct=index, points=index
        )

    board = await StatsService(session).leaderboard(PERIOD_TODAY, day=DAY)

    assert len(board.rows) == 3
    assert [row.user_id for row in board.rows] == [5, 4, 3]


async def test_viewer_outside_the_top_gets_their_own_row(session):
    await SettingsService(session).set_leaderboard_rows(3)
    for index in range(1, 6):
        await add_participant(
            session, index, f"№{index}", attempts=10, correct=index, points=index
        )

    board = await StatsService(session).leaderboard(PERIOD_TODAY, day=DAY, viewer_id=1)

    assert board.self_row is not None
    assert (board.self_row.rank, board.self_row.user_id) == (5, 1)


async def test_viewer_inside_the_top_gets_no_extra_row(session):
    await SettingsService(session).set_leaderboard_rows(3)
    for index in range(1, 6):
        await add_participant(
            session, index, f"№{index}", attempts=10, correct=index, points=index
        )

    board = await StatsService(session).leaderboard(PERIOD_TODAY, day=DAY, viewer_id=5)

    assert board.self_row is None


async def test_period_switch_uses_the_other_set_of_numbers(session):
    await UserService(session).register(1, "Иван", now=MOMENT)
    session.add(UserDailyStats(user_id=1, quiz_date=DAY, attempts=1, correct=1, points=1))
    session.add(UserTotalStats(user_id=1, attempts=30, correct=25, points=25))
    await session.flush()

    stats = StatsService(session)
    today = await stats.leaderboard(PERIOD_TODAY, day=DAY)
    total = await stats.leaderboard(PERIOD_TOTAL)

    assert today.rows[0].stats.points == 1
    assert total.rows[0].stats.points == 25


# --- пересчёт ------------------------------------------------------------


async def test_recalc_restores_broken_aggregates(session):
    from app.models import Answer, AnswerSource
    from app.services.stats.scoring import ScoringService
    from tests.conftest import make_question

    session.add_all([make_question("dev.ch08.001"), make_question("dev.ch08.002")])
    user = await UserService(session).register(7, "Иван", now=MOMENT)
    await session.flush()

    service = ScoringService(session)
    await service.record_answer(
        user, "dev.ch08.001", is_correct=True, source=AnswerSource.GROUP,
        poll_id="p1", now=MOMENT,
    )
    await service.record_answer(
        user, "dev.ch08.002", is_correct=False, source=AnswerSource.GROUP,
        poll_id="p2", now=MOMENT,
    )

    # портим агрегаты
    total = await session.get(UserTotalStats, 7)
    total.attempts, total.correct, total.points = 99, 99, 99
    await session.flush()

    report = await recalculate_stats(session)

    assert (report.daily_rows, report.total_rows) == (1, 1)
    restored = await StatsService(session).total(7)
    assert (restored.attempts, restored.correct, restored.points) == (2, 1, 1)
    assert isinstance(await session.scalar(select(Answer)), Answer)


async def test_recalc_ignores_answers_marked_as_not_counted(session):
    from app.models import Answer, AnswerSource, LimitMode
    from app.services.stats.scoring import ScoringService
    from tests.conftest import make_question

    session.add(make_question("dev.ch08.001"))
    await UserService(session).register(7, "Иван", now=MOMENT)
    await SettingsService(session).set_limit_mode(LimitMode.DISABLED_FOR_ADMINS)
    admin = await UserService(session).grant_admin(7)
    await session.flush()

    await ScoringService(session).record_answer(
        admin, "dev.ch08.001", is_correct=True, source=AnswerSource.PRIVATE, now=MOMENT
    )

    report = await recalculate_stats(session)

    assert (report.daily_rows, report.total_rows) == (0, 0)
    stored = await session.scalar(select(Answer))
    assert stored.counted is False
