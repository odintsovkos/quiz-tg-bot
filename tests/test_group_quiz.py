"""Групповая викторина: подключение, выбор без повторов, публикация, ответы."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace

import pytest
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.methods import SendPoll

from app.core.db import session_scope
from app.models import AskedQuestion, Chat, GroupPoll
from app.services.quiz.group import (
    ChatUnavailableError,
    GroupQuizService,
)
from app.services.quiz.schedule import (
    MISFIRE_GRACE_SECONDS,
    ScheduleService,
    job_id,
)
from app.services.quiz.selector import QuestionSelector
from app.services.stats.reading import StatsService
from app.services.users import UserService
from tests.conftest import make_question

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)  # 15:00 MSK
DEV = "Разработчик · Глава 8"
ADMIN_CAT = "Администратор · Глава 2"


class FakeBot:
    """Заглушка Telegram: тесты не ходят в сеть."""

    def __init__(self, *, fail: bool = False, error: Exception | None = None) -> None:
        self.fail = fail
        #: Отказ, который подставляется вместо стандартного «бот исключён»:
        #: так тесты различают постоянную и временную недоступность.
        self.error = error
        self.polls: list[dict] = []
        self.messages: list[tuple[int, str]] = []
        self._poll_counter = 0

    async def send_poll(self, **kwargs):
        if self.error is not None:
            raise self.error
        if self.fail:
            raise TelegramForbiddenError(
                method=SendPoll(chat_id=kwargs["chat_id"], question="x", options=["a", "b"]),
                message="Forbidden: bot was kicked",
            )
        self.polls.append(kwargs)
        self._poll_counter += 1
        return SimpleNamespace(
            message_id=self._poll_counter,
            poll=SimpleNamespace(id=f"poll-{self._poll_counter}"),
        )

    async def send_message(self, chat_id: int, text: str, **_kwargs):
        self.messages.append((chat_id, text))
        return SimpleNamespace(message_id=1)


async def add_chat(session, *, categories=None, chat_id: int = -100) -> Chat:
    chat = Chat(
        id=chat_id,
        title="Чат 1С",
        is_active=True,
        interval_minutes=60,
        window_start=time(9, 0),
        window_end=time(21, 0),
        timezone="Europe/Moscow",
        round_number=1,
        connected_at=MOMENT,
        connected_by=1,
    )
    if categories:
        chat.set_categories(categories)
    session.add(chat)
    await session.flush()
    return chat


async def add_questions(session, count: int, category: str = DEV, prefix: str = "q"):
    for index in range(count):
        session.add(make_question(f"{prefix}.{index:03d}", category))
    await session.flush()


# --- подключение и отключение --------------------------------------------


async def test_disconnect_stops_publications_and_keeps_statistics(session):
    await add_questions(session, 2)
    chat = await add_chat(session)
    user = await UserService(session).register(7, "Иван", now=MOMENT)
    service = GroupQuizService(session)
    bot = FakeBot()
    outcome = await service.publish(bot, chat, now=MOMENT)
    await service.accept_poll_answer(user, outcome.poll.poll_id, [0], now=MOMENT)
    attempts_before = (await StatsService(session).total(7)).attempts

    assert await service.disconnect(chat.id) is True

    assert await service.disconnect(chat.id) is False
    assert (await StatsService(session).total(7)).attempts == attempts_before == 1


async def test_pausing_a_chat_keeps_its_settings(session):
    chat = await add_chat(session)
    service = GroupQuizService(session)

    await service.set_active(chat, False)

    assert chat.is_active is False
    assert chat.interval_minutes == 60


# --- выбор вопроса без повторов ------------------------------------------


async def test_question_is_not_repeated_within_a_round(session):
    await add_questions(session, 3)
    chat = await add_chat(session)
    selector = QuestionSelector(session)

    asked: list[str] = []
    for _ in range(3):
        selection = await selector.pick(chat)
        assert selection.new_round is False
        asked.append(selection.question.id)
        await selector.record(chat, selection.question, now=MOMENT)

    assert len(set(asked)) == 3


async def test_exhausted_round_starts_a_new_one_with_the_oldest_question(session):
    await add_questions(session, 2)
    chat = await add_chat(session)
    selector = QuestionSelector(session)

    first = await selector.pick(chat)
    await selector.record(chat, first.question, now=MOMENT)
    second = await selector.pick(chat)
    await selector.record(chat, second.question, now=MOMENT + timedelta(minutes=1))

    third = await selector.pick(chat)

    assert third.new_round is True
    assert chat.round_number == 2
    assert third.question.id == first.question.id  # задавался раньше остальных


async def test_no_active_questions_gives_nothing(session):
    await add_chat(session)

    selection = await QuestionSelector(session).pick(await _first_chat(session))

    assert selection.question is None


async def _first_chat(session) -> Chat:
    from sqlalchemy import select

    return await session.scalar(select(Chat))


async def test_chat_categories_narrow_the_choice(session):
    await add_questions(session, 2, DEV)
    await add_questions(session, 1, ADMIN_CAT, prefix="a")
    chat = await add_chat(session, categories=[ADMIN_CAT])

    selection = await QuestionSelector(session).pick(chat)

    assert selection.question.category == ADMIN_CAT


# --- публикация ----------------------------------------------------------


async def test_publish_sends_a_quiz_poll_with_explanation(session):
    await add_questions(session, 1)
    chat = await add_chat(session)
    bot = FakeBot()

    outcome = await GroupQuizService(session).publish(bot, chat, now=MOMENT)

    sent = bot.polls[0]
    assert sent["type"] == "quiz"
    assert sent["is_anonymous"] is False
    assert sent["explanation"] == "Пояснение"
    assert sent["options"][sent["correct_option_id"]] == "Вариант 0"
    assert outcome.poll is not None


async def test_publish_links_the_poll_with_the_question_and_chat(session):
    await add_questions(session, 1)
    chat = await add_chat(session)

    outcome = await GroupQuizService(session).publish(FakeBot(), chat, now=MOMENT)

    stored = await session.get(GroupPoll, outcome.poll.poll_id)
    assert (stored.chat_id, stored.question_id) == (chat.id, "q.000")
    asked = await session.get(AskedQuestion, 1)
    assert (asked.chat_id, asked.question_id, asked.round_number) == (chat.id, "q.000", 1)


async def test_publish_reports_an_empty_bank(session):
    chat = await add_chat(session)

    outcome = await GroupQuizService(session).publish(FakeBot(), chat, now=MOMENT)

    assert outcome.empty_bank is True
    assert outcome.poll is None


async def test_unavailable_chat_raises(session):
    await add_questions(session, 1)
    chat = await add_chat(session)

    with pytest.raises(ChatUnavailableError):
        await GroupQuizService(session).publish(FakeBot(fail=True), chat, now=MOMENT)


# --- приём ответов -------------------------------------------------------


async def test_correct_group_answer_is_scored(session):
    await add_questions(session, 1)
    chat = await add_chat(session)
    user = await UserService(session).register(7, "Иван", now=MOMENT)
    service = GroupQuizService(session)
    outcome = await service.publish(FakeBot(), chat, now=MOMENT)

    recorded = await service.accept_poll_answer(
        user, outcome.poll.poll_id, [outcome.poll.correct_option_id], now=MOMENT
    )

    assert recorded.is_correct and recorded.points == 1
    assert (await StatsService(session).total(7)).points == 1


async def test_wrong_group_answer_counts_as_an_attempt(session):
    await add_questions(session, 1)
    chat = await add_chat(session)
    user = await UserService(session).register(7, "Иван", now=MOMENT)
    service = GroupQuizService(session)
    outcome = await service.publish(FakeBot(), chat, now=MOMENT)

    wrong = (outcome.poll.correct_option_id + 1) % 4
    recorded = await service.accept_poll_answer(
        user, outcome.poll.poll_id, [wrong], now=MOMENT
    )

    assert recorded.is_correct is False and recorded.points == 0
    total = await StatsService(session).total(7)
    assert (total.attempts, total.points) == (1, 0)


async def test_repeated_answer_to_the_same_poll_keeps_the_first_result(session):
    await add_questions(session, 1)
    chat = await add_chat(session)
    user = await UserService(session).register(7, "Иван", now=MOMENT)
    service = GroupQuizService(session)
    outcome = await service.publish(FakeBot(), chat, now=MOMENT)

    correct = outcome.poll.correct_option_id
    await service.accept_poll_answer(user, outcome.poll.poll_id, [correct], now=MOMENT)
    again = await service.accept_poll_answer(
        user, outcome.poll.poll_id, [(correct + 1) % 4], now=MOMENT
    )

    assert again.accepted is False
    assert (await StatsService(session).total(7)).points == 1


async def test_answer_to_an_unknown_poll_is_ignored(session):
    user = await UserService(session).register(7, "Иван", now=MOMENT)

    assert await GroupQuizService(session).accept_poll_answer(user, "нет", [0]) is None


async def test_five_correct_answers_give_five_participants_a_point_each(session):
    await add_questions(session, 1)
    chat = await add_chat(session)
    service = GroupQuizService(session)
    outcome = await service.publish(FakeBot(), chat, now=MOMENT)

    for user_id in range(1, 6):
        participant = await UserService(session).register(
            user_id, f"№{user_id}", now=MOMENT
        )
        await service.accept_poll_answer(
            participant, outcome.poll.poll_id, [outcome.poll.correct_option_id], now=MOMENT
        )

    stats = StatsService(session)
    for user_id in range(1, 6):
        assert (await stats.total(user_id)).points == 1


# --- расписание ----------------------------------------------------------


class FakeScheduler:
    """Планировщик без реального цикла событий."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}

    def add_job(self, func, **kwargs):
        self.jobs[kwargs["id"]] = kwargs
        return SimpleNamespace(id=kwargs["id"])

    def get_job(self, identifier):
        if identifier not in self.jobs:
            return None
        return SimpleNamespace(
            id=identifier, remove=lambda: self.jobs.pop(identifier, None)
        )

    def get_jobs(self):
        return [self.get_job(identifier) for identifier in list(self.jobs)]


