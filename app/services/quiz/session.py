"""Личные режимы: сессионная викторина и одиночный случайный вопрос.

Оба пишут результат через `ScoringService`, поэтому статистика у них общая.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.models import (
    AnswerSource,
    Question,
    QuizSession,
    RandomQuestionIssue,
    SessionQuestion,
    SessionStatus,
    User,
)
from app.repositories.questions import QuestionRepository
from app.repositories.sessions import SessionRepository
from app.services.quiz.limits import KIND_QUIZ, KIND_RANDOM, LimitDecision, LimitService
from app.services.quiz.topics import TopicPreferenceService
from app.services.settings import SettingsService
from app.services.stats.scoring import RecordedAnswer, ScoringService


@dataclass(frozen=True, slots=True)
class StartOutcome:
    """Итог попытки начать викторину."""

    session: QuizSession | None = None
    #: Уже идущая сессия, если участник пытается начать вторую.
    active: QuizSession | None = None
    #: Отказ по дневному лимиту.
    refused: LimitDecision | None = None
    #: В применяемых темах нет активных вопросов — лимит не расходуется.
    no_questions: bool = False
    #: Вопросов меньше, чем размер сессии.
    shortened_to: int | None = None
    #: Сохранённый выбор тем оказался неприменим.
    topics_fell_back: bool = False


@dataclass(frozen=True, slots=True)
class RandomOutcome:
    """Итог выдачи одиночного случайного вопроса."""

    issue: RandomQuestionIssue | None = None
    question: Question | None = None
    refused: LimitDecision | None = None
    no_questions: bool = False
    topics_fell_back: bool = False


@dataclass(frozen=True, slots=True)
class SessionProgress:
    """Счёт по сессии."""

    answered: int
    correct: int
    total: int
    points: int

    @property
    def finished(self) -> bool:
        return self.answered >= self.total


class QuizSessionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._questions = QuestionRepository(session)
        self._sessions = SessionRepository(session)
        self._topics = TopicPreferenceService(session)
        self._limits = LimitService(session)
        self._settings = SettingsService(session)
        self._scoring = ScoringService(session)

    # --- сессия ----------------------------------------------------------

    async def start(
        self, user: User, *, restart: bool = False, now: datetime | None = None
    ) -> StartOutcome:
        """Начать сессию.

        Порядок важен: сначала проверяется наличие вопросов, и только потом
        списывается лимит — спека требует не расходовать лимит, когда вопросов
        нет вовсе.
        """
        moment = now or utc_now()
        await self.close_if_abandoned(user.id, now=moment)

        active = await self._sessions.active_for(user.id)
        if active is not None:
            if not restart:
                return StartOutcome(active=active)
            await self._sessions.close(active, SessionStatus.ABORTED, moment)

        settings = await self._settings.get()
        applied = await self._topics.applied(user.id)
        pool = await self._questions.pick_random_active(
            applied.categories or None, limit=settings.session_size
        )
        if not pool:
            return StartOutcome(no_questions=True, topics_fell_back=applied.fell_back)

        decision = await self._limits.consume(user, KIND_QUIZ, now=moment)
        if not decision.allowed:
            return StartOutcome(refused=decision)

        quiz = await self._sessions.create(
            user.id, [question.id for question in pool], moment
        )
        return StartOutcome(
            session=quiz,
            shortened_to=len(pool) if len(pool) < settings.session_size else None,
            topics_fell_back=applied.fell_back,
        )

    async def current_question(self, quiz: QuizSession) -> SessionQuestion | None:
        """Первый неотвеченный вопрос сессии — вопросы выдаются по одному."""
        for item in quiz.questions:
            if not item.answered:
                return item
        return None

    async def answer(
        self,
        user: User,
        quiz: QuizSession,
        position: int,
        option_index: int,
        *,
        now: datetime | None = None,
    ) -> tuple[RecordedAnswer | None, Question | None]:
        """Принять ответ на вопрос сессии.

        Ровно один ответ на вопрос: повторное нажатие по уже отвеченному
        возвращает `None` и статистику не меняет.
        """
        moment = now or utc_now()
        item = next(
            (candidate for candidate in quiz.questions if candidate.position == position),
            None,
        )
        if item is None or item.answered:
            return None, None

        question = await self._questions.get(item.question_id)
        if question is None:  # вопрос удалили между выдачей и ответом
            return None, None

        is_correct = option_index == question.correct_index
        recorded = await self._scoring.record_answer(
            user,
            question.id,
            is_correct=is_correct,
            source=AnswerSource.PRIVATE,
            session_id=quiz.id,
            now=moment,
        )
        if not recorded.accepted:
            return None, question

        item.answered = True
        item.is_correct = is_correct
        item.chosen_option = option_index
        quiz.last_activity_at = moment
        await self._session.flush()

        if await self.current_question(quiz) is None:
            await self._sessions.close(quiz, SessionStatus.COMPLETED, moment)

        return recorded, question

    async def progress(self, quiz: QuizSession) -> SessionProgress:
        answered = sum(1 for item in quiz.questions if item.answered)
        correct = sum(1 for item in quiz.questions if item.is_correct)
        return SessionProgress(
            answered=answered,
            correct=correct,
            total=quiz.total_questions,
            points=correct,
        )

    async def abort(self, quiz: QuizSession, *, now: datetime | None = None) -> None:
        """Прервать сессию досрочно; данные до прерывания остаются в статистике."""
        await self._sessions.close(quiz, SessionStatus.ABORTED, now or utc_now())

    async def close_if_abandoned(
        self, user_id: int, *, now: datetime | None = None
    ) -> QuizSession | None:
        """Закрыть сессию, заброшенную дольше установленного времени."""
        moment = now or utc_now()
        active = await self._sessions.active_for(user_id)
        if active is None:
            return None

        settings = await self._settings.get()
        deadline = active.last_activity_at + timedelta(
            minutes=settings.session_timeout_minutes
        )
        if moment < deadline:
            return None
        return await self._sessions.close(active, SessionStatus.EXPIRED, moment)

    # --- одиночный случайный вопрос --------------------------------------

    async def issue_random(
        self, user: User, *, now: datetime | None = None
    ) -> RandomOutcome:
        """Выдать один случайный вопрос, не трогая прогресс сессии."""
        moment = now or utc_now()
        applied = await self._topics.applied(user.id)
        question = await self._questions.pick_random_unanswered(
            user.id, applied.categories or None
        )
        if question is None:
            return RandomOutcome(
                no_questions=True, topics_fell_back=applied.fell_back
            )

        decision = await self._limits.consume(user, KIND_RANDOM, now=moment)
        if not decision.allowed:
            return RandomOutcome(refused=decision)

        issue = await self._sessions.add_issue(user.id, question.id, moment)
        return RandomOutcome(
            issue=issue, question=question, topics_fell_back=applied.fell_back
        )

    async def answer_random(
        self,
        user: User,
        issue: RandomQuestionIssue,
        option_index: int,
        *,
        now: datetime | None = None,
    ) -> tuple[RecordedAnswer | None, Question | None]:
        """Принять ответ на выданный случайный вопрос."""
        if issue.answered:
            return None, None

        question = await self._questions.get(issue.question_id)
        if question is None:
            return None, None

        is_correct = option_index == question.correct_index
        recorded = await self._scoring.record_answer(
            user,
            question.id,
            is_correct=is_correct,
            source=AnswerSource.PRIVATE,
            issue_id=issue.id,
            now=now or utc_now(),
        )
        if not recorded.accepted:
            return None, question

        issue.answered = True
        issue.is_correct = is_correct
        await self._session.flush()
        return recorded, question
