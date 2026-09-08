from datetime import UTC, date, datetime, time

from app.core.time import (
    format_local,
    is_within_window,
    next_midnight,
    quiz_date,
    to_timezone,
)

MSK = "Europe/Moscow"


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def test_quiz_date_before_moscow_midnight():
    # 20:59 UTC = 23:59 MSK того же дня
    assert quiz_date(utc(2026, 3, 10, 20, 59), MSK) == date(2026, 3, 10)


def test_quiz_date_after_moscow_midnight():
    # 21:00 UTC = 00:00 MSK следующего дня
    assert quiz_date(utc(2026, 3, 10, 21, 0), MSK) == date(2026, 3, 11)


def test_quiz_date_uses_configured_timezone():
    moment = utc(2026, 3, 10, 21, 0)
    assert quiz_date(moment, "UTC") == date(2026, 3, 10)
    assert quiz_date(moment, MSK) == date(2026, 3, 11)


def test_naive_datetime_is_treated_as_utc():
    assert quiz_date(datetime(2026, 3, 10, 21, 0), MSK) == date(2026, 3, 11)


def test_next_midnight_is_the_upcoming_local_midnight():
    moment = utc(2026, 3, 10, 20, 59)  # 23:59 MSK
    assert next_midnight(moment, MSK) == utc(2026, 3, 10, 21, 0)


def test_window_inside_one_day():
    # окно 09:00–18:00 MSK
    start, end = time(9, 0), time(18, 0)
    assert not is_within_window(utc(2026, 3, 10, 5, 59), start, end, MSK)  # 08:59
    assert is_within_window(utc(2026, 3, 10, 6, 0), start, end, MSK)  # 09:00
    assert is_within_window(utc(2026, 3, 10, 14, 59), start, end, MSK)  # 17:59
    assert not is_within_window(utc(2026, 3, 10, 15, 0), start, end, MSK)  # 18:00


def test_window_crossing_midnight():
    # окно 22:00–06:00 MSK
    start, end = time(22, 0), time(6, 0)
    assert is_within_window(utc(2026, 3, 10, 19, 30), start, end, MSK)  # 22:30
    assert is_within_window(utc(2026, 3, 10, 22, 0), start, end, MSK)  # 01:00
    assert not is_within_window(utc(2026, 3, 10, 4, 0), start, end, MSK)  # 07:00
    assert not is_within_window(utc(2026, 3, 10, 3, 0), start, end, MSK)  # 06:00


def test_equal_bounds_mean_round_the_clock():
    assert is_within_window(utc(2026, 3, 10, 3, 0), time(0, 0), time(0, 0), MSK)


def test_to_timezone_and_format():
    moment = utc(2026, 3, 10, 21, 0)
    assert to_timezone(moment, MSK).hour == 0
    assert format_local(moment, MSK) == "11.03.2026 00:00"
