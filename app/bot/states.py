"""Состояния FSM для многошаговых диалогов кабинета.

Хранилище — память: незавершённый диалог теряется при перезапуске, и это
осознанный размен (см. `design.md`). Состояние викторины при этом лежит в БД.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AddQuestion(StatesGroup):
    """Пошаговое добавление вопроса."""

    identifier = State()
    text = State()
    options = State()
    category = State()
    difficulty = State()
    explanation = State()


class EditQuestion(StatesGroup):
    """Правка одного поля существующего вопроса."""

    value = State()


class EditSchedule(StatesGroup):
    """Ввод периодичности или окна активности чата."""

    interval = State()
    window = State()


class EditLimits(StatesGroup):
    """Ввод числовых значений лимитов."""

    value = State()


class EditSettings(StatesGroup):
    """Ввод общих настроек бота."""

    value = State()


class ManageAdmins(StatesGroup):
    """Ввод идентификатора будущего администратора."""

    user_id = State()
