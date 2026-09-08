"""Порядок показа вариантов: перестановка, устойчивость, клавиатуры."""

from __future__ import annotations

from app.bot.callbacks import RandomAnswerCallback, SessionAnswerCallback
from app.bot.keyboards.quiz import OPTION_LABELS, random_question, session_question
from app.services.quiz.options import display_order, shuffled_order
from tests.conftest import make_question


def test_display_order_is_a_permutation():
    for count in range(2, 11):
        assert sorted(display_order(count, ("s", 1))) == list(range(count))


def test_display_order_is_stable_for_the_same_key():
    first = display_order(4, (7, 2))
    assert all(display_order(4, (7, 2)) == first for _ in range(5))


def test_display_order_differs_between_keys():
    orders = {tuple(display_order(4, (1, position))) for position in range(20)}
    assert len(orders) > 1


def test_shuffled_order_is_a_permutation_and_varies():
    orders = {tuple(shuffled_order(4)) for _ in range(50)}
    assert len(orders) > 1
    for order in orders:
        assert sorted(order) == [0, 1, 2, 3]


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_session_keyboard_keeps_the_original_option_index():
    question = make_question()
    buttons = _buttons(session_question(question, session_id=5, position=3))[:4]

    for button in buttons:
        data = SessionAnswerCallback.unpack(button.callback_data)
        assert button.text.endswith(question.options[data.option].text)


def test_random_keyboard_keeps_the_original_option_index():
    question = make_question()
    buttons = _buttons(random_question(question, issue_id=11))

    for button in buttons:
        data = RandomAnswerCallback.unpack(button.callback_data)
        assert button.text.endswith(question.options[data.option].text)


def test_option_labels_follow_the_display_order():
    question = make_question()
    buttons = _buttons(session_question(question, session_id=5, position=3))[:4]

    assert [button.text[0] for button in buttons] == list(OPTION_LABELS[:4])


def test_session_keyboard_is_redrawn_in_the_same_order():
    question = make_question()
    first = [b.text for b in _buttons(session_question(question, 5, 3))]
    again = [b.text for b in _buttons(session_question(question, 5, 3))]

    assert first == again


def test_correct_option_is_not_always_first_in_private():
    """У всех вопросов банка верный вариант записан первым."""
    question = make_question()
    first_shown = {
        _buttons(session_question(question, 5, position))[0].text
        for position in range(20)
    }

    assert len(first_shown) > 1


# --- сквозная проверка ---------------------------------------------------


async def test_answer_by_shown_button_is_scored_and_reviewed(session):
    """Ответ по кнопке показа учитывается по тексту варианта, а не по позиции."""
    from app.models import Question
    from app.services.quiz.review import ReviewService
    from app.services.quiz.session import QuizSessionService
    from app.services.settings import SettingsService
    from app.services.users import UserService

    for index in range(5):
        session.add(make_question(f"q.{index:03d}", correct_index=0))
    user = await UserService(session).register(7, "Иван", now=None)
    await session.flush()
    await SettingsService(session).set_session_size(3)

    service = QuizSessionService(session)
    quiz = (await service.start(user)).session
    for position in range(3):
        item = await service.current_question(quiz)
        question = await session.get(Question, item.question_id)
        buttons = _buttons(session_question(question, quiz.id, position))[:4]
        correct_text = question.options[question.correct_index].text
        chosen = next(b for b in buttons if b.text.endswith(correct_text))
        option = SessionAnswerCallback.unpack(chosen.callback_data).option
        recorded, _ = await service.answer(user, quiz, position, option)
        assert recorded.is_correct

    items = await ReviewService(session).build(quiz)
    assert len(items) == 3
    for item in items:
        assert item.is_correct and item.chosen == item.correct


def test_admin_card_keeps_the_storage_order():
    """В кабинете список вариантов — редактируемый источник, его не мешаем."""
    from app.bot.handlers.admin_questions import render_question

    question = make_question()
    card = render_question(question)
    shown = [line for line in card.splitlines() if line.startswith(("✅", "▫️"))]

    assert [line.split()[-1] for line in shown] == ["0", "1", "2", "3"]
    assert shown[0].startswith("✅")
