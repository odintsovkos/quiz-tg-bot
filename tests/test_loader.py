import json

from app.services.content.loader import load_directory, load_file

VALID_YAML = """
manual:
  id: dev
  title: Руководство разработчика
  short: Разработчик
chapter:
  id: ch08
  title: Глава 8. Работа с запросами
  source: "Руководство разработчика (главы)/010 Глава 8.html"
questions:
  - id: dev.ch08.001
    text: Какое слово убирает дубли строк выборки?
    difficulty: medium
    options:
      - text: РАЗЛИЧНЫЕ
        correct: true
      - text: ПЕРВЫЕ
      - text: СГРУППИРОВАТЬ ПО
      - text: УПОРЯДОЧИТЬ ПО
    explanation: Ключевое слово РАЗЛИЧНЫЕ исключает дубли.
    reference: 8.4.7.2. Использование слова «РАЗЛИЧНЫЕ»
"""


def write(tmp_path, name: str, content: str):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_category_is_built_from_manual_and_chapter(tmp_path):
    path = write(tmp_path, "dev/ch08.yaml", VALID_YAML)

    result = load_file(path, root=tmp_path)

    assert result.ok
    draft = result.drafts[0]
    assert draft.category == "Разработчик · Глава 8. Работа с запросами"
    assert draft.source_file.replace("\\", "/") == "dev/ch08.yaml"
    assert draft.correct_index == 0
    assert draft.reference.startswith("8.4.7.2")


def test_json_and_yaml_files_are_both_read(tmp_path):
    write(tmp_path, "dev/ch08.yaml", VALID_YAML)
    payload = {
        "manual": {"id": "admin", "short": "Администратор"},
        "chapter": {"id": "ch02", "title": "Глава 2. Запуск"},
        "questions": [
            {
                "id": "admin.ch02.001",
                "text": "Вопрос?",
                "difficulty": "easy",
                "options": [
                    {"text": "Да", "correct": True},
                    {"text": "Нет"},
                ],
            }
        ],
    }
    write(tmp_path, "admin/ch02.json", json.dumps(payload, ensure_ascii=False))

    result = load_directory(tmp_path)

    assert result.ok, [str(issue) for issue in result.issues]
    assert {draft.id for draft in result.drafts} == {"dev.ch08.001", "admin.ch02.001"}


def test_batch_collects_three_different_violations(tmp_path):
    broken = """
manual: {id: dev, short: Разработчик}
chapter: {id: ch09, title: Глава 9}
questions:
  - id: dev.ch09.001
    text: ""
    difficulty: medium
    options:
      - {text: А, correct: true}
      - {text: Б}
  - id: dev.ch09.002
    text: Вопрос?
    difficulty: невозможный
    options:
      - {text: А, correct: true}
      - {text: Б}
  - id: dev.ch09.003
    text: Вопрос?
    difficulty: hard
    options:
      - {text: А, correct: true}
      - {text: Б, correct: true}
"""
    write(tmp_path, "dev/ch09.yaml", broken)

    result = load_directory(tmp_path)

    assert len(result.issues) == 3
    rendered = " ".join(str(issue) for issue in result.issues)
    assert "dev.ch09.001" in rendered
    assert "dev.ch09.002" in rendered
    assert "dev.ch09.003" in rendered
    assert "dev/ch09.yaml" in rendered.replace("\\", "/")


def test_duplicate_ids_across_files_are_reported(tmp_path):
    write(tmp_path, "dev/ch08.yaml", VALID_YAML)
    write(tmp_path, "dev/ch08-copy.yaml", VALID_YAML)

    result = load_directory(tmp_path)

    assert any("дублируется" in issue.message for issue in result.issues)


def test_broken_yaml_is_reported_with_file(tmp_path):
    write(tmp_path, "dev/ch10.yaml", "questions: [ unbalanced")

    result = load_directory(tmp_path)

    assert not result.ok
    assert "dev/ch10.yaml" in str(result.issues[0]).replace("\\", "/")


def test_missing_directory_is_reported(tmp_path):
    result = load_directory(tmp_path / "нет-такого")
    assert not result.ok
    assert "каталог не найден" in result.issues[0].message


def test_inactive_flag_is_read(tmp_path):
    content = VALID_YAML.replace(
        "    difficulty: medium", "    active: false\n    difficulty: medium"
    )
    path = write(tmp_path, "dev/ch08.yaml", content)

    result = load_file(path, root=tmp_path)

    assert result.drafts[0].is_active is False
