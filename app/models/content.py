"""Банк вопросов: вопрос и его варианты ответа."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, EnumText
from app.models.enums import Difficulty


class Question(Base):
    """Вопрос банка.

    Первичный ключ — строковый идентификатор из файла-источника
    (например `dev.ch08.001`): он переживает экспорт-импорт и правки,
    поэтому статистика по вопросу не теряется.
    """

    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    text: Mapped[str] = mapped_column(Text())
    category: Mapped[str] = mapped_column(String(256), index=True)
    difficulty: Mapped[Difficulty] = mapped_column(
        EnumText(Difficulty, 16), default=Difficulty.MEDIUM
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean(), default=True, server_default="1", index=True
    )
    explanation: Mapped[str | None] = mapped_column(Text(), default=None)
    reference: Mapped[str | None] = mapped_column(Text(), default=None)
    source_file: Mapped[str | None] = mapped_column(Text(), default=None)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, default=None)
    updated_at: Mapped[datetime | None] = mapped_column(default=None)

    options: Mapped[list[QuestionOption]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionOption.position",
        lazy="selectin",
    )

    @property
    def correct_index(self) -> int:
        """Позиция верного варианта — её ждёт нативный quiz-опрос Telegram."""
        for index, option in enumerate(self.options):
            if option.is_correct:
                return index
        raise ValueError(f"У вопроса {self.id} нет верного варианта")


class QuestionOption(Base):
    """Вариант ответа. Удаляется вместе с вопросом."""

    __tablename__ = "question_options"
    __table_args__ = (UniqueConstraint("question_id", "position"),)

    id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer())
    text: Mapped[str] = mapped_column(Text())
    is_correct: Mapped[bool] = mapped_column(Boolean(), default=False)

    question: Mapped[Question] = relationship(back_populates="options")
