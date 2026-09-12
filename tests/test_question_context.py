"""Шапка вопроса в личке: тема, раздел, маркер сложности.

Спека `private-quiz`, требование «Шапка вопроса в личке».
"""

from __future__ import annotations

from app.bot import texts
from app.models import Difficulty
from app.services.content.validation import MAX_QUESTION_LENGTH
from app.services.stats.reading import QuestionStats, difficulty_of

APPENDIX = "Администратор · Приложение 2. Описание элементов журнала регистрации"
CHAPTER = "Разработчик · Глава 6. Командный интерфейс"
SECTION = "6.1.2.1.1. Формирование и размещение стандартных команд"


def measured(answers: int = 40, correct: int = 9) -> object:
    return difficulty_of(QuestionStats(answers, correct), Difficulty.MEDIUM)


def authored(level: Difficulty = Difficulty.MEDIUM) -> object:
    return difficulty_of(QuestionStats(7, 3), level)


# --- раздел против темы ---------------------------------------------------


def test_section_is_dropped_when_it_repeats_the_category():
    """Пара из банка: у вопросов приложения раздел равен названию приложения."""
    repeated = "Приложение 2. Описание элементов журнала регистрации"
    assert texts.section_of(APPENDIX, repeated) is None


def test_section_is_kept_when_it_adds_something():
    assert texts.section_of(CHAPTER, SECTION) == SECTION


def test_section_of_empty_reference_is_nothing():
    assert texts.section_of(CHAPTER, None) is None
    assert texts.section_of(CHAPTER, "   ") is None


def test_section_numbering_does_not_hide_a_meaningful_section():
    """Нумерация снимается только для сравнения, в показ идёт как есть."""
    assert texts.section_of(CHAPTER, "20.1. Общие сведения") == "20.1. Общие сведения"


# --- сборка шапки --------------------------------------------------------


def test_context_of_a_question_with_everything_has_two_lines():
    """Тема и раздел — под заголовком; сложность уходит в сам заголовок."""
    context = texts.question_context(CHAPTER, SECTION)

    lines = context.splitlines()
    assert lines[0] == ""  # шапка приклеивается к строке «Вопрос N из M»
    assert lines[1] == f"📘 {CHAPTER}"
    assert lines[2] == f"<i>{SECTION}</i>"
    assert len(lines) == 3


def test_context_of_a_question_with_only_a_category_is_one_line():
    context = texts.question_context("Тема без раздела")

    assert context == "\n📘 Тема без раздела"


def test_context_has_no_blank_lines_or_dashes_for_missing_parts():
    context = texts.question_context(CHAPTER, None)

    assert "\n\n" not in context
    assert "—" not in context
    assert context.splitlines()[1:] == [f"📘 {CHAPTER}"]


# --- маркер в строке заголовка -------------------------------------------


def test_marker_goes_into_the_title_line_behind_a_gap():
    assert texts.difficulty_marker(measured()) == "  🔴 верно отвечают 23%"
    assert texts.difficulty_marker(authored()) == "  🟡 Сложность: средняя"


def test_no_marker_leaves_the_title_line_untouched():
    assert texts.difficulty_marker(difficulty_of(QuestionStats(7, 3), None)) == ""
    assert texts.difficulty_marker(None) == ""


def test_context_escapes_markup_in_the_category_and_section():
    context = texts.question_context("Тема <b> и &", "Раздел <i> и &")

    assert "Тема &lt;b&gt; и &amp;" in context
    assert "Раздел &lt;i&gt; и &amp;" in context
    assert "<b>" not in context


# --- маркер сложности ----------------------------------------------------


def test_marker_of_a_measured_question_names_the_share():
    assert texts.difficulty_line(measured()) == "🔴 верно отвечают 23%"


def test_marker_below_the_threshold_names_the_level_in_words():
    """Доли верных ещё нет, поэтому уровень называется словом."""
    assert texts.difficulty_line(authored()) == "🟡 Сложность: средняя"
    assert texts.difficulty_line(authored(Difficulty.EASY)) == "🟢 Сложность: низкая"
    assert texts.difficulty_line(authored(Difficulty.HARD)) == "🔴 Сложность: высокая"


