"""Зоны роутеров и их фильтры.

Четыре зоны: личка обычного участника, кабинет администратора, групповой чат
и ответы на опросы. Каждая объявляет свои фильтры один раз, поэтому хендлеру
внутри уже не нужно проверять ни тип чата, ни роль.
"""

from __future__ import annotations

from aiogram import F, Router

from app.bot.filters import IsAdmin, IsOwner

#: Личные сообщения любого участника.
private_user = Router(name="private_user")
private_user.message.filter(F.chat.type == "private")
private_user.callback_query.filter(F.message.chat.type == "private")

#: Кабинет администратора — та же личка, но роль проверяется фильтром.
private_admin = Router(name="private_admin")
private_admin.message.filter(F.chat.type == "private", IsAdmin())
private_admin.callback_query.filter(F.message.chat.type == "private", IsAdmin())

#: Разделы кабинета, доступные только владельцу.
private_owner = Router(name="private_owner")
private_owner.message.filter(F.chat.type == "private", IsOwner())
private_owner.callback_query.filter(F.message.chat.type == "private", IsOwner())

#: Групповые чаты.
group = Router(name="group")
group.message.filter(F.chat.type.in_({"group", "supergroup"}))

#: Ответы на опросы приходят отдельным типом обновления, без привязки к чату.
polls = Router(name="polls")
