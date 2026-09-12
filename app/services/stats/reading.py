"""Чтение статистики: карточка участника и таблица результатов."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Answer, Difficulty, User, UserDailyStats, UserTotalStats
from app.services.settings import SettingsService

PERIOD_TODAY = "today"
PERIOD_TOTAL = "total"

#: Сколько учтённых ответов нужно, чтобы доля верных что-то говорила о вопросе.
#: По трём-четырём ответам доля — шум, и выдавать её за сложность нельзя.
DIFFICULTY_SAMPLE_THRESHOLD = 20

#: Границы уровней по доле верных ответов.
EASY_SHARE_FROM = 0.7
MEDIUM_SHARE_FROM = 0.4


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
class QuestionStats:
    """Ответы на один вопрос банка: сколько учтено и сколько из них верных."""

    answers: int
    correct: int

    @property
    def share(self) -> float | None:
        """Доля верных; при нуле ответов — отсутствует, а не ноль."""
        if self.answers <= 0:
            return None
        return self.correct / self.answers

    @property
    def is_reliable(self) -> bool:
        """Набралось ли ответов, чтобы доля что-то значила."""
        return self.answers >= DIFFICULTY_SAMPLE_THRESHOLD


EMPTY_QUESTION_STATS = QuestionStats(0, 0)


@dataclass(frozen=True, slots=True)
class QuestionDifficulty:
    """Сложность вопроса в одном из трёх состояний.

    Состояния различимы снаружи: измеренная (`measured` и `share` заданы),
    только авторская (`authored` задан, `share` — нет) и неизвестная (ничего).
    Подставлять уровень по умолчанию нельзя: участник не отличил бы его
    от настоящего.
    """

    authored: Difficulty | None
    measured: Difficulty | None
    share: float | None
    answers: int

    @property
    def shown(self) -> Difficulty | None:
        """Уровень, который идёт на экран: измеренный, иначе авторский."""
        return self.measured or self.authored

    @property
    def is_measured(self) -> bool:
        return self.measured is not None

    @property
    def percent(self) -> int | None:
        """Доля верных в процентах — одна на все экраны, чтобы не разошлись.

        Округление арифметическое: встроенный `round` банковский и превратил
        бы 22,5% в 22, а участник ждёт 23.
        """
        if self.share is None:
            return None
        return int(self.share * 100 + 0.5)


def level_of_share(share: float) -> Difficulty:
    """Уровень по доле верных ответов."""
    if share >= EASY_SHARE_FROM:
        return Difficulty.EASY
    if share >= MEDIUM_SHARE_FROM:
        return Difficulty.MEDIUM
    return Difficulty.HARD


def difficulty_of(
    stats: QuestionStats, authored: Difficulty | None
) -> QuestionDifficulty:
    """Свести статистику вопроса и авторскую оценку в одно из трёх состояний."""
    share = stats.share
    if stats.is_reliable and share is not None:
        return QuestionDifficulty(
            authored=authored,
            measured=level_of_share(share),
            share=share,
            answers=stats.answers,
        )
    return QuestionDifficulty(
        authored=authored, measured=None, share=None, answers=stats.answers
    )


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

    async def question(self, question_id: str) -> QuestionStats:
        """Учтённые ответы на вопрос и верные среди них — одним агрегатом.

        Считается по `answers`, а не по отдельной таблице-счётчику: экран
        показывает один вопрос, поэтому это один запрос по индексу
        `ix_answers_question_id`. Неучтённые ответы (режим без лимитов для
        администраторов) в счёт не идут — иначе прогоны администратора по
        своему же банку искажали бы картину.
        """
        row = (
            await self._session.execute(
                select(
                    func.count(Answer.id),
                    func.coalesce(
                        func.sum(case((Answer.is_correct, 1), else_=0)), 0
                    ),
                ).where(
                    Answer.question_id == question_id,
                    Answer.counted.is_(True),
                )
            )
        ).one()
        return QuestionStats(answers=int(row[0]), correct=int(row[1]))

    async def question_difficulty(
        self, question_id: str, authored: Difficulty | None
    ) -> QuestionDifficulty:
        """Сложность вопроса для показа: измеренная, авторская или никакая."""
        return difficulty_of(await self.question(question_id), authored)

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
