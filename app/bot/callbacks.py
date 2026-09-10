"""Типизированные данные inline-кнопок.

Разбор идёт фабриками `CallbackData` aiogram, а не вручную: кнопка от прошлой
версии меню не совпадёт с фильтром и будет отклонена, а не приведёт к ошибке
(см. `design.md`, «Тексты и клавиатуры отдельно от логики»).
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class MenuCallback(CallbackData, prefix="menu"):
    """Переход по главному меню личных сообщений."""

    action: str


class SessionAnswerCallback(CallbackData, prefix="sq"):
    """Ответ на вопрос сессии: позиция вопроса и выбранный вариант."""

    session_id: int
    position: int
    option: int


class SessionActionCallback(CallbackData, prefix="sa"):
    """Действие над сессией: продолжить, начать заново, прервать."""

    action: str
    session_id: int


class ReviewCallback(CallbackData, prefix="rv"):
    """Разбор пройденной сессии: страница списка вопросов или возврат к итогу."""

    session_id: int
    page: int = 0
    action: str = "open"


class RandomAnswerCallback(CallbackData, prefix="rq"):
    """Ответ на одиночный случайный вопрос: идентификатор конкретной выдачи."""

    issue_id: int
    option: int


class RandomActionCallback(CallbackData, prefix="ra"):
    """Действие в режиме случайных вопросов (например, «ещё вопрос»)."""

    action: str


class TopicCallback(CallbackData, prefix="tp"):
    """Экран выбора тем: тема адресуется индексом, руководство — группой.

    `group` и `page` возвращают к тому же экрану после переключения темы:
    список глав листается страницами и не помещается в одно сообщение.
    """

    action: str
    index: int = -1
    group: int = -1
    page: int = 0


class LeaderboardCallback(CallbackData, prefix="lb"):
    """Переключение периода таблицы результатов."""

    period: str


class AdminCallback(CallbackData, prefix="adm"):
    """Навигация по кабинету администратора."""

    section: str
    action: str = "open"
    page: int = 0


class AdminChatCallback(CallbackData, prefix="admc"):
    """Действие над конкретным чатом из кабинета.

    `group`, `index` и `page` адресуют экран категорий чата — руководство,
    категорию в общем списке и страницу глав: категорий под сотню, одним
    списком их разметка не влезает в предел Telegram, поэтому выбор
    двухуровневый и возвращаться нужно на тот же экран.
    """

    action: str
    chat_id: int
    page: int = 0
    group: int = -1
    index: int = -1


class AdminQuestionCallback(CallbackData, prefix="admq"):
    """Действие над конкретным вопросом из кабинета."""

    action: str
    question_id: str
    page: int = 0


class AdminLimitCallback(CallbackData, prefix="adml"):
    """Управление режимом и значениями дневных лимитов."""

    action: str
    value: str = ""


class AdminUserCallback(CallbackData, prefix="admu"):
    """Управление списком администраторов (доступно владельцу)."""

    action: str
    user_id: int
