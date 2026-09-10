"""Групповая викторина: подключение чата, публикация опроса, приём ответов."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime, time

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import (
    ChatMemberAdministrator,
    ChatMemberOwner,
    InputPollOption,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.throttling import send_with_retry
from app.core.logging import get_logger
from app.core.time import utc_now
from app.models import AnswerSource, Chat, GroupPoll, User
from app.repositories.chats import ChatRepository
from app.repositories.questions import QuestionRepository
from app.services.quiz.options import shuffled_order
from app.services.quiz.selector import QuestionSelector
from app.services.stats.scoring import RecordedAnswer, ScoringService

logger = get_logger(__name__)

DEFAULT_INTERVAL_MINUTES = 180
DEFAULT_WINDOW = (time(9, 0), time(21, 0))


class ChatRightsError(RuntimeError):
    """У бота нет нужного права в чате — подключение отклоняется."""

    def __init__(self, missing: str) -> None:
        self.missing = missing
        super().__init__(missing)


class ChatUnavailableError(RuntimeError):
    """Публикация невозможна: бот исключён из чата или лишён прав."""


class PublicationDeferredError(RuntimeError):
    """Публикация не удалась по временной причине — Telegram недоступен.

    Отдельный тип нужен потому, что `TelegramNetworkError`
    и `TelegramServerError` — подклассы `TelegramAPIError`: без разделения
    обрыв связи неотличим от исключения бота из чата, и чат отключался бы
    от каждого сетевого сбоя.
    """


#: Отказы, которые говорят о недоступности Telegram, а не о правах бота.
#: `TelegramRetryAfter` сюда попадает уже исчерпав попытки `send_with_retry`:
#: упёршийся лимит частоты — тоже повод пропустить момент, а не отключить чат.
DEFERRING_ERRORS = (TelegramNetworkError, TelegramServerError, TelegramRetryAfter)


#: Обрывки ответов Telegram, по которым узнаётся недоступная тема форума.
#: Кода ошибки, отличающего этот случай, Bot API не даёт — только текст.
TOPIC_ERROR_MARKERS = (
    "message thread not found",
    "topic_closed",
    "topic closed",
    "topic_deleted",
    "topic deleted",
)


def is_topic_unavailable(error: BaseException) -> bool:
    """Отказ Telegram касается именно темы, а не чата целиком."""
    text = str(error).lower()
    return any(marker in text for marker in TOPIC_ERROR_MARKERS)


@dataclass(frozen=True, slots=True)
class PublishOutcome:
    """Итог попытки опубликовать вопрос."""

    poll: GroupPoll | None = None
    #: В заданных категориях нет активных вопросов.
    empty_bank: bool = False
    new_round: bool = False
    #: Ветка публикации отвалилась, вопрос ушёл в общую ленту.
    topic_lost: bool = False


async def check_rights(bot: Bot, chat_id: int) -> None:
    """Убедиться, что бот может отправлять сообщения и опросы.

    Спека `group-quiz`: без прав подключение отклоняется с понятным
    сообщением, а не падает позже при первой публикации.
    """
    member = await bot.get_chat_member(chat_id, (await bot.me()).id)
    if isinstance(member, ChatMemberOwner):
        return
    if not isinstance(member, ChatMemberAdministrator):
        # обычный участник: права определяются настройками чата
        permissions = (await bot.get_chat(chat_id)).permissions
        if permissions is not None:
            if not permissions.can_send_messages:
                raise ChatRightsError("messages")
            if not permissions.can_send_polls:
                raise ChatRightsError("polls")
        return
    if not member.can_post_messages and member.can_post_messages is not None:
        raise ChatRightsError("messages")


class GroupQuizService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._chats = ChatRepository(session)
        self._questions = QuestionRepository(session)
        self._selector = QuestionSelector(session)
        self._scoring = ScoringService(session)

    # --- подключение -----------------------------------------------------

    async def connect(
        self,
        bot: Bot,
        chat_id: int,
        title: str,
        connected_by: int,
        *,
        timezone: str,
        now: datetime | None = None,
    ) -> tuple[Chat, bool]:
        """Подключить чат. Второй элемент — признак «был подключён раньше»."""
        existing = await self._chats.get(chat_id)
        if existing is not None:
            existing.title = title
            existing.is_active = True
            await self._session.flush()
            return existing, True

        await check_rights(bot, chat_id)

        chat = await self._chats.add(
            Chat(
                id=chat_id,
                title=title,
                is_active=True,
                interval_minutes=DEFAULT_INTERVAL_MINUTES,
                window_start=DEFAULT_WINDOW[0],
                window_end=DEFAULT_WINDOW[1],
                timezone=timezone,
                round_number=1,
                connected_at=now or utc_now(),
                connected_by=connected_by,
            )
        )
        return chat, False

    async def disconnect(self, chat_id: int) -> bool:
        """Отключить чат. Статистика участников сохраняется."""
        chat = await self._chats.get(chat_id)
        if chat is None:
            return False
        await self._chats.remove(chat)
        return True

    async def set_active(self, chat: Chat, is_active: bool) -> Chat:
        chat.is_active = is_active
        await self._session.flush()
        return chat

    async def set_topic(
        self, chat: Chat, topic_id: int | None, topic_title: str | None = None
    ) -> Chat:
        """Задать ветку публикации либо вернуть чат на общую ленту."""
        return await self._chats.set_topic(chat, topic_id, topic_title)

    # --- публикация ------------------------------------------------------

    async def publish(
        self, bot: Bot, chat: Chat, *, now: datetime | None = None
    ) -> PublishOutcome:
        """Опубликовать вопрос нативным quiz-опросом.

        Опрос неанонимный: иначе обновление `poll_answer` не приходит и ответ
        нельзя связать с участником.
        """
        moment = now or utc_now()
        selection = await self._selector.pick(chat)
        if selection.question is None:
            return PublishOutcome(empty_bank=True)

        question = selection.question

        # Верный вариант в банке записан первым, поэтому порядок для показа
        # перемешивается, а отметка верного пересчитывается под него.
        order = shuffled_order(len(question.options))
        options: list[InputPollOption | str] = [
            question.options[index].text for index in order
        ]
        correct_option_id = order.index(question.correct_index)

        def send(thread_id: int | None) -> Awaitable[Message]:
            return send_with_retry(
                lambda: bot.send_poll(
                    chat_id=chat.id,
                    message_thread_id=thread_id,
                    question=question.text,
                    options=options,
                    type="quiz",
                    correct_option_id=correct_option_id,
                    explanation=question.explanation,
                    is_anonymous=False,
                )
            )

        topic_lost = False
        try:
            message = await send(chat.topic_id)
        except DEFERRING_ERRORS as error:
            logger.warning(
                "publication deferred",
                extra={"chat_id": chat.id, "error": str(error)},
            )
            raise PublicationDeferredError(str(error)) from error
        except TelegramAPIError as error:
            if chat.topic_id is None or not is_topic_unavailable(error):
                logger.warning(
                    "chat unavailable", extra={"chat_id": chat.id, "error": str(error)}
                )
                raise ChatUnavailableError(str(error)) from error

            # Недоступна тема, а не чат: снимаем ветку и печатаем в общую
            # ленту, иначе удалённая тема тихо съедала бы по вопросу
            # за интервал.
            logger.info(
                "publication topic is gone",
                extra={"chat_id": chat.id, "topic_id": chat.topic_id},
            )
            await self._chats.set_topic(chat, None, None)
            topic_lost = True
            try:
                message = await send(None)
            except DEFERRING_ERRORS as fallback_error:
                logger.warning(
                    "publication deferred",
                    extra={"chat_id": chat.id, "error": str(fallback_error)},
                )
                raise PublicationDeferredError(str(fallback_error)) from fallback_error
            except TelegramAPIError as fallback_error:
                logger.warning(
                    "chat unavailable",
                    extra={"chat_id": chat.id, "error": str(fallback_error)},
                )
                raise ChatUnavailableError(str(fallback_error)) from fallback_error

        if message.poll is None:  # pragma: no cover - Telegram всегда его возвращает
            raise ChatUnavailableError("Telegram не вернул опубликованный опрос")

        poll = await self._chats.add_poll(
            GroupPoll(
                poll_id=message.poll.id,
                chat_id=chat.id,
                question_id=question.id,
                message_id=message.message_id,
                correct_option_id=correct_option_id,
                published_at=moment,
            )
        )
        await self._selector.record(chat, question, now=moment)
        return PublishOutcome(
            poll=poll, new_round=selection.new_round, topic_lost=topic_lost
        )

    # --- приём ответов ---------------------------------------------------

    async def accept_poll_answer(
        self,
        user: User,
        poll_id: str,
        option_ids: list[int],
        *,
        now: datetime | None = None,
    ) -> RecordedAnswer | None:
        """Принять ответ на опубликованный опрос.

        Ответ по неизвестному опросу игнорируется без ошибки; повторный
        отсеивается уникальным индексом внутри `ScoringService`.
        """
        poll = await self._chats.get_poll(poll_id)
        if poll is None:
            return None
        if not option_ids:  # отзыв голоса — учитывать нечего
            return None

        is_correct = option_ids[0] == poll.correct_option_id
        return await self._scoring.record_answer(
            user,
            poll.question_id,
            is_correct=is_correct,
            source=AnswerSource.GROUP,
            chat_id=poll.chat_id,
            poll_id=poll_id,
            now=now,
        )
