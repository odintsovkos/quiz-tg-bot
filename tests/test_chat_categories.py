"""Экран категорий чата в кабинете.

Экран собран как выбор тем в личке: руководства, затем главы страницами.
Категорий столько же, сколько тем в банке, — под сотню; одним списком их
разметка не влезает в предел Telegram, а плоским списком администратор
листал страницы всего банка, чтобы собрать одно руководство.
"""

from __future__ import annotations

from datetime import UTC, datetime, time

from app.bot import texts_admin
from app.bot.callbacks import AdminChatCallback
from app.bot.handlers.admin_questions import (
    handle_chat_category_action,
    render_chat_categories,
    reset_chat_categories,
    select_all_chat_categories,
    set_chat_category_group,
)
from app.bot.keyboards.admin import (
    CATEGORIES_PAGE_SIZE,
    categories_page_count,
    chat_category_chapters,
    chat_category_groups,
)
from app.models import Chat, User, UserRole
from app.services.content.categories import group_topics
from app.services.users import UserService
from tests.conftest import make_question
from tests.screen import ScreenBot, query

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
DEV = "Руководство разработчика"
ADM = "Руководство администратора"


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


def many_categories(count: int = 89, manual: str = DEV) -> list[str]:
    return [f"{manual} · Глава {index + 1}" for index in range(count)]


