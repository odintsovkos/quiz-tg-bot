"""Выбор тем и дневные лимиты."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.core.db import session_scope
from app.models import LimitMode, UserDailyLimits
from app.services.quiz.limits import KIND_QUIZ, KIND_RANDOM, LimitService
from app.services.quiz.topics import TopicPreferenceService
from app.services.settings import SettingsService
from app.services.users import UserService
from tests.conftest import make_question

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
DEV = "Разработчик · Глава 8"
ADMIN = "Администратор · Глава 2"
CS = "Клиент-сервер · Глава 1"


async def setup_bank(session):
    session.add(make_question("dev.001", DEV))
    session.add(make_question("adm.001", ADMIN))
    session.add(make_question("cs.001", CS, is_active=False))
    user = await UserService(session).register(7, "Иван", now=MOMENT)
    await session.flush()
    return user


# --- темы ----------------------------------------------------------------


async def test_available_topics_exclude_those_without_active_questions(session):
    await setup_bank(session)

    available = await TopicPreferenceService(session).available()

    assert available == sorted([ADMIN, DEV])


async def test_choosing_several_topics_is_saved_and_applied(session):
    await setup_bank(session)
    service = TopicPreferenceService(session)

    await service.save(7, [DEV, ADMIN])

    applied = await service.applied(7)
    assert sorted(applied.categories) == sorted([DEV, ADMIN])
    assert applied.fell_back is False


async def test_selection_survives_a_restart(session_factory):
    async with session_scope(session_factory) as session:
        await setup_bank(session)
        await TopicPreferenceService(session).save(7, [DEV])

    # новая сессия — как после перезапуска процесса
    async with session_factory() as session:
        applied = await TopicPreferenceService(session).applied(7)

    assert applied.categories == [DEV]


async def test_selecting_a_whole_manual_keeps_the_other_choices(session):
    """Кнопка «выбрать все» дополняет выбор, а не заменяет его целиком."""
    await setup_bank(session)
    service = TopicPreferenceService(session)
    await service.save(7, [ADMIN])

    await service.set_many(7, [DEV], chosen=True)
    assert sorted(await service.selected(7)) == sorted([ADMIN, DEV])

    await service.set_many(7, [DEV], chosen=False)
    assert await service.selected(7) == [ADMIN]


async def test_reset_means_all_topics(session):
    await setup_bank(session)
    service = TopicPreferenceService(session)
    await service.save(7, [DEV])

    await service.reset(7)

    applied = await service.applied(7)
    assert applied.categories == []
    assert applied.fell_back is False


async def test_toggle_switches_a_topic_on_and_off(session):
    await setup_bank(session)
    service = TopicPreferenceService(session)

    assert await service.toggle(7, DEV) is True
    assert await service.selected(7) == [DEV]
    assert await service.toggle(7, DEV) is False
    assert await service.selected(7) == []


async def test_emptied_topic_falls_back_to_all_topics(session):
    """Спека `private-quiz`, сценарий «Выбранная тема опустела»."""
    await setup_bank(session)
    service = TopicPreferenceService(session)
    await service.save(7, [CS])  # в этой теме только неактивный вопрос

    applied = await service.applied(7)

    assert applied.categories == []
    assert applied.fell_back is True


async def test_partially_emptied_selection_keeps_the_rest(session):
    await setup_bank(session)
    service = TopicPreferenceService(session)
    await service.save(7, [DEV, CS])

    applied = await service.applied(7)

    assert applied.categories == [DEV]
    assert applied.fell_back is False


# --- лимиты --------------------------------------------------------------


async def test_quiz_limit_is_spent_and_then_refused(session):
    user = await setup_bank(session)
    await SettingsService(session).set_quiz_limit(2)
    service = LimitService(session)

    assert (await service.consume(user, KIND_QUIZ, now=MOMENT)).allowed
    assert (await service.consume(user, KIND_QUIZ, now=MOMENT)).allowed
    refused = await service.consume(user, KIND_QUIZ, now=MOMENT)

    assert refused.allowed is False
    assert refused.limit == 2


async def test_limits_are_independent(session):
    user = await setup_bank(session)
    await SettingsService(session).set_random_limit(1)
    service = LimitService(session)

    await service.consume(user, KIND_RANDOM, now=MOMENT)
    assert (await service.consume(user, KIND_RANDOM, now=MOMENT)).allowed is False
    assert (await service.consume(user, KIND_QUIZ, now=MOMENT)).allowed is True


async def test_limits_reset_on_the_next_day(session):
    user = await setup_bank(session)
    await SettingsService(session).set_quiz_limit(1)
    service = LimitService(session)

    await service.consume(user, KIND_QUIZ, now=MOMENT)
    tomorrow = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)

    assert (await service.consume(user, KIND_QUIZ, now=tomorrow)).allowed is True


async def test_race_of_two_consumptions_allows_exactly_one(session_factory):
    """При остатке в единицу два одновременных списания дают одно разрешение."""
    async with session_scope(session_factory) as session:
        await setup_bank(session)
        await SettingsService(session).set_quiz_limit(1)

    async def consume() -> bool:
        async with session_scope(session_factory) as session:
            user = await UserService(session).get(7)
            decision = await LimitService(session).consume(user, KIND_QUIZ, now=MOMENT)
            return decision.allowed

    outcomes = await asyncio.gather(consume(), consume(), return_exceptions=True)
    allowed = [item for item in outcomes if item is True]

    async with session_factory() as session:
        row = await session.get(UserDailyLimits, 1)
        assert row.quiz_starts == 1
    assert len(allowed) == 1


# --- режимы лимитов ------------------------------------------------------


async def test_disabled_for_all_lets_everyone_through(session):
    user = await setup_bank(session)
    await SettingsService(session).set_quiz_limit(1)
    await SettingsService(session).set_limit_mode(LimitMode.DISABLED_FOR_ALL)
    service = LimitService(session)

    for _ in range(6):
        assert (await service.consume(user, KIND_QUIZ, now=MOMENT)).allowed


async def test_disabled_for_admins_still_limits_plain_users(session):
    await setup_bank(session)
    await SettingsService(session).set_quiz_limit(1)
    await SettingsService(session).set_limit_mode(LimitMode.DISABLED_FOR_ADMINS)
    users = UserService(session)
    plain = await users.register(8, "Пётр", now=MOMENT)
    admin = await users.grant_admin(7)
    service = LimitService(session)

    await service.consume(plain, KIND_QUIZ, now=MOMENT)
    assert (await service.consume(plain, KIND_QUIZ, now=MOMENT)).allowed is False

    for _ in range(10):
        assert (await service.consume(admin, KIND_QUIZ, now=MOMENT)).allowed


async def test_mode_change_applies_to_the_next_request(session):
    user = await setup_bank(session)
    await SettingsService(session).set_quiz_limit(1)
    service = LimitService(session)

    await service.consume(user, KIND_QUIZ, now=MOMENT)
    assert (await service.consume(user, KIND_QUIZ, now=MOMENT)).allowed is False

    await SettingsService(session).set_limit_mode(LimitMode.DISABLED_FOR_ALL)
    assert (await service.consume(user, KIND_QUIZ, now=MOMENT)).allowed is True


async def test_returning_limits_accounts_for_what_was_already_spent(session):
    """Спека `private-quiz`, сценарий «Возврат лимитов»."""
    user = await setup_bank(session)
    await SettingsService(session).set_quiz_limit(2)
    service = LimitService(session)

    await service.consume(user, KIND_QUIZ, now=MOMENT)
    await SettingsService(session).set_limit_mode(LimitMode.DISABLED_FOR_ALL)
    await service.consume(user, KIND_QUIZ, now=MOMENT)
    await SettingsService(session).set_limit_mode(LimitMode.ENABLED)

    state = await service.state(user, now=MOMENT)
    assert state.quiz_used == 1  # безлимитный запуск счётчик не трогал
    assert (await service.consume(user, KIND_QUIZ, now=MOMENT)).allowed is True
    assert (await service.consume(user, KIND_QUIZ, now=MOMENT)).allowed is False


async def test_state_reports_both_remainders_and_the_reset_moment(session):
    user = await setup_bank(session)
    service = LimitService(session)
    await service.consume(user, KIND_RANDOM, now=MOMENT)

    state = await service.state(user, now=MOMENT)

    assert (state.quiz_left, state.random_left) == (5, 19)
    assert state.enforced is True
    assert state.reset_at == datetime(2026, 3, 10, 21, 0, tzinfo=UTC)
