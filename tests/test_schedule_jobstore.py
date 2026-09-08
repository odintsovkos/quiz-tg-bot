"""Задача расписания в настоящем планировщике APScheduler.

Остальные тесты расписания работают на подставном планировщике и потому
не проверяют ни то, что задача вообще создаётся, ни то, что она ссылается
на функцию уровня модуля, а не на связанный метод.
"""

from __future__ import annotations

from datetime import UTC, datetime, time

import pytest

from app.core.scheduler import create_scheduler
from app.models import Chat
from app.services.quiz.schedule import (
    ScheduleService,
    job_id,
    publish_scheduled_job,
)
from tests.screen import ScreenBot

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


@pytest.fixture
async def scheduler(tmp_path):
    scheduler = create_scheduler("Europe/Moscow")
    scheduler.start(paused=True)
    try:
        yield scheduler
    finally:
        scheduler.shutdown(wait=False)


def make_chat(chat_id: int = -1002895411698) -> Chat:
    return Chat(
        id=chat_id,
        title="Чат 1С",
        is_active=True,
        interval_minutes=180,
        window_start=time(9, 0),
        window_end=time(21, 0),
        timezone="Europe/Moscow",
        round_number=1,
        connected_at=MOMENT,
        connected_by=1,
    )


async def test_connecting_a_chat_creates_its_job(scheduler, session_factory):
    """Подключение чата не должно падать ни на сериализации, ни на блокировке."""
    chat = make_chat()
    service = ScheduleService(scheduler, session_factory, ScreenBot())

    service.apply(chat)

    stored = scheduler.get_job(job_id(chat.id))
    assert stored is not None
    assert stored.args == (chat.id,)


async def test_the_job_points_at_a_module_level_function(scheduler, session_factory):
    """Связанный метод утащил бы за собой планировщик — см. `schedule.py`."""
    chat = make_chat()
    ScheduleService(scheduler, session_factory, ScreenBot()).apply(chat)

    stored = scheduler.get_job(job_id(chat.id))

    assert stored.func is publish_scheduled_job


async def test_removing_a_chat_drops_its_job(scheduler, session_factory):
    chat = make_chat()
    service = ScheduleService(scheduler, session_factory, ScreenBot())
    service.apply(chat)

    service.remove(chat.id)

    assert scheduler.get_job(job_id(chat.id)) is None
