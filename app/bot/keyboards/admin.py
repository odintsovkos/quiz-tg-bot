"""Клавиатуры кабинета администратора."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot import texts_admin
from app.bot.callbacks import (
    AdminCallback,
    AdminChatCallback,
    AdminLimitCallback,
    AdminQuestionCallback,
    AdminUserCallback,
)
from app.models import Chat, LimitMode, Question, User, UserRole
from app.services.content.categories import TopicGroup

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


#: Сколько глав руководства показывать на одной странице выбора.
CATEGORIES_PAGE_SIZE = 8


def categories_page_count(items: int) -> int:
    """Сколько страниц занимает список; пустой список — одна страница."""
    return max(1, -(-items // CATEGORIES_PAGE_SIZE))


def chat_category_groups(
    chat: Chat, groups: list[TopicGroup]
) -> InlineKeyboardMarkup:
    """Первый уровень выбора категорий: руководства и число отмеченных глав.

    Экран собран как выбор тем в личке: плоским списком администратор листал
    страницы всего банка, чтобы собрать одно руководство.
    """
    selected = set(chat.category_list)
    builder = InlineKeyboardBuilder()
    for index, group in enumerate(groups):
        chosen = sum(1 for item in group.items if item.category in selected)
        builder.button(
            text=texts_admin.CHAT_CATEGORIES_GROUP_BUTTON.format(
                name=group.name, selected=chosen, total=len(group.items)
            ),
            callback_data=AdminChatCallback(
                action="cat_open", chat_id=chat.id, group=index
            ),
        )
    builder.adjust(1)
    # «Все категории» отмечает банк целиком, «Сбросить» снимает отметки:
    # пустой набор тоже означает все категории, но кнопки отвечают на разные
    # вопросы — «хочу видеть выбранным всё» и «хочу начать выбор заново».
    builder.row(
        InlineKeyboardButton(
            text="✅ Все категории",
            callback_data=AdminChatCallback(
                action="cat_all", chat_id=chat.id
            ).pack(),
        ),
        InlineKeyboardButton(
            text="♻️ Сбросить",
            callback_data=AdminChatCallback(
                action="cat_reset", chat_id=chat.id
            ).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ К чату",
            callback_data=AdminChatCallback(action="open", chat_id=chat.id).pack(),
        )
    )
    return builder.as_markup()


def chat_category_chapters(
    chat: Chat, group_index: int, group: TopicGroup, page: int = 0
) -> InlineKeyboardMarkup:
    """Второй уровень: главы одного руководства страницей.

    Страницы нужны не для красоты: под сотню категорий одним списком дают
    разметку, которую Telegram отвергает как слишком длинную. Индекс главы
    сквозной по всему банку, поэтому ни листание, ни переход между
    руководствами не меняют смысла нажатия.
    """
    pages = categories_page_count(len(group.items))
    page = max(0, min(page, pages - 1))
    start = page * CATEGORIES_PAGE_SIZE

    selected = set(chat.category_list)
    builder = InlineKeyboardBuilder()
    for item in group.items[start : start + CATEGORIES_PAGE_SIZE]:
        mark = "✅ " if item.category in selected else "▫️ "
        builder.button(
            text=f"{mark}{item.title}",
            callback_data=AdminChatCallback(
                action="cat_toggle",
                chat_id=chat.id,
                group=group_index,
                index=item.index,
                page=page,
            ),
        )
    builder.adjust(1)

    all_chosen = all(item.category in selected for item in group.items)
    builder.row(
        InlineKeyboardButton(
            text="◻️ Снять все" if all_chosen else "✅ Выбрать все",
            callback_data=AdminChatCallback(
                action="cat_group_all",
                chat_id=chat.id,
                group=group_index,
                page=page,
            ).pack(),
        )
    )

    if pages > 1:
        builder.row(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=AdminChatCallback(
                    action="cat_open",
                    chat_id=chat.id,
                    group=group_index,
                    page=(page - 1) % pages,
                ).pack(),
            ),
            InlineKeyboardButton(
                text=texts_admin.CHAT_CATEGORIES_PAGE_LABEL.format(
                    page=page + 1, pages=pages
                ),
                callback_data=AdminChatCallback(
                    action="cat_noop", chat_id=chat.id, page=page
                ).pack(),
            ),
            InlineKeyboardButton(
                text="➡️",
                callback_data=AdminChatCallback(
                    action="cat_open",
                    chat_id=chat.id,
                    group=group_index,
                    page=(page + 1) % pages,
                ).pack(),
            ),
        )

    # Уйти к чату можно с любой страницы глав, не листая назад.
    builder.row(
        InlineKeyboardButton(
            text="⬅️ К руководствам",
            callback_data=AdminChatCallback(
                action="cat_groups", chat_id=chat.id
            ).pack(),
        ),
        InlineKeyboardButton(
            text="🏠 К чату",
            callback_data=AdminChatCallback(action="open", chat_id=chat.id).pack(),
        ),
    )
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