async def test_rebuild_creates_a_job_per_active_chat(session_factory):
    async with session_scope(session_factory) as session:
        await add_chat(session, chat_id=-100)
        paused = await add_chat(session, chat_id=-200)
        paused.is_active = False

    scheduler = FakeScheduler()
    count = await ScheduleService(scheduler, session_factory, FakeBot()).rebuild()

    assert count == 1
    assert set(scheduler.jobs) == {
        job_id(-100, time(hour, 0)) for hour in range(9, 21)
    }


async def test_job_does_not_catch_up_missed_runs(session_factory):
    async with session_scope(session_factory) as session:
        await add_chat(session)

    scheduler = FakeScheduler()
    await ScheduleService(scheduler, session_factory, FakeBot()).rebuild()

    job = scheduler.jobs[job_id(-100, time(9, 0))]
    assert job["coalesce"] is True
    assert job["misfire_grace_time"] == MISFIRE_GRACE_SECONDS


async def test_changing_the_interval_applies_immediately(session_factory):
    scheduler = FakeScheduler()
    async with session_scope(session_factory) as session:
        chat = await add_chat(session)
        service = ScheduleService(scheduler, session_factory, FakeBot())
        service.apply(chat)
        assert len(scheduler.jobs) == 12

        chat.interval_minutes = 30
        service.apply(chat)

    assert len(scheduler.jobs) == 24
    assert job_id(-100, time(9, 30)) in scheduler.jobs


