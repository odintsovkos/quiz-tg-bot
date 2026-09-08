"""Доступ к профилям участников."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserRole


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def add(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        return user

    async def set_anchor(self, user: User, message_id: int | None) -> User:
        """Запомнить сообщение-якорь личной переписки участника."""
        user.anchor_message_id = message_id
        await self._session.flush()
        return user

    async def anchor_of(self, user_id: int) -> int | None:
        statement = select(User.anchor_message_id).where(User.id == user_id)
        return await self._session.scalar(statement)

    async def list_by_roles(self, roles: tuple[UserRole, ...]) -> list[User]:
        statement = (
            select(User).where(User.role.in_(roles)).order_by(User.display_name, User.id)
        )
        return list(await self._session.scalars(statement))

    async def count(self) -> int:
        return int(await self._session.scalar(select(func.count()).select_from(User)) or 0)
