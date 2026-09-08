"""Настройки времени выполнения — таблица `settings` вида ключ-значение.

Меняются из кабинета и применяются немедленно: кэш в памяти сбрасывается при
записи, поэтому перезапуск не нужен (см. `design.md`, «Настройки: два уровня»).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import DEFAULT_TIMEZONE, utc_now
from app.models import LimitMode, Setting

KEY_SESSION_SIZE: Final = "session_size"
KEY_LEADERBOARD_ROWS: Final = "leaderboard_rows"
KEY_TIMEZONE: Final = "timezone"
KEY_LIMIT_MODE: Final = "limit_mode"
KEY_QUIZ_LIMIT: Final = "daily_quiz_limit"
KEY_RANDOM_LIMIT: Final = "daily_random_limit"
KEY_SESSION_TIMEOUT: Final = "session_timeout_minutes"

DEFAULTS: Final[dict[str, str]] = {
    KEY_SESSION_SIZE: "10",
    KEY_LEADERBOARD_ROWS: "10",
    KEY_TIMEZONE: DEFAULT_TIMEZONE,
    KEY_LIMIT_MODE: LimitMode.ENABLED.value,
    KEY_QUIZ_LIMIT: "5",
    KEY_RANDOM_LIMIT: "20",
    KEY_SESSION_TIMEOUT: "180",
}

MIN_SESSION_SIZE: Final = 1
MAX_SESSION_SIZE: Final = 50
MIN_LEADERBOARD_ROWS: Final = 3
MAX_LEADERBOARD_ROWS: Final = 50


class SettingsValidationError(ValueError):
    """Значение отклонено — прежнее остаётся в силе."""


@dataclass(slots=True)
class RuntimeSettings:
    """Снимок настроек на момент чтения."""

    session_size: int
    leaderboard_rows: int
    timezone: str
    limit_mode: LimitMode
    quiz_limit: int
    random_limit: int
    session_timeout_minutes: int


class SettingsService:
    """Чтение и запись настроек с кэшем, общим для процесса."""

    _cache: ClassVar[dict[str, str] | None] = None

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def reset_cache(cls) -> None:
        """Сбросить кэш — вызывается при записи и в тестах."""
        cls._cache = None

    async def _values(self) -> dict[str, str]:
        if SettingsService._cache is None:
            rows = await self._session.scalars(select(Setting))
            stored = {row.key: row.value for row in rows}
            SettingsService._cache = {**DEFAULTS, **stored}
        return SettingsService._cache

    async def get(self) -> RuntimeSettings:
        values = await self._values()
        return RuntimeSettings(
            session_size=int(values[KEY_SESSION_SIZE]),
            leaderboard_rows=int(values[KEY_LEADERBOARD_ROWS]),
            timezone=values[KEY_TIMEZONE],
            limit_mode=LimitMode(values[KEY_LIMIT_MODE]),
            quiz_limit=int(values[KEY_QUIZ_LIMIT]),
            random_limit=int(values[KEY_RANDOM_LIMIT]),
            session_timeout_minutes=int(values[KEY_SESSION_TIMEOUT]),
        )

    async def set_raw(self, key: str, value: str) -> None:
        stored = await self._session.get(Setting, key)
        if stored is None:
            self._session.add(Setting(key=key, value=value, updated_at=utc_now()))
        else:
            stored.value = value
            stored.updated_at = utc_now()
        await self._session.flush()
        SettingsService.reset_cache()

    async def set_session_size(self, value: int) -> None:
        _require_range(value, MIN_SESSION_SIZE, MAX_SESSION_SIZE, "Размер сессии")
        await self.set_raw(KEY_SESSION_SIZE, str(value))

    async def set_leaderboard_rows(self, value: int) -> None:
        _require_range(
            value, MIN_LEADERBOARD_ROWS, MAX_LEADERBOARD_ROWS, "Число строк рейтинга"
        )
        await self.set_raw(KEY_LEADERBOARD_ROWS, str(value))

    async def set_timezone(self, value: str) -> None:
        """Сменить таймзону суточного сброса.

        Уже сохранённые дневные итоги не пересчитываются: их дата записана
        по действовавшей тогда таймзоне.
        """
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise SettingsValidationError(f"Неизвестная таймзона: {value}") from exc
        await self.set_raw(KEY_TIMEZONE, value)

    async def set_limit_mode(self, mode: LimitMode) -> None:
        await self.set_raw(KEY_LIMIT_MODE, mode.value)

    async def set_quiz_limit(self, value: int) -> None:
        _require_positive(value, "Лимит запусков викторины")
        await self.set_raw(KEY_QUIZ_LIMIT, str(value))

    async def set_random_limit(self, value: int) -> None:
        _require_positive(value, "Лимит случайных вопросов")
        await self.set_raw(KEY_RANDOM_LIMIT, str(value))


def _require_positive(value: int, what: str) -> None:
    if value <= 0:
        raise SettingsValidationError(
            f"{what} должен быть положительным числом, получено {value}."
        )


def _require_range(value: int, low: int, high: int, what: str) -> None:
    if not low <= value <= high:
        raise SettingsValidationError(
            f"{what} должен быть от {low} до {high}, получено {value}."
        )
