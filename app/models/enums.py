"""Перечисления предметной области.

Значения хранятся в БД строками, чтобы дамп был читаемым, а добавление
нового варианта не требовало миграции числовых кодов.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Роль участника. Владелец задаётся конфигурацией и из бота не меняется."""

    USER = "user"
    ADMIN = "admin"
    OWNER = "owner"

    @property
    def is_admin(self) -> bool:
        return self in (UserRole.ADMIN, UserRole.OWNER)


class Difficulty(StrEnum):
    """Уровень сложности вопроса из фиксированного набора."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class AnswerSource(StrEnum):
    """Откуда пришёл ответ — от этого зависит применение лимитов и учёт."""

    GROUP = "group"
    PRIVATE = "private"


class SessionStatus(StrEnum):
    """Состояние личной сессии викторины."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ABORTED = "aborted"
    EXPIRED = "expired"


class LimitMode(StrEnum):
    """Режим дневных лимитов личных режимов."""

    ENABLED = "enabled"
    DISABLED_FOR_ALL = "disabled_for_all"
    DISABLED_FOR_ADMINS = "disabled_for_admins"