def buttons(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def actions(markup) -> list[str]:
    return [
        AdminChatCallback.unpack(button.callback_data).action
        for row in markup.inline_keyboard
        for button in row
    ]


def chapters(chat: Chat, categories: list[str], group: int = 0, page: int = 0):
    groups = group_topics(categories)
    return chat_category_chapters(chat, group, groups[group], page)


# --- первый уровень: руководства -----------------------------------------


def test_the_group_screen_counts_the_chosen_chapters():
    categories = [f"{DEV} · Глава 1", f"{DEV} · Глава 2", f"{ADM} · Глава 1"]
    chat = make_chat([f"{DEV} · Глава 2"])

    labels = buttons(chat_category_groups(chat, group_topics(categories)))

    assert f"{DEV} — 1 из 2" in labels
    assert f"{ADM} — 0 из 1" in labels


def test_the_whole_bank_fits_the_telegram_limit_on_both_levels():
    categories = many_categories()
    chat = make_chat(categories)

    groups = chat_category_groups(chat, group_topics(categories)).model_dump_json()
    page = chapters(chat, categories).model_dump_json()

    assert len(groups.encode()) < 10_000
    assert len(page.encode()) < 10_000


def test_every_button_fits_the_callback_data_limit():
    """Telegram отвергает callback-данные длиннее 64 байт.

    Проверяется на худшем случае: настоящий идентификатор супергруппы,
    последняя страница банка и трёхзначный индекс главы.
    """
    categories = many_categories()
    chat = make_chat(categories)
    chat.id = -1002895411698

    markups = [
        chat_category_groups(chat, group_topics(categories)),
        chapters(chat, categories, page=categories_page_count(len(categories)) - 1),
    ]

    for markup in markups:
        for row in markup.inline_keyboard:
            for button in row:
                assert len(button.callback_data.encode()) <= 64, button.callback_data


def test_all_categories_and_reset_stand_side_by_side():
    """Экран чата отвечает на те же вопросы, что и выбор тем в личке."""
    markup = chat_category_groups(make_chat(), group_topics(many_categories(3)))
    row = next(
        row for row in markup.inline_keyboard if any("Сбросить" in b.text for b in row)
    )

    assert [AdminChatCallback.unpack(b.callback_data).action for b in row] == [
        "cat_all",
        "cat_reset",
    ]


# --- второй уровень: главы -----------------------------------------------


def test_a_page_shows_only_its_own_slice():
    categories = many_categories()

    labels = buttons(chapters(make_chat(), categories))

    assert "Глава 1" in labels[0]
    assert not any(f"Глава {CATEGORIES_PAGE_SIZE + 1}" in label for label in labels)


def test_the_index_stays_global_across_manuals():
    """Индекс сквозной по банку: у второго руководства он не начинается с нуля."""
    categories = many_categories(2) + many_categories(2, ADM)

    markup = chapters(make_chat(), categories, group=1)

    assert [
        AdminChatCallback.unpack(button.callback_data).index
        for row in markup.inline_keyboard
        for button in row
        if AdminChatCallback.unpack(button.callback_data).action == "cat_toggle"
    ] == [2, 3]


def test_the_pager_keeps_the_manual():
    categories = many_categories()

    markup = chapters(make_chat(), categories, page=2)

    assert all(
        AdminChatCallback.unpack(button.callback_data).group in {0, -1}
        for row in markup.inline_keyboard
        for button in row
    )
    label = texts_admin.CHAT_CATEGORIES_PAGE_LABEL.format(
        page=3, pages=categories_page_count(len(categories))
    )
    assert label in buttons(markup)


def test_a_short_list_has_no_pager():
    labels = buttons(chapters(make_chat(), many_categories(3)))

    assert "⬅️" not in labels
    assert categories_page_count(3) == 1


def test_the_page_is_clamped_to_the_last_one():
    labels = buttons(chapters(make_chat(), many_categories(10), page=99))

    assert any("Глава 10" in label for label in labels)


def test_selection_is_marked():
    categories = many_categories()

    labels = buttons(chapters(make_chat([categories[0]]), categories))

    assert labels[0].startswith("✅")
    assert labels[1].startswith("▫️")


def test_select_all_button_flips_to_clear_when_everything_is_chosen():
    categories = many_categories(3)

    def label(chat: Chat) -> str:
        markup = chapters(chat, categories)
        return next(
            button.text
            for row in markup.inline_keyboard
            for button in row
            if AdminChatCallback.unpack(button.callback_data).action == "cat_group_all"
        )

    assert label(make_chat()) == "✅ Выбрать все"
    assert label(make_chat(categories)) == "◻️ Снять все"


def test_the_chapters_screen_leaves_for_the_chat_in_one_tap():
    labels = buttons(chapters(make_chat(), many_categories()))

    assert any("К руководствам" in label for label in labels)
    assert any("К чату" in label for label in labels)


# --- заголовок ------------------------------------------------------------


def test_the_title_sums_the_selection_up_instead_of_listing_it():
    """Перечислением под сотню категорий съели бы сообщение целиком."""
    categories = many_categories()

    text = render_chat_categories(make_chat(categories[:12]), len(categories))

    assert "Чат 1С" in text
    assert "12 из 89" in text
    assert categories[0] not in text


def test_an_empty_selection_reads_as_all_categories():
    assert "все" in render_chat_categories(make_chat(), 89)


# --- правила выбора -------------------------------------------------------


async def test_all_categories_marks_the_bank_and_reset_clears_it(session):
    """«Все категории» отмечает банк целиком, соседняя кнопка снимает выбор."""
    chat = make_chat()
    session.add(make_question("dev.001", f"{DEV} · Глава 8"))
    session.add(make_question("adm.001", f"{ADM} · Глава 2"))
    await session.flush()

    assert await select_all_chat_categories(session, chat) == [
        f"{ADM} · Глава 2",
        f"{DEV} · Глава 8",
    ]
    assert await reset_chat_categories(session, chat) == []


async def test_a_deactivated_category_is_not_marked(session):
    """Отмечается то же, что показано на экране, — категории с вопросами."""
    chat = make_chat()
    session.add(make_question("dev.001", f"{DEV} · Глава 8"))
    session.add(make_question("adm.001", f"{ADM} · Глава 2", is_active=False))
    await session.flush()

    assert await select_all_chat_categories(session, chat) == [f"{DEV} · Глава 8"]


async def test_a_manual_is_marked_and_cleared_without_touching_the_others(session):
    chat = make_chat([f"{ADM} · Глава 2"])
    session.add(make_question("dev.001", f"{DEV} · Глава 8"))
    session.add(make_question("dev.002", f"{DEV} · Глава 9"))
    session.add(make_question("adm.001", f"{ADM} · Глава 2"))
    await session.flush()
    manual = [f"{DEV} · Глава 8", f"{DEV} · Глава 9"]

    assert await set_chat_category_group(session, chat, manual) is True
    assert chat.category_list == [f"{ADM} · Глава 2", *manual]

    assert await set_chat_category_group(session, chat, manual) is False
    assert chat.category_list == [f"{ADM} · Глава 2"]


# --- навигация по экрану --------------------------------------------------


async def setup(session) -> tuple[User, Chat]:
    """Банк из двух руководств по две главы и подключённый чат."""
    for prefix, manual in (("dev", DEV), ("adm", ADM)):
        for index in range(2):
            session.add(
                make_question(f"{prefix}.{index}", f"{manual} · Глава {index + 1}")
            )
    user = await UserService(session).register(7, "Иван", now=MOMENT)
    user.role = UserRole.OWNER
    chat = make_chat()
    session.add(chat)
    await session.flush()
    return user, chat


async def test_the_first_screen_shows_the_manuals(session):
    user, chat = await setup(session)
    bot = ScreenBot()
    event = query(bot)

    await handle_chat_category_action(
        event,
        AdminChatCallback(action="set_categories", chat_id=chat.id),
        session,
        user,
        chat,
    )

    assert "Чат 1С" in bot.sent[-1][1]
    assert "cat_open" in actions(bot.markups[-1])


async def test_opening_a_manual_shows_its_chapters(session):
    user, chat = await setup(session)
    bot = ScreenBot()
    event = query(bot)

    await handle_chat_category_action(
        event,
        AdminChatCallback(action="cat_open", chat_id=chat.id, group=1),
        session,
        user,
        chat,
    )

    # Категории отсортированы, поэтому руководство разработчика — второе.
    assert DEV in bot.sent[-1][1]
    assert any("Глава 1" in label for label in buttons(bot.markups[-1]))


async def test_toggling_a_chapter_stays_inside_the_manual(session):
    user, chat = await setup(session)
    bot = ScreenBot()
    event = query(bot)

    await handle_chat_category_action(
        event,
        AdminChatCallback(action="cat_toggle", chat_id=chat.id, group=1, index=2),
        session,
        user,
        chat,
    )

    assert chat.category_list == [f"{DEV} · Глава 1"]
    assert event.answered == [(texts_admin.SCHEDULE_CATEGORIES_SAVED, False)]
    assert DEV in bot.sent[-1][1]
    assert "cat_groups" in actions(bot.markups[-1])


async def test_marking_a_manual_returns_to_its_chapters(session):
    user, chat = await setup(session)
    bot = ScreenBot()
    event = query(bot)

    await handle_chat_category_action(
        event,
        AdminChatCallback(action="cat_group_all", chat_id=chat.id, group=1),
        session,
        user,
        chat,
    )

    assert chat.category_list == [f"{DEV} · Глава 1", f"{DEV} · Глава 2"]
    assert event.answered == [
        (texts_admin.CHAT_CATEGORIES_GROUP_ALL_SELECTED, False)
    ]
    assert "cat_group_all" in actions(bot.markups[-1])


async def test_resetting_returns_to_the_manuals(session):
    user, chat = await setup(session)
    bot = ScreenBot()
    event = query(bot)

    await handle_chat_category_action(
        event,
        AdminChatCallback(action="cat_reset", chat_id=chat.id, group=1),
        session,
        user,
        chat,
    )

    assert chat.category_list == []
    assert event.answered == [(texts_admin.CHAT_CATEGORIES_RESET, False)]
    assert "cat_open" in actions(bot.markups[-1])


async def test_an_empty_bank_says_so_instead_of_an_empty_screen(session):
    user = await UserService(session).register(7, "Иван", now=MOMENT)
    user.role = UserRole.OWNER
    chat = make_chat()
    session.add(chat)
    await session.flush()
    bot = ScreenBot()

    await handle_chat_category_action(
        query(bot),
        AdminChatCallback(action="set_categories", chat_id=chat.id),
        session,
        user,
        chat,
    )

    assert bot.sent[-1][1] == texts_admin.SCHEDULE_EMPTY_CATEGORIES


# --- соседние экраны кабинета --------------------------------------------


def test_the_chat_card_offers_categories_directly():
    """Список чатов добавил уровень навигации; категории не должны утонуть."""
    from app.bot.keyboards.admin import chat_actions

    labels = buttons(chat_actions(make_chat()))

    assert any("Категории" in label for label in labels)
    assert any("Расписание" in label for label in labels)


def test_the_schedule_menu_does_not_repeat_categories():
    """Категории правят из карточки чата; в расписании речь только о времени."""
    from app.bot.keyboards.admin import schedule_actions

    labels = buttons(schedule_actions(-100))

    assert not any("Категории" in label for label in labels)
    assert any("Периодичность" in label for label in labels)
