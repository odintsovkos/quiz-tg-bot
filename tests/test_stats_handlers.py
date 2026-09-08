"""Отрисовка карточки статистики и таблицы результатов."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.bot.handlers.stats import (
    build_leaderboard,
    render_leaderboard,
    render_stats_card,
)
from app.models import UserDailyStats, UserTotalStats
from app.services.settings import SettingsService
from app.services.stats.reading import PERIOD_TODAY, PERIOD_TOTAL
from app.services.users import UserService

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


def today(session_settings_timezone: str = "Europe/Moscow") -> date:
    from app.core.time import quiz_date, utc_now

    return quiz_date(utc_now(), session_settings_timezone)


async def participant(session, user_id, name, *, attempts, correct, points):
    await UserService(session).register(user_id, name, now=MOMENT)
    session.add(
        UserDailyStats(
            user_id=user_id,
            quiz_date=today(),
            attempts=attempts,
            correct=correct,
            points=points,
        )
    )
    session.add(
        UserTotalStats(user_id=user_id, attempts=attempts, correct=correct, points=points)
    )
    await session.flush()
    return await UserService(session).get(user_id)


async def test_newcomer_card_shows_zeroes_and_an_invitation(session):
    user = await UserService(session).register(7, "Иван", now=MOMENT)

    card = await render_stats_card(session, user)

    assert "❓ Попыток: 0" in card
    assert "—" in card  # точность и место не определены
    assert "/quiz" in card


async def test_card_shows_both_periods_and_ranks(session):
    user = await participant(session, 7, "Иван", attempts=4, correct=3, points=3)

    card = await render_stats_card(session, user)

    assert "❓ Попыток: 4" in card
    assert "75%" in card
    assert "🥇 Место: 1 из 1" in card


async def test_leaderboard_today_is_sorted_descending(session):
    await participant(session, 1, "Первый", attempts=10, correct=2, points=2)
    viewer = await participant(session, 2, "Второй", attempts=10, correct=8, points=8)

    board = await build_leaderboard(session, PERIOD_TODAY, viewer.id)
    text = render_leaderboard(board)

    assert text.index("Второй") < text.index("Первый")
    assert "за сегодня" in text.lower()


async def test_period_switch_recomputes_from_total_numbers(session):
    viewer = await UserService(session).register(7, "Иван", now=MOMENT)
    session.add(
        UserDailyStats(user_id=7, quiz_date=today(), attempts=1, correct=1, points=1)
    )
    session.add(UserTotalStats(user_id=7, attempts=40, correct=30, points=30))
    await session.flush()

    todays = render_leaderboard(await build_leaderboard(session, PERIOD_TODAY, viewer.id))
    overall = render_leaderboard(await build_leaderboard(session, PERIOD_TOTAL, viewer.id))

    assert "⭐ 1" in todays
    assert "⭐ 30" in overall
    assert "за всё время" in overall.lower()


async def test_empty_today_says_so(session):
    viewer = await UserService(session).register(7, "Иван", now=MOMENT)

    text = render_leaderboard(await build_leaderboard(session, PERIOD_TODAY, viewer.id))

    assert "ещё никто не отвечал" in text


async def test_viewer_outside_the_top_sees_their_own_row(session):
    await SettingsService(session).set_leaderboard_rows(3)
    for index in range(1, 6):
        await participant(
            session, index, f"№{index}", attempts=10, correct=index, points=index
        )

    text = render_leaderboard(await build_leaderboard(session, PERIOD_TODAY, 1))

    assert "Вы: 5. №1" in text
