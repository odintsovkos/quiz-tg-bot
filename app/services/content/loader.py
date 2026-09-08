"""Чтение файлов-источников банка вопросов.

Формат описан в `data/questions/README.md`: один файл — одна глава одного
руководства, категория собирается как `{manual.short} · {chapter.title}`.
Читаются `.yaml`, `.yml` и `.json`; ошибки не прерывают обход — собираются
все, чтобы автор увидел разом весь список.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.services.content.validation import (
    OptionDraft,
    QuestionDraft,
    ValidationIssue,
    ValidationResult,
    validate_batch,
)

SUPPORTED_SUFFIXES = (".yaml", ".yml", ".json")
CATEGORY_SEPARATOR = " · "


@dataclass(slots=True)
class LoadResult:
    """Прочитанные вопросы и найденные при чтении нарушения."""

    drafts: list[QuestionDraft]
    issues: list[ValidationIssue]

    @property
    def ok(self) -> bool:
        return not self.issues


def _parse_file(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _category_of(payload: dict[str, Any], fallback: str) -> str:
    manual = payload.get("manual") or {}
    chapter = payload.get("chapter") or {}
    short = str(manual.get("short") or "").strip()
    title = str(chapter.get("title") or "").strip()
    if short and title:
        return f"{short}{CATEGORY_SEPARATOR}{title}"
    return title or short or fallback


def _option_drafts(raw: Any) -> tuple[OptionDraft, ...]:
    if not isinstance(raw, list):
        return ()
    options: list[OptionDraft] = []
    for item in raw:
        if isinstance(item, dict):
            options.append(
                OptionDraft(
                    text=str(item.get("text", "")),
                    is_correct=bool(item.get("correct", False)),
                )
            )
        else:
            options.append(OptionDraft(text=str(item)))
    return tuple(options)


def load_file(path: Path, root: Path | None = None) -> LoadResult:
    """Прочитать один файл-источник."""
    source = str(path.relative_to(root)) if root else str(path)
    drafts: list[QuestionDraft] = []
    issues: list[ValidationIssue] = []

    try:
        payload = _parse_file(path)
    except (yaml.YAMLError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return LoadResult([], [ValidationIssue("", f"файл не разобран: {exc}", source)])

    if not isinstance(payload, dict):
        return LoadResult([], [ValidationIssue("", "ожидался объект верхнего уровня", source)])

    raw_questions = payload.get("questions")
    if not isinstance(raw_questions, list):
        return LoadResult([], [ValidationIssue("", "нет списка «questions»", source)])

    category = _category_of(payload, fallback=path.stem)

    for index, raw in enumerate(raw_questions, start=1):
        if not isinstance(raw, dict):
            issues.append(ValidationIssue("", f"вопрос {index} — не объект", source))
            continue
        drafts.append(
            QuestionDraft(
                id=str(raw.get("id", "")).strip(),
                text=str(raw.get("text", "")).strip(),
                category=str(raw.get("category") or category).strip(),
                difficulty=str(raw.get("difficulty", "medium")).strip(),
                options=_option_drafts(raw.get("options")),
                explanation=_optional_text(raw.get("explanation")),
                reference=_optional_text(raw.get("reference")),
                is_active=bool(raw.get("active", True)),
                source_file=source,
            )
        )

    return LoadResult(drafts, issues)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def iter_source_files(root: Path) -> Iterable[Path]:
    """Файлы-источники в каталоге, в устойчивом порядке."""
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            yield path


def load_directory(root: Path) -> LoadResult:
    """Прочитать все файлы каталога и проверить партию целиком.

    Спека `quiz-content`, сценарий «Несколько ошибок в партии»: отчёт
    перечисляет все проблемы, а не только первую.
    """
    if not root.exists():
        return LoadResult([], [ValidationIssue("", f"каталог не найден: {root}", str(root))])

    drafts: list[QuestionDraft] = []
    issues: list[ValidationIssue] = []
    for path in iter_source_files(root):
        result = load_file(path, root=root)
        drafts.extend(result.drafts)
        issues.extend(result.issues)

    validation: ValidationResult = validate_batch(drafts)
    issues.extend(validation.issues)
    return LoadResult(drafts, issues)
