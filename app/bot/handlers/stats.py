"""Личная карточка статистики и таблица результатов."""

from __future__ import annotations

from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import replies, texts
from app.bot.callbacks import LeaderboardCallback
from app.bot.keyboards.common import back_to_menu, leaderboard_switch
from app.bot.routers import private_user
from app.core.time import quiz_date, utc_now
from app.models import User
from app.repositories.sessions import SessionRepository
from app.services.settings import SettingsService
from app.services.stats.reading import (
    PERIOD_TODAY,
    Leaderboard,
    StatsService,
)
from app.services.stats.reading import StatsLine as Line


async def render_stats_card(session: AsyncSession, user: User) -> str:
    """Собрать карточку статистики участника."""
    settings = await SettingsService(session).get()
    day = quiz_date(utc_now(), settings.timezone)
    service = StatsService(session)

    daily = await service.daily(user.id, day)
    total = await service.total(user.id)
    daily_rank = await service.rank(user.id, PERIOD_TODAY, day)
    total_rank = await service.rank(user.id, "total")
    daily_total = await service.participants(PERIOD_TODAY, day)
    total_total = await service.participants("total")

    card = texts.STATS_CARD.format(
        daily_attempts=daily.attempts,
        daily_correct=daily.correct,
        daily_points=daily.points,
        daily_accuracy=texts.accuracy(daily.correct, daily.attempts),
        daily_rank=_place(daily_rank, daily_total),
        total_attempts=total.attempts,
        total_correct=total.correct,
        total_points=total.points,
        total_accuracy=texts.accuracy(total.correct, total.attempts),
        total_rank=_place(total_rank, total_total),
    )
    if total.attempts == 0:
        card += texts.STATS_NEWCOMER

    session_line = await _active_session_line(session, user.id)
    if session_line:
        card += session_line
    return card


def _place(rank: int | None, total: int) -> str:
    """Место с числом участников; без места — прочерк без «из N»."""
    if rank is None:
        return texts.RANK_UNDEFINED
    return texts.STATS_PLACE.format(rank=rank, total=total)


async def _active_session_line(session: AsyncSession, user_id: int) -> str:
    """Строка о текущей сессии, если она идёт."""
    active = await SessionRepository(session).active_for(user_id)
    if active is None:
        return ""
    answered = sum(1 for item in active.questions if item.answered)
    correct = sum(1 for item in active.questions if item.is_correct)
    return texts.STATS_SESSION_LINE.format(correct=correct, answered=answered)


def render_leaderboard(board: Leaderboard) -> str:
    """Собрать текст таблицы результатов."""
    title = (
        texts.LEADERBOARD_TODAY_TITLE
        if board.period == PERIOD_TODAY
        else texts.LEADERBOARD_TOTAL_TITLE
    )
    if not board.rows:
        empty = (
            texts.LEADERBOARD_EMPTY_TODAY
            if board.period == PERIOD_TODAY
            else texts.LEADERBOARD_EMPTY_TOTAL
        )
        return f"{title}\n\n{empty}"

    lines = [title, ""]
    lines.extend(_row_text(row.rank, row.name, row.stats) for row in board.rows)
    text = "\n".join(lines)

    if board.self_row is not None:
        text += texts.LEADERBOARD_SELF_ROW.format(
            rank=texts.rank_label(board.self_row.rank),
            name=board.self_row.name,
            points=board.self_row.stats.points,
            accuracy=texts.accuracy(
                board.self_row.stats.correct, board.self_row.stats.attempts
            ),
        )
    return text


def _row_text(rank: int, name: str, stats: Line) -> str:
    return texts.LEADERBOARD_ROW.format(
        rank=texts.rank_label(rank),
        name=name,
        points=stats.points,
        accuracy=texts.accuracy(stats.correct, stats.attempts),
    )


async def build_leaderboard(
    session: AsyncSession, period: str, viewer_id: int
) -> Leaderboard:
    settings = await SettingsService(session).get()
    day = quiz_date(utc_now(), settings.timezone) if period == PERIOD_TODAY else None
    return await StatsService(session).leaderboard(
        period, day=day, viewer_id=viewer_id
    )


@private_user.message(Command("stats"))
async def handle_stats(message: Message, session: AsyncSession, user: User) -> None:
    await replies.show(
        message, session, user, await render_stats_card(session, user), back_to_menu()
    )


@private_user.message(Command("top"))
async def handle_top(message: Message, session: AsyncSession, user: User) -> None:
    board = await build_leaderboard(session, PERIOD_TODAY, user.id)
    await replies.show(
        message,
        session,
        user,
        render_leaderboard(board),
        leaderboard_switch(PERIOD_TODAY),
    )


@private_user.callback_query(LeaderboardCallback.filter())
async def handle_period_switch(
    query: CallbackQuery,
    callback_data: LeaderboardCallback,
    session: AsyncSession,
    user: User,
) -> None:
    """Переключение периода пересчитывает таблицу по нужному набору показателей."""
    board = await build_leaderboard(session, callback_data.period, user.id)
    await replies.show(
        query,
        session,
        user,
        render_leaderboard(board),
        leaderboard_switch(callback_data.period),
    )
    await query.answer()
