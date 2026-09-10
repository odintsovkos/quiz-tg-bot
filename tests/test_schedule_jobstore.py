"""Задача расписания в настоящем планировщике APScheduler.

Остальные тесты расписания работают на подставном планировщике и потому
не проверяют ни то, что задача вообще создаётся, ни то, что она ссылается
на функцию уровня модуля, а не на связанный метод.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.scheduler import create_scheduler
from app.models import Chat
from app.services.quiz.schedule import (
    ScheduleService,
    job_id,
    job_prefix,
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


def slot_times(scheduler, chat_id: int) -> list[time]:
    """Моменты публикации чата, как их видит планировщик."""
    prefix = job_prefix(chat_id)
    moments = []
    for job in scheduler.get_jobs():
        if not job.id.startswith(prefix):
            continue
        parts = {field.name: str(field) for field in job.trigger.fields}
        moments.append(time(int(parts["hour"]), int(parts["minute"])))
    return sorted(moments)


async def test_connecting_a_chat_creates_its_job(scheduler, session_factory):
    """Подключение чата не должно падать ни на сериализации, ни на блокировке."""
    chat = make_chat()
    service = ScheduleService(scheduler, session_factory, ScreenBot())

    service.apply(chat)

    stored = scheduler.get_job(job_id(chat.id, time(9, 0)))
    assert stored is not None
    assert stored.args == (chat.id,)


async def test_the_job_points_at_a_module_level_function(scheduler, session_factory):
    """Связанный метод утащил бы за собой планировщик — см. `schedule.py`."""
    chat = make_chat()
    ScheduleService(scheduler, session_factory, ScreenBot()).apply(chat)

    stored = scheduler.get_job(job_id(chat.id, time(9, 0)))

    assert stored.func is publish_scheduled_job


async def test_removing_a_chat_drops_every_job_of_its_own(scheduler, session_factory):
    chat = make_chat()
    service = ScheduleService(scheduler, session_factory, ScreenBot())
    service.apply(chat)

    service.remove(chat.id)

    assert slot_times(scheduler, chat.id) == []


async def test_slots_are_anchored_to_the_window_start(scheduler, session_factory):
    """Сетка идёт от начала окна, а не от момента создания задач."""
    chat = make_chat()

    ScheduleService(scheduler, session_factory, ScreenBot()).apply(chat)

    assert slot_times(scheduler, chat.id) == [
        time(9, 0),
        time(12, 0),
        time(15, 0),
        time(18, 0),
    ]


async def test_the_next_run_is_the_window_start_whatever_the_hour(
    scheduler, session_factory
):
    """Прежний `interval`-триггер дал бы 10:22 при запуске в 19:22."""
    chat = make_chat()
    ScheduleService(scheduler, session_factory, ScreenBot()).apply(chat)
    evening = datetime(2026, 9, 10, 19, 22, tzinfo=ZoneInfo("Europe/Moscow"))

    upcoming = min(
        job.trigger.get_next_fire_time(None, evening)
        for job in scheduler.get_jobs()
        if job.id.startswith(job_prefix(chat.id))
    )

    assert (upcoming.hour, upcoming.minute) == (9, 0)
    assert upcoming.date() == evening.date() + timedelta(days=1)


async def test_rebuilding_keeps_the_same_slots(scheduler, session_factory, session):
    """Перезапуск процесса не должен сдвигать расписание."""
    chat = make_chat()
    session.add(chat)
    await session.commit()
    service = ScheduleService(scheduler, session_factory, ScreenBot())

    await service.rebuild()
    first = slot_times(scheduler, chat.id)
    await service.rebuild()

    assert first == slot_times(scheduler, chat.id)
    assert first == [time(9, 0), time(12, 0), time(15, 0), time(18, 0)]


async def test_changing_categories_does_not_move_the_slots(scheduler, session_factory):
    """`apply` зовётся на любой правке чата и раньше переанкоривал сетку."""
    chat = make_chat()
    service = ScheduleService(scheduler, session_factory, ScreenBot())
    service.apply(chat)
    before = slot_times(scheduler, chat.id)

    chat.set_categories(["Разработка"])
    service.apply(chat)

    assert slot_times(scheduler, chat.id) == before


async def test_a_shorter_interval_refills_the_window(scheduler, session_factory):
    chat = make_chat()
    service = ScheduleService(scheduler, session_factory, ScreenBot())
    service.apply(chat)

    chat.interval_minutes = 360
    service.apply(chat)

    assert slot_times(scheduler, chat.id) == [time(9, 0), time(15, 0)]


async def test_removing_a_chat_spares_a_chat_with_an_id_prefix(
    scheduler, session_factory
):
    """`-100123` не должен снимать задачи `-1001234`."""
    short = make_chat(-100123)
    long = make_chat(-1001234)
    service = ScheduleService(scheduler, session_factory, ScreenBot())
    service.apply(short)
    service.apply(long)

    service.remove(short.id)

    assert slot_times(scheduler, short.id) == []
    assert slot_times(scheduler, long.id) == [
        time(9, 0),
        time(12, 0),
        time(15, 0),
        time(18, 0),
    ]


async def test_a_paused_chat_keeps_no_jobs(scheduler, session_factory):
    chat = make_chat()
    service = ScheduleService(scheduler, session_factory, ScreenBot())
    service.apply(chat)

    chat.is_active = False
    service.apply(chat)

    assert slot_times(scheduler, chat.id) == []
