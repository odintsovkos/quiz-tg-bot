"""Клавиатуры личных режимов."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot import texts
from app.bot.callbacks import (
    MenuCallback,
    RandomActionCallback,
    RandomAnswerCallback,
    ReviewCallback,
    SessionActionCallback,
    SessionAnswerCallback,
    TopicCallback,
)
from app.services.quiz.topics import TopicGroup

#: Сколько глав показывать на одной странице выбора тем.
TOPICS_PAGE_SIZE = 8


def session_question(
    order: Sequence[tuple[str, int]], session_id: int, position: int
) -> InlineKeyboardMarkup:
    """Ряд букв вариантов: сами варианты напечатаны в тексте сообщения.

    Порядок показа приходит готовым — тем же, по которому собран список
    в теле сообщения. В кнопке остаётся исходный номер варианта, поэтому
    проверка ответа и разбор сессии работают как прежде.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        *(
            InlineKeyboardButton(
                text=label,
                callback_data=SessionAnswerCallback(
                    session_id=session_id, position=position, option=index
                ).pack(),
            )
            for label, index in order
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="⏹ Прервать",
            callback_data=SessionActionCallback(
                action="abort", session_id=session_id
            ).pack(),
        )
    )
    return builder.as_markup()


def session_conflict(session_id: int) -> InlineKeyboardMarkup:
    """Выбор при попытке начать вторую сессию поверх активной."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="▶️ Продолжить текущую",
        callback_data=SessionActionCallback(action="continue", session_id=session_id),
    )
    builder.button(
        text="🔄 Начать новую",
        callback_data=SessionActionCallback(action="restart", session_id=session_id),
    )
    builder.adjust(1)
    return builder.as_markup()


def session_finished(session_id: int | None = None) -> InlineKeyboardMarkup:
    """Итог сессии. Разбор предлагается только по пройденной сессии."""
    builder = InlineKeyboardBuilder()
    if session_id is not None:
        builder.button(
            text="📖 Разбор",
            callback_data=ReviewCallback(session_id=session_id, page=0),
        )
    builder.button(text="🔄 Ещё викторина", callback_data=MenuCallback(action="quiz"))
    builder.button(text="⬅️ В меню", callback_data=MenuCallback(action="root"))
    builder.adjust(1)
    return builder.as_markup()


def review_page(session_id: int, page: int, pages: int) -> InlineKeyboardMarkup:
    """Страница разбора: листание и возврат к итогу сессии."""
    builder = InlineKeyboardBuilder()
    if pages > 1:
        builder.row(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=ReviewCallback(
                    session_id=session_id, page=(page - 1) % pages
                ).pack(),
            ),
            InlineKeyboardButton(
                text=texts.TOPICS_PAGE_LABEL.format(page=page + 1, pages=pages),
                callback_data=ReviewCallback(
                    session_id=session_id, page=page, action="noop"
                ).pack(),
            ),
            InlineKeyboardButton(
                text="➡️",
                callback_data=ReviewCallback(
                    session_id=session_id, page=(page + 1) % pages
                ).pack(),
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ К итогу",
            callback_data=ReviewCallback(
                session_id=session_id, action="result"
            ).pack(),
        )
    )
    return builder.as_markup()


def random_question(
    order: Sequence[tuple[str, int]], issue_id: int
) -> InlineKeyboardMarkup:
    """То же, что у вопроса сессии: буквы одним рядом, тексты — в сообщении."""
    builder = InlineKeyboardBuilder()
    builder.row(
        *(
            InlineKeyboardButton(
                text=label,
                callback_data=RandomAnswerCallback(
                    issue_id=issue_id, option=index
                ).pack(),
            )
            for label, index in order
        )
    )
    return builder.as_markup()


def random_next() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🎲 Ещё вопрос", callback_data=RandomActionCallback(action="next")
    )
    builder.button(text="⬅️ В меню", callback_data=MenuCallback(action="root"))
    builder.adjust(1)
    return builder.as_markup()


def topic_groups(groups: list[TopicGroup], selected: set[str]) -> InlineKeyboardMarkup:
    """Первый уровень выбора тем: руководства и число отмеченных в них глав."""
    builder = InlineKeyboardBuilder()
    for index, group in enumerate(groups):
        chosen = sum(1 for item in group.items if item.category in selected)
        builder.button(
            text=texts.TOPICS_GROUP_BUTTON.format(
                name=group.name, selected=chosen, total=len(group.items)
            ),
            callback_data=TopicCallback(action="open", group=index),
        )
    builder.adjust(1)
    # «Все темы» отмечает весь банк, «Сбросить» снимает отметки: пустой выбор
    # тоже означает все темы, но эти кнопки отвечают на разные вопросы —
    # «хочу видеть выбранным всё» и «хочу начать выбор заново».
    builder.row(
        InlineKeyboardButton(
            text="✅ Все темы",
            callback_data=TopicCallback(action="select_all").pack(),
        ),
        InlineKeyboardButton(
            text="♻️ Сбросить",
            callback_data=TopicCallback(action="reset").pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ В меню",
            callback_data=MenuCallback(action="root").pack(),
        )
    )
    return builder.as_markup()


def topic_chapters(
    group_index: int, group: TopicGroup, selected: set[str], page: int
) -> InlineKeyboardMarkup:
    """Второй уровень: главы одного руководства страницей.

    Страница нужна не для красоты: 85 тем одним списком дают разметку около
    14 КБ, а Telegram отвергает её как слишком длинную.
    """
    pages = page_count(len(group.items))
    page = max(0, min(page, pages - 1))
    start = page * TOPICS_PAGE_SIZE

    builder = InlineKeyboardBuilder()
    for item in group.items[start : start + TOPICS_PAGE_SIZE]:
        mark = "✅ " if item.category in selected else "▫️ "
        builder.button(
            text=f"{mark}{item.title}",
            callback_data=TopicCallback(
                action="toggle", index=item.index, group=group_index, page=page
            ),
        )
    builder.adjust(1)

    all_chosen = all(item.category in selected for item in group.items)
    builder.row(
        InlineKeyboardButton(
            text="◻️ Снять все" if all_chosen else "✅ Выбрать все",
            callback_data=TopicCallback(
                action="all", group=group_index, page=page
            ).pack(),
        )
    )

    if pages > 1:
        builder.row(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=TopicCallback(
                    action="open", group=group_index, page=(page - 1) % pages
                ).pack(),
            ),
            InlineKeyboardButton(
                text=texts.TOPICS_PAGE_LABEL.format(page=page + 1, pages=pages),
                callback_data=TopicCallback(action="noop").pack(),
            ),
            InlineKeyboardButton(
                text="➡️",
                callback_data=TopicCallback(
                    action="open", group=group_index, page=(page + 1) % pages
                ).pack(),
            ),
        )

    builder.row(
        InlineKeyboardButton(
            text="⬅️ К руководствам",
            callback_data=TopicCallback(action="root").pack(),
        ),
        InlineKeyboardButton(
            text="🏠 В меню",
            callback_data=MenuCallback(action="root").pack(),
        ),
    )
    return builder.as_markup()


def page_count(items: int) -> int:
    """Сколько страниц занимает список глав; пустой список — одна страница."""
    return max(1, -(-items // TOPICS_PAGE_SIZE))
