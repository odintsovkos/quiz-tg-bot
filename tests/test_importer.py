from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select

from app.core.db import session_scope
from app.models import Answer, AnswerSource, Question
from app.services.content.importer import (
    QuestionImportError,
    export_questions,
    import_directory,
)
from tests.conftest import make_user

FILE = """
manual: {{id: dev, short: Разработчик}}
chapter: {{id: ch08, title: Глава 8. Работа с запросами}}
questions:
  - id: dev.ch08.001
    text: {text}
    difficulty: medium
    options:
      - {{text: РАЗЛИЧНЫЕ, correct: true}}
      - {{text: ПЕРВЫЕ}}
    explanation: Пояснение
    reference: 8.4.7.2
  - id: dev.ch08.002
    text: Второй вопрос?
    difficulty: hard
    options:
      - {{text: Да, correct: true}}
      - {{text: Нет}}
"""


def write_bank(root, text: str = "Первый вопрос?"):
    root.mkdir(parents=True, exist_ok=True)
    (root / "ch08.yaml").write_text(FILE.format(text=text), encoding="utf-8")
    return root


async def test_first_import_adds_every_question(session_factory, tmp_path):
    root = write_bank(tmp_path / "bank")

    async with session_scope(session_factory) as session:
        report = await import_directory(session, root)

    assert (report.added, report.updated, report.unchanged) == (2, 0, 0)
    assert report.files == 1


async def test_repeated_import_changes_nothing(session_factory, tmp_path):
    root = write_bank(tmp_path / "bank")
    async with session_scope(session_factory) as session:
        await import_directory(session, root)

    async with session_scope(session_factory) as session:
        report = await import_directory(session, root)

    assert (report.added, report.updated) == (0, 0)
    assert report.unchanged == 2


async def test_changed_text_is_counted_as_updated(session_factory, tmp_path):
    root = write_bank(tmp_path / "bank")
    async with session_scope(session_factory) as session:
        await import_directory(session, root)

    (root / "ch08.yaml").write_text(
        FILE.format(text="Переформулированный вопрос?"), encoding="utf-8"
    )

    async with session_scope(session_factory) as session:
        report = await import_directory(session, root)
        question = await session.get(Question, "dev.ch08.001")
        assert question.text == "Переформулированный вопрос?"

    assert (report.added, report.updated, report.unchanged) == (0, 1, 1)


async def test_invalid_batch_leaves_the_bank_untouched(session_factory, tmp_path):
    root = write_bank(tmp_path / "bank")
    async with session_scope(session_factory) as session:
        await import_directory(session, root)

    (root / "broken.yaml").write_text(
        """
manual: {id: dev, short: Разработчик}
chapter: {id: ch09, title: Глава 9}
questions:
  - id: dev.ch09.001
    text: Вопрос с двумя верными?
    difficulty: medium
    options:
      - {text: А, correct: true}
      - {text: Б, correct: true}
""",
        encoding="utf-8",
    )

    with pytest.raises(QuestionImportError) as exc:
        async with session_scope(session_factory) as session:
            await import_directory(session, root)

    rendered = str(exc.value)
    assert "dev.ch09.001" in rendered
    assert "broken.yaml" in rendered.replace("\\", "/")

    async with session_scope(session_factory) as session:
        total = await session.scalar(select(func.count()).select_from(Question))
    assert total == 2


async def test_question_removed_from_file_stays_with_its_statistics(
    session_factory, tmp_path
):
    root = write_bank(tmp_path / "bank")
    async with session_scope(session_factory) as session:
        await import_directory(session, root)
        session.add(make_user())

    async with session_scope(session_factory) as session:
        session.add(
            Answer(
                user_id=1,
                question_id="dev.ch08.002",
                source=AnswerSource.PRIVATE,
                is_correct=True,
                answered_at=datetime(2026, 3, 10, tzinfo=UTC),
                quiz_date=date(2026, 3, 10),
            )
        )

    (root / "ch08.yaml").write_text(
        FILE.format(text="Первый вопрос?").split("  - id: dev.ch08.002")[0],
        encoding="utf-8",
    )

    async with session_scope(session_factory) as session:
        await import_directory(session, root)
        survivor = await session.get(Question, "dev.ch08.002")
        answers = await session.scalar(
            select(func.count()).select_from(Answer).where(
                Answer.question_id == "dev.ch08.002"
            )
        )

    assert survivor is not None
    assert answers == 1


async def test_export_import_round_trip(session_factory, tmp_path, engine):
    from app.core.db import create_engine, create_session_factory
    from app.models import Base

    root = write_bank(tmp_path / "bank")
    async with session_scope(session_factory) as session:
        await import_directory(session, root)

    export_dir = tmp_path / "export"
    async with session_scope(session_factory) as session:
        files = await export_questions(session, export_dir)
        original = {
            question.id: (
                question.text,
                question.category,
                str(question.difficulty),
                question.explanation,
                question.reference,
                tuple((option.text, option.is_correct) for option in question.options),
            )
            for question in await session.scalars(select(Question))
        }
    assert files == 1

    clean_engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'clean.sqlite3'}")
    async with clean_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    clean_factory = create_session_factory(clean_engine)
    try:
        async with session_scope(clean_factory) as session:
            report = await import_directory(session, export_dir)
        assert report.added == 2

        async with session_scope(clean_factory) as session:
            restored = {
                question.id: (
                    question.text,
                    question.category,
                    str(question.difficulty),
                    question.explanation,
                    question.reference,
                    tuple(
                        (option.text, option.is_correct) for option in question.options
                    ),
                )
                for question in await session.scalars(select(Question))
            }
    finally:
        await clean_engine.dispose()

    assert restored == original
