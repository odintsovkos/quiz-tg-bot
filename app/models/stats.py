"""Учёт: ответы, агрегаты статистики, дневные лимиты, выбор тем."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, EnumText
from app.models.enums import AnswerSource


class Answer(Base):
    """Единственное место, куда пишутся результаты — и групповые, и личные.

    Идемпотентность обеспечивают частичные уникальные индексы, а не проверка
    в коде: повторный ответ упирается в нарушение уникальности, которое
    сервис перехватывает и игнорирует.

    Флаг `counted` проставляется один раз по действующему на момент ответа
    режиму лимитов и роли и больше не меняется — поэтому смена режима не
    пересчитывает прошлое.
    """

    __tablename__ = "answers"
    __table_args__ = (
        # В SQLite NULL-значения в уникальном индексе считаются различными,
        # поэтому один индекс закрывает и групповые, и личные ответы:
        # у групповых заполнен poll_id, у личных — session_id или issue_id.
        Index("uq_answers_poll_user", "poll_id", "user_id", unique=True),
        Index(
            "uq_answers_session_question",
            "session_id",
            "question_id",
            unique=True,
        ),
        Index("uq_answers_issue", "issue_id", unique=True),
        Index("ix_answers_user_quiz_date", "user_id", "quiz_date"),
    )

    id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    source: Mapped[AnswerSource] = mapped_column(EnumText(AnswerSource, 16))
    chat_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    poll_id: Mapped[str | None] = mapped_column(String(64), default=None)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("quiz_sessions.id", ondelete="SET NULL"), default=None
    )
    issue_id: Mapped[int | None] = mapped_column(
        ForeignKey("random_question_issues.id", ondelete="SET NULL"), default=None
    )
    is_correct: Mapped[bool] = mapped_column(Boolean())
    counted: Mapped[bool] = mapped_column(Boolean(), default=True)
    answered_at: Mapped[datetime] = mapped_column()
    quiz_date: Mapped[date] = mapped_column(index=True)


class UserDailyStats(Base):
    """Дневные показатели участника. Ключ — пара «участник и дата викторины»."""

    __tablename__ = "user_daily_stats"
    __table_args__ = (UniqueConstraint("user_id", "quiz_date"),)

    id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    quiz_date: Mapped[date] = mapped_column(index=True)
    attempts: Mapped[int] = mapped_column(Integer(), default=0, server_default="0")
    correct: Mapped[int] = mapped_column(Integer(), default=0, server_default="0")
    points: Mapped[int] = mapped_column(Integer(), default=0, server_default="0")


class UserTotalStats(Base):
    """Показатели за всё время. Никогда не обнуляются."""

    __tablename__ = "user_total_stats"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    attempts: Mapped[int] = mapped_column(Integer(), default=0, server_default="0")
    correct: Mapped[int] = mapped_column(Integer(), default=0, server_default="0")
    points: Mapped[int] = mapped_column(Integer(), default=0, server_default="0")


class UserDailyLimits(Base):
    """Расход дневных лимитов.

    Отдельная таблица, а не колонки дневной статистики: сессия, начатая и
    брошенная без единого ответа, лимит израсходовала, а в статистику не попала.
    """

    __tablename__ = "user_daily_limits"
    __table_args__ = (UniqueConstraint("user_id", "quiz_date"),)

    id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    quiz_date: Mapped[date] = mapped_column(index=True)
    quiz_starts: Mapped[int] = mapped_column(Integer(), default=0, server_default="0")
    random_questions: Mapped[int] = mapped_column(Integer(), default=0, server_default="0")


class UserTopicPreference(Base):
    """Выбранная участником тема. Несколько строк — несколько тем."""

    __tablename__ = "user_topic_preferences"
    __table_args__ = (UniqueConstraint("user_id", "category"),)

    id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(256))