async def test_publication_inside_the_window_happens(session_factory):
    async with session_scope(session_factory) as session:
        await add_questions(session, 1)
        await add_chat(session)

    bot = FakeBot()
    service = ScheduleService(FakeScheduler(), session_factory, bot)

    assert await service.publish_scheduled(-100, now=MOMENT) is True
    assert len(bot.polls) == 1


async def test_no_moment_of_publication_falls_outside_the_window(session_factory):
    """Вне окна не публикуется, потому что моментов там нет.

    Раньше это держалось проверкой внутри задачи: сетка шла от момента
    запуска процесса и попадала куда угодно, включая ночь.
    """
    scheduler = FakeScheduler()
    async with session_scope(session_factory) as session:
        chat = await add_chat(session)
        ScheduleService(scheduler, session_factory, FakeBot()).apply(chat)

    hours = {job["hour"] for job in scheduler.jobs.values()}

    assert hours == set(range(9, 21))
    assert not hours & {21, 22, 23, 0, 1, 2}


async def test_paused_chat_is_not_published_to(session_factory):
    async with session_scope(session_factory) as session:
        await add_questions(session, 1)
        chat = await add_chat(session)
        chat.is_active = False

    bot = FakeBot()
    service = ScheduleService(FakeScheduler(), session_factory, bot)

    assert await service.publish_scheduled(-100, now=MOMENT) is False
    assert bot.polls == []


