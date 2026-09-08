"""ORM-модели. Импортируются все, чтобы Alembic видел полную схему."""

from app.models.base import Base
from app.models.content import Question, QuestionOption
from app.models.core import Chat, Setting, User
from app.models.enums import (
    AnswerSource,
    Difficulty,
    LimitMode,
    SessionStatus,
    UserRole,
)
from app.models.process import (
    AskedQuestion,
    GroupPoll,
    QuizSession,
    RandomQuestionIssue,
    SessionMessage,
    SessionQuestion,
)
from app.models.stats import (
    Answer,
    UserDailyLimits,
    UserDailyStats,
    UserTopicPreference,
    UserTotalStats,
)

__all__ = [
    "Answer",
    "AnswerSource",
    "AskedQuestion",
    "Base",
    "Chat",
    "Difficulty",
    "GroupPoll",
    "LimitMode",
    "Question",
    "QuestionOption",
    "QuizSession",
    "RandomQuestionIssue",
    "SessionMessage",
    "SessionQuestion",
    "SessionStatus",
    "Setting",
    "User",
    "UserDailyLimits",
    "UserDailyStats",
    "UserRole",
    "UserTopicPreference",
    "UserTotalStats",
]
