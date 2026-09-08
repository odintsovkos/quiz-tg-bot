"""Точка входа процесса бота: `python -m app.main`.

Спека `bot-core`, «Корректный запуск и остановка»: при нехватке конфигурации
процесс завершается внятным сообщением; по сигналу остановки останавливается
опрос Telegram, затем планировщик, затем закрывается движок БД.
"""

from __future__ import annotations

import asyncio
import signal
import sys

from aiogram.exceptions import TelegramUnauthorizedError

from app.core.config import ConfigError, Settings, load_settings
from app.core.container import Application, build_application
from app.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    """Перевести сигналы остановки в событие; на Windows часть их недоступна."""
    loop = asyncio.get_running_loop()
    for signal_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, signal_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:  # pragma: no cover - платформозависимо
            signal.signal(sig, lambda *_: stop_event.set())


async def run(settings: Settings) -> None:
    """Собрать приложение, вести опрос до сигнала и корректно завершиться."""
    application: Application = build_application(settings)
    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    try:
        await application.start()
        polling = asyncio.create_task(
            application.dispatcher.start_polling(application.bot, handle_signals=False)
        )
        stopper = asyncio.create_task(stop_event.wait())
        done, pending = await asyncio.wait(
            {polling, stopper}, return_when=asyncio.FIRST_COMPLETED
        )
        if polling in done:
            polling.result()  # пробросить ошибку опроса, если она была
        else:
            await application.dispatcher.stop_polling()
            await polling
        for task in pending:
            task.cancel()
    finally:
        await application.shutdown()


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 2

    setup_logging(settings.log_level)
    try:
        asyncio.run(run(settings))
    except TelegramUnauthorizedError:
        # Отдельно от прочих ошибок: почти всегда это опечатка в BOT_TOKEN,
        # и трассировка тут ничего не добавляет.
        print(
            "Telegram отклонил токен. Проверьте BOT_TOKEN в окружении или .env.",
            file=sys.stderr,
        )
        return 2
    except KeyboardInterrupt:  # pragma: no cover - интерактивная остановка
        logger.info("interrupted by user")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
