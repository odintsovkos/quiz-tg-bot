"""Клавиатуры, общие для нескольких экранов."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import LeaderboardCallback, MenuCallback
from app.services.stats.reading import PERIOD_TODAY, PERIOD_TOTAL


def main_menu() -> InlineKeyboardMarkup:
    """Главное меню личных сообщений."""
    builder = InlineKeyboardBuilder()
    builder.button(text="▶️ Викторина", callback_data=MenuCallback(action="quiz"))
    builder.button(text="🎲 Случайный вопрос", callback_data=MenuCallback(action="random"))
    builder.button(text="📚 Темы", callback_data=MenuCallback(action="topics"))
    builder.button(text="📊 Моя статистика", callback_data=MenuCallback(action="stats"))
    builder.button(text="🏆 Таблица результатов", callback_data=MenuCallback(action="top"))
    builder.button(text="⏳ Лимиты", callback_data=MenuCallback(action="limits"))
    builder.adjust(1, 1, 1, 2, 1)
    return builder.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ В меню", callback_data=MenuCallback(action="root").pack()
                )
            ]
        ]
    )


def leaderboard_switch(period: str) -> InlineKeyboardMarkup:
    """Переключатель периода: показывается кнопка другого периода."""
    other = PERIOD_TOTAL if period == PERIOD_TODAY else PERIOD_TODAY
    label = "За всё время" if other == PERIOD_TOTAL else "За сегодня"
    builder = InlineKeyboardBuilder()
    builder.button(text=label, callback_data=LeaderboardCallback(period=other))
    builder.button(text="⬅️ В меню", callback_data=MenuCallback(action="root"))
    builder.adjust(1)
    return builder.as_markup()
