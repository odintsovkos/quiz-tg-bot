"""Кабинет: раздел вопросов и пошаговое добавление."""

from __future__ import annotations

from dataclasses import replace

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import replies, texts_admin
from app.bot.callbacks import AdminCallback, AdminChatCallback, AdminQuestionCallback
from app.bot.keyboards import admin as keyboards
from app.bot.routers import private_admin
from app.bot.states import AddQuestion, EditQuestion
from app.core.time import format_local
from app.models import Chat, Question, User
from app.repositories.questions import QuestionRepository
from app.services.admin import (
    AdminQuestionService,
    QuestionValidationError,
    draft_from,
)
from app.services.content.categories import group_topics
from app.services.content.validation import OptionDraft, QuestionDraft

CORRECT_MARK = "*"
SKIP = "-"


def render_question(question: Question) -> str:
    """Карточка вопроса."""
    options = "\n".join(
        f"{'✅' if option.is_correct else '▫️'} {option.text}"
        for option in question.options
    )
    if question.updated_at is not None:
        edited = texts_admin.QUESTION_EDITED_BY.format(
            user=question.updated_by, moment=format_local(question.updated_at)
        )
    else:
        edited = texts_admin.QUESTION_NEVER_EDITED

    return texts_admin.QUESTION_CARD.format(
        id=question.id,
        text=question.text,
        category=question.category,
        difficulty=str(question.difficulty),
        state=(
            texts_admin.QUESTION_STATE_ACTIVE
            if question.is_active
            else texts_admin.QUESTION_STATE_INACTIVE
        ),
        options=options,
        explanation=question.explanation or "—",
        reference=question.reference or "—",
        edited=edited,
    )


async def show_questions(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
    callback_data: AdminCallback,
    state: FSMContext,
) -> None:
    if callback_data.action == "add":
        # Мастер добавления вопроса живёт своей лентой: он принимает
        # текстовый ввод шаг за шагом и в модель якоря не переводится.
        await state.set_state(AddQuestion.identifier)
        await replies.send_plain(query, user, texts_admin.QUESTION_ASK_ID)
        return

    page = await AdminQuestionService(session).page(callback_data.page)
    if not page.items:
        await replies.show(
            query, session, user, texts_admin.QUESTIONS_EMPTY, keyboards.back()
        )
        return

    await replies.show(
        query,
        session,
        user,
        texts_admin.QUESTIONS_TITLE.format(
            page=page.page + 1, pages=page.pages, filter="все"
        ),
        keyboards.questions_page(page.items, page.page, page.pages),
    )


