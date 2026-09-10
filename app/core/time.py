"""Время и таймзоны.

Все моменты хранятся в UTC; перевод в действующую таймзону происходит только
на границах: вычисление даты викторины, проверка окна активности, отображение
(см. `design.md`, «Суточные границы считаются от даты ответа»).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Europe/Moscow"

#: Суточный период сетки публикаций. Он же потолок для верхней границы
#: периодичности: интервал больше суток не мог бы означать ничего, кроме
#: «раз в день в начале окна».
MINUTES_IN_DAY = 24 * 60


def _minutes_of_day(moment: time) -> int:
    return moment.hour * 60 + moment.minute


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


def publication_slots(
    window_start: time,
    window_end: time,
    interval_minutes: int,
) -> list[time]:
    """Моменты публикации внутри окна активности — времена суток.

    Сетка отсчитывается от начала окна: первый момент приходится на само
    начало, каждый следующий — на интервал позже, последним берётся момент
    строго раньше окончания окна. Поэтому набор зависит только от настроек
    чата и одинаков при любом времени запуска процесса.

    Длительность окна считается по модулю суток, а нулевая означает
    круглосуточное окно: одна формула покрывает и обычное окно `09:00–21:00`,
    и равные границы, которые `is_within_window` уже трактует как
    круглосуточные, и окно через полночь вроде `22:00–06:00`.
    """
    if interval_minutes <= 0:
        raise ValueError("периодичность должна быть положительной")

    start = _minutes_of_day(window_start)
    span = (_minutes_of_day(window_end) - start) % MINUTES_IN_DAY or MINUTES_IN_DAY

    slots: list[time] = []
    offset = 0
    while offset < span:
        moment = (start + offset) % MINUTES_IN_DAY
        slots.append(time(hour=moment // 60, minute=moment % 60))
        offset += interval_minutes
    return slots


def format_local(
    moment: datetime,
    tz_name: str = DEFAULT_TIMEZONE,
    fmt: str = "%d.%m.%Y %H:%M",
) -> str:
    """Отобразить момент в действующей таймзоне."""
    return to_timezone(moment, tz_name).strftime(fmt)
