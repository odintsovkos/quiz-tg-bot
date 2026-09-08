"""Планировщик публикаций.

APScheduler с задачами в памяти. Источник истины — таблица чатов: при старте
`ScheduleService.rebuild()` создаёт задачи по ней, поэтому переживать
перезапуск самим задачам незачем.

Хранилище задач в той же SQLite (решение архивного `design.md`) отменено:
APScheduler пишет синхронным драйвером, а сессия события в этот момент держит
транзакцию асинхронным, — второй писатель в один файл давал `database is
locked` при подключении чата. Пересборка задач по таблице чатов делала
сохранение задач бесполезным и до того.
"""

from __future__ import annotations

from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler


def create_scheduler(timezone: str) -> AsyncIOScheduler:
    return AsyncIOScheduler(
        jobstores={"default": MemoryJobStore()},
        timezone=timezone,
        job_defaults={"coalesce": True, "max_instances": 1},
    )
