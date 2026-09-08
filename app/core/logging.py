"""Структурное логирование.

Одна строка на событие в формате `ключ=значение`: читается глазами и
разбирается grep'ом, не требуя внешних зависимостей.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class KeyValueFormatter(logging.Formatter):
    """Формат `время уровень логгер сообщение ключ=значение ...`."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED and not key.startswith("_")
        }
        if extras:
            rendered = " ".join(f"{key}={_render(value)}" for key, value in sorted(extras.items()))
            return f"{base} {rendered}"
        return base


def _render(value: Any) -> str:
    text = str(value)
    if any(ch.isspace() for ch in text):
        return f'"{text}"'
    return text


def setup_logging(level: str = "INFO") -> None:
    """Настроить корневой логгер один раз при старте процесса."""
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        KeyValueFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # aiogram и apscheduler на INFO слишком многословны
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
