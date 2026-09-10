"""Экран категорий чата в кабинете.

Категорий столько же, сколько тем в банке, — под сотню. Одним списком их
разметка не влезает в предел Telegram, и он отвечает «reply markup is too
long», поэтому экран листается страницами.
"""

from __future__ import annotations

from datetime import UTC, datetime, time

from app.bot.callbacks import AdminChatCallback
from app.bot.handlers.admin_questions import (
    CATEGORIES_PAGE_SIZE,
    categories_page_count,
    chat_categories_keyboard,
    render_chat_categories,
)
from app.models import Chat

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


def make_chat(selected: list[str] | None = None) -> Chat:
    chat = Chat(
        id=-100,
        title="Чат 1С",
        is_active=True,
        interval_minutes=180,
        window_start=time(9, 0),
        window_end=time(21, 0),
        timezone="Europe/Moscow",
        round_number=1,
        connected_at=MOMENT,
        connected_by=1,
    )
    chat.set_categories(selected or [])
    return chat


def many_categories(count: int = 89) -> list[str]:
    return [f"Руководство разработчика · Глава {index + 1}" for index in range(count)]


def buttons(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_the_whole_bank_still_fits_the_telegram_limit():
    markup = chat_categories_keyboard(make_chat(), many_categories()).as_markup()

    assert len(markup.model_dump_json().encode()) < 10_000


def test_a_page_shows_only_its_own_slice():
    categories = many_categories()

    markup = chat_categories_keyboard(make_chat(), categories).as_markup()

    labels = buttons(markup)
    assert any(categories[0] in label for label in labels)
    assert not any(categories[CATEGORIES_PAGE_SIZE] in label for label in labels)


def test_the_index_stays_global_across_pages():
    """Листание не меняет смысла нажатия: индекс сквозной по всему списку."""
    categories = many_categories()

    markup = chat_categories_keyboard(make_chat(), categories, page=2).as_markup()

    expected = AdminChatCallback(
        action=f"cat{2 * CATEGORIES_PAGE_SIZE}", chat_id=-100, page=2
    ).pack()
    packed = [
        button.callback_data for row in markup.inline_keyboard for button in row
    ]
    assert expected in packed


def test_a_short_list_has_no_pager():
    markup = chat_categories_keyboard(make_chat(), many_categories(3)).as_markup()

    assert "⬅️" not in buttons(markup)
    assert categories_page_count(3) == 1


def test_the_page_is_clamped_to_the_last_one():
    categories = many_categories(10)

    markup = chat_categories_keyboard(make_chat(), categories, page=99).as_markup()

    labels = buttons(markup)
    assert any(categories[-1] in label for label in labels)


def test_selection_is_marked():
    categories = many_categories()
    chat = make_chat([categories[0]])

    markup = chat_categories_keyboard(chat, categories).as_markup()

    assert any(label.startswith("✅") for label in buttons(markup))


def test_the_chat_card_offers_categories_directly():
    """Список чатов добавил уровень навигации; категории не должны утонуть."""
    from app.bot.keyboards.admin import chat_actions

    markup = chat_actions(make_chat())

    labels = buttons(markup)
    assert any("Категории" in label for label in labels)
    assert any("Расписание" in label for label in labels)


def test_the_screen_names_the_chat_and_its_categories():
    """Заголовок экрана собирается из данных чата и ничего не требует сверх.

    Прежде он брал строку расписания, где есть ещё и моменты публикации,
    и экран падал на невыданном `slots`.
    """
    categories = many_categories()

    text = render_chat_categories(make_chat([categories[1], categories[0]]))

    assert "Чат 1С" in text
    assert f"{categories[0]}, {categories[1]}" in text


def test_an_empty_selection_reads_as_all_categories():
    text = render_chat_categories(make_chat())

    assert "все" in text


def test_the_schedule_menu_does_not_repeat_categories():
    """Категории правят из карточки чата; в расписании речь только о времени."""
    from app.bot.keyboards.admin import schedule_actions

    labels = buttons(schedule_actions(-100))

    assert not any("Категории" in label for label in labels)
    assert any("Периодичность" in label for label in labels)
