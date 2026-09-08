"""Кабинет: управление администраторами (доступно владельцу).

Роутер владельца, а не администратора: снятие и назначение прав — исключительно
его дело, и фильтр роутера проверяет это в момент нажатия.
"""

from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import replies, texts_admin
from app.bot.callbacks import AdminUserCallback
from app.bot.keyboards import admin as keyboards
from app.bot.routers import private_owner
from app.bot.states import ManageAdmins
from app.models import User
from app.services.users import (
    OwnerCannotBeRevokedError,
    UnknownUserError,
    UserService,
)


def render_admins(admins: list[User]) -> str:
    lines = [texts_admin.ADMINS_TITLE, ""]
    if len(admins) <= 1:
        lines.append(texts_admin.ADMINS_EMPTY)
    lines.extend(
        texts_admin.ADMIN_LINE.format(
            name=admin.display_name,
            id=admin.id,
            role=texts_admin.ADMIN_ROLE_NAMES[admin.role.value],
        )
        for admin in admins
    )
    return "\n".join(lines)


async def show_admins(
    target: replies.Sender, session: AsyncSession, user: User
) -> None:
    admins = await UserService(session).list_admins()
    await replies.show(
        target, session, user, render_admins(admins), keyboards.admins_actions(admins)
    )


@private_owner.callback_query(AdminUserCallback.filter())
async def handle_admin_user_action(
    query: CallbackQuery,
    callback_data: AdminUserCallback,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    service = UserService(session)

    if callback_data.action == "grant":
        await state.set_state(ManageAdmins.user_id)
        await replies.show(
            query, session, user, texts_admin.ADMINS_ASK_ID, keyboards.back()
        )
        await query.answer()
        return

    try:
        revoked = await service.revoke_admin(callback_data.user_id)
    except OwnerCannotBeRevokedError:
        await query.answer(texts_admin.ADMIN_OWNER_PROTECTED, show_alert=True)
        return
    except UnknownUserError:
        await query.answer(texts_admin.ADMIN_UNKNOWN_USER, show_alert=True)
        return

    await show_admins(query, session, user)
    await query.answer(texts_admin.ADMIN_REVOKED.format(name=revoked.display_name))


@private_owner.message(ManageAdmins.user_id)
async def handle_admin_id_input(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    try:
        user_id = int((message.text or "").strip())
    except ValueError:
        await replies.show(
            message, session, user, texts_admin.ADMIN_BAD_ID, keyboards.back()
        )
        return

    try:
        granted = await UserService(session).grant_admin(user_id)
    except UnknownUserError:
        await replies.show(
            message, session, user, texts_admin.ADMIN_UNKNOWN_USER, keyboards.back()
        )
        return

    await state.clear()
    admins = await UserService(session).list_admins()
    await replies.show(
        message,
        session,
        user,
        texts_admin.ADMIN_GRANTED.format(name=granted.display_name)
        + "\n\n"
        + render_admins(admins),
        keyboards.admins_actions(admins),
    )
