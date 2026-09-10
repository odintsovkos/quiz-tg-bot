"""Расписание автопубликации.

На каждый момент публикации активного чата — своя `cron`-задача с
`coalesce=True` и фиксированным `misfire_grace_time`: после простоя
публикуется не более одного вопроса, пропущенные моменты не догоняются.

Моменты берутся у `publication_slots` и отсчитываются от начала окна
активности, а `cron` привязан к настенным часам. Поэтому сетка не зависит
ни от времени запуска процесса, ни от того, когда правились настройки чата,
и переход на летнее время APScheduler отрабатывает сам. Задача типа
`interval` этого не давала: без `start_date` APScheduler подставляет
`now + interval`, и сетка привязывалась к моменту `add_job`.

Окно активности расписание не проверяет: моментов вне окна попросту нет.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, time

from aiogram import Bot
from apscheduler.schedulers.base import BaseScheduler
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.core.db import SessionFactory, session_scope
from app.core.logging import get_logger
from app.core.time import publication_slots, utc_now
from app.models import Chat, UserRole
from app.repositories.chats import ChatRepository
from app.repositories.users import UserRepository
from app.services.quiz.group import (
    ChatUnavailableError,
    GroupQuizService,
    PublicationDeferredError,
)

logger = get_logger(__name__)

JOB_PREFIX = "chat-publish-"

#: Запас на опоздание задачи. Фиксированный, а не в один интервал: сетка
#: привязана к времени суток, и публикация, опоздавшая на пару минут после
#: старта процесса, допустима, а на два часа — уже нет, это выдача не в тот
#: момент, который администратор видит в кабинете.
MISFIRE_GRACE_SECONDS = 5 * 60


def job_prefix(chat_id: int) -> str:
    """Общее начало идентификаторов задач чата.

    Разделитель на конце обязателен: без него снятие чата `-100123` задело бы
    и задачи чата `-1001234`.
    """
    return f"{JOB_PREFIX}{chat_id}-"


def job_id(chat_id: int, slot: time) -> str:
    return f"{job_prefix(chat_id)}{slot:%H%M}"


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
        prefix = job_prefix(chat_id)
        for job in self._scheduler.get_jobs():
            if job.id.startswith(prefix):
                job.remove()

    def _schedule(self, chat: Chat) -> None:
        slots = publication_slots(
            chat.window_start, chat.window_end, chat.interval_minutes
        )
        for slot in slots:
            self._scheduler.add_job(
                publish_scheduled_job,
                trigger="cron",
                hour=slot.hour,
                minute=slot.minute,
                timezone=chat.timezone,
                id=job_id(chat.id, slot),
                args=[chat.id],
                coalesce=True,
                misfire_grace_time=MISFIRE_GRACE_SECONDS,
                replace_existing=True,
            )
        logger.info(
            "chat schedule built",
            extra={"chat_id": chat.id, "slots": len(slots)},
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
        """Публикация по расписанию.

        Окно активности здесь не проверяется: моментов вне окна расписание
        не создаёт. А вот отключиться чат между созданием задачи и её
        срабатыванием мог, поэтому его состояние проверяется.
        """
        moment = now or utc_now()
        async with self._work(session) as work:
            chat = await ChatRepository(work).get(chat_id)
            if chat is None or not chat.is_active:
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

        Расписание не трогаем сознательно: `cron`-задачи чата продолжают
        срабатывать в свои моменты (спека `group-quiz`, «Ручной запуск»).
        """
        async with self._work(session) as session:
            chat = await ChatRepository(session).get(chat_id)
            if chat is None:
                return False

            service = GroupQuizService(session)
            try:
                outcome = await service.publish(self._bot, chat, now=now)
            except PublicationDeferredError:
                # Telegram недоступен — момент пропущен, но чат в порядке:
                # ни отключения, ни снятия задач, ни писем администраторам.
                # Публикация выполнится в следующий момент расписания.
                return False
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
