"""Процесс викторины: личные сессии, опубликованные опросы, история выдач."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, EnumText
from app.models.enums import SessionStatus


class QuizSession(Base):
    """Личная сессия викторины.

    Состояние сессии лежит в БД, а не в FSM, поэтому сессия переживает
    перезапуск процесса.
    """

    __tablename__ = "quiz_sessions"

    id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[SessionStatus] = mapped_column(
        EnumText(SessionStatus, 16), default=SessionStatus.ACTIVE
    )
    total_questions: Mapped[int] = mapped_column(Integer())
    started_at: Mapped[datetime] = mapped_column()
    last_activity_at: Mapped[datetime] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column(default=None)

    questions: Mapped[list[SessionQuestion]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SessionQuestion.position",
        lazy="selectin",
    )
    messages: Mapped[list[SessionMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SessionMessage.id",
        lazy="selectin",
    )


class SessionMessage(Base):
    """Сообщение ленты сессии — строка реестра для последующей уборки.

    Учитываются и сообщения бота, и команда запуска, отправленная участником:
    после сессии в переписке не должно остаться ничего, кроме итога.
    """

    __tablename__ = "session_messages"
    __table_args__ = (UniqueConstraint("session_id", "message_id"),)

    id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_sessions.id", ondelete="CASCADE"), index=True
    )
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)

    session: Mapped[QuizSession] = relationship(back_populates="messages")


class SessionQuestion(Base):
    """Вопрос внутри сессии. Набор фиксируется при старте — повторов внутри нет."""

    __tablename__ = "session_questions"
    __table_args__ = (
        UniqueConstraint("session_id", "question_id"),
        UniqueConstraint("session_id", "position"),
    )

    id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_sessions.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer())
    answered: Mapped[bool] = mapped_column(Boolean(), default=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean(), default=None)
    chosen_option: Mapped[int | None] = mapped_column(Integer(), default=None)
    """Выбранный участником вариант — его показывает разбор при ошибке.

    Ответы в `Answer` хранят только верность: какой именно вариант был
    выбран, восстановить оттуда нельзя.
    """

    session: Mapped[QuizSession] = relationship(back_populates="questions")


class RandomQuestionIssue(Base):
    """Выдача одиночного случайного вопроса.

    Отдельная запись на каждую выдачу: её идентификатор попадает в данные
    кнопки, поэтому повторное нажатие по уже отвеченной выдаче отсеивается
    уникальным индексом так же, как в сессии.
    """

    __tablename__ = "random_question_issues"

    id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    issued_at: Mapped[datetime] = mapped_column()
    answered: Mapped[bool] = mapped_column(Boolean(), default=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean(), default=None)


class GroupPoll(Base):
    """Связь опубликованного quiz-опроса с вопросом и чатом.

    Обновление `poll_answer` не привязано к сообщению, поэтому соответствие
    храним сами.
    """

    __tablename__ = "group_polls"

    poll_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    message_id: Mapped[int] = mapped_column(BigInteger)
    correct_option_id: Mapped[int] = mapped_column(Integer())
    published_at: Mapped[datetime] = mapped_column()


class AskedQuestion(Base):
    """Факт выдачи вопроса в чат — основа выбора без повторов через круги."""

    __tablename__ = "asked_questions"
    __table_args__ = (UniqueConstraint("chat_id", "question_id", "round_number"),)

    id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    asked_at: Mapped[datetime] = mapped_column()
    round_number: Mapped[int] = mapped_column(Integer())