@private_admin.callback_query(AdminQuestionCallback.filter())
async def handle_question_action(
    query: CallbackQuery,
    callback_data: AdminQuestionCallback,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    service = AdminQuestionService(session)
    question = await service.get(callback_data.question_id)
    if question is None:
        await query.answer(texts_admin.QUESTION_UNKNOWN, show_alert=True)
        return

    action = callback_data.action

    if action == "open":
        await replies.show(
            query,
            session,
            user,
            render_question(question),
            keyboards.question_card(question, callback_data.page),
        )
    elif action == "toggle":
        await service.set_active(question, not question.is_active, editor_id=user.id)
        await replies.show(
            query,
            session,
            user,
            render_question(question),
            keyboards.question_card(question, callback_data.page),
        )
        await query.answer(
            texts_admin.QUESTION_ACTIVATED
            if question.is_active
            else texts_admin.QUESTION_DEACTIVATED
        )
        return
    elif action.startswith("edit_"):
        field = action.removeprefix("edit_")
        await state.set_state(EditQuestion.value)
        await state.update_data(question_id=question.id, field=field, page=callback_data.page)
        await replies.show(
            query, session, user, _prompt_for(field), keyboards.back()
        )
    await query.answer()


def _prompt_for(field: str) -> str:
    return {
        "text": texts_admin.QUESTION_ASK_TEXT,
        "options": texts_admin.QUESTION_ASK_OPTIONS,
        "category": texts_admin.QUESTION_ASK_CATEGORY,
        "difficulty": texts_admin.QUESTION_ASK_DIFFICULTY,
        "explanation": texts_admin.QUESTION_ASK_EXPLANATION,
    }[field]


def parse_options(raw: str) -> tuple[OptionDraft, ...]:
    """Разобрать варианты: по одному в строке, верный помечен звёздочкой."""
    options: list[OptionDraft] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        is_correct = stripped.startswith(CORRECT_MARK)
        options.append(
            OptionDraft(
                text=stripped.removeprefix(CORRECT_MARK).strip(),
                is_correct=is_correct,
            )
        )
    return tuple(options)


def apply_field(draft: QuestionDraft, field: str, raw: str) -> QuestionDraft:
    """Собрать новый черновик с изменённым полем."""
    if field == "options":
        return replace(draft, options=parse_options(raw))
    value = raw.strip()
    if field == "explanation":
        return replace(draft, explanation=None if value == SKIP else value)
    if field == "text":
        return replace(draft, text=value)
    if field == "category":
        return replace(draft, category=value)
    if field == "difficulty":
        return replace(draft, difficulty=value)
    raise ValueError(f"Поле {field} не редактируется из кабинета")


@private_admin.message(EditQuestion.value)
async def handle_question_edit(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    data = await state.get_data()
    service = AdminQuestionService(session)
    question = await service.get(str(data["question_id"]))
    if question is None:
        await state.clear()
        await replies.show(
            message, session, user, texts_admin.QUESTION_UNKNOWN, keyboards.back()
        )
        return

    draft = apply_field(draft_from(question), str(data["field"]), message.text or "")
    try:
        await service.save(draft, editor_id=user.id)
    except QuestionValidationError as error:
        issues = "\n".join(f"— {issue.message}" for issue in error.result.issues)
        await replies.show(
            message,
            session,
            user,
            texts_admin.QUESTION_REJECTED.format(issues=issues),
            keyboards.back(),
        )
        return

    await state.clear()
    page = int(data.get("page", 0))
    saved = await service.get(question.id)
    if saved is None:  # pragma: no cover - вопрос удалили между сохранением и показом
        await replies.show(
            message, session, user, texts_admin.QUESTION_SAVED, keyboards.back()
        )
        return
    await replies.show(
        message,
        session,
        user,
        texts_admin.QUESTION_SAVED + "\n\n" + render_question(saved),
        keyboards.question_card(saved, page),
    )


# --- пошаговое добавление -------------------------------------------------


@private_admin.message(AddQuestion.identifier)
async def add_identifier(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    identifier = (message.text or "").strip()
    if await AdminQuestionService(session).get(identifier) is not None:
        await message.answer(texts_admin.QUESTION_ID_TAKEN)
        return
    await state.update_data(identifier=identifier)
    await state.set_state(AddQuestion.text)
    await message.answer(texts_admin.QUESTION_ASK_TEXT)


@private_admin.message(AddQuestion.text)
async def add_text(message: Message, state: FSMContext) -> None:
    await state.update_data(text=(message.text or "").strip())
    await state.set_state(AddQuestion.options)
    await message.answer(texts_admin.QUESTION_ASK_OPTIONS)


@private_admin.message(AddQuestion.options)
async def add_options(message: Message, state: FSMContext) -> None:
    await state.update_data(options=message.text or "")
    await state.set_state(AddQuestion.category)
    await message.answer(texts_admin.QUESTION_ASK_CATEGORY)


@private_admin.message(AddQuestion.category)
async def add_category(message: Message, state: FSMContext) -> None:
    await state.update_data(category=(message.text or "").strip())
    await state.set_state(AddQuestion.difficulty)
    await message.answer(texts_admin.QUESTION_ASK_DIFFICULTY)


@private_admin.message(AddQuestion.difficulty)
async def add_difficulty(message: Message, state: FSMContext) -> None:
    await state.update_data(difficulty=(message.text or "").strip())
    await state.set_state(AddQuestion.explanation)
    await message.answer(texts_admin.QUESTION_ASK_EXPLANATION)


def draft_from_form(data: dict[str, str]) -> QuestionDraft:
    """Собрать черновик из ответов пошагового диалога."""
    explanation = data.get("explanation", "").strip()
    return QuestionDraft(
        id=data["identifier"],
        text=data["text"],
        category=data["category"],
        difficulty=data["difficulty"],
        options=parse_options(data["options"]),
        explanation=None if explanation in ("", SKIP) else explanation,
        is_active=True,
    )


@private_admin.message(AddQuestion.explanation)
async def add_explanation(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    await state.update_data(explanation=(message.text or "").strip())
    data = await state.get_data()

    try:
        question = await AdminQuestionService(session).save(
            draft_from_form(data), editor_id=user.id
        )
    except QuestionValidationError as error:
        issues = "\n".join(f"— {issue.message}" for issue in error.result.issues)
        await message.answer(texts_admin.QUESTION_REJECTED.format(issues=issues))
        await state.set_state(AddQuestion.text)
        await message.answer(texts_admin.QUESTION_ASK_TEXT)
        return

    await state.clear()
    await message.answer(texts_admin.QUESTION_ADDED.format(id=question.id))
    await message.answer(render_question(question))


# --- категории чата ------------------------------------------------------


async def chat_categories(session: AsyncSession) -> list[str]:
    """Категории, доступные для выбора чату, — только с активными вопросами."""
    return await QuestionRepository(session).list_categories(only_active=True)


async def handle_chat_category_action(
    query: CallbackQuery,
    callback_data: AdminChatCallback,
    session: AsyncSession,
    user: User,
    chat: Chat,
) -> None:
    """Экран категорий чата: два уровня, переключение не уводит со страницы.

    Кнопки и навигация те же, что у выбора тем в личке, — раскладка по
    руководствам общая (`group_topics`). Разница в правилах, и она нарочная:
    набор без активных вопросов кабинет отклоняет, а участнику молча
    подставляет все темы.
    """
    action = callback_data.action
    if action == "cat_noop":  # счётчик страниц — подпись, а не кнопка
        await query.answer()
        return

    categories = await chat_categories(session)
    if not categories:
        await replies.show(
            query,
            session,
            user,
            texts_admin.SCHEDULE_EMPTY_CATEGORIES,
            keyboards.back(),
        )
        await query.answer()
        return

    groups = group_topics(categories)
    group_index = callback_data.group

    if action == "cat_all":
        await select_all_chat_categories(session, chat)
        await query.answer(texts_admin.CHAT_CATEGORIES_ALL_SELECTED)
    elif action == "cat_reset":
        await reset_chat_categories(session, chat)
        await query.answer(texts_admin.CHAT_CATEGORIES_RESET)
    elif action == "cat_group_all" and 0 <= group_index < len(groups):
        try:
            chosen = await set_chat_category_group(
                session, chat, [item.category for item in groups[group_index].items]
            )
        except EmptyCategorySelection:
            await query.answer(texts_admin.SCHEDULE_EMPTY_CATEGORIES, show_alert=True)
            return
        await query.answer(
            texts_admin.CHAT_CATEGORIES_GROUP_ALL_SELECTED
            if chosen
            else texts_admin.CHAT_CATEGORIES_GROUP_ALL_CLEARED
        )
    elif action == "cat_toggle":
        try:
            await toggle_chat_category(session, chat, callback_data.index)
        except EmptyCategorySelection:
            # Ничего не изменилось — экран уже показывает верное состояние.
            await query.answer(texts_admin.SCHEDULE_EMPTY_CATEGORIES, show_alert=True)
            return
        await query.answer(texts_admin.SCHEDULE_CATEGORIES_SAVED)
    else:
        await query.answer()

    stay_in_group = (
        action in {"cat_open", "cat_toggle", "cat_group_all"}
        and 0 <= group_index < len(groups)
    )
    if not stay_in_group:
        await replies.show(
            query,
            session,
            user,
            render_chat_categories(chat, len(categories)),
            keyboards.chat_category_groups(chat, groups),
        )
        return

    group = groups[group_index]
    await replies.show(
        query,
        session,
        user,
        texts_admin.CHAT_CATEGORIES_GROUP_TITLE.format(
            group=group.name, title=chat.title
        ),
        keyboards.chat_category_chapters(chat, group_index, group, callback_data.page),
    )


def render_chat_categories(chat: Chat, total: int) -> str:
    """Заголовок первого уровня: чат и сводка по отмеченному.

    Отмеченные не перечисляются: их бывает под сотню, и списком они съедают
    сообщение целиком.
    """
    selected = chat.category_list
    return texts_admin.CHAT_CATEGORIES_TITLE.format(
        title=chat.title,
        categories=(
            texts_admin.CHAT_CATEGORIES_COUNT.format(
                selected=len(selected), total=total
            )
            if selected
            else texts_admin.CHAT_CATEGORIES_ALL
        ),
    )


class EmptyCategorySelection(ValueError):
    """В выбранном наборе категорий нет активных вопросов."""


async def select_all_chat_categories(session: AsyncSession, chat: Chat) -> list[str]:
    """Отметить все категории банка явным списком.

    Пустой набор тоже означает «все», но на экране он выглядит как «ничего
    не выбрано». Явный список отвечает администратору, который хочет видеть
    банк отмеченным; цена — категория, добавленная в банк позже, в такой
    набор не попадёт, пока её не отметят.
    """
    chat.set_categories(await chat_categories(session))
    await session.flush()
    return chat.category_list


async def reset_chat_categories(session: AsyncSession, chat: Chat) -> list[str]:
    """Снять отметки: пустой набор — вопросы из всех категорий."""
    chat.set_categories([])
    await session.flush()
    return chat.category_list


async def set_chat_category_group(
    session: AsyncSession, chat: Chat, categories: list[str]
) -> bool:
    """Отметить или снять сразу все главы руководства; вернуть, что сделано.

    Кнопка одна: пока отмечено не всё — отмечаем, отмечено всё — снимаем.
    Отметки в других руководствах не трогаются.
    """
    available = await chat_categories(session)
    selected = set(chat.category_list)
    chosen = not set(categories) <= selected
    selected = selected | set(categories) if chosen else selected - set(categories)

    if selected and not selected & set(available):
        raise EmptyCategorySelection(categories)

    chat.set_categories(sorted(selected))
    await session.flush()
    return chosen


async def toggle_chat_category(
    session: AsyncSession, chat: Chat, index: int
) -> list[str]:
    """Включить или выключить категорию чата.

    Спека `admin-console`: набор, в котором нет активных вопросов,
    отклоняется — прежний остаётся в силе.
    """
    categories = await chat_categories(session)
    if not 0 <= index < len(categories):
        raise EmptyCategorySelection(index)

    category = categories[index]
    selected = set(chat.category_list)
    selected.symmetric_difference_update({category})

    if selected and not selected & set(categories):
        raise EmptyCategorySelection(category)

    chat.set_categories(sorted(selected))
    await session.flush()
    return chat.category_list
