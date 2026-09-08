"""Начисление баллов — единственный путь записи результата.

И групповой обработчик `poll_answer`, и личная викторина вызывают один и тот
же метод, поэтому статистика не разъезжается между режимами.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import quiz_date, utc_now
from app.models import (
    Answer,
    AnswerSource,
    LimitMode,
    User,
    UserDailyStats,
    UserRole,
    UserTotalStats,
)
from app.services.settings import SettingsService

POINTS_FOR_CORRECT = 1


@dataclass(frozen=True, slots=True)
class RecordedAnswer:
    """Итог попытки записи."""

    #: Ложь означает, что ответ по этой паре уже был записан раньше.
    accepted: bool
    #: Учтён ли ответ в агрегатах (режим лимитов и роль на момент ответа).
    counted: bool
    is_correct: bool
    points: int


def is_counted(
    role: UserRole, source: AnswerSource, limit_mode: LimitMode
) -> bool:
    """Учитывать ли ответ в дневной и общей статистике.

    Спека `scoring-and-stats`: исключение действует только в режиме
    «отключены только для администраторов» и только на личные режимы;
    групповые ответы тех же участников учитываются на общих основаниях.
    """
    if limit_mode is not LimitMode.DISABLED_FOR_ADMINS:
        return True
    if source is AnswerSource.GROUP:
        return True
    return not role.is_admin


class ScoringService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._settings = SettingsService(session)

    async def record_answer(
        self,
        user: User,
        question_id: str,
        *,
        is_correct: bool,
        source: AnswerSource,
        chat_id: int | None = None,
        poll_id: str | None = None,
        session_id: int | None = None,
        issue_id: int | None = None,
        now: datetime | None = None,
    ) -> RecordedAnswer:
        """Записать ответ и обновить агрегаты в той же транзакции.

        Идемпотентность обеспечивают уникальные индексы: повторная запись
        по той же паре («опрос и участник» либо «сессия и вопрос») упирается
        в нарушение уникальности, которое здесь перехватывается.
        """
        settings = await self._settings.get()
        moment = now or utc_now()
        counted = is_counted(user.role, source, settings.limit_mode)
        points = POINTS_FOR_CORRECT if (is_correct and counted) else 0

        answer = Answer(
            user_id=user.id,
            question_id=question_id,
            source=source,
            chat_id=chat_id,
            poll_id=poll_id,
            session_id=session_id,
            issue_id=issue_id,
            is_correct=is_correct,
            counted=counted,
            answered_at=moment,
            quiz_date=quiz_date(moment, settings.timezone),
        )

        savepoint = await self._session.begin_nested()
        try:
            self._session.add(answer)
            await self._session.flush()
        except IntegrityError:
            await savepoint.rollback()
            return RecordedAnswer(
                accepted=False, counted=False, is_correct=is_correct, points=0
            )
        await savepoint.commit()

        if counted:
            await self._bump_aggregates(
                user.id, answer.quiz_date, is_correct=is_correct, points=points
            )

        return RecordedAnswer(
            accepted=True, counted=counted, is_correct=is_correct, points=points
        )

    async def _bump_aggregates(
        self, user_id: int, day: date, *, is_correct: bool, points: int
    ) -> None:
        daily = await self._session.scalar(
            select(UserDailyStats).where(
                UserDailyStats.user_id == user_id, UserDailyStats.quiz_date == day
            )
        )
        if daily is None:
            # Значения по умолчанию SQLAlchemy проставляет при вставке,
            # а прибавлять к ним надо уже сейчас — задаём нули явно.
            daily = UserDailyStats(
                user_id=user_id, quiz_date=day, attempts=0, correct=0, points=0
            )
            self._session.add(daily)
        daily.attempts += 1
        daily.correct += int(is_correct)
        daily.points += points

        total = await self._session.get(UserTotalStats, user_id)
        if total is None:
            total = UserTotalStats(user_id=user_id, attempts=0, correct=0, points=0)
            self._session.add(total)
        total.attempts += 1
        total.correct += int(is_correct)
        total.points += points

        await self._session.flush()
