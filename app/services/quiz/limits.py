"""Дневные лимиты личных режимов.

Проверка и списание — одна операция с условием на текущее значение, а не
«прочитать, сравнить, записать»: иначе два быстрых нажатия подряд проскакивают
мимо лимита (см. `design.md`, «Лимиты, выбор тем и учёт»).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import next_midnight, quiz_date, utc_now
from app.models import LimitMode, User, UserDailyLimits, UserRole
from app.services.settings import SettingsService

KIND_QUIZ = "quiz_starts"
KIND_RANDOM = "random_questions"


@dataclass(frozen=True, slots=True)
class LimitState:
    """Остатки на сегодня и момент их обновления."""

    quiz_used: int
    quiz_limit: int
    random_used: int
    random_limit: int
    enforced: bool
    reset_at: datetime

    @property
    def quiz_left(self) -> int:
        return max(self.quiz_limit - self.quiz_used, 0)

    @property
    def random_left(self) -> int:
        return max(self.random_limit - self.random_used, 0)


@dataclass(frozen=True, slots=True)
class LimitDecision:
    """Итог попытки списания."""

    allowed: bool
    limit: int
    reset_at: datetime


def limits_apply(role: UserRole, mode: LimitMode) -> bool:
    """Действуют ли лимиты на этого участника при этом режиме."""
    if mode is LimitMode.DISABLED_FOR_ALL:
        return False
    return not (mode is LimitMode.DISABLED_FOR_ADMINS and role.is_admin)


class LimitService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._settings = SettingsService(session)

    async def state(self, user: User, *, now: datetime | None = None) -> LimitState:
        settings = await self._settings.get()
        moment = now or utc_now()
        day = quiz_date(moment, settings.timezone)
        row = await self._row(user.id, day)
        return LimitState(
            quiz_used=row.quiz_starts if row else 0,
            quiz_limit=settings.quiz_limit,
            random_used=row.random_questions if row else 0,
            random_limit=settings.random_limit,
            enforced=limits_apply(user.role, settings.limit_mode),
            reset_at=next_midnight(moment, settings.timezone),
        )

    async def consume(
        self, user: User, kind: str, *, now: datetime | None = None
    ) -> LimitDecision:
        """Проверить и списать лимит одной атомарной операцией.

        Режим лимитов читается из настроек времени выполнения, поэтому его
        смена действует на ближайший же запрос, без перезапуска бота.
        """
        settings = await self._settings.get()
        moment = now or utc_now()
        day = quiz_date(moment, settings.timezone)
        limit = (
            settings.quiz_limit if kind == KIND_QUIZ else settings.random_limit
        )
        reset_at = next_midnight(moment, settings.timezone)

        if not limits_apply(user.role, settings.limit_mode):
            return LimitDecision(allowed=True, limit=limit, reset_at=reset_at)

        await self._ensure_row(user.id, day)

        column = getattr(UserDailyLimits, kind)
        statement = (
            update(UserDailyLimits)
            .where(
                UserDailyLimits.user_id == user.id,
                UserDailyLimits.quiz_date == day,
                column < limit,
            )
            .values({kind: column + 1})
        )
        result = await self._session.execute(
            statement.execution_options(synchronize_session=False)
        )
        await self._session.flush()
        # Списание состоялось, только если UPDATE нашёл строку с остатком.
        updated = cast("CursorResult[Any]", result).rowcount
        return LimitDecision(allowed=updated == 1, limit=limit, reset_at=reset_at)

    async def _row(self, user_id: int, day: date) -> UserDailyLimits | None:
        # populate_existing — счётчик мог измениться прямым UPDATE,
        # объект в карте идентичности об этом не знает.
        row: UserDailyLimits | None = await self._session.scalar(
            select(UserDailyLimits)
            .where(
                UserDailyLimits.user_id == user_id, UserDailyLimits.quiz_date == day
            )
            .execution_options(populate_existing=True)
        )
        return row

    async def _ensure_row(self, user_id: int, day: date) -> None:
        """Создать строку расхода, не мешая параллельной попытке сделать то же."""
        statement = (
            insert(UserDailyLimits)
            .values(user_id=user_id, quiz_date=day, quiz_starts=0, random_questions=0)
            .on_conflict_do_nothing(index_elements=["user_id", "quiz_date"])
        )
        await self._session.execute(statement)
        await self._session.flush()
