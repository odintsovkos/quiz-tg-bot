"""Повтор отправки при превышении лимита частоты Telegram.

Спека `bot-core`: система выдерживает указанную Telegram паузу и повторяет
отправку, а не теряет сообщение.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from aiogram.exceptions import TelegramRetryAfter

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

MAX_ATTEMPTS = 3


async def send_with_retry(
    action: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = MAX_ATTEMPTS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Выполнить отправку, выдерживая паузу, названную Telegram.

    Пауза берётся из самой ошибки: гадать интервал не нужно, Telegram его
    сообщает. Число попыток ограничено, чтобы бесконечно упирающийся вызов
    не заблокировал обработку.
    """
    last_error: TelegramRetryAfter | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await action()
        except TelegramRetryAfter as error:
            last_error = error
            logger.warning(
                "telegram rate limit",
                extra={"retry_after": error.retry_after, "attempt": attempt},
            )
            if attempt == max_attempts:
                break
            await sleep(error.retry_after)

    if last_error is None:  # pragma: no cover - недостижимо: цикл всегда завершится
        raise RuntimeError("отправка не выполнена и ошибка не зафиксирована")
    raise last_error
