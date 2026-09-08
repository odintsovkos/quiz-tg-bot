"""Разбор пройденной сессии.

Лента сессии убирается вместе с пояснениями, поэтому разбор собирается заново
по сохранённой сессии: `SessionQuestion` помнит, что и как было отвечено,
а `Question` — верный вариант, пояснение и ссылку на раздел документации.
Ничего дополнительно сохранять не нужно.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Question, QuizSession


@dataclass(frozen=True, slots=True)
class ReviewItem:
    """Один вопрос сессии глазами разбора."""

    number: int
    text: str
    correct: str
    chosen: str | None
    explanation: str | None
    reference: str | None
    answered: bool
    is_correct: bool


def _chosen(question: Question, index: int | None) -> str | None:
    """Текст выбранного варианта.

    Индекс приходит из базы и мог быть записан, когда у вопроса было больше
    вариантов, поэтому границы проверяются. У сессий, пройденных до появления
    этого поля, вариант не сохранён — тогда `None`.
    """
    if index is None or not 0 <= index < len(question.options):
        return None
    return question.options[index].text


class ReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def build(self, quiz: QuizSession) -> list[ReviewItem]:
        """Разбор в порядке выдачи вопросов.

        Вопрос, удалённый из банка после сессии, в разбор не попадает:
        показать по нему нечего.
        """
        items: list[ReviewItem] = []
        for item in quiz.questions:
            question = await self._session.get(Question, item.question_id)
            if question is None:
                continue
            items.append(
                ReviewItem(
                    number=item.position + 1,
                    text=question.text,
                    correct=question.options[question.correct_index].text,
                    chosen=_chosen(question, item.chosen_option),
                    explanation=question.explanation,
                    reference=question.reference,
                    answered=item.answered,
                    is_correct=bool(item.is_correct),
                )
            )
        return items
