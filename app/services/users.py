"""Профиль участника и роли.

Сервис не знает о типах aiogram: на вход приходят простые значения, которые
middleware достаёт из события.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.models import User, UserRole
from app.repositories.users import UserRepository


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)

    async def register(
        self,
        user_id: int,
        display_name: str,
        username: str | None = None,
        *,
        now: datetime | None = None,
    ) -> User:
        """Создать профиль при первом контакте, иначе обновить имя и момент.

        Спека `bot-core`: отображаемое имя обновляется при каждом
        взаимодействии, накопленная статистика при этом сохраняется.
        """
        moment = now or utc_now()
        user = await self._users.get(user_id)
        if user is None:
            return await self._users.add(
                User(
                    id=user_id,
                    role=UserRole.USER,
                    display_name=display_name,
                    username=username,
                    first_seen_at=moment,
                    last_seen_at=moment,
                )
            )

        user.display_name = display_name
        user.username = username
        user.last_seen_at = moment
        await self._session.flush()
        return user

    async def get(self, user_id: int) -> User | None:
        return await self._users.get(user_id)

    async def ensure_owner(
        self, owner_id: int, *, now: datetime | None = None
    ) -> User:
        """Выдать роль владельца идентификатору из конфигурации.

        Роль владельца задаётся развёртыванием и не меняется из интерфейса
        бота; повторный запуск ничего не дублирует.
        """
        moment = now or utc_now()
        user = await self._users.get(owner_id)
        if user is None:
            user = await self._users.add(
                User(
                    id=owner_id,
                    role=UserRole.OWNER,
                    display_name="Владелец",
                    username=None,
                    first_seen_at=moment,
                    last_seen_at=moment,
                )
            )
            return user

        if user.role is not UserRole.OWNER:
            user.role = UserRole.OWNER
            await self._session.flush()
        return user

    async def list_admins(self) -> list[User]:
        return await self._users.list_by_roles((UserRole.ADMIN, UserRole.OWNER))

    async def grant_admin(self, user_id: int) -> User:
        """Назначить администратора. Владелец остаётся владельцем."""
        user = await self._require(user_id)
        if user.role is UserRole.USER:
            user.role = UserRole.ADMIN
            await self._session.flush()
        return user

    async def revoke_admin(self, user_id: int) -> User:
        """Снять права администратора.

        Владельца снять нельзя — вызывающий получает отказ, а не молчаливое
        бездействие (спека `admin-console`, «Попытка снять владельца»).
        """
        user = await self._require(user_id)
        if user.role is UserRole.OWNER:
            raise OwnerCannotBeRevokedError(user_id)
        if user.role is UserRole.ADMIN:
            user.role = UserRole.USER
            await self._session.flush()
        return user

    async def _require(self, user_id: int) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise UnknownUserError(user_id)
        return user


class UnknownUserError(LookupError):
    """Участник ещё не писал боту — назначать ему роль не с чего."""

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        super().__init__(f"Участник {user_id} системе неизвестен")


class OwnerCannotBeRevokedError(PermissionError):
    """Роль владельца задаётся конфигурацией и из бота не снимается."""

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        super().__init__("Владельца нельзя лишить прав из интерфейса бота")
