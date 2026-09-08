"""Выбор тем участником.

Темы хранятся строками таблицы предпочтений, а не полем профиля: их может быть
несколько, и связь переживает переименование категорий. Применяемый набор
вычисляется на каждый запрос, поэтому фоновая чистка предпочтений не нужна
(см. `design.md`, «Лимиты, выбор тем и учёт»).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserTopicPreference
from app.repositories.questions import QuestionRepository
from app.services.content.loader import CATEGORY_SEPARATOR

#: Группа для категорий без префикса руководства.
GROUP_OTHER = "Прочее"


@dataclass(frozen=True, slots=True)
class TopicItem:
    """Одна глава на экране выбора."""

    #: Позиция в общем списке доступных тем — ею адресуется кнопка.
    index: int
    #: Название главы без префикса руководства: префикс уже в заголовке группы.
    title: str
    category: str


@dataclass(frozen=True, slots=True)
class TopicGroup:
    """Руководство и его главы."""

    name: str
    items: tuple[TopicItem, ...]


def group_topics(available: list[str]) -> list[TopicGroup]:
    """Разложить темы по руководствам, сохранив общие индексы.

    Экран со всеми темами сразу не помещается в лимит Telegram на размер
    клавиатуры, поэтому выбор двухуровневый. Индекс остаётся общим: кнопка
    по-прежнему адресует тему позицией в списке `available`.
    """
    order: list[str] = []
    items: dict[str, list[TopicItem]] = {}
    for index, category in enumerate(available):
        group, _, title = category.partition(CATEGORY_SEPARATOR)
        if not title:
            group, title = GROUP_OTHER, category
        if group not in items:
            order.append(group)
            items[group] = []
        items[group].append(TopicItem(index=index, title=title, category=category))
    return [TopicGroup(name=name, items=tuple(items[name])) for name in order]


@dataclass(frozen=True, slots=True)
class AppliedTopics:
    """Темы, которые действительно применятся к выдаче."""

    #: Пустой список означает «все темы».
    categories: list[str]
    #: Истина, если сохранённый выбор оказался неприменим и снят.
    fell_back: bool


class TopicPreferenceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._questions = QuestionRepository(session)

    async def selected(self, user_id: int) -> list[str]:
        """Сохранённый выбор как есть, включая опустевшие темы."""
        statement = (
            select(UserTopicPreference.category)
            .where(UserTopicPreference.user_id == user_id)
            .order_by(UserTopicPreference.category)
        )
        return list(await self._session.scalars(statement))

    async def available(self) -> list[str]:
        """Темы, в которых есть активные вопросы."""
        return await self._questions.list_categories(only_active=True)

    async def save(self, user_id: int, categories: list[str]) -> None:
        """Заменить выбор целиком. Пустой список означает «все темы»."""
        await self._session.execute(
            delete(UserTopicPreference).where(UserTopicPreference.user_id == user_id)
        )
        for category in dict.fromkeys(categories):
            self._session.add(
                UserTopicPreference(user_id=user_id, category=category)
            )
        await self._session.flush()

    async def toggle(self, user_id: int, category: str) -> bool:
        """Включить или выключить одну тему; вернуть новое состояние."""
        existing = await self._session.scalar(
            select(UserTopicPreference).where(
                UserTopicPreference.user_id == user_id,
                UserTopicPreference.category == category,
            )
        )
        if existing is None:
            self._session.add(
                UserTopicPreference(user_id=user_id, category=category)
            )
            await self._session.flush()
            return True

        await self._session.delete(existing)
        await self._session.flush()
        return False

    async def set_many(
        self, user_id: int, categories: list[str], *, chosen: bool
    ) -> None:
        """Отметить или снять сразу несколько тем, не трогая остальной выбор.

        Нужно для кнопки «выбрать всё руководство»: `save` заменяет выбор
        целиком и стёр бы отметки в других руководствах.
        """
        if not categories:
            return
        if not chosen:
            await self._session.execute(
                delete(UserTopicPreference).where(
                    UserTopicPreference.user_id == user_id,
                    UserTopicPreference.category.in_(categories),
                )
            )
            await self._session.flush()
            return

        existing = set(
            await self._session.scalars(
                select(UserTopicPreference.category).where(
                    UserTopicPreference.user_id == user_id,
                    UserTopicPreference.category.in_(categories),
                )
            )
        )
        for category in dict.fromkeys(categories):
            if category not in existing:
                self._session.add(
                    UserTopicPreference(user_id=user_id, category=category)
                )
        await self._session.flush()

    async def reset(self, user_id: int) -> None:
        await self.save(user_id, [])

    async def applied(self, user_id: int) -> AppliedTopics:
        """Пересечь выбор с темами, где есть активные вопросы.

        Если пересечение пусто, поведение как при выборе «все темы», о чём
        вызывающий сообщает участнику.
        """
        selected = await self.selected(user_id)
        if not selected:
            return AppliedTopics(categories=[], fell_back=False)

        available = set(await self.available())
        applied = [category for category in selected if category in available]
        if not applied:
            return AppliedTopics(categories=[], fell_back=True)
        return AppliedTopics(categories=applied, fell_back=False)
