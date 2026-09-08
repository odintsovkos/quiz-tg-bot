"""Заглушки Telegram для тестов единственного экрана."""

from __future__ import annotations

from types import SimpleNamespace

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import (
    AnswerCallbackQuery,
    DeleteMessage,
    EditMessageText,
    SendMessage,
    SendPoll,
)
from aiogram.types import ChatMemberOwner
from aiogram.types import User as TgUser


class ScreenBot:
    """Бот, который запоминает правки, отправки и удаления."""

    def __init__(
        self,
        *,
        edit_error: str | None = None,
        topic_error: str | None = None,
        undeletable: set[int] | None = None,
        batch_delete: bool = True,
    ) -> None:
        self.edit_error = edit_error
        self.topic_error = topic_error
        self.undeletable = undeletable or set()
        self.batch_delete = batch_delete
        self.sent: list[tuple[int, str]] = []
        self.edits: list[tuple[int, int, str]] = []
        self.markups: list = []
        self.polls: list[dict] = []
        self.alerts: list[tuple[str | None, bool]] = []
        self.deleted: list[int] = []
        self.delete_calls: list[list[int]] = []
        self._next_id = 100
        # FSM-middleware aiogram различает состояния по идентификатору бота.
        self.id = 1

    async def send_message(self, chat_id: int, text: str, **kwargs):
        self._next_id += 1
        self.sent.append((chat_id, text))
        self.markups.append(kwargs.get("reply_markup"))
        return SimpleNamespace(message_id=self._next_id, chat=SimpleNamespace(id=chat_id))

    async def edit_message_text(self, text: str, *, chat_id: int, message_id: int, **kw):
        if self.edit_error is not None:
            raise TelegramBadRequest(
                method=EditMessageText(text=text, chat_id=chat_id, message_id=message_id),
                message=self.edit_error,
            )
        self.edits.append((chat_id, message_id, text))
        self.markups.append(kw.get("reply_markup"))
        return SimpleNamespace(message_id=message_id)

    async def delete_messages(self, chat_id: int, message_ids: list[int]):
        self.delete_calls.append(list(message_ids))
        if not self.batch_delete or self.undeletable & set(message_ids):
            raise TelegramBadRequest(
                method=DeleteMessage(chat_id=chat_id, message_id=message_ids[0]),
                message="Bad Request: message can't be deleted",
            )
        self.deleted.extend(message_ids)

    async def __call__(self, method, *_args, **_kwargs):
        """Вызов метода API объектом бота — так работает `message.answer`."""
        if isinstance(method, SendMessage):
            return await self.send_message(
                method.chat_id, method.text, reply_markup=method.reply_markup
            )
        if isinstance(method, AnswerCallbackQuery):
            self.alerts.append((method.text, bool(method.show_alert)))
            return True
        raise NotImplementedError(type(method).__name__)

    async def send_poll(self, **kwargs):
        if self.topic_error is not None and kwargs.get("message_thread_id") is not None:
            raise TelegramBadRequest(
                method=SendPoll(
                    chat_id=kwargs["chat_id"], question="x", options=["a", "b"]
                ),
                message=self.topic_error,
            )
        self._next_id += 1
        self.polls.append(kwargs)
        return SimpleNamespace(
            message_id=self._next_id,
            poll=SimpleNamespace(id=f"poll-{self._next_id}"),
        )

    async def me(self):
        return SimpleNamespace(id=self.id)

    async def get_chat_member(self, chat_id: int, user_id: int):
        """Бот — владелец чата: прав хватает на всё."""
        return ChatMemberOwner(
            user=TgUser(id=user_id, is_bot=True, first_name="Бот"), is_anonymous=False
        )

    async def delete_message(self, chat_id: int, message_id: int):
        if message_id in self.undeletable:
            raise TelegramBadRequest(
                method=DeleteMessage(chat_id=chat_id, message_id=message_id),
                message="Bad Request: message can't be deleted",
            )
        self.deleted.append(message_id)


def message(bot: ScreenBot, chat_id: int = 7, message_id: int = 1):
    """Входящее сообщение участника в личке."""
    return SimpleNamespace(
        bot=bot,
        message_id=message_id,
        chat=SimpleNamespace(id=chat_id, type="private"),
        answers=[],
    )


def query(bot: ScreenBot, chat_id: int = 7, message_id: int = 1):
    """Нажатие кнопки в личке."""
    answered: list[tuple[str | None, bool]] = []

    async def answer(text: str | None = None, show_alert: bool = False, **_kwargs):
        answered.append((text, show_alert))

    return SimpleNamespace(
        bot=bot,
        message=SimpleNamespace(
            message_id=message_id, chat=SimpleNamespace(id=chat_id, type="private")
        ),
        answer=answer,
        answered=answered,
    )
