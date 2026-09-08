"""Служебные команды: `python -m app.cli <команда>`.

Команды работают с той же БД, что и бот, и не требуют запущенного процесса.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.core.config import ConfigError, load_settings
from app.core.db import create_engine, create_session_factory, session_scope
from app.core.logging import setup_logging
from app.services.content.importer import (
    QuestionImportError,
    export_questions,
    import_directory,
)
from app.services.stats.recalc import recalculate_stats

DEFAULT_QUESTIONS_DIR = Path("data/questions")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    importer = commands.add_parser(
        "import-questions", help="загрузить вопросы из каталога файлов-источников"
    )
    importer.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=DEFAULT_QUESTIONS_DIR,
        help=f"каталог с файлами вопросов (по умолчанию {DEFAULT_QUESTIONS_DIR})",
    )

    exporter = commands.add_parser(
        "export-questions", help="выгрузить банк в формат, пригодный для импорта"
    )
    exporter.add_argument("path", type=Path, help="каталог, куда писать файлы")

    commands.add_parser(
        "recalc-stats", help="пересчитать агрегаты статистики по таблице ответов"
    )
    return parser


async def _import(path: Path) -> int:
    settings = load_settings()
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        async with session_scope(factory) as session:
            report = await import_directory(session, path)
    except QuestionImportError as exc:
        print(f"Импорт отклонён, банк не изменён. Найдено проблем: {len(exc.issues)}")
        for issue in exc.issues:
            print(f"  - {issue}")
        return 1
    finally:
        await engine.dispose()

    print(report.render())
    return 0


async def _export(path: Path) -> int:
    settings = load_settings()
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        async with session_scope(factory) as session:
            files = await export_questions(session, path)
    finally:
        await engine.dispose()

    print(f"Выгружено файлов: {files} в каталог {path}")
    return 0


async def _recalc() -> int:
    settings = load_settings()
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        async with session_scope(factory) as session:
            report = await recalculate_stats(session)
    finally:
        await engine.dispose()

    print(report.render())
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 2
    setup_logging(settings.log_level)

    if arguments.command == "import-questions":
        return asyncio.run(_import(arguments.path))
    if arguments.command == "export-questions":
        return asyncio.run(_export(arguments.path))
    return asyncio.run(_recalc())


if __name__ == "__main__":
    raise SystemExit(main())
