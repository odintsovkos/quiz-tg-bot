"""Личные режимы: викторина, случайный вопрос, темы, лимиты, главное меню."""

from __future__ import annotations

from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import replies, review, texts
from app.bot.callbacks import (
    MenuCallback,
    RandomActionCallback,
    RandomAnswerCallback,
    ReviewCallback,
    SessionActionCallback,
    SessionAnswerCallback,
    TopicCallback,
)
from app.bot.handlers.stats import (
    build_leaderboard,
    render_leaderboard,
    render_stats_card,
)
from app.bot.keyboards import quiz as keyboards
from app.bot.keyboards.common import back_to_menu, leaderboard_switch, main_menu
from app.bot.routers import private_user
from app.core.time import format_local, quiz_date, utc_now
from app.models import AnswerSource, Question, QuizSession, User
from app.repositories.sessions import SessionRepository
from app.services.quiz.limits import LimitService
from app.services.quiz.review import ReviewService
from app.services.quiz.session import (
    QuizSessionService,
    RandomOutcome,
    StartOutcome,
)
from app.services.quiz.topics import TopicPreferenceService, group_topics
from app.services.settings import SettingsService
from app.services.stats.reading import PERIOD_TODAY, StatsService
from app.services.stats.scoring import RecordedAnswer, is_counted

Sender = Message | CallbackQuery


