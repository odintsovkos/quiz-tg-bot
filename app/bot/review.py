"""Отрисовка разбора сессии.

Разбор с пояснениями по десятку вопросов не влезает в сообщение Telegram
(4096 символов), поэтому он листается страницами, как экран тем. Страницы
нарезаются по фактической длине, а не по фиксированному числу вопросов:
пояснения бывают и в строку, и в абзац.
"""

from __future__ import annotations

from app.bot import texts
from app.services.quiz.review import ReviewItem

#: Запас до предела Telegram: заголовок, разделители и разметка.
PAGE_LIMIT = 3500


def item_text(item: ReviewItem) -> str:
    if not item.answered:
        mark = texts.REVIEW_MARK_SKIPPED
    elif item.is_correct:
        mark = texts.REVIEW_MARK_CORRECT
    else:
        mark = texts.REVIEW_MARK_WRONG

    text = texts.REVIEW_ITEM.format(
        mark=mark, number=item.number, text=item.text, correct=item.correct
    )
    if not item.answered:
        text += texts.REVIEW_ITEM_SKIPPED
    elif not item.is_correct and item.chosen is not None:
        # Верный вариант показан всегда; при ошибке важно ещё и то,
        # на чём участник ошибся.
        text += texts.REVIEW_ITEM_CHOSEN.format(chosen=item.chosen)
    if item.explanation:
        text += texts.REVIEW_ITEM_EXPLANATION.format(explanation=item.explanation)
    if item.reference:
        text += texts.REVIEW_ITEM_REFERENCE.format(reference=item.reference)
    return text


def paginate(items: list[ReviewItem]) -> list[list[str]]:
    """Разложить разбор по страницам. Пустой разбор — одна пустая страница."""
    pages: list[list[str]] = [[]]
    length = 0
    for item in items:
        block = item_text(item)
        # Вопрос длиннее страницы всё равно едет отдельной страницей:
        # резать его пополам хуже, чем показать как есть.
        if pages[-1] and length + len(block) > PAGE_LIMIT:
            pages.append([])
            length = 0
        pages[-1].append(block)
        length += len(block)
    return pages


def render(items: list[ReviewItem], page: int) -> tuple[str, int, int]:
    """Текст страницы разбора, её номер и общее число страниц."""
    pages = paginate(items)
    page = max(0, min(page, len(pages) - 1))
    if not items:
        return texts.REVIEW_EMPTY, page, len(pages)

    title = texts.REVIEW_TITLE.format(page=page + 1, pages=len(pages))
    return "\n\n".join([title, *pages[page]]), page, len(pages)
