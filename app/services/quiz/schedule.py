"""Расписание автопубликации.

На каждый активный чат — задача типа `interval` с `coalesce=True` и
`misfire_grace_time` в один интервал: после простоя публикуется не более
одного вопроса, пропущенные интервалы не догоняются.

Окно активности проверяет сама задача при срабатывании, а не расписание, —
поэтому изменение окна не требует пересоздания задач.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from apscheduler.schedulers.base import BaseScheduler
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.core.db import SessionFactory, session_scope
from app.core.logging import get_logger
from app.core.time import is_within_window, utc_now
from app.models import Chat, UserRole
from app.repositories.chats import ChatRepository
from app.repositories.users import UserRepository
from app.services.quiz.group import (
    ChatUnavailableError,
    GroupQuizService,
)

logger = get_logger(__name__)

JOB_PREFIX = "chat-publish-"


def job_id(chat_id: int) -> str:
    return f"{JOB_PREFIX}{chat_id}"


@dataclass(slots=True)
class JobContext:
    """Ресурсы процесса, из которых задача собирает себе сервис.

    Хранилище задач в SQLite пиклит всё, до чего дотянется через `func` и
    `args`. Связанный метод утащил бы за собой сам планировщик, а он
    не сериализуем, поэтому задача — функция уровня модуля с примитивным
    аргументом, а ресурсы она берёт отсюда.
    """

    scheduler: BaseScheduler
    session_factory: SessionFactory
    bot: Bot


_context: JobContext | None = None


def bind_jobs(scheduler: BaseScheduler, session_factory: SessionFactory, bot: Bot) -> None:
    """Связать задачи расписания с ресурсами текущего процесса."""
    global _context
    _context = JobContext(scheduler, session_factory, bot)


async def publish_scheduled_job(chat_id: int) -> bool:
    """Цель задачи APScheduler. Ссылается по имени модуля, не пиклится."""
    if _context is None:  # pragma: no cover - задача без запущенного процесса
        logger.error("schedule job fired before the process was bound")
        return False
    service = ScheduleService(
        _context.scheduler, _context.session_factory, _context.bot
    )
    return await service.publish_scheduled(chat_id)


class ScheduleService:
    """Единственная точка, где задачи создаются, обновляются и снимаются."""

    def __init__(
        self,
        scheduler: BaseScheduler,
        session_factory: SessionFactory,
        bot: Bot,
    ) -> None:
        self._scheduler = scheduler
        self._session_factory = session_factory
        self._bot = bot

    async def rebuild(self) -> int:
        """Пересобрать задачи по таблице чатов.

        Источник истины — таблица чатов, а не сохранённые задачи: иначе
        отключённый чат мог бы остаться с живой задачей.
        """
        for job in self._scheduler.get_jobs():
            if job.id.startswith(JOB_PREFIX):
                job.remove()

        async with session_scope(self._session_factory) as session:
            chats = await ChatRepository(session).list_active()

        for chat in chats:
            self._schedule(chat)
        logger.info("schedule rebuilt", extra={"chats": len(chats)})
        return len(chats)

    def apply(self, chat: Chat) -> None:
        """Применить настройки чата немедленно, без перезапуска бота."""
        self.remove(chat.id)
        if chat.is_active:
            self._schedule(chat)

    def remove(self, chat_id: int) -> None:
        job = self._scheduler.get_job(job_id(chat_id))
        if job is not None:
            job.remove()

    def _schedule(self, chat: Chat) -> None:
        interval_seconds = chat.interval_minutes * 60
        self._scheduler.add_job(
            publish_scheduled_job,
            trigger="interval",
            seconds=interval_seconds,
            id=job_id(chat.id),
            args=[chat.id],
            coalesce=True,
            misfire_grace_time=interval_seconds,
            replace_existing=True,
        )

    @asynccontextmanager
    async def _work(
        self, existing: AsyncSession | None
    ) -> AsyncIterator[AsyncSession]:
        """Сессия события, если она есть, иначе своя короткая транзакция.

        Открыть вторую сессию поверх уже идущей — это второй писатель в тот же
        файл SQLite: внешняя транзакция держит блокировку до возврата из
        хендлера, а вложенная запись ждёт её и не дожидается никогда.
        Из задачи планировщика внешней сессии нет, поэтому она нужна своя.
        """
        if existing is not None:
            yield existing
            return
        async with session_scope(self._session_factory) as session:
            yield session

    async def publish_scheduled(
        self,
        chat_id: int,
        *,
        now: datetime | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        """Публикация по расписанию: вне окна активности — молча выйти."""
        moment = now or utc_now()
        async with self._work(session) as work:
            chat = await ChatRepository(work).get(chat_id)
            if chat is None or not chat.is_active:
                return False
            if not is_within_window(
                moment, chat.window_start, chat.window_end, chat.timezone
            ):
                return False

        return await self.publish_now(chat_id, now=moment, session=session)

    async def publish_now(
        self,
        chat_id: int,
        *,
        now: datetime | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        """Опубликовать вопрос немедленно, не сдвигая расписание.

        Расписание не трогаем сознательно: задача `interval` продолжает
        срабатывать в свои моменты (спека `group-quiz`, «Ручной запуск»).
        """
        async with self._work(session) as session:
            chat = await ChatRepository(session).get(chat_id)
            if chat is None:
                return False

            service = GroupQuizService(session)
            try:
                outcome = await service.publish(self._bot, chat, now=now)
            except ChatUnavailableError:
                chat.is_active = False
                await session.flush()
                self.remove(chat_id)
                await self._notify_admins(
                    session, texts.NOTIFY_CHAT_UNAVAILABLE.format(chat=chat.title)
                )
                return False

            if outcome.empty_bank:
                await self._notify_admins(
                    session, texts.NOTIFY_EMPTY_BANK.format(chat=chat.title)
                )
                return False

            if outcome.topic_lost:
                # Вопрос опубликован в общую ленту, но администратор должен
                # узнать, что тема отвалилась и её нужно задать заново.
                await self._notify_admins(
                    session, texts.TOPIC_LOST.format(chat=chat.title)
                )
        return True

    async def _notify_admins(self, session: AsyncSession, text: str) -> None:
        """Уведомить администраторов в личке."""
        admins = await UserRepository(session).list_by_roles(
            (UserRole.ADMIN, UserRole.OWNER)
        )
        for admin in admins:
            try:
                await self._bot.send_message(admin.id, text)
            except Exception:  # один недоступный администратор не мешает остальным
                logger.warning("could not notify admin", extra={"user_id": admin.id})
