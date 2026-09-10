"""Раскладка категорий банка по руководствам.

Категория вида «Руководство · Глава» состоит из имени руководства и главы,
и оба экрана выбора — темы в личке и категории чата в кабинете — показывают
её двумя уровнями: одним списком под сотню кнопок Telegram отвергает как
слишком длинную разметку. Раскладка живёт здесь, а не рядом с одним из
экранов, потому что общего у них именно имя категории.
"""

from __future__ import annotations

from dataclasses import dataclass

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
