"""Базовый класс ORM и общие типы колонок."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Date, DateTime, MetaData, String
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """Момент времени, всегда возвращаемый с таймзоной UTC.

    SQLite не хранит смещение и отдаёт наивное значение; без этой обёртки
    сравнение прочитанного момента с `utc_now()` падало бы на смешении
    наивного и осведомлённого времени.
    """

    impl = DateTime
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(timezone=True)

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Общий предок моделей.

    Соглашение об именах нужно, чтобы `alembic revision --autogenerate`
    давал стабильные имена ограничений, а не случайные.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map = {  # noqa: RUF012 - контракт SQLAlchemy
        datetime: UtcDateTime(),
        date: Date(),
    }


class EnumText(TypeDecorator[Any]):
    """Хранение StrEnum текстом с обратным преобразованием при чтении.

    Без него из БД возвращалась бы обычная строка, и сравнение `role is
    UserRole.OWNER` молча давало бы ложь.
    """

    impl = String
    cache_ok = True

    def __init__(self, enum_class: type[StrEnum], length: int = 32) -> None:
        self._enum_class = enum_class
        super().__init__(length=length)

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return str(self._enum_class(value).value)

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        return self._enum_class(value)
