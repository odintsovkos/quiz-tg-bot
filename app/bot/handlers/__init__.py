"""Хендлеры. Импорт модуля регистрирует их в роутерах своих зон."""

from app.bot.handlers import (
    admin,
    admin_questions,
    admin_users,
    common,
    group,
    quiz,
    stats,
)

__all__ = [
    "admin",
    "admin_questions",
    "admin_users",
    "common",
    "group",
    "quiz",
    "stats",
]
