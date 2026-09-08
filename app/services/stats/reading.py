"""Чтение статистики: карточка участника и таблица результатов."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserDailyStats, UserTotalStats
from app.services.settings import SettingsService

PERIOD_TODAY = "today"
PERIOD_TOTAL = "total"


@dataclass(frozen=True, slots=True)
class StatsLine:
    """Набор показателей за период."""

    attempts: int
    correct: int
    points: int

    @property
    def accuracy(self) -> float | None:
        """Доля верных ответов; при нуле попыток — отсутствует, а не ноль."""
        if self.attempts <= 0:
            return None
        return self.correct / self.attempts


EMPTY = StatsLine(0, 0, 0)


@dataclass(frozen=True, slots=True)
class LeaderboardRow:
    rank: int
    user_id: int
    name: str
    stats: StatsLine


@dataclass(frozen=True, slots=True)
class Leaderboard:
    period: str
    rows: tuple[LeaderboardRow, ...]
    #: Строка запросившего, если он не попал в показанные верхние строки.
    self_row: LeaderboardRow | None


class StatsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._settings = SettingsService(session)

    async def daily(self, user_id: int, day: date) -> StatsLine:
        row = await self._session.scalar(
            select(UserDailyStats).where(
                UserDailyStats.user_id == user_id, UserDailyStats.quiz_date == day
            )
        )
        return _line(row)

    async def total(self, user_id: int) -> StatsLine:
        return _line(await self._session.get(UserTotalStats, user_id))

    async def rank(self, user_id: int, period: str, day: date | None = None) -> int | None:
        """Место участника; `None`, если попыток в периоде не было."""
        ordered = await self._ordered_rows(period, day)
        for index, (row_user_id, _name, _stats) in enumerate(ordered, start=1):
            if row_user_id == user_id:
                return index
        return None

    async def participants(self, period: str, day: date | None = None) -> int:
        """Сколько участников имеют попытки в периоде — знаменатель места."""
        return len(await self._ordered_rows(period, day))

    async def leaderboard(
        self,
        period: str,
        *,
        day: date | None = None,
        viewer_id: int | None = None,
    ) -> Leaderboard:
        """Таблица результатов с ограничением по числу строк.

        Сортировка — по баллам, затем по точности, затем по меньшему числу
        попыток. Участники без попыток в период не попадают.
        """
        settings = await self._settings.get()
        ordered = await self._ordered_rows(period, day)

        rows = tuple(
            LeaderboardRow(rank=index, user_id=user_id, name=name, stats=stats)
            for index, (user_id, name, stats) in enumerate(ordered, start=1)
        )
        shown = rows[: settings.leaderboard_rows]

        self_row = None
        if viewer_id is not None and all(row.user_id != viewer_id for row in shown):
            self_row = next((row for row in rows if row.user_id == viewer_id), None)

        return Leaderboard(period=period, rows=shown, self_row=self_row)

    async def _ordered_rows(
        self, period: str, day: date | None
    ) -> list[tuple[int, str, StatsLine]]:
        statement = self._period_query(period, day)
        result = await self._session.execute(statement)
        rows = [
            (user_id, name, StatsLine(attempts, correct, points))
            for user_id, name, attempts, correct, points in result
            if attempts > 0
        ]
        rows.sort(key=lambda item: (-item[2].points, -(item[2].accuracy or 0), item[2].attempts))
        return rows

    def _period_query(
        self, period: str, day: date | None
    ) -> Select[tuple[int, str, int, int, int]]:
        if period == PERIOD_TODAY:
            if day is None:
                raise ValueError("Для периода «сегодня» нужна дата викторины")
            return (
                select(
                    User.id,
                    User.display_name,
                    UserDailyStats.attempts,
                    UserDailyStats.correct,
                    UserDailyStats.points,
                )
                .join(UserDailyStats, UserDailyStats.user_id == User.id)
                .where(UserDailyStats.quiz_date == day)
            )
        return (
            select(
                User.id,
                User.display_name,
                UserTotalStats.attempts,
                UserTotalStats.correct,
                UserTotalStats.points,
            ).join(UserTotalStats, UserTotalStats.user_id == User.id)
        )


def _line(row: UserDailyStats | UserTotalStats | None) -> StatsLine:
    if row is None:
        return EMPTY
    return StatsLine(attempts=row.attempts, correct=row.correct, points=row.points)
