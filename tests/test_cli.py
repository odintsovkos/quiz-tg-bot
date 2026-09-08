"""CLI проверяется на временной БД: сеть и Telegram не задействованы."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.cli import main
from app.models import Base, Question

BANK = """
manual: {id: dev, short: Разработчик}
chapter: {id: ch08, title: Глава 8. Работа с запросами}
questions:
  - id: dev.ch08.001
    text: Какое слово убирает дубли?
    difficulty: medium
    options:
      - {text: РАЗЛИЧНЫЕ, correct: true}
      - {text: ПЕРВЫЕ}
"""


@pytest.fixture
def cli_env(monkeypatch, tmp_path):
    """Окружение CLI: свой файл БД со схемой, созданной по моделям."""
    import asyncio

    from app.core.db import create_engine

    db_path = tmp_path / "cli.sqlite3"

    async def prepare() -> None:
        engine = create_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(prepare())

    monkeypatch.setenv("BOT_TOKEN", "123:fake")
    monkeypatch.setenv("OWNER_ID", "1")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.chdir(tmp_path)
    return db_path


def write_bank(tmp_path, content: str = BANK):
    root = tmp_path / "questions"
    root.mkdir(exist_ok=True)
    (root / "ch08.yaml").write_text(content, encoding="utf-8")
    return root


def test_import_questions_reports_the_result(cli_env, tmp_path, capsys):
    root = write_bank(tmp_path)

    assert main(["import-questions", str(root)]) == 0

    output = capsys.readouterr().out
    assert "Добавлено: 1" in output


def test_import_questions_rejects_a_broken_batch(cli_env, tmp_path, capsys):
    two_correct = BANK.replace(
        "      - {text: ПЕРВЫЕ}", "      - {text: ПЕРВЫЕ, correct: true}"
    )
    write_bank(tmp_path, two_correct)

    assert main(["import-questions", str(tmp_path / "questions")]) == 1
    assert "Импорт отклонён" in capsys.readouterr().out


def test_export_questions_writes_files(cli_env, tmp_path, capsys):
    root = write_bank(tmp_path)
    main(["import-questions", str(root)])
    capsys.readouterr()

    target = tmp_path / "export"
    assert main(["export-questions", str(target)]) == 0
    assert "Выгружено файлов: 1" in capsys.readouterr().out
    assert list(target.glob("*.yaml"))


def test_recalc_stats_runs_on_an_empty_bank(cli_env, capsys):
    assert main(["recalc-stats"]) == 0
    assert "Пересчитано" in capsys.readouterr().out


def test_import_defaults_to_the_repository_directory(cli_env, tmp_path, capsys):
    """Без аргумента команда берёт `data/questions/`."""
    root = tmp_path / "data" / "questions"
    root.mkdir(parents=True)
    (root / "ch08.yaml").write_text(BANK, encoding="utf-8")

    assert main(["import-questions"]) == 0
    assert "Добавлено: 1" in capsys.readouterr().out


def test_imported_question_is_readable(cli_env, tmp_path):
    """CLI сам открывает и закрывает цикл событий, поэтому тест синхронный."""
    import asyncio

    from app.core.db import create_engine, create_session_factory

    main(["import-questions", str(write_bank(tmp_path))])

    async def read() -> Question:
        engine = create_engine(f"sqlite+aiosqlite:///{cli_env}")
        try:
            factory = create_session_factory(engine)
            async with factory() as session:
                return await session.scalar(select(Question))
        finally:
            await engine.dispose()

    question = asyncio.run(read())
    assert question.id == "dev.ch08.001"
    assert question.correct_index == 0
