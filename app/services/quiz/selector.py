"""Выбор вопроса для чата без повторов — через круги.

Пока в текущем круге остаются не заданные вопросы, берётся случайный из них.
Когда круг исчерпан, его номер увеличивается, и в новом круге снова доступны
все, с предпочтением задававшимся раньше остальных. Счётчик круга вместо
очистки истории сохраняет полную историю выдач (см. `design.md`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.models import Chat, Question
from app.repositories.chats import ChatRepository
from app.repositories.questions import QuestionRepository


@dataclass(frozen=True, slots=True)
class Selection:
    """Выбранный вопрос и признак того, что начался новый круг."""

    question: Question | None
    new_round: bool = False


class QuestionSelector:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._questions = QuestionRepository(session)
        self._chats = ChatRepository(session)

    async def pick(self, chat: Chat) -> Selection:
        """Выбрать вопрос для чата с учётом его категорий."""
        categories = chat.category_list or None

        question = await self._questions.pick_for_chat(
            chat.id, chat.round_number, categories
        )
        if question is not None:
            return Selection(question=question)

        # круг исчерпан либо банк пуст — проверяем, есть ли вообще вопросы
        if await self._questions.count_active(categories) == 0:
            return Selection(question=None)

        chat.round_number += 1
        await self._session.flush()
        oldest = await self._questions.pick_oldest_asked_for_chat(chat.id, categories)
        return Selection(question=oldest, new_round=True)

    async def record(
        self, chat: Chat, question: Question, *, now: datetime | None = None
    ) -> None:
        """Отметить факт выдачи вопроса в этот чат в текущем круге."""
        await self._chats.record_asked(
            chat.id, question.id, chat.round_number, now or utc_now()
        )
