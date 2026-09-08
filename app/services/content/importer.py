"""Импорт и экспорт банка вопросов.

Импорт идемпотентен и целиком помещается в одну транзакцию: любая ошибка
партии откатывает всё, как требует спека `quiz-content`. Вопросы, исчезнувшие
из файлов, не удаляются — вместе с ними потерялась бы статистика.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.models import Question
from app.repositories.questions import QuestionRepository
from app.services.content.loader import CATEGORY_SEPARATOR, load_directory
from app.services.content.validation import QuestionDraft, ValidationIssue


class QuestionImportError(Exception):
    """Партия не прошла проверку — банк не изменён."""

    def __init__(self, issues: list[ValidationIssue]) -> None:
        self.issues = issues
        super().__init__("\n".join(str(issue) for issue in issues))


@dataclass(slots=True)
class ImportReport:
    """Отчёт импорта: добавлено / обновлено / без изменений."""

    added: int = 0
    updated: int = 0
    unchanged: int = 0
    files: int = 0
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.added + self.updated + self.unchanged

    def render(self) -> str:
        return (
            f"Файлов: {self.files}. Вопросов: {self.total}. "
            f"Добавлено: {self.added}, обновлено: {self.updated}, "
            f"без изменений: {self.unchanged}."
        )


async def import_drafts(
    session: AsyncSession,
    drafts: list[QuestionDraft],
    *,
    updated_by: int | None = None,
    now: datetime | None = None,
) -> ImportReport:
    """Записать проверенную партию. Вызывающий отвечает за транзакцию."""
    repository = QuestionRepository(session)
    report = ImportReport()
    moment = now or utc_now()

    for draft in drafts:
        existed = await repository.get(draft.id) is not None
        _, changed = await repository.upsert(draft, updated_by=updated_by, updated_at=moment)
        if not existed:
            report.added += 1
        elif changed:
            report.updated += 1
        else:
            report.unchanged += 1

    await session.flush()
    return report


async def import_directory(
    session: AsyncSession,
    root: Path,
    *,
    updated_by: int | None = None,
) -> ImportReport:
    """Прочитать каталог и импортировать партию целиком.

    При любой ошибке партии не загружается ни один вопрос — вызывающий
    получает исключение до коммита, поэтому транзакция откатывается.
    """
    loaded = load_directory(root)
    if loaded.issues:
        raise QuestionImportError(loaded.issues)

    report = await import_drafts(session, loaded.drafts, updated_by=updated_by)
    report.files = len({draft.source_file for draft in loaded.drafts if draft.source_file})
    return report


def _split_category(category: str) -> tuple[str, str]:
    """Разобрать категорию обратно на короткое имя руководства и главу."""
    if CATEGORY_SEPARATOR in category:
        short, title = category.split(CATEGORY_SEPARATOR, 1)
        return short.strip(), title.strip()
    return "", category


def _manual_and_chapter(question_id: str) -> tuple[str, str]:
    """`dev.ch08.001` → (`dev`, `ch08`); при другом виде id — что получится."""
    parts = question_id.split(".")
    manual = parts[0] if parts else ""
    chapter = parts[1] if len(parts) > 1 else ""
    return manual, chapter


async def export_questions(session: AsyncSession, target: Path) -> int:
    """Выгрузить банк в файлы того же формата, что принимает импорт.

    Один файл на категорию — как и в исходном банке, где файл соответствует
    главе руководства. Выгруженный каталог импортируется обратно без потерь.
    """
    target.mkdir(parents=True, exist_ok=True)
    questions = list(
        await session.scalars(select(Question).order_by(Question.category, Question.id))
    )

    by_category: dict[str, list[Question]] = defaultdict(list)
    for question in questions:
        by_category[question.category].append(question)

    written = 0
    for category, items in by_category.items():
        short, chapter_title = _split_category(category)
        manual_id, chapter_id = _manual_and_chapter(items[0].id)
        payload: dict[str, Any] = {
            "manual": {"id": manual_id, "short": short or manual_id},
            "chapter": {"id": chapter_id, "title": chapter_title},
            "questions": [_question_payload(question) for question in items],
        }

        name = f"{manual_id or 'bank'}-{chapter_id or str(written)}.yaml"
        path = target / name
        path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=1000),
            encoding="utf-8",
        )
        written += 1
    return written


def _question_payload(question: Question) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": question.id,
        "text": question.text,
        "difficulty": str(question.difficulty),
        "options": [
            {"text": option.text, "correct": True}
            if option.is_correct
            else {"text": option.text}
            for option in question.options
        ],
    }
    if question.explanation:
        payload["explanation"] = question.explanation
    if question.reference:
        payload["reference"] = question.reference
    if not question.is_active:
        payload["active"] = False
    return payload
