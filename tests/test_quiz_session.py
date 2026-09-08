"""Сессия личной викторины и одиночный случайный вопрос."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import LimitMode, Question, SessionStatus
from app.services.quiz.limits import KIND_QUIZ, LimitService
from app.services.quiz.session import QuizSessionService
from app.services.quiz.topics import TopicPreferenceService
from app.services.settings import SettingsService
from app.services.stats.reading import StatsService
from app.services.users import UserService
from tests.conftest import make_question

MOMENT = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
DEV = "Разработчик · Глава 8"
ADMIN = "Администратор · Глава 2"


async def setup(session, *, questions: int = 12, category: str = DEV):
    for index in range(questions):
        session.add(make_question(f"q.{index:03d}", category, correct_index=index % 4))
    user = await UserService(session).register(7, "Иван", now=MOMENT)
    await session.flush()
    return user


# --- старт ---------------------------------------------------------------


async def test_start_creates_a_session_of_the_configured_size(session):
    user = await setup(session)
    await SettingsService(session).set_session_size(5)

    outcome = await QuizSessionService(session).start(user, now=MOMENT)

    assert outcome.session is not None
    assert outcome.session.total_questions == 5
    assert len(outcome.session.questions) == 5
    assert outcome.shortened_to is None


async def test_questions_within_a_session_are_unique(session):
    user = await setup(session)
    await SettingsService(session).set_session_size(10)

    outcome = await QuizSessionService(session).start(user, now=MOMENT)

    ids = [item.question_id for item in outcome.session.questions]
    assert len(set(ids)) == len(ids)


async def test_second_start_offers_the_running_session(session):
    user = await setup(session)
    service = QuizSessionService(session)
    first = await service.start(user, now=MOMENT)

    second = await service.start(user, now=MOMENT)

    assert second.session is None
    assert second.active is not None
    assert second.active.id == first.session.id


async def test_restart_closes_the_previous_session(session):
    user = await setup(session)
    service = QuizSessionService(session)
    first = await service.start(user, now=MOMENT)

    second = await service.start(user, restart=True, now=MOMENT)

    assert second.session.id != first.session.id
    assert first.session.status is SessionStatus.ABORTED


async def test_shortage_of_questions_shortens_the_session_with_a_warning(session):
    user = await setup(session, questions=3)
    await SettingsService(session).set_session_size(10)

    outcome = await QuizSessionService(session).start(user, now=MOMENT)

    assert outcome.session.total_questions == 3
    assert outcome.shortened_to == 3


async def test_no_questions_means_no_session_and_no_limit_spent(session):
    user = await setup(session, questions=0)

    outcome = await QuizSessionService(session).start(user, now=MOMENT)

    assert outcome.no_questions and outcome.session is None
    state = await LimitService(session).state(user, now=MOMENT)
    assert state.quiz_used == 0


async def test_limit_refusal_prevents_the_session(session):
    user = await setup(session)
    await SettingsService(session).set_quiz_limit(1)
    service = QuizSessionService(session)

    first = await service.start(user, now=MOMENT)
    await service.abort(first.session, now=MOMENT)
    second = await service.start(user, now=MOMENT)

    assert second.refused is not None
    assert second.refused.limit == 1
    assert second.session is None


async def test_aborted_session_does_not_return_the_limit(session):
    user = await setup(session)
    service = QuizSessionService(session)
    outcome = await service.start(user, now=MOMENT)

    await service.abort(outcome.session, now=MOMENT)

    state = await LimitService(session).state(user, now=MOMENT)
    assert state.quiz_used == 1


async def test_topics_narrow_the_pool(session):
    user = await setup(session, questions=4)
    session.add(make_question("adm.001", ADMIN))
    await session.flush()
    await TopicPreferenceService(session).save(7, [ADMIN])
    await SettingsService(session).set_session_size(10)

    outcome = await QuizSessionService(session).start(user, now=MOMENT)

    assert [item.question_id for item in outcome.session.questions] == ["adm.001"]


# --- прохождение ---------------------------------------------------------


async def test_questions_are_served_one_at_a_time(session):
    user = await setup(session)
    await SettingsService(session).set_session_size(3)
    service = QuizSessionService(session)
    quiz = (await service.start(user, now=MOMENT)).session

    first = await service.current_question(quiz)
    assert first.position == 0

    await service.answer(user, quiz, 0, 0, now=MOMENT)

    assert (await service.current_question(quiz)).position == 1


async def test_correct_answer_is_recorded_and_scored(session):
    user = await setup(session)
    await SettingsService(session).set_session_size(1)
    service = QuizSessionService(session)
    quiz = (await service.start(user, now=MOMENT)).session
    item = await service.current_question(quiz)
    question = await session.get(Question, item.question_id)

    recorded, returned = await service.answer(
        user, quiz, item.position, question.correct_index, now=MOMENT
    )

    assert recorded.is_correct and recorded.points == 1
    assert returned.id == question.id
    assert (await StatsService(session).total(7)).points == 1


async def test_repeated_click_on_an_answered_question_changes_nothing(session):
    user = await setup(session)
    await SettingsService(session).set_session_size(2)
    service = QuizSessionService(session)
    quiz = (await service.start(user, now=MOMENT)).session
    item = await service.current_question(quiz)

    await service.answer(user, quiz, item.position, 0, now=MOMENT)
    again = await service.answer(user, quiz, item.position, 1, now=MOMENT)

    assert again == (None, None)
    assert (await StatsService(session).total(7)).attempts == 1


async def test_session_completes_after_the_last_answer(session):
    user = await setup(session)
    await SettingsService(session).set_session_size(2)
    service = QuizSessionService(session)
    quiz = (await service.start(user, now=MOMENT)).session

    for position in range(2):
        await service.answer(user, quiz, position, 0, now=MOMENT)

    assert quiz.status is SessionStatus.COMPLETED
    progress = await service.progress(quiz)
    assert progress.finished and progress.answered == 2


async def test_abort_keeps_the_answers_already_given(session):
    user = await setup(session)
    await SettingsService(session).set_session_size(3)
    service = QuizSessionService(session)
    quiz = (await service.start(user, now=MOMENT)).session
    await service.answer(user, quiz, 0, 0, now=MOMENT)

    await service.abort(quiz, now=MOMENT)

    assert quiz.status is SessionStatus.ABORTED
    assert (await StatsService(session).total(7)).attempts == 1


async def test_abandoned_session_is_closed_and_a_new_one_starts(session):
    user = await setup(session)
    await SettingsService(session).set_session_size(2)
    service = QuizSessionService(session)
    old = (await service.start(user, now=MOMENT)).session
    await service.answer(user, old, 0, 0, now=MOMENT)

    later = MOMENT + timedelta(hours=4)
    outcome = await service.start(user, now=later)

    assert old.status is SessionStatus.EXPIRED
    assert outcome.session is not None and outcome.session.id != old.id
    assert (await StatsService(session).total(7)).attempts == 1


# --- одиночный случайный вопрос ------------------------------------------


async def test_random_question_is_issued_and_spends_its_own_limit(session):
    user = await setup(session)
    service = QuizSessionService(session)

    outcome = await service.issue_random(user, now=MOMENT)

    assert outcome.question is not None and outcome.issue is not None
    state = await LimitService(session).state(user, now=MOMENT)
    assert (state.random_used, state.quiz_used) == (1, 0)


async def test_random_question_does_not_touch_an_active_session(session):
    user = await setup(session)
    await SettingsService(session).set_session_size(3)
    service = QuizSessionService(session)
    quiz = (await service.start(user, now=MOMENT)).session

    await service.issue_random(user, now=MOMENT)

    progress = await service.progress(quiz)
    assert progress.answered == 0
    assert (await service.current_question(quiz)).position == 0


async def test_random_answer_is_scored_like_a_session_answer(session):
    user = await setup(session)
    service = QuizSessionService(session)
    outcome = await service.issue_random(user, now=MOMENT)

    recorded, question = await service.answer_random(
        user, outcome.issue, outcome.question.correct_index, now=MOMENT
    )

    assert recorded.is_correct and recorded.points == 1
    assert question.id == outcome.question.id
    assert (await StatsService(session).total(7)).points == 1


async def test_repeated_answer_to_one_issue_is_ignored(session):
    user = await setup(session)
    service = QuizSessionService(session)
    outcome = await service.issue_random(user, now=MOMENT)

    await service.answer_random(user, outcome.issue, 0, now=MOMENT)
    again = await service.answer_random(user, outcome.issue, 1, now=MOMENT)

    assert again == (None, None)
    assert (await StatsService(session).total(7)).attempts == 1


async def test_unanswered_questions_are_preferred(session):
    user = await setup(session, questions=2)
    service = QuizSessionService(session)

    first = await service.issue_random(user, now=MOMENT)
    await service.answer_random(user, first.issue, 0, now=MOMENT)
    second = await service.issue_random(user, now=MOMENT)

    assert second.question.id != first.question.id


async def test_random_limit_refusal_gives_no_question(session):
    user = await setup(session)
    await SettingsService(session).set_random_limit(1)
    service = QuizSessionService(session)

    await service.issue_random(user, now=MOMENT)
    refused = await service.issue_random(user, now=MOMENT)

    assert refused.refused is not None and refused.question is None


async def test_empty_topics_fall_back_and_report_it(session):
    user = await setup(session, questions=1)
    await TopicPreferenceService(session).save(7, ["Несуществующая тема"])

    outcome = await QuizSessionService(session).issue_random(user, now=MOMENT)

    assert outcome.question is not None
    assert outcome.topics_fell_back is True


async def test_admin_without_limits_can_keep_starting_sessions(session):
    await setup(session)
    await SettingsService(session).set_quiz_limit(1)
    await SettingsService(session).set_limit_mode(LimitMode.DISABLED_FOR_ADMINS)
    admin = await UserService(session).grant_admin(7)
    service = QuizSessionService(session)

    for _ in range(3):
        outcome = await service.start(admin, restart=True, now=MOMENT)
        assert outcome.session is not None

    assert (await LimitService(session).consume(admin, KIND_QUIZ, now=MOMENT)).allowed
