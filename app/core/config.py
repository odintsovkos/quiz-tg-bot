"""Конфигурация развёртывания: читается один раз при старте процесса.

Настройки, которые администратор меняет из кабинета, живут не здесь,
а в таблице `settings` (см. `app/services/settings.py`).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(RuntimeError):
    """Конфигурация неполна или некорректна — запуск невозможен."""


class Settings(BaseSettings):
    """Переменные окружения развёртывания."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: str = Field(alias="BOT_TOKEN", min_length=1)
    owner_id: int = Field(alias="OWNER_ID")
    db_path: Path = Field(default=Path("data/quizbot.sqlite3"), alias="DB_PATH")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    default_timezone: str = Field(default="Europe/Moscow", alias="DEFAULT_TIMEZONE")

    @field_validator("log_level")
    @classmethod
    def _check_log_level(cls, value: str) -> str:
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL должен быть одним из {sorted(allowed)}")
        return upper

    @field_validator("default_timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:  # pragma: no cover - зависит от ОС
            raise ValueError(f"DEFAULT_TIMEZONE — неизвестная таймзона: {value}") from exc
        return value

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"


def _missing_names(error: ValidationError) -> list[str]:
    names: list[str] = []
    for item in error.errors():
        location = item["loc"]
        if location:
            names.append(str(location[0]).upper())
    return names


def load_settings() -> Settings:
    """Собрать настройки, превратив ошибку валидации во внятное сообщение.

    Спека `bot-core`, сценарий «Отсутствует обязательная настройка»: запуск
    прерывается сообщением, называющим недостающий параметр.
    """
    try:
        return Settings()  # type: ignore[call-arg]  # значения приходят из окружения
    except ValidationError as exc:
        names = ", ".join(_missing_names(exc)) or "неизвестный параметр"
        raise ConfigError(
            f"Не заданы или некорректны обязательные настройки: {names}. "
            "Заполните их в окружении или в файле .env (см. .env.example)."
        ) from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Настройки процесса; кэшируются на весь его жизненный цикл."""
    return load_settings()
