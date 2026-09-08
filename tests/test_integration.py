"""Сквозные проверки поведения: суточная граница, группа, режим без лимитов."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from types import SimpleNamespace

from app.core.db import session_scope
from app.models import AnswerSource, Chat, LimitMode
from app.services.quiz.group import GroupQuizService
from app.services.quiz.limits import KIND_QUIZ, LimitService
from app.services.quiz.session import QuizSessionService
from app.services.settings import SettingsService
from app.services.stats.reading import PERIOD_TODAY, PERIOD_TOTAL, StatsService
from app.services.stats.scoring import ScoringService
from app.services.users import UserService
from tests.conftest import make_question

DEV = "Разработчик · Глава 8"

# 20:59 UTC = 23:59 MSK 10 марта; 21:00 UTC = 00:00 MSK 11 марта
BEFORE_MIDNIGHT = datetime(2026, 3, 10, 20, 59, tzinfo=UTC)
AFTER_MIDNIGHT = datetime(2026, 3, 10, 21, 0, tzinfo=UTC)
YESTERDAY = date(2026, 3, 10)
TODAY = date(2026, 3, 11)


class FakeBot:
    def __init__(self) -> None:
        self.counter = 0
        self.messages: list[tuple[int, str]] = []

    async def send_poll(self, **_kwargs):
        self.counter += 1
        return SimpleNamespace(
            message_id=self.counter, poll=SimpleNamespace(id=f"poll-{self.counter}")
        )

    async def send_message(self, chat_id: int, text: str, **_kwargs):
        self.messages.append((chat_id, text))


async def seed(session, questions: int = 5):
    for index in range(questions):
        session.add(make_question(f"q.{index:03d}", DEV))
    await session.flush()


# --- 9.1 суточная граница ------------------------------------------------


async def test_answers_around_midnight_land_in_different_days(session):
    """Спека `scoring-and-stats`: смена дня определяется датой ответа."""
    await seed(session, 2)
    user = await UserService(session).register(7, "Иван")
    service = ScoringService(session)

    await service.record_answer(
        user, "q.000", is_correct=True, source=AnswerSource.GROUP,
        poll_id="p1", now=BEFORE_MIDNIGHT,
    )
    await service.record_answer(
        user, "q.001", is_correct=True, source=AnswerSource.GROUP,
        poll_id="p2", now=AFTER_MIDNIGHT,
    )

    stats = StatsService(session)
    yesterday = await stats.daily(7, YESTERDAY)
    today = await stats.daily(7, TODAY)
    total = await stats.total(7)

    assert (yesterday.attempts, yesterday.points) == (1, 1)
    assert (today.attempts, today.points) == (1, 1)
    assert (total.attempts, total.points) == (2, 2)


async def test_bot_offline_at_midnight_still_starts_the_new_day(session_factory):
    """Первый ответ после запуска попадает в новый день, вчерашние итоги целы."""
    async with session_scope(session_factory) as session:
        await seed(session, 2)
        user = await UserService(session).register(7, "Иван")
        await ScoringService(session).record_answer(
            user, "q.000", is_correct=True, source=AnswerSource.GROUP,
            poll_id="p1", now=BEFORE_MIDNIGHT,
        )

    # процесс «выключен» на полночь и запущен утром
    morning = datetime(2026, 3, 11, 6, 0, tzinfo=UTC)
    async with session_scope(session_factory) as session:
        user = await UserService(session).get(7)
        await ScoringService(session).record_answer(
            user, "q.001", is_correct=False, source=AnswerSource.GROUP,
            poll_id="p2", now=morning,
        )

    async with session_factory() as session:
        stats = StatsService(session)
        assert (await stats.daily(7, YESTERDAY)).points == 1
        today = await stats.daily(7, TODAY)
        assert (today.attempts, today.points) == (1, 0)
        assert (await stats.total(7)).attempts == 2


async def test_past_day_totals_remain_readable(session):
    await seed(session, 1)
    user = await UserService(session).register(7, "Иван")
    await ScoringService(session).record_answer(
        user, "q.000", is_correct=True, source=AnswerSource.GROUP,
        poll_id="p1", now=BEFORE_MIDNIGHT,
    )

    board = await StatsService(session).leaderboard(PERIOD_TODAY, day=YESTERDAY)

    assert [row.user_id for row in board.rows] == [7]
    assert board.rows[0].stats.points == 1


async def test_daily_limits_reset_with_the_day(session):
    await seed(session, 1)
    user = await UserService(session).register(7, "Иван")
    await SettingsService(session).set_quiz_limit(1)
    service = LimitService(session)

    assert (await service.consume(user, KIND_QUIZ, now=BEFORE_MIDNIGHT)).allowed
    assert not (await service.consume(user, KIND_QUIZ, now=BEFORE_MIDNIGHT)).allowed
    assert (await service.consume(user, KIND_QUIZ, now=AFTER_MIDNIGHT)).allowed


# --- 9.2 групповой опрос → пять верных ответов → таблица -----------------


async def test_group_poll_five_correct_answers_reach_the_leaderboard(session):
    await seed(session, 1)
    session.add(
        Chat(
            id=-100,
            title="Чат",
            is_active=True,
            interval_minutes=60,
            window_start=time(9, 0),
            window_end=time(21, 0),
            timezone="Europe/Moscow",
            round_number=1,
            connected_at=BEFORE_MIDNIGHT,
            connected_by=1,
        )
    )
    await session.flush()
    chat = await session.get(Chat, -100)

    service = GroupQuizService(session)
    outcome = await service.publish(FakeBot(), chat, now=BEFORE_MIDNIGHT)

    for user_id in range(1, 6):
        participant = await UserService(session).register(user_id, f"Участник {user_id}")
        recorded = await service.accept_poll_answer(
            participant,
            outcome.poll.poll_id,
            [outcome.poll.correct_option_id],
            now=BEFORE_MIDNIGHT,
        )
        assert recorded.points == 1

    board = await StatsService(session).leaderboard(PERIOD_TODAY, day=YESTERDAY)

    assert len(board.rows) == 5
    assert all(row.stats.points == 1 for row in board.rows)


# --- 9.3 режим «отключены только для администраторов» --------------------


async def test_admins_only_mode_end_to_end(session):
    await seed(session, 6)
    users = UserService(session)
    await users.register(7, "Админ")
    admin = await users.grant_admin(7)
    plain = await users.register(8, "Участник")

    settings = SettingsService(session)
    await settings.set_limit_mode(LimitMode.DISABLED_FOR_ADMINS)
    await settings.set_quiz_limit(1)
    await settings.set_session_size(1)

    quiz = QuizSessionService(session)
    scoring = ScoringService(session)
    stats = StatsService(session)

    # 1. личный ответ администратора не меняет агрегаты
    admin_session = (await quiz.start(admin, now=BEFORE_MIDNIGHT)).session
    await quiz.answer(admin, admin_session, 0, 0, now=BEFORE_MIDNIGHT)
    assert (await stats.total(7)).attempts == 0

    # 2. групповой ответ администратора учитывается
    await scoring.record_answer(
        admin, "q.005", is_correct=True, source=AnswerSource.GROUP,
        poll_id="p1", now=BEFORE_MIDNIGHT,
    )
    assert (await stats.total(7)).points == 1

    # 3. обычный участник по-прежнему упирается в лимит
    first = await quiz.start(plain, now=BEFORE_MIDNIGHT)
    assert first.session is not None
    await quiz.abort(first.session, now=BEFORE_MIDNIGHT)
    assert (await quiz.start(plain, now=BEFORE_MIDNIGHT)).refused is not None

    # 4. смена режима не пересчитывает прошлое
    await settings.set_limit_mode(LimitMode.ENABLED)
    assert (await stats.total(7)).attempts == 1

    new_session = (await quiz.start(admin, restart=True, now=BEFORE_MIDNIGHT)).session
    await quiz.answer(admin, new_session, 0, 0, now=BEFORE_MIDNIGHT)
    assert (await stats.total(7)).attempts == 2


async def test_admins_only_mode_keeps_the_admin_out_of_the_leaderboard(session):
    await seed(session, 2)
    users = UserService(session)
    await users.register(7, "Админ")
    admin = await users.grant_admin(7)
    plain = await users.register(8, "Участник")
    await SettingsService(session).set_limit_mode(LimitMode.DISABLED_FOR_ADMINS)
    scoring = ScoringService(session)

    await scoring.record_answer(
        admin, "q.000", is_correct=True, source=AnswerSource.PRIVATE, now=BEFORE_MIDNIGHT
    )
    await scoring.record_answer(
        plain, "q.001", is_correct=True, source=AnswerSource.PRIVATE, now=BEFORE_MIDNIGHT
    )

    board = await StatsService(session).leaderboard(PERIOD_TOTAL)

    assert [row.user_id for row in board.rows] == [8]
