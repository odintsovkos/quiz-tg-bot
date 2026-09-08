"""Доступ к подключённым групповым чатам."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AskedQuestion, Chat, GroupPoll


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, chat_id: int) -> Chat | None:
        return await self._session.get(Chat, chat_id)

    async def list_all(self) -> list[Chat]:
        return list(await self._session.scalars(select(Chat).order_by(Chat.title)))

    async def list_active(self) -> list[Chat]:
        statement = select(Chat).where(Chat.is_active.is_(True)).order_by(Chat.title)
        return list(await self._session.scalars(statement))

    async def add(self, chat: Chat) -> Chat:
        self._session.add(chat)
        await self._session.flush()
        return chat

    async def remove(self, chat: Chat) -> None:
        await self._session.delete(chat)
        await self._session.flush()

    async def set_topic(
        self, chat: Chat, topic_id: int | None, topic_title: str | None
    ) -> Chat:
        """Задать ветку публикации либо вернуть чат на общую ленту."""
        chat.topic_id = topic_id
        chat.topic_title = topic_title if topic_id is not None else None
        await self._session.flush()
        return chat

    async def clear_topic(self, chat: Chat) -> Chat:
        return await self.set_topic(chat, None, None)

    async def record_asked(
        self, chat_id: int, question_id: str, round_number: int, moment: datetime
    ) -> None:
        self._session.add(
            AskedQuestion(
                chat_id=chat_id,
                question_id=question_id,
                round_number=round_number,
                asked_at=moment,
            )
        )
        await self._session.flush()

    async def add_poll(self, poll: GroupPoll) -> GroupPoll:
        self._session.add(poll)
        await self._session.flush()
        return poll

    async def get_poll(self, poll_id: str) -> GroupPoll | None:
        return await self._session.get(GroupPoll, poll_id)