def test_marker_colours_follow_the_level():
    assert texts.difficulty_line(measured(20, 20)) == "🟢 верно отвечают 100%"
    assert texts.difficulty_line(measured(20, 10)) == "🟡 верно отвечают 50%"
    assert texts.difficulty_line(measured(20, 5)) == "🔴 верно отвечают 25%"


def test_no_marker_without_statistics_and_without_authored_level():
    assert texts.difficulty_line(difficulty_of(QuestionStats(7, 3), None)) is None
    assert texts.difficulty_line(None) is None


# --- экраны вопроса ------------------------------------------------------


def test_both_question_screens_carry_the_context_above_the_question():
    context = texts.question_context(CHAPTER, SECTION)
    marker = texts.difficulty_marker(measured())
    options = "<b>А.</b> Раз\n<b>Б.</b> Два"

    quiz = texts.quiz_question_screen(4, 10, "Вопрос?", options, context, marker)
    single = texts.random_question_screen("Вопрос?", options, context, marker)

    for rendered in (quiz, single):
        head, _, body = rendered.partition("\n\n<blockquote>")
        assert head.endswith(f"<i>{SECTION}</i>")
        assert f"📘 {CHAPTER}" in head
        assert body.startswith("Вопрос?</blockquote>")

    assert quiz.startswith("<b>Вопрос 4 из 10</b>  🔴 верно отвечают 23%\n📘")
    assert single.startswith("<b>Случайный вопрос</b>  🔴 верно отвечают 23%\n📘")


def test_options_stay_at_the_bottom_of_the_screen():
    """Шапка не трогает список вариантов: он по-прежнему в теле сообщения."""
    options = "<b>А.</b> Раз\n<b>Б.</b> Два"

    quiz = texts.quiz_question_screen(
        4, 10, "Вопрос?", options, texts.question_context(CHAPTER), "  🟡 Сложность: средняя"
    )

    assert quiz.endswith(f"</blockquote>\n\n{options}")


def test_poll_question_puts_the_category_first():
    assert texts.poll_question("Тема", "Вопрос?") == "Тема\n\nВопрос?"


def test_poll_question_puts_the_difficulty_under_the_category():
    composed = texts.poll_question("Тема", "Вопрос?", "🔴 Сложность: высокая")

    assert composed == "Тема\n🔴 Сложность: высокая\n\nВопрос?"


def test_poll_question_drops_the_difficulty_before_the_category():
    """При переполнении первым уходит маркер, тема держится до последнего."""
    marker = "🔴 Сложность: высокая"
    text = "Вопрос?"
    # Тема с вопросом ещё влезает, а вместе с маркером — уже нет.
    category = "Т" * (MAX_QUESTION_LENGTH - len(text) - 2)

    composed = texts.poll_question(category, text, marker)

    assert composed == f"{category}\n\n{text}"
    assert texts.poll_length(composed) == MAX_QUESTION_LENGTH


def test_poll_question_drops_both_when_only_the_question_fits():
    text = "Вопрос?"
    category = "Т" * (MAX_QUESTION_LENGTH - len(text) - 1)

    assert texts.poll_question(category, text, "🔴 Сложность: высокая") == text


def test_poll_question_fills_the_limit_to_the_last_unit():
    text = "Вопрос?"
    category = "Т" * (MAX_QUESTION_LENGTH - len(text) - 2)

    composed = texts.poll_question(category, text)

    assert texts.poll_length(composed) == MAX_QUESTION_LENGTH
    assert composed.startswith(category)


def test_poll_question_drops_the_category_instead_of_cutting_the_question():
    text = "Вопрос?"
    category = "Т" * (MAX_QUESTION_LENGTH - len(text) - 1)

    assert texts.poll_question(category, text) == text


def test_poll_question_without_a_category_is_the_question_itself():
    assert texts.poll_question("   ", "Вопрос?") == "Вопрос?"


def test_question_screens_without_context_stay_as_they_were():
    options = "<b>А.</b> Раз"

    quiz = texts.quiz_question_screen(1, 3, "Вопрос?", options)

    assert quiz == (
        "<b>Вопрос 1 из 3</b>\n\n<blockquote>Вопрос?</blockquote>\n\n" + options
    )
