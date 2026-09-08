"""Участники, настройки времени выполнения и подключённые чаты."""

from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import BigInteger, Boolean, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, EnumText
from app.models.enums import UserRole


class User(Base):
    """Профиль участника.

    Спека `bot-core`: хранятся только идентификатор, имя для отображения,
    username и моменты первого и последнего взаимодействия.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    role: Mapped[UserRole] = mapped_column(
        EnumText(UserRole, 16), default=UserRole.USER, server_default=UserRole.USER.value
    )
    display_name: Mapped[str] = mapped_column(String(256))
    username: Mapped[str | None] = mapped_column(String(64), default=None)
    first_seen_at: Mapped[datetime] = mapped_column()
    last_seen_at: Mapped[datetime] = mapped_column()
    anchor_message_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    """Сообщение-якорь личной переписки: единственный экран, который правится.

    Живёт в БД, а не в FSM: хранилище FSM у нас в памяти и перезапуск
    процесса не переживает.
    """


class Setting(Base):
    """Настройка времени выполнения: меняется из кабинета без перезапуска."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text())
    updated_at: Mapped[datetime] = mapped_column()


class Chat(Base):
    """Подключённый групповой чат с собственным расписанием.

    Периодичность, окно активности и категории живут здесь, а не в общей
    таблице настроек: они по определению у каждого чата свои.
    """

    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="1")
    interval_minutes: Mapped[int] = mapped_column(Integer(), default=180, server_default="180")
    window_start: Mapped[time] = mapped_column(Time(), default=time(9, 0))
    window_end: Mapped[time] = mapped_column(Time(), default=time(21, 0))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    categories: Mapped[str | None] = mapped_column(Text(), default=None)
    topic_id: Mapped[int | None] = mapped_column(Integer(), default=None)
    """Ветка публикации — тема форума. Пусто означает общую ленту чата."""
    topic_title: Mapped[str | None] = mapped_column(String(256), default=None)
    """Название темы на момент привязки.

    Хранится, потому что показать в кабинете голый идентификатор бессмысленно,
    а спросить имя темы у Telegram по идентификатору нечем.
    """
    round_number: Mapped[int] = mapped_column(Integer(), default=1, server_default="1")
    connected_at: Mapped[datetime] = mapped_column()
    connected_by: Mapped[int] = mapped_column(BigInteger)

    @property
    def category_list(self) -> list[str]:
        """Категории чата; пустой список означает «все категории»."""
        if not self.categories:
            return []
        return [item for item in self.categories.split("\n") if item]

    def set_categories(self, values: list[str]) -> None:
        self.categories = "\n".join(values) if values else None
