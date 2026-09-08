from datetime import UTC, datetime

import pytest

from app.core.db import session_scope
from app.models import UserRole
from app.services.users import (
    OwnerCannotBeRevokedError,
    UnknownUserError,
    UserService,
)

FIRST = datetime(2026, 3, 10, 10, 0, tzinfo=UTC)
LATER = datetime(2026, 3, 11, 10, 0, tzinfo=UTC)


async def test_first_contact_creates_a_profile_with_the_user_role(session):
    user = await UserService(session).register(7, "Иван", "ivan", now=FIRST)

    assert user.role is UserRole.USER
    assert (user.first_seen_at, user.last_seen_at) == (FIRST, FIRST)


async def test_group_answer_registers_an_unknown_user(session_factory):
    """Спека `bot-core`: профиль создаётся и при первом ответе в группе."""
    async with session_scope(session_factory) as session:
        await UserService(session).register(7, "Иван", now=FIRST)

    async with session_factory() as session:
        assert await UserService(session).get(7) is not None


async def test_renaming_in_telegram_updates_the_display_name(session):
    service = UserService(session)
    await service.register(7, "Иван", "ivan", now=FIRST)

    user = await service.register(7, "Иван Петров", "ivan_p", now=LATER)

    assert user.display_name == "Иван Петров"
    assert user.username == "ivan_p"
    assert user.first_seen_at == FIRST
    assert user.last_seen_at == LATER


async def test_owner_role_is_assigned_on_first_start(session):
    owner = await UserService(session).ensure_owner(1, now=FIRST)
    assert owner.role is UserRole.OWNER


async def test_second_start_does_not_duplicate_the_owner(session_factory):
    async with session_scope(session_factory) as session:
        await UserService(session).ensure_owner(1, now=FIRST)
    async with session_scope(session_factory) as session:
        await UserService(session).ensure_owner(1, now=LATER)

    async with session_factory() as session:
        admins = await UserService(session).list_admins()
    assert [(user.id, user.role) for user in admins] == [(1, UserRole.OWNER)]


async def test_existing_user_is_promoted_to_owner(session):
    service = UserService(session)
    await service.register(1, "Иван", now=FIRST)

    owner = await service.ensure_owner(1, now=LATER)

    assert owner.role is UserRole.OWNER
    assert owner.first_seen_at == FIRST


async def test_admin_can_be_granted_and_revoked(session):
    service = UserService(session)
    await service.register(7, "Иван", now=FIRST)

    assert (await service.grant_admin(7)).role is UserRole.ADMIN
    assert (await service.revoke_admin(7)).role is UserRole.USER


async def test_owner_cannot_be_revoked(session):
    service = UserService(session)
    await service.ensure_owner(1, now=FIRST)

    with pytest.raises(OwnerCannotBeRevokedError):
        await service.revoke_admin(1)


async def test_granting_to_an_unknown_user_is_rejected(session):
    with pytest.raises(UnknownUserError):
        await UserService(session).grant_admin(999)


async def test_admin_list_contains_admins_and_the_owner(session):
    service = UserService(session)
    await service.ensure_owner(1, now=FIRST)
    await service.register(7, "Иван", now=FIRST)
    await service.register(8, "Пётр", now=FIRST)
    await service.grant_admin(7)

    admins = await service.list_admins()

    assert {user.id for user in admins} == {1, 7}
