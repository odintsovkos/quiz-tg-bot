"""Сервисы кабинета администратора: банк вопросов и сводная статистика."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import quiz_date, utc_now
from app.models import Answer, Question, User
from app.repositories.questions import QuestionRepository
from app.services.content.validation import (
    OptionDraft,
    QuestionDraft,
    ValidationResult,
    validate_question,
)
from app.services.settings import SettingsService

PAGE_SIZE = 5


class QuestionValidationError(ValueError):
    """Правка не прошла валидацию — прежняя версия вопроса сохраняется."""

    def __init__(self, result: ValidationResult) -> None:
        self.result = result
        super().__init__("; ".join(issue.message for issue in result.issues))


@dataclass(frozen=True, slots=True)
class QuestionPage:
    items: tuple[Question, ...]
    page: int
    pages: int
    total: int


@dataclass(frozen=True, slots=True)
class Summary:
    users: int
    active_today: int
    answers_today: int
    answers_total: int
    correct_total: int
    questions_total: int
    questions_active: int

    @property
    def questions_inactive(self) -> int:
        return self.questions_total - self.questions_active


def draft_from(question: Question) -> QuestionDraft:
    """Черновик из сохранённого вопроса — вход того же валидатора, что импорт."""
    return QuestionDraft(
        id=question.id,
        text=question.text,
        category=question.category,
        difficulty=str(question.difficulty),
        options=tuple(
            OptionDraft(text=option.text, is_correct=option.is_correct)
            for option in question.options
        ),
        explanation=question.explanation,
        reference=question.reference,
        is_active=question.is_active,
        source_file=question.source_file,
    )


class AdminQuestionService:
    """Просмотр и правка банка из кабинета.

    Правки проходят тот же валидатор, что импорт из файлов, — поэтому оба пути
    ведут себя одинаково по построению.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._questions = QuestionRepository(session)

    def _filtered(
        self, category: str | None, is_active: bool | None
    ) -> Select[tuple[Question]]:
        statement = select(Question)
        if category:
            statement = statement.where(Question.category == category)
        if is_active is not None:
            statement = statement.where(Question.is_active.is_(is_active))
        return statement

    async def page(
        self,
        page: int = 0,
        *,
        category: str | None = None,
        is_active: bool | None = None,
    ) -> QuestionPage:
        base = self._filtered(category, is_active)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(base.subquery())
            )
            or 0
        )
        pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
        page = max(0, min(page, pages - 1))
        items = await self._session.scalars(
            base.order_by(Question.id).offset(page * PAGE_SIZE).limit(PAGE_SIZE)
        )
        return QuestionPage(
            items=tuple(items), page=page, pages=pages, total=total
        )

    async def get(self, question_id: str) -> Question | None:
        return await self._questions.get(question_id)

    async def save(
        self,
        draft: QuestionDraft,
        *,
        editor_id: int,
        now: datetime | None = None,
    ) -> Question:
        """Создать или обновить вопрос, зафиксировав автора и время правки."""
        result = validate_question(draft)
        if not result.ok:
            raise QuestionValidationError(result)

        moment = now or utc_now()
        question, _ = await self._questions.upsert(
            draft, updated_by=editor_id, updated_at=moment
        )
        # Автор и время фиксируются и тогда, когда поля не изменились:
        # спека требует знать, кто и когда трогал вопрос.
        question.updated_by = editor_id
        question.updated_at = moment
        await self._session.flush()
        return question

    async def set_active(
        self, question: Question, is_active: bool, *, editor_id: int
    ) -> Question:
        question.is_active = is_active
        question.updated_by = editor_id
        question.updated_at = utc_now()
        await self._session.flush()
        return question

    async def categories(self) -> list[str]:
        return await self._questions.list_categories(only_active=False)


class SummaryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._settings = SettingsService(session)

    async def build(self, *, now: datetime | None = None) -> Summary:
        settings = await self._settings.get()
        day: date = quiz_date(now or utc_now(), settings.timezone)

        users = int(
            await self._session.scalar(select(func.count()).select_from(User)) or 0
        )
        active_today = int(
            await self._session.scalar(
                select(func.count(func.distinct(Answer.user_id))).where(
                    Answer.quiz_date == day
                )
            )
            or 0
        )
        answers_today = int(
            await self._session.scalar(
                select(func.count()).select_from(Answer).where(Answer.quiz_date == day)
            )
            or 0
        )
        answers_total = int(
            await self._session.scalar(select(func.count()).select_from(Answer)) or 0
        )
        correct_total = int(
            await self._session.scalar(
                select(func.sum(case((Answer.is_correct.is_(True), 1), else_=0)))
            )
            or 0
        )
        questions_total = int(
            await self._session.scalar(select(func.count()).select_from(Question)) or 0
        )
        questions_active = int(
            await self._session.scalar(
                select(func.count())
                .select_from(Question)
                .where(Question.is_active.is_(True))
            )
            or 0
        )
        return Summary(
            users=users,
            active_today=active_today,
            answers_today=answers_today,
            answers_total=answers_total,
            correct_total=correct_total,
            questions_total=questions_total,
            questions_active=questions_active,
        )


