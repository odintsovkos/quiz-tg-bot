"""Доступ к банку вопросов — единственное место с запросами по нему."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Answer, AskedQuestion, Question, QuestionOption
from app.services.content.validation import QuestionDraft


class QuestionRepository:
    """Чтение и запись вопросов и их вариантов."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, question_id: str) -> Question | None:
        return await self._session.get(Question, question_id)

    async def all_ids(self) -> set[str]:
        rows = await self._session.scalars(select(Question.id))
        return set(rows)

    async def list_categories(self, *, only_active: bool = True) -> list[str]:
        """Категории, в которых есть вопросы (по умолчанию — активные)."""
        statement = select(Question.category).distinct().order_by(Question.category)
        if only_active:
            statement = statement.where(Question.is_active.is_(True))
        return list(await self._session.scalars(statement))

    async def count(self, *, is_active: bool | None = None) -> int:
        statement = select(func.count()).select_from(Question)
        if is_active is not None:
            statement = statement.where(Question.is_active.is_(is_active))
        return int(await self._session.scalar(statement) or 0)

    def _active_in_categories(self, categories: list[str] | None) -> Select[tuple[Question]]:
        statement = select(Question).where(Question.is_active.is_(True))
        if categories:
            statement = statement.where(Question.category.in_(categories))
        return statement

    async def count_active(self, categories: list[str] | None = None) -> int:
        statement = select(func.count()).select_from(
            self._active_in_categories(categories).subquery()
        )
        return int(await self._session.scalar(statement) or 0)

    async def pick_random_active(
        self,
        categories: list[str] | None = None,
        *,
        limit: int = 1,
        exclude_ids: set[str] | None = None,
    ) -> list[Question]:
        """Случайные активные вопросы подходящих категорий."""
        statement = self._active_in_categories(categories)
        if exclude_ids:
            statement = statement.where(Question.id.not_in(exclude_ids))
        statement = statement.order_by(func.random()).limit(limit)
        return list(await self._session.scalars(statement))

    async def pick_random_unanswered(
        self,
        user_id: int,
        categories: list[str] | None = None,
    ) -> Question | None:
        """Случайный вопрос, на который участник ещё не отвечал.

        Спека `private-quiz`: предпочтение неотвеченных; когда они кончились,
        ограничение снимается — отдельная таблица «показанных» не нужна,
        история ответов уже её содержит.
        """
        answered = select(Answer.question_id).where(Answer.user_id == user_id)
        statement = (
            self._active_in_categories(categories)
            .where(Question.id.not_in(answered))
            .order_by(func.random())
            .limit(1)
        )
        question: Question | None = await self._session.scalar(statement)
        if question is not None:
            return question
        fallback = self._active_in_categories(categories).order_by(func.random()).limit(1)
        last_resort: Question | None = await self._session.scalar(fallback)
        return last_resort

    async def pick_for_chat(
        self,
        chat_id: int,
        round_number: int,
        categories: list[str] | None = None,
    ) -> Question | None:
        """Вопрос для чата вне текущего круга.

        Спека `group-quiz`: пока в круге остаются не заданные вопросы,
        берём случайный из них; выбор нового круга — забота вызывающего.
        """
        asked = select(AskedQuestion.question_id).where(
            AskedQuestion.chat_id == chat_id,
            AskedQuestion.round_number == round_number,
        )
        statement = (
            self._active_in_categories(categories)
            .where(Question.id.not_in(asked))
            .order_by(func.random())
            .limit(1)
        )
        found: Question | None = await self._session.scalar(statement)
        return found

    async def pick_oldest_asked_for_chat(
        self,
        chat_id: int,
        categories: list[str] | None = None,
    ) -> Question | None:
        """Вопрос, задававшийся в этом чате дольше всех остальных.

        Нужен при переходе на новый круг: спека требует отдавать предпочтение
        тем, что задавались раньше.
        """
        last_asked = (
            select(
                AskedQuestion.question_id.label("question_id"),
                func.max(AskedQuestion.asked_at).label("asked_at"),
            )
            .where(AskedQuestion.chat_id == chat_id)
            .group_by(AskedQuestion.question_id)
            .subquery()
        )
        statement = (
            self._active_in_categories(categories)
            .join(last_asked, last_asked.c.question_id == Question.id, isouter=True)
            .order_by(last_asked.c.asked_at.asc().nulls_first())
            .limit(1)
        )
        oldest: Question | None = await self._session.scalar(statement)
        return oldest

    async def upsert(
        self,
        draft: QuestionDraft,
        *,
        updated_by: int | None = None,
        updated_at: datetime | None = None,
    ) -> tuple[Question, bool]:
        """Вставить или обновить вопрос по идентификатору.

        Возвращает вопрос и признак того, что состав полей изменился —
        по нему импорт отличает «обновлено» от «без изменений».
        """
        existing = await self.get(draft.id)
        if existing is None:
            question = Question(
                id=draft.id,
                text=draft.text,
                category=draft.category,
                difficulty=draft.difficulty,
                is_active=draft.is_active,
                explanation=draft.explanation,
                reference=draft.reference,
                source_file=draft.source_file,
                updated_by=updated_by,
                updated_at=updated_at,
                options=[
                    QuestionOption(
                        position=index, text=option.text, is_correct=option.is_correct
                    )
                    for index, option in enumerate(draft.options)
                ],
            )
            self._session.add(question)
            return question, True

        changed = _apply_draft(existing, draft)
        if changed:
            existing.updated_by = updated_by
            existing.updated_at = updated_at
        return existing, changed

    async def set_active(self, question: Question, is_active: bool) -> None:
        question.is_active = is_active


def _apply_draft(question: Question, draft: QuestionDraft) -> bool:
    """Перенести поля черновика в вопрос; вернуть, изменилось ли что-нибудь."""
    changed = False
    for field_name, value in (
        ("text", draft.text),
        ("category", draft.category),
        ("difficulty", draft.difficulty),
        ("is_active", draft.is_active),
        ("explanation", draft.explanation),
        ("reference", draft.reference),
        ("source_file", draft.source_file),
    ):
        if getattr(question, field_name) != value:
            setattr(question, field_name, value)
            changed = True

    current = [(option.text, option.is_correct) for option in question.options]
    wanted = [(option.text, option.is_correct) for option in draft.options]
    if current != wanted:
        question.options.clear()
        question.options.extend(
            QuestionOption(position=index, text=text, is_correct=is_correct)
            for index, (text, is_correct) in enumerate(wanted)
        )
        changed = True
    return changed