async def test_manual_publication_does_not_touch_the_schedule(session_factory):
    async with session_scope(session_factory) as session:
        await add_questions(session, 2)
        chat = await add_chat(session)

    scheduler = FakeScheduler()
    service = ScheduleService(scheduler, session_factory, FakeBot())
    async with session_scope(session_factory) as session:
        service.apply(await _first_chat(session))
    before = dict(scheduler.jobs)

    assert await service.publish_now(-100, now=MOMENT) is True

    assert scheduler.jobs == before
    assert set(before) == {job_id(-100, time(hour, 0)) for hour in range(9, 21)}
    assert chat.id == -100


async def test_empty_bank_notifies_admins(session_factory):
    async with session_scope(session_factory) as session:
        await add_chat(session)
        await UserService(session).ensure_owner(1, now=MOMENT)

    bot = FakeBot()
    service = ScheduleService(FakeScheduler(), session_factory, bot)

    assert await service.publish_now(-100, now=MOMENT) is False
    assert bot.messages and "пропущена" in bot.messages[0][1]


async def test_unavailable_chat_is_deactivated_and_admins_notified(session_factory):
    async with session_scope(session_factory) as session:
        await add_questions(session, 1)
        await add_chat(session)
        await UserService(session).ensure_owner(1, now=MOMENT)

    bot = FakeBot(fail=True)
    scheduler = FakeScheduler()
    service = ScheduleService(scheduler, session_factory, bot)
    async with session_scope(session_factory) as session:
        service.apply(await _first_chat(session))

    assert await service.publish_now(-100, now=MOMENT) is False

    assert scheduler.jobs == {}
    assert bot.messages and "недоступен" in bot.messages[0][1]
    async with session_factory() as session:
        assert (await _first_chat(session)).is_active is False


# --- проверка прав при подключении ---------------------------------------


class RightsBot(FakeBot):
    """Заглушка, отвечающая на проверку прав бота в чате."""

    def __init__(self, *, can_send_messages=True, can_send_polls=True) -> None:
        super().__init__()
        self._permissions = SimpleNamespace(
            can_send_messages=can_send_messages, can_send_polls=can_send_polls
        )

    async def me(self):
        return SimpleNamespace(id=999)

    async def get_chat_member(self, _chat_id, _user_id):
        return SimpleNamespace()  # обычный участник

    async def get_chat(self, _chat_id):
        return SimpleNamespace(permissions=self._permissions)


async def test_connect_stores_the_chat_with_its_schedule(session):
    bot = RightsBot()

    chat, existed = await GroupQuizService(session).connect(
        bot, -100, "Чат 1С", 1, timezone="Europe/Moscow", now=MOMENT
    )

    assert existed is False
    assert (chat.id, chat.title, chat.is_active) == (-100, "Чат 1С", True)
    assert chat.interval_minutes == 180
    assert (chat.window_start, chat.window_end) == (time(9, 0), time(21, 0))


async def test_connect_is_refused_without_the_right_to_send_polls(session):
    from app.services.quiz.group import ChatRightsError

    bot = RightsBot(can_send_polls=False)

    with pytest.raises(ChatRightsError) as error:
        await GroupQuizService(session).connect(
            bot, -100, "Чат", 1, timezone="Europe/Moscow", now=MOMENT
        )

    assert error.value.missing == "polls"


async def test_connect_is_refused_without_the_right_to_send_messages(session):
    from app.services.quiz.group import ChatRightsError

    bot = RightsBot(can_send_messages=False)

    with pytest.raises(ChatRightsError) as error:
        await GroupQuizService(session).connect(
            bot, -100, "Чат", 1, timezone="Europe/Moscow", now=MOMENT
        )

    assert error.value.missing == "messages"


async def test_connecting_an_already_connected_chat_reports_it(session):
    await add_chat(session)

    chat, existed = await GroupQuizService(session).connect(
        RightsBot(), -100, "Новое название", 1, timezone="Europe/Moscow", now=MOMENT
    )

    assert existed is True
    assert chat.title == "Новое название"


