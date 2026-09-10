"""Клавиатуры кабинета администратора."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    AdminCallback,
    AdminChatCallback,
    AdminLimitCallback,
    AdminQuestionCallback,
    AdminUserCallback,
)
from app.models import Chat, LimitMode, Question, User, UserRole

SECTION_TITLES = {
    "chats": "💬 Чаты",
    "schedule": "🗓 Расписание",
    "questions": "❓ Вопросы",
    "limits": "⏳ Лимиты",
    "settings": "⚙️ Настройки",
    "summary": "📈 Сводка",
    "admins": "👤 Администраторы",
}


def root(role: UserRole) -> InlineKeyboardMarkup:
    """Корневое меню; раздел администраторов виден только владельцу."""
    builder = InlineKeyboardBuilder()
    for section, title in SECTION_TITLES.items():
        if section == "admins" and role is not UserRole.OWNER:
            continue
        builder.button(text=title, callback_data=AdminCallback(section=section))
    builder.adjust(2)
    return builder.as_markup()


def back() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ В кабинет", callback_data=AdminCallback(section="root"))
    return builder.as_markup()


def chat_list(chats: list[Chat]) -> InlineKeyboardMarkup:
    """Уровень над карточкой чата: по кнопке на чат."""
    builder = InlineKeyboardBuilder()
    for chat in chats:
        mark = "▶️" if chat.is_active else "⏸"
        builder.button(
            text=f"{mark} {chat.title}",
            callback_data=AdminChatCallback(action="open", chat_id=chat.id),
        )
    builder.button(text="⬅️ В кабинет", callback_data=AdminCallback(section="root"))
    builder.adjust(1)
    return builder.as_markup()


def chat_actions(chat: Chat) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if chat.is_active:
        builder.button(
            text="⏸ Приостановить",
            callback_data=AdminChatCallback(action="pause", chat_id=chat.id),
        )
    else:
        builder.button(
            text="▶️ Возобновить",
            callback_data=AdminChatCallback(action="resume", chat_id=chat.id),
        )
    builder.button(
        text="🚀 Запустить вопрос",
        callback_data=AdminChatCallback(action="publish", chat_id=chat.id),
    )
    builder.button(
        text="🗓 Расписание",
        callback_data=AdminChatCallback(action="schedule", chat_id=chat.id),
    )
    # Категории живут здесь и только здесь: на экране расписания они были
    # второй кнопкой к тому же экрану, а расписание — это про время.
    builder.button(
        text="📚 Категории",
        callback_data=AdminChatCallback(action="set_categories", chat_id=chat.id),
    )
    if chat.topic_id is not None:
        builder.button(
            text="↩️ В общую ленту",
            callback_data=AdminChatCallback(action="topic_clear", chat_id=chat.id),
        )
    builder.button(
        text="❌ Отключить",
        callback_data=AdminChatCallback(action="remove", chat_id=chat.id),
    )
    builder.button(text="⬅️ К чатам", callback_data=AdminCallback(section="chats"))
    builder.adjust(2, 2, 1, 1, 1)
    return builder.as_markup()


def schedule_actions(chat_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="⏱ Периодичность",
        callback_data=AdminChatCallback(action="set_interval", chat_id=chat_id),
    )
    builder.button(
        text="🕘 Окно активности",
        callback_data=AdminChatCallback(action="set_window", chat_id=chat_id),
    )
    builder.button(
        text="⬅️ К чату",
        callback_data=AdminChatCallback(action="open", chat_id=chat_id),
    )
    builder.adjust(1)
    return builder.as_markup()


def questions_page(
    questions: tuple[Question, ...], page: int, pages: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for question in questions:
        mark = "" if question.is_active else "🚫 "
        builder.button(
            text=f"{mark}{question.id}",
            callback_data=AdminQuestionCallback(
                action="open", question_id=question.id, page=page
            ),
        )
    builder.adjust(1)

    navigation = InlineKeyboardBuilder()
    if page > 0:
        navigation.button(
            text="⬅️", callback_data=AdminCallback(section="questions", page=page - 1)
        )
    if page + 1 < pages:
        navigation.button(
            text="➡️", callback_data=AdminCallback(section="questions", page=page + 1)
        )
    navigation.button(
        text="➕ Добавить",
        callback_data=AdminCallback(section="questions", action="add"),
    )
    navigation.button(text="⬅️ В кабинет", callback_data=AdminCallback(section="root"))
    navigation.adjust(2, 2)
    builder.attach(navigation)
    return builder.as_markup()


def question_card(question: Question, page: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for action, title in (
        ("edit_text", "✏️ Текст"),
        ("edit_options", "✏️ Варианты"),
        ("edit_category", "✏️ Категория"),
        ("edit_difficulty", "✏️ Сложность"),
        ("edit_explanation", "✏️ Пояснение"),
    ):
        builder.button(
            text=title,
            callback_data=AdminQuestionCallback(
                action=action, question_id=question.id, page=page
            ),
        )
    builder.button(
        text="🚫 Деактивировать" if question.is_active else "✅ Активировать",
        callback_data=AdminQuestionCallback(
            action="toggle", question_id=question.id, page=page
        ),
    )
    builder.button(
        text="⬅️ К списку", callback_data=AdminCallback(section="questions", page=page)
    )
    builder.adjust(2, 2, 1, 1, 1)
    return builder.as_markup()


def limits_actions(mode: LimitMode) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for candidate in LimitMode:
        if candidate is mode:
            continue
        builder.button(
            text=f"Режим: {candidate.value}",
            callback_data=AdminLimitCallback(action="mode", value=candidate.value),
        )
    builder.button(
        text="✏️ Лимит викторин", callback_data=AdminLimitCallback(action="set_quiz")
    )
    builder.button(
        text="✏️ Лимит случайных", callback_data=AdminLimitCallback(action="set_random")
    )
    builder.button(text="⬅️ В кабинет", callback_data=AdminCallback(section="root"))
    builder.adjust(1)
    return builder.as_markup()


def limits_confirm(mode: LimitMode) -> InlineKeyboardMarkup:
    """Подтверждение режима, в котором ответы администраторов не учитываются."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Подтвердить",
        callback_data=AdminLimitCallback(action="mode_confirm", value=mode.value),
    )
    builder.button(text="↩️ Отмена", callback_data=AdminCallback(section="limits"))
    builder.adjust(1)
    return builder.as_markup()


def settings_actions() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✏️ Размер сессии",
        callback_data=AdminCallback(section="settings", action="session_size"),
    )
    builder.button(
        text="✏️ Строк рейтинга",
        callback_data=AdminCallback(section="settings", action="rows"),
    )
    builder.button(
        text="✏️ Таймзона",
        callback_data=AdminCallback(section="settings", action="timezone"),
    )
    builder.button(text="⬅️ В кабинет", callback_data=AdminCallback(section="root"))
    builder.adjust(1)
    return builder.as_markup()


def admins_actions(admins: list[User]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for admin in admins:
        if admin.role is UserRole.OWNER:
            continue
        builder.button(
            text=f"❌ Снять {admin.display_name}",
            callback_data=AdminUserCallback(action="revoke", user_id=admin.id),
        )
    builder.button(
        text="➕ Назначить",
        callback_data=AdminUserCallback(action="grant", user_id=0),
    )
    builder.button(text="⬅️ В кабинет", callback_data=AdminCallback(section="root"))
    builder.adjust(1)
    return builder.as_markup()
