"""Пересчёт агрегатов статистики по таблице ответов.

Агрегаты — производные и восстановимые: таблица ответов остаётся источником
истины, а эта команда — страховка на случай, когда агрегаты разошлись
(см. `design.md`, «Одна запись ответа на оба режима»).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Answer, UserDailyStats, UserTotalStats


@dataclass(slots=True)
class RecalcReport:
    daily_rows: int = 0
    total_rows: int = 0

    def render(self) -> str:
        return (
            f"Пересчитано: дневных строк {self.daily_rows}, "
            f"строк за всё время {self.total_rows}."
        )


async def recalculate_stats(session: AsyncSession) -> RecalcReport:
    """Собрать агрегаты заново по учтённым ответам."""
    await session.execute(delete(UserDailyStats))
    await session.execute(delete(UserTotalStats))

    counted = Answer.counted.is_(True)
    correct_sum = func.sum(case((Answer.is_correct.is_(True), 1), else_=0))

    daily = await session.execute(
        select(
            Answer.user_id,
            Answer.quiz_date,
            func.count().label("attempts"),
            correct_sum.label("correct"),
        )
        .where(counted)
        .group_by(Answer.user_id, Answer.quiz_date)
    )
    report = RecalcReport()
    for user_id, quiz_date, attempts, correct in daily:
        session.add(
            UserDailyStats(
                user_id=user_id,
                quiz_date=quiz_date,
                attempts=int(attempts),
                correct=int(correct or 0),
                points=int(correct or 0),
            )
        )
        report.daily_rows += 1

    totals = await session.execute(
        select(Answer.user_id, func.count().label("attempts"), correct_sum.label("correct"))
        .where(counted)
        .group_by(Answer.user_id)
    )
    for user_id, attempts, correct in totals:
        session.add(
            UserTotalStats(
                user_id=user_id,
                attempts=int(attempts),
                correct=int(correct or 0),
                points=int(correct or 0),
            )
        )
        report.total_rows += 1

    await session.flush()
    return report
