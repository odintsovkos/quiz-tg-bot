"""Композиционный корень: сборка и жизненный цикл приложения."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncEngine

from app.bot.factory import create_bot, create_dispatcher
from app.bot.handlers.common import register_commands
from app.core.config import Settings
from app.core.db import (
    SessionFactory,
    create_engine,
    create_session_factory,
    session_scope,
)
from app.core.logging import get_logger
from app.core.scheduler import create_scheduler
from app.services.quiz.schedule import ScheduleService, bind_jobs
from app.services.users import UserService

logger = get_logger(__name__)


@dataclass(slots=True)
class Application:
    """Собранные ресурсы процесса и их корректное закрытие."""

    settings: Settings
    engine: AsyncEngine
    session_factory: SessionFactory
    scheduler: AsyncIOScheduler
    bot: Bot
    dispatcher: Dispatcher
    _started: bool = field(default=False, init=False)

    async def start(self) -> None:
        """Поднять то, что не требует сети: роль владельца и планировщик.

        Регистрация списка команд обращается к Telegram, поэтому висит на
        startup-хуке диспетчера и выполняется при начале опроса.
        """
        async with session_scope(self.session_factory) as session:
            await UserService(session).ensure_owner(self.settings.owner_id)

        if not self.scheduler.running:
            self.scheduler.start()

        # Задачи пересобираются по таблице чатов, а не по сохранённым:
        # отключённый чат не должен остаться с живой задачей.
        await ScheduleService(self.scheduler, self.session_factory, self.bot).rebuild()

        self._started = True
        logger.info("application started", extra={"owner_id": self.settings.owner_id})

    async def shutdown(self) -> None:
        """Остановить планировщик, закрыть сессию бота и движок БД.

        Вызывается и при штатной остановке, и при ошибке запуска, поэтому
        каждый шаг переживает то, что предыдущий не выполнялся.
        """
        if self.scheduler.running:
            # AsyncIOScheduler откладывает саму остановку в цикл событий,
            # поэтому уступаем управление, чтобы она успела произойти.
            self.scheduler.shutdown(wait=False)
            await asyncio.sleep(0)
        await self.dispatcher.storage.close()
        await self.bot.session.close()
        await self.engine.dispose()
        self._started = False
        logger.info("application stopped")


def build_application(settings: Settings) -> Application:
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    scheduler = create_scheduler(settings.default_timezone)
    bot = create_bot(settings.bot_token)
    dispatcher = create_dispatcher(session_factory)

    dispatcher["settings"] = settings
    dispatcher["session_factory"] = session_factory
    dispatcher["scheduler"] = scheduler
    # Задача расписания хранится в БД и ресурсы процесса в себе не несёт:
    # она берёт их отсюда при срабатывании.
    bind_jobs(scheduler, session_factory, bot)

    dispatcher.startup.register(register_commands)

    return Application(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        scheduler=scheduler,
        bot=bot,
        dispatcher=dispatcher,
    )
