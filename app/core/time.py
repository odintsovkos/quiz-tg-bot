"""Время и таймзоны.

Все моменты хранятся в UTC; перевод в действующую таймзону происходит только
на границах: вычисление даты викторины, проверка окна активности, отображение
(см. `design.md`, «Суточные границы считаются от даты ответа»).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Europe/Moscow"


def utc_now() -> datetime:
    """Текущий момент в UTC с явной таймзоной."""
    return datetime.now(tz=UTC)


def as_utc(moment: datetime) -> datetime:
    """Привести момент к UTC; наивное время считается уже UTC."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def to_timezone(moment: datetime, tz_name: str) -> datetime:
    """Перевести момент в указанную таймзону."""
    return as_utc(moment).astimezone(ZoneInfo(tz_name))


def quiz_date(moment: datetime, tz_name: str = DEFAULT_TIMEZONE) -> date:
    """Дата викторины — календарная дата момента в действующей таймзоне.

    Именно она служит ключом дневной статистики и дневных лимитов, поэтому
    новый день начинается сам собой: у первого ответа после полуночи уже
    другая дата, даже если процесс в полночь не работал.
    """
    return to_timezone(moment, tz_name).date()


def next_midnight(moment: datetime, tz_name: str = DEFAULT_TIMEZONE) -> datetime:
    """Момент ближайшей полуночи после `moment` — время обновления лимитов (UTC)."""
    local = to_timezone(moment, tz_name)
    tomorrow = local.date() + timedelta(days=1)
    local_midnight = datetime.combine(tomorrow, time(0, 0), tzinfo=ZoneInfo(tz_name))
    return local_midnight.astimezone(UTC)


def is_within_window(
    moment: datetime,
    start: time,
    end: time,
    tz_name: str = DEFAULT_TIMEZONE,
) -> bool:
    """Попадает ли момент в окно активности `[start, end)` в данной таймзоне.

    Окно, у которого начало позже окончания, считается пересекающим полночь
    (например 22:00–06:00). Равные границы означают круглосуточное окно.
    """
    local_time = to_timezone(moment, tz_name).time()
    if start == end:
        return True
    if start < end:
        return start <= local_time < end
    return local_time >= start or local_time < end


def format_local(
    moment: datetime,
    tz_name: str = DEFAULT_TIMEZONE,
    fmt: str = "%d.%m.%Y %H:%M",
) -> str:
    """Отобразить момент в действующей таймзоне."""
    return to_timezone(moment, tz_name).strftime(fmt)
