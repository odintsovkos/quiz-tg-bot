from app.services.content.validation import (
    MAX_EXPLANATION_LENGTH,
    MAX_OPTION_LENGTH,
    MAX_QUESTION_LENGTH,
    OptionDraft,
    QuestionDraft,
    validate_batch,
    validate_question,
)


def draft(**overrides) -> QuestionDraft:
    values = {
        "id": "dev.ch08.001",
        "text": "Что такое запрос?",
        "category": "Разработчик · Глава 8",
        "difficulty": "medium",
        "options": (
            OptionDraft("Верный", True),
            OptionDraft("Неверный"),
        ),
        "explanation": "Пояснение",
        "source_file": "dev/ch08.yaml",
    }
    values.update(overrides)
    return QuestionDraft(**values)


def messages(result) -> str:
    return " | ".join(issue.message for issue in result.issues)


def test_valid_question_passes():
    assert validate_question(draft()).ok


def test_missing_text_is_rejected():
    result = validate_question(draft(text="  "))
    assert not result.ok
    assert "text" in messages(result)


def test_missing_category_is_rejected():
    assert "category" in messages(validate_question(draft(category="")))


def test_too_long_question_names_the_limit():
    result = validate_question(draft(text="я" * (MAX_QUESTION_LENGTH + 1)))
    assert str(MAX_QUESTION_LENGTH) in messages(result)


def test_too_long_option_names_the_limit():
    long_option = OptionDraft("я" * (MAX_OPTION_LENGTH + 1), True)
    result = validate_question(draft(options=(long_option, OptionDraft("Другой"))))
    assert str(MAX_OPTION_LENGTH) in messages(result)


def test_too_long_explanation_names_the_limit():
    result = validate_question(draft(explanation="я" * (MAX_EXPLANATION_LENGTH + 1)))
    assert str(MAX_EXPLANATION_LENGTH) in messages(result)


def test_single_option_is_rejected():
    result = validate_question(draft(options=(OptionDraft("Один", True),)))
    assert "вариантов 1" in messages(result)


def test_eleven_options_are_rejected():
    options = tuple(
        OptionDraft(f"Вариант {index}", index == 0) for index in range(11)
    )
    assert "вариантов 11" in messages(validate_question(draft(options=options)))


def test_two_correct_options_are_rejected():
    options = (OptionDraft("А", True), OptionDraft("Б", True))
    result = validate_question(draft(options=options))
    assert "верных вариантов 2" in messages(result)


def test_no_correct_option_is_rejected():
    options = (OptionDraft("А"), OptionDraft("Б"))
    assert "верных вариантов 0" in messages(validate_question(draft(options=options)))


def test_unknown_difficulty_is_rejected():
    assert "сложность" in messages(validate_question(draft(difficulty="невозможный")))


def test_duplicate_options_are_rejected():
    options = (OptionDraft("Одно и то же", True), OptionDraft("Одно и то же "))
    assert "повторяет" in messages(validate_question(draft(options=options)))


def test_options_differing_only_by_case_are_allowed():
    """Регистр бывает значимым: «macOS64tc.zip» и «macos64tc.zip» — разные строки."""
    options = (OptionDraft("macOS64tc.zip", True), OptionDraft("macos64tc.zip"))
    assert validate_question(draft(options=options)).ok


def test_issue_points_at_file_and_id():
    issue = validate_question(draft(text="")).issues[0]
    assert issue.question_id == "dev.ch08.001"
    assert issue.source == "dev/ch08.yaml"
    assert "dev/ch08.yaml" in str(issue)


def test_duplicate_ids_within_batch_are_rejected():
    result = validate_batch([draft(), draft(source_file="dev/ch09.yaml")])
    assert "дублируется" in messages(result)


def test_batch_reports_every_problem():
    result = validate_batch(
        [
            draft(id="a", text=""),
            draft(id="b", difficulty="нет такой"),
            draft(id="c", options=(OptionDraft("А", True), OptionDraft("Б", True))),
        ]
    )
    assert len(result.issues) == 3