async def _screen(
    target: Sender,
    session: AsyncSession,
    user: User,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Показать экран: одинаково и на команду, и на нажатие кнопки."""
    await replies.show(target, session, user, text, markup)


# --- главное меню --------------------------------------------------------


@private_user.message(Command("menu"))
async def handle_menu(message: Message, session: AsyncSession, user: User) -> None:
    await _screen(message, session, user, texts.MENU_TITLE, main_menu())


@private_user.callback_query(MenuCallback.filter())
async def handle_menu_button(
    query: CallbackQuery,
    callback_data: MenuCallback,
    session: AsyncSession,
    user: User,
) -> None:
    """Каждый пункт меню ведёт в свой режим."""
    action = callback_data.action
    if action == "root":
        await _screen(query, session, user, texts.MENU_TITLE, main_menu())
    elif action == "quiz":
        await start_quiz(query, session, user)
    elif action == "random":
        await send_random(query, session, user)
    elif action == "topics":
        await show_topics(query, session, user)
    elif action == "stats":
        await _screen(
            query, session, user, await render_stats_card(session, user), back_to_menu()
        )
    elif action == "top":
        board = await build_leaderboard(session, PERIOD_TODAY, user.id)
        await _screen(
            query,
            session,
            user,
            render_leaderboard(board),
            leaderboard_switch(PERIOD_TODAY),
        )
    elif action == "limits":
        await _screen(
            query, session, user, await render_limits(session, user), back_to_menu()
        )
    await query.answer()


# --- викторина -----------------------------------------------------------


@private_user.message(Command("quiz"))
async def handle_quiz_command(
    message: Message, session: AsyncSession, user: User
) -> None:
    await start_quiz(message, session, user)


async def start_quiz(
    target: Sender, session: AsyncSession, user: User, *, restart: bool = False
) -> None:
    outcome = await QuizSessionService(session).start(user, restart=restart)
    await _render_start(target, session, user, outcome)


async def _feed(
    target: Sender,
    session: AsyncSession,
    user: User,
    quiz: QuizSession,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Сообщение ленты сессии: живёт до уборки, экраном не становится."""
    await replies.send_feed(target, session, user, quiz, text, markup)


async def _render_start(
    target: Sender, session: AsyncSession, user: User, outcome: StartOutcome
) -> None:
    service = QuizSessionService(session)

    if outcome.active is not None:
        progress = await service.progress(outcome.active)
        await _screen(
            target,
            session,
            user,
            texts.SESSION_ALREADY_ACTIVE.format(
                number=progress.answered + 1, total=progress.total
            ),
            keyboards.session_conflict(outcome.active.id),
        )
        return

    if outcome.no_questions:
        await _screen(target, session, user, texts.SESSION_NO_QUESTIONS, back_to_menu())
        return

    if outcome.refused is not None:
        settings = await SettingsService(session).get()
        await _screen(
            target,
            session,
            user,
            texts.LIMIT_QUIZ_REACHED.format(
                limit=outcome.refused.limit,
                reset_at=format_local(outcome.refused.reset_at, settings.timezone),
            ),
            back_to_menu(),
        )
        return

    if outcome.session is None:  # pragma: no cover - иначе сессия всегда есть
        return

    # Сессия началась: с этого момента всё уходит в ленту и учитывается
    # в реестре, включая команду запуска.
    await _track_launch(target, session, outcome.session)

    if outcome.topics_fell_back:
        await _feed(target, session, user, outcome.session, texts.TOPICS_FALLBACK_APPLIED)
    if outcome.shortened_to is not None:
        await _feed(
            target,
            session,
            user,
            outcome.session,
            texts.SESSION_SHORTER_THAN_ASKED.format(count=outcome.shortened_to),
        )

    await _send_current_question(target, session, user, outcome.session)


async def _track_launch(
    target: Sender, session: AsyncSession, quiz: QuizSession
) -> None:
    """Учесть команду запуска в реестре: она уйдёт вместе с лентой."""
    if not isinstance(target, Message):
        return
    await replies.track(session, quiz, target.chat.id, target.message_id)


async def _send_current_question(
    target: Sender, session: AsyncSession, user: User, quiz: QuizSession
) -> None:
    service = QuizSessionService(session)
    item = await service.current_question(quiz)
    if item is None:
        return
    question = await session.get(Question, item.question_id)
    if question is None:  # вопрос удалили между стартом сессии и выдачей
        return
    await _feed(
        target,
        session,
        user,
        quiz,
        texts.QUIZ_QUESTION.format(
            number=item.position + 1, total=quiz.total_questions, text=question.text
        ),
        keyboards.session_question(question, quiz.id, item.position),
    )


@private_user.callback_query(SessionActionCallback.filter())
async def handle_session_action(
    query: CallbackQuery,
    callback_data: SessionActionCallback,
    session: AsyncSession,
    user: User,
) -> None:
    service = QuizSessionService(session)
    quiz = await SessionRepository(session).get(callback_data.session_id)
    if quiz is None or quiz.user_id != user.id:
        await query.answer(texts.BUTTON_EXPIRED, show_alert=True)
        return

    if callback_data.action == "continue":
        # Реестр пуст: уход на другой экран его уже убрал, поэтому вопрос
        # выдаётся заново и лента начинается с чистого листа.
        await _send_current_question(query, session, user, quiz)
    elif callback_data.action == "restart":
        await start_quiz(query, session, user, restart=True)
    elif callback_data.action == "abort":
        await service.abort(quiz)
        # Показ экрана сам уберёт ленту прерванной сессии.
        await _screen(query, session, user, texts.SESSION_ABORTED, keyboards.session_finished())
    await query.answer()


@private_user.callback_query(SessionAnswerCallback.filter())
async def handle_session_answer(
    query: CallbackQuery,
    callback_data: SessionAnswerCallback,
    session: AsyncSession,
    user: User,
) -> None:
    service = QuizSessionService(session)
    quiz = await SessionRepository(session).get(callback_data.session_id)
    if quiz is None or quiz.user_id != user.id:
        await query.answer(texts.BUTTON_EXPIRED, show_alert=True)
        return

    recorded, question = await service.answer(
        user, quiz, callback_data.position, callback_data.option
    )
    if recorded is None or question is None:
        await query.answer(texts.ANSWER_ALREADY_GIVEN, show_alert=True)
        return

    finished = await service.current_question(quiz) is None
    if not finished:
        await _feed(query, session, user, quiz, feedback_text(recorded, question))
    await query.answer()

    if finished:
        # Итог показывается экраном, а показ экрана убирает ленту сессии.
        await _screen(
            query,
            session,
            user,
            await render_session_result(session, user, quiz, recorded),
            keyboards.session_finished(quiz.id),
        )
    else:
        await _send_current_question(query, session, user, quiz)


def feedback_text(recorded: RecordedAnswer, question: Question) -> str:
    """Верность, верный вариант при ошибке, пояснение и ссылка."""
    if recorded.is_correct:
        text = texts.ANSWER_CORRECT
    else:
        correct = question.options[question.correct_index].text
        text = texts.ANSWER_WRONG.format(correct=correct)
    if question.explanation:
        text += texts.ANSWER_EXPLANATION.format(explanation=question.explanation)
    if question.reference:
        text += texts.ANSWER_REFERENCE.format(reference=question.reference)
    return text


async def render_session_result(
    session: AsyncSession,
    user: User,
    quiz: QuizSession,
    last: RecordedAnswer | None = None,
) -> str:
    """Итог сессии вместе с обновлёнными дневным и общим результатами."""
    service = QuizSessionService(session)
    progress = await service.progress(quiz)
    settings = await SettingsService(session).get()
    stats = StatsService(session)
    day = quiz_date(utc_now(), settings.timezone)
    daily = await stats.daily(user.id, day)
    total = await stats.total(user.id)

    text = texts.SESSION_RESULT.format(
        correct=progress.correct,
        total=progress.total,
        points=progress.points,
        accuracy=texts.accuracy(progress.correct, progress.answered),
        daily_points=daily.points,
        daily_accuracy=texts.accuracy(daily.correct, daily.attempts),
        total_points=total.points,
        total_accuracy=texts.accuracy(total.correct, total.attempts),
    )
    if last is not None and not last.counted:
        text += texts.SESSION_RESULT_NOT_COUNTED
    return text


# --- разбор сессии -------------------------------------------------------


@private_user.callback_query(ReviewCallback.filter())
async def handle_review(
    query: CallbackQuery,
    callback_data: ReviewCallback,
    session: AsyncSession,
    user: User,
) -> None:
    """Разбор открывается на месте итога и туда же возвращается."""
    if callback_data.action == "noop":  # счётчик страниц — подпись, а не кнопка
        await query.answer()
        return

    quiz = await SessionRepository(session).get(callback_data.session_id)
    if quiz is None or quiz.user_id != user.id:
        await query.answer(texts.BUTTON_EXPIRED, show_alert=True)
        return

    if callback_data.action == "result":
        await _screen(
            query,
            session,
            user,
            await render_session_result(session, user, quiz),
            keyboards.session_finished(quiz.id),
        )
        await query.answer()
        return

    items = await ReviewService(session).build(quiz)
    text, page, pages = review.render(items, callback_data.page)
    await _screen(
        query, session, user, text, keyboards.review_page(quiz.id, page, pages)
    )
    await query.answer()


# --- случайный вопрос ----------------------------------------------------


@private_user.message(Command("random"))
async def handle_random_command(
    message: Message, session: AsyncSession, user: User
) -> None:
    await send_random(message, session, user)


@private_user.callback_query(RandomActionCallback.filter())
async def handle_random_next(
    query: CallbackQuery, session: AsyncSession, user: User
) -> None:
    await send_random(query, session, user)
    await query.answer()


async def send_random(target: Sender, session: AsyncSession, user: User) -> None:
    outcome: RandomOutcome = await QuizSessionService(session).issue_random(user)

    if outcome.no_questions:
        await _screen(target, session, user, texts.SESSION_NO_QUESTIONS, back_to_menu())
        return
    if outcome.refused is not None:
        settings = await SettingsService(session).get()
        await _screen(
            target,
            session,
            user,
            texts.LIMIT_RANDOM_REACHED.format(
                limit=outcome.refused.limit,
                reset_at=format_local(outcome.refused.reset_at, settings.timezone),
            ),
            back_to_menu(),
        )
        return

    if outcome.question is None or outcome.issue is None:  # pragma: no cover
        return

    text = texts.RANDOM_QUESTION.format(text=outcome.question.text)
    if outcome.topics_fell_back:
        # Отдельным сообщением предупреждение завело бы вторую ленту:
        # у случайного вопроса экран один.
        text = texts.TOPICS_FALLBACK_APPLIED + "\n\n" + text

    await _screen(
        target,
        session,
        user,
        text,
        keyboards.random_question(outcome.question, outcome.issue.id),
    )


@private_user.callback_query(RandomAnswerCallback.filter())
async def handle_random_answer(
    query: CallbackQuery,
    callback_data: RandomAnswerCallback,
    session: AsyncSession,
    user: User,
) -> None:
    issue = await SessionRepository(session).get_issue(callback_data.issue_id)
    if issue is None or issue.user_id != user.id:
        await query.answer(texts.BUTTON_EXPIRED, show_alert=True)
        return

    recorded, question = await QuizSessionService(session).answer_random(
        user, issue, callback_data.option
    )
    if recorded is None or question is None:
        await query.answer(texts.ANSWER_ALREADY_GIVEN, show_alert=True)
        return

    text = feedback_text(recorded, question)
    if not recorded.counted:
        text += "\n\n" + texts.LIMITS_NOT_COUNTED_NOTICE
    await _screen(query, session, user, text, keyboards.random_next())
    await query.answer()


# --- темы ----------------------------------------------------------------


@private_user.message(Command("topics"))
async def handle_topics_command(
    message: Message, session: AsyncSession, user: User
) -> None:
    await show_topics(message, session, user)


async def show_topics(target: Sender, session: AsyncSession, user: User) -> None:
    service = TopicPreferenceService(session)
    available = await service.available()
    if not available:
        await _screen(target, session, user, texts.TOPICS_EMPTY_BANK, back_to_menu())
        return
    selected = set(await service.selected(user.id))
    groups = group_topics(available)
    await _screen(
        target, session, user, texts.TOPICS_TITLE, keyboards.topic_groups(groups, selected)
    )


@private_user.callback_query(TopicCallback.filter())
async def handle_topic_button(
    query: CallbackQuery,
    callback_data: TopicCallback,
    session: AsyncSession,
    user: User,
) -> None:
    """Экран выбора тем: два уровня, переключение темы не уводит со страницы."""
    action = callback_data.action
    if action == "noop":  # счётчик страниц — подпись, а не кнопка
        await query.answer()
        return

    service = TopicPreferenceService(session)
    available = await service.available()
    groups = group_topics(available)

    if action == "reset":
        await service.reset(user.id)
        await query.answer(texts.TOPICS_RESET)
    elif action == "all" and 0 <= callback_data.group < len(groups):
        categories = [item.category for item in groups[callback_data.group].items]
        # Кнопка одна: пока отмечено не всё — отмечаем, отмечено всё — снимаем.
        already = set(await service.selected(user.id))
        chosen = not all(category in already for category in categories)
        await service.set_many(user.id, categories, chosen=chosen)
        await query.answer(
            texts.TOPICS_GROUP_ALL_SELECTED
            if chosen
            else texts.TOPICS_GROUP_ALL_CLEARED
        )
    elif action == "toggle":
        if 0 <= callback_data.index < len(available):
            await service.toggle(user.id, available[callback_data.index])
            await query.answer(texts.TOPICS_SAVED)
        else:
            # тема исчезла из банка с момента отрисовки клавиатуры
            await query.answer(texts.BUTTON_EXPIRED, show_alert=True)
    else:
        await query.answer()

    selected = set(await service.selected(user.id))
    group_index = callback_data.group
    stay_in_group = (
        action in {"open", "toggle", "all"} and 0 <= group_index < len(groups)
    )
    if not stay_in_group:
        await _screen(
            query,
            session,
            user,
            texts.TOPICS_TITLE,
            keyboards.topic_groups(groups, selected),
        )
        return

    group = groups[group_index]
    await _screen(
        query,
        session,
        user,
        texts.TOPICS_GROUP_TITLE.format(group=group.name),
        keyboards.topic_chapters(group_index, group, selected, callback_data.page),
    )


# --- лимиты --------------------------------------------------------------


@private_user.message(Command("limits"))
async def handle_limits(message: Message, session: AsyncSession, user: User) -> None:
    await _screen(
        message, session, user, await render_limits(session, user), back_to_menu()
    )


async def render_limits(session: AsyncSession, user: User) -> str:
    state = await LimitService(session).state(user)
    settings = await SettingsService(session).get()
    if not state.enforced:
        text = texts.LIMITS_DISABLED
        # Предупреждение уместно только там, где ответы не идут в зачёт:
        # в режиме «отключены для всех» они учитываются на общих основаниях.
        if not is_counted(user.role, AnswerSource.PRIVATE, settings.limit_mode):
            text += "\n\n" + texts.LIMITS_NOT_COUNTED_NOTICE
        return text

    return texts.LIMITS_STATE.format(
        quiz_left=state.quiz_left,
        quiz_limit=state.quiz_limit,
        random_left=state.random_left,
        random_limit=state.random_limit,
        reset_at=format_local(state.reset_at, settings.timezone),
    )
