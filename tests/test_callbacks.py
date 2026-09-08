from aiogram.types import CallbackQuery, User

from app.bot import texts
from app.bot.callbacks import (
    AdminCallback,
    MenuCallback,
    SessionAnswerCallback,
    TopicCallback,
)


def test_callback_round_trip():
    packed = SessionAnswerCallback(session_id=5, position=2, option=1).pack()

    unpacked = SessionAnswerCallback.unpack(packed)

    assert (unpacked.session_id, unpacked.position, unpacked.option) == (5, 2, 1)


def query(data: str) -> CallbackQuery:
    return CallbackQuery(
        id="1",
        from_user=User(id=7, is_bot=False, first_name="Иван"),
        chat_instance="ci",
        data=data,
    )


async def test_stale_button_from_a_previous_menu_is_declined():
    """Кнопка прошлой версии меню не подходит фильтру — это отказ, не ошибка."""
    assert await MenuCallback.filter()(query("menu:quiz:extra:fields")) is False


async def test_button_of_another_section_is_declined():
    packed = AdminCallback(section="chats").pack()

    assert await MenuCallback.filter()(query(packed)) is False


async def test_matching_button_is_accepted():
    accepted = await MenuCallback.filter()(query(MenuCallback(action="quiz").pack()))

    assert accepted["callback_data"].action == "quiz"


def test_optional_fields_have_defaults():
    unpacked = TopicCallback.unpack(TopicCallback(action="reset").pack())
    assert unpacked.index == -1


def test_packed_data_fits_telegram_limit():
    """Telegram допускает не более 64 байт в данных кнопки."""
    longest = AdminCallback(section="questions", action="deactivate", page=999).pack()
    assert len(longest.encode()) <= 64


def test_accuracy_is_undefined_without_attempts():
    assert texts.accuracy(0, 0) == texts.ACCURACY_UNDEFINED
    assert texts.accuracy(1, 2) == "50%"
