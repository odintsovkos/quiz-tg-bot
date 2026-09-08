"""Доступ к личным сессиям викторины и выдачам случайных вопросов."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    QuizSession,
    RandomQuestionIssue,
    SessionMessage,
    SessionQuestion,
    SessionStatus,
)


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def active_for(self, user_id: int) -> QuizSession | None:
        statement = (
            select(QuizSession)
            .where(
                QuizSession.user_id == user_id,
                QuizSession.status == SessionStatus.ACTIVE,
            )
            .order_by(QuizSession.started_at.desc())
            .limit(1)
        )
        found: QuizSession | None = await self._session.scalar(statement)
        return found

    async def get(self, session_id: int) -> QuizSession | None:
        return await self._session.get(QuizSession, session_id)

    async def create(
        self, user_id: int, question_ids: list[str], moment: datetime
    ) -> QuizSession:
        quiz = QuizSession(
            user_id=user_id,
            status=SessionStatus.ACTIVE,
            total_questions=len(question_ids),
            started_at=moment,
            last_activity_at=moment,
            questions=[
                SessionQuestion(
                    question_id=question_id, position=index, answered=False
                )
                for index, question_id in enumerate(question_ids)
            ],
        )
        self._session.add(quiz)
        await self._session.flush()
        return quiz

    async def close(
        self, quiz: QuizSession, status: SessionStatus, moment: datetime
    ) -> QuizSession:
        quiz.status = status
        quiz.finished_at = moment
        await self._session.flush()
        return quiz

    async def add_message(
        self, session_id: int, chat_id: int, message_id: int
    ) -> None:
        """Учесть сообщение ленты сессии; повтор того же сообщения игнорируется."""
        known = await self._session.scalar(
            select(SessionMessage.id).where(
                SessionMessage.session_id == session_id,
                SessionMessage.message_id == message_id,
            )
        )
        if known is not None:
            return
        self._session.add(
            SessionMessage(
                session_id=session_id, chat_id=chat_id, message_id=message_id
            )
        )
        await self._session.flush()

    async def list_messages(self, session_id: int) -> list[SessionMessage]:
        statement = (
            select(SessionMessage)
            .where(SessionMessage.session_id == session_id)
            .order_by(SessionMessage.id)
        )
        return list(await self._session.scalars(statement))

    async def is_tracked(self, chat_id: int, message_id: int) -> bool:
        """Учтено ли сообщение в реестре какой-нибудь сессии этого чата."""
        found = await self._session.scalar(
            select(SessionMessage.id).where(
                SessionMessage.chat_id == chat_id,
                SessionMessage.message_id == message_id,
            )
        )
        return found is not None

    async def user_messages(self, user_id: int) -> list[SessionMessage]:
        """Весь непубликованный след сессий участника.

        Уборка привязана к участнику, а не к конкретной сессии: остатки
        закрытой сессии тоже должны исчезнуть при следующем показе экрана.
        """
        statement = (
            select(SessionMessage)
            .join(QuizSession, QuizSession.id == SessionMessage.session_id)
            .where(QuizSession.user_id == user_id)
            .order_by(SessionMessage.id)
        )
        return list(await self._session.scalars(statement))

    async def clear_user_messages(self, user_id: int) -> None:
        known = select(QuizSession.id).where(QuizSession.user_id == user_id)
        await self._session.execute(
            delete(SessionMessage).where(SessionMessage.session_id.in_(known))
        )
        await self._session.flush()

    async def clear_messages(self, session_id: int) -> None:
        await self._session.execute(
            delete(SessionMessage).where(SessionMessage.session_id == session_id)
        )
        await self._session.flush()

    async def add_issue(
        self, user_id: int, question_id: str, moment: datetime
    ) -> RandomQuestionIssue:
        issue = RandomQuestionIssue(
            user_id=user_id,
            question_id=question_id,
            issued_at=moment,
            answered=False,
        )
        self._session.add(issue)
        await self._session.flush()
        return issue

    async def get_issue(self, issue_id: int) -> RandomQuestionIssue | None:
        return await self._session.get(RandomQuestionIssue, issue_id)