# --- перемешивание вариантов ---------------------------------------------


async def test_published_options_are_shuffled(session):
    """Верный вариант в банке первый — в опросе он не должен быть первым всегда."""
    await add_questions(session, 1)
    chat = await add_chat(session)
    bot = FakeBot()
    service = GroupQuizService(session)

    positions = set()
    for _ in range(20):
        outcome = await service.publish(bot, chat, now=MOMENT)
        positions.add(outcome.poll.correct_option_id)

    assert len(positions) > 1
    for sent in bot.polls:
        assert sorted(sent["options"]) == sorted(f"Вариант {i}" for i in range(4))


async def test_stored_correct_option_matches_the_published_order(session):
    await add_questions(session, 1)
    chat = await add_chat(session)
    bot = FakeBot()

    for _ in range(10):
        outcome = await GroupQuizService(session).publish(bot, chat, now=MOMENT)
        stored = await session.get(GroupPoll, outcome.poll.poll_id)
        assert bot.polls[-1]["options"][stored.correct_option_id] == "Вариант 0"
        assert bot.polls[-1]["correct_option_id"] == stored.correct_option_id


def network_error() -> TelegramNetworkError:
    return TelegramNetworkError(
        method=SendPoll(chat_id=-100, question="x", options=["a", "b"]),
        message="Connection reset by peer",
    )


async def test_a_network_failure_keeps_the_chat_active(session_factory):
    """Обрыв связи — не исключение бота из чата.

    `TelegramNetworkError` — подкласс `TelegramAPIError`, и до разделения
    отказов каждый сетевой сбой отключал чат вместе с его расписанием.
    """
    async with session_scope(session_factory) as session:
        await add_questions(session, 1)
        await add_chat(session)
        await UserService(session).ensure_owner(1, now=MOMENT)

    bot = FakeBot(error=network_error())
    scheduler = FakeScheduler()
    service = ScheduleService(scheduler, session_factory, bot)
    async with session_scope(session_factory) as session:
        service.apply(await _first_chat(session))

    assert await service.publish_now(-100, now=MOMENT) is False

    assert bot.messages == [], "администраторов зря побеспокоили"
    async with session_factory() as session:
        assert (await _first_chat(session)).is_active is True


async def test_a_network_failure_leaves_the_schedule_in_place(session_factory):
    async with session_scope(session_factory) as session:
        await add_questions(session, 1)
        await add_chat(session)

    bot = FakeBot(error=network_error())
    scheduler = FakeScheduler()
    service = ScheduleService(scheduler, session_factory, bot)
    async with session_scope(session_factory) as session:
        service.apply(await _first_chat(session))
    before = dict(scheduler.jobs)

    await service.publish_scheduled(-100, now=MOMENT)

    assert scheduler.jobs == before
    assert set(before) == {job_id(-100, time(hour, 0)) for hour in range(9, 21)}


async def test_the_next_moment_publishes_after_a_network_failure(session_factory):
    """Пропущен только сбойный момент, а не автопубликация целиком."""
    async with session_scope(session_factory) as session:
        await add_questions(session, 2)
        await add_chat(session)

    bot = FakeBot(error=network_error())
    service = ScheduleService(FakeScheduler(), session_factory, bot)

    assert await service.publish_scheduled(-100, now=MOMENT) is False
    assert bot.polls == []

    bot.error = None
    assert await service.publish_scheduled(-100, now=MOMENT) is True
    assert len(bot.polls) == 1


async def test_an_exhausted_rate_limit_does_not_deactivate_the_chat(session_factory):
    """`send_with_retry` исчерпал попытки — момент пропущен, чат жив."""
    async with session_scope(session_factory) as session:
        await add_questions(session, 1)
        await add_chat(session)
        await UserService(session).ensure_owner(1, now=MOMENT)

    bot = FakeBot(
        error=TelegramRetryAfter(
            method=SendPoll(chat_id=-100, question="x", options=["a", "b"]),
            message="Too Many Requests",
            retry_after=1,
        )
    )
    service = ScheduleService(FakeScheduler(), session_factory, bot)

    assert await service.publish_scheduled(-100, now=MOMENT) is False

    assert bot.messages == []
    async with session_factory() as session:
        assert (await _first_chat(session)).is_active is True
