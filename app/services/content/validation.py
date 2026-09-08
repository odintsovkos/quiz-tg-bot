"""Валидация вопроса — один модуль на два входа.

Правила вызывают и импорт из файлов, и редактирование из кабинета, поэтому
поведение обоих путей одинаково по построению, а не по договорённости
(см. `design.md`, «Валидация вопросов — один модуль на два входа»).

Ограничения длин — это лимиты нативного quiz-опроса Telegram, которым
выдаётся вопрос в группе.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.enums import Difficulty

MAX_QUESTION_LENGTH = 300
MAX_OPTION_LENGTH = 100
MAX_EXPLANATION_LENGTH = 200
MIN_OPTIONS = 2
MAX_OPTIONS = 10


@dataclass(frozen=True, slots=True)
class OptionDraft:
    """Вариант ответа до сохранения."""

    text: str
    is_correct: bool = False


@dataclass(frozen=True, slots=True)
class QuestionDraft:
    """Вопрос до сохранения — общий вход для импорта и кабинета."""

    id: str
    text: str
    category: str
    difficulty: str
    options: tuple[OptionDraft, ...]
    explanation: str | None = None
    reference: str | None = None
    is_active: bool = True
    source_file: str | None = None

    @property
    def correct_index(self) -> int:
        for index, option in enumerate(self.options):
            if option.is_correct:
                return index
        raise ValueError(f"У вопроса {self.id} нет верного варианта")


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """Одно нарушение с адресом: файл и идентификатор вопроса."""

    question_id: str
    message: str
    source: str | None = None

    def __str__(self) -> str:
        where = f"{self.source}: " if self.source else ""
        return f"{where}{self.question_id or '<без id>'} — {self.message}"


@dataclass(slots=True)
class ValidationResult:
    """Итог проверки: пусто — значит валидно."""

    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def extend(self, other: ValidationResult) -> None:
        self.issues.extend(other.issues)


def validate_question(draft: QuestionDraft, source: str | None = None) -> ValidationResult:
    """Проверить один вопрос. Собираются все нарушения, а не первое."""
    issues: list[ValidationIssue] = []

    def fail(message: str) -> None:
        issues.append(ValidationIssue(draft.id, message, source or draft.source_file))

    if not draft.id.strip():
        fail("не заполнено обязательное поле «id»")
    if not draft.text.strip():
        fail("не заполнено обязательное поле «text»")
    elif len(draft.text) > MAX_QUESTION_LENGTH:
        fail(
            f"текст вопроса {len(draft.text)} символов, "
            f"допустимо не более {MAX_QUESTION_LENGTH}"
        )

    if not draft.category.strip():
        fail("не заполнено обязательное поле «category»")

    if draft.difficulty not in {item.value for item in Difficulty}:
        allowed = ", ".join(item.value for item in Difficulty)
        fail(f"недопустимая сложность «{draft.difficulty}», допустимо: {allowed}")

    count = len(draft.options)
    if count < MIN_OPTIONS or count > MAX_OPTIONS:
        fail(f"вариантов {count}, допустимо от {MIN_OPTIONS} до {MAX_OPTIONS}")

    correct = sum(1 for option in draft.options if option.is_correct)
    if correct != 1:
        fail(f"верных вариантов {correct}, должен быть ровно один")

    seen: set[str] = set()
    for index, option in enumerate(draft.options, start=1):
        if not option.text.strip():
            fail(f"вариант {index} пуст")
        elif len(option.text) > MAX_OPTION_LENGTH:
            fail(
                f"вариант {index} — {len(option.text)} символов, "
                f"допустимо не более {MAX_OPTION_LENGTH}"
            )
        # Сравнение с учётом регистра — как в `tools/validate_questions.py`,
        # которым уже проверен весь банк: варианты вида «macOS64tc.zip» и
        # «macos64tc.zip» различаются осмысленно. Проверка ловит другое —
        # решётку после пробела, из-за которой YAML молча обрезает значение
        # и варианты становятся одинаковыми.
        normalized = option.text.strip()
        if normalized and normalized in seen:
            fail(f"вариант {index} повторяет один из предыдущих")
        seen.add(normalized)

    if draft.explanation is not None and len(draft.explanation) > MAX_EXPLANATION_LENGTH:
        fail(
            f"пояснение {len(draft.explanation)} символов, "
            f"допустимо не более {MAX_EXPLANATION_LENGTH}"
        )

    return ValidationResult(issues)


def validate_batch(drafts: list[QuestionDraft]) -> ValidationResult:
    """Проверить партию целиком: каждый вопрос плюс уникальность идентификаторов."""
    result = ValidationResult()
    for draft in drafts:
        result.extend(validate_question(draft))

    seen: dict[str, QuestionDraft] = {}
    for draft in drafts:
        previous = seen.get(draft.id)
        if previous is not None:
            result.issues.append(
                ValidationIssue(
                    draft.id,
                    f"идентификатор дублируется в партии (ранее — {previous.source_file})",
                    draft.source_file,
                )
            )
        else:
            seen[draft.id] = draft
    return result
