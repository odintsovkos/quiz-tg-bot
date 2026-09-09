"""Все пользовательские строки бота.

Вынесены отдельным модулем, чтобы позже добавить локализацию; реализуется
только русский.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import time
from html import escape

# --- общее ---------------------------------------------------------------

ERROR_GENERIC = "Что-то пошло не так. Попробуйте ещё раз чуть позже."
ACCESS_DENIED = "Команда доступна только администраторам бота."
BUTTON_EXPIRED = "Кнопка устарела — откройте меню заново."
UNKNOWN_COMMAND = "Не понимаю команду. Наберите /help."

# --- старт и справка -----------------------------------------------------

START = (
    "Привет, {name}!\n\n"
    "Я задаю вопросы из банка — по темам, которые вы выберете.\n"
    "Здесь, в личке, можно пройти викторину из нескольких вопросов, взять "
    "один случайный вопрос, выбрать интересные темы и посмотреть свою "
    "статистику и таблицу результатов.\n\n"
    "Наберите /menu, чтобы открыть главное меню.\n"
    "Наберите /help, чтобы увидеть список команд."
)

HELP_USER = (
    "<b>Что я умею</b>\n\n"
    "/quiz — запустить викторину\n"
    "/random — один случайный вопрос\n"
    "/topics — выбрать темы вопросов\n"
    "/stats — моя статистика\n"
    "/top — таблица результатов\n"
    "/limits — остаток дневных лимитов\n"
    "/menu — главное меню\n"
    "/help — эта справка"
)

HELP_ADMIN_EXTRA = "\n\n<b>Администратору</b>\n/admin — кабинет администратора"

MENU_TITLE = "Главное меню"

# --- команды в меню Telegram ---------------------------------------------

COMMAND_DESCRIPTIONS: dict[str, str] = {
    "start": "Начать работу с ботом",
    "menu": "Главное меню",
    "quiz": "Запустить викторину",
    "random": "Случайный вопрос",
    "topics": "Выбрать темы",
    "stats": "Моя статистика",
    "top": "Таблица результатов",
    "limits": "Остаток лимитов",
    "topic": "Публиковать вопросы в эту тему",
    "help": "Справка",
}

# --- викторина -----------------------------------------------------------

QUIZ_QUESTION = (
    "<b>Вопрос {number} из {total}</b>\n\n<blockquote>{text}</blockquote>\n\n{options}"
)
RANDOM_QUESTION = (
    "<b>Случайный вопрос</b>\n\n<blockquote>{text}</blockquote>\n\n{options}"
)

ANSWER_CORRECT = "✅ <b>Верно!</b>"
ANSWER_WRONG = "❌ <b>Неверно</b>\n\nВерный ответ: <b>{correct}</b>"
ANSWER_EXPLANATION = "\n\n<blockquote>{explanation}</blockquote>"
ANSWER_REFERENCE = "\n\n<i>Источник: {reference}</i>"
ANSWER_ALREADY_GIVEN = "На этот вопрос вы уже ответили."

SESSION_ALREADY_ACTIVE = (
    "У вас уже идёт викторина — вопрос {number} из {total}. "
    "Продолжить её или начать новую?"
)
SESSION_SHORTER_THAN_ASKED = (
    "В выбранных темах нашлось только {count} вопросов — викторина будет из них."
)
SESSION_NO_QUESTIONS = (
    "В выбранных темах нет ни одного активного вопроса. "
    "Измените выбор тем командой /topics — лимит при этом не расходуется."
)
SESSION_RESULT = (
    "<b>Викторина завершена</b>\n\n"
    "✅ Верных: {correct} из {total}\n"
    "⭐ За сессию: {points}\n"
    "🎯 Точность: {accuracy}\n\n"
    "☀️ Сегодня: ⭐ {daily_points}  🎯 {daily_accuracy}\n"
    "🗓 За всё время: ⭐ {total_points}  🎯 {total_accuracy}"
)
SESSION_RESULT_NOT_COUNTED = (
    "\n\n<i>Сейчас действует режим без лимитов для администраторов, "
    "поэтому эти ответы в общий зачёт не пошли.</i>"
)
SESSION_ABORTED = "Викторина прервана. Засчитанные ответы сохранены."

REVIEW_TITLE = "<b>Разбор викторины</b>  <i>стр. {page} из {pages}</i>"
REVIEW_EMPTY = "Разбирать нечего: вопросы этой сессии больше не в банке."
REVIEW_ITEM = "{mark} <b>{number}.</b> {text}\n<b>Верно:</b> {correct}"
REVIEW_ITEM_CHOSEN = "\n<b>Вы ответили:</b> {chosen}"
REVIEW_ITEM_SKIPPED = "\n<i>Вы не ответили на этот вопрос.</i>"
REVIEW_ITEM_EXPLANATION = "\n{explanation}"
REVIEW_ITEM_REFERENCE = "\n<i>Источник: {reference}</i>"
REVIEW_MARK_CORRECT = "✅"
REVIEW_MARK_WRONG = "❌"
REVIEW_MARK_SKIPPED = "▫️"

SESSION_PROGRESS = "Текущий счёт: ✅ {correct} из {answered}  ⭐ {points}"
SESSION_NONE_ACTIVE = "Сейчас у вас нет активной викторины."

TOPICS_FALLBACK_APPLIED = (
    "В выбранных вами темах не осталось активных вопросов, поэтому вопрос взят "
    "из всех тем. Обновите выбор командой /topics."
)

# --- темы ----------------------------------------------------------------

TOPICS_TITLE = (
    "<b>Темы вопросов</b>\n\nВыберите руководство, затем отметьте нужные главы. "
    "Отмеченные темы применяются к викторине и к случайным вопросам. "
    "Если не выбрано ничего — используются все темы."
)
TOPICS_GROUP_TITLE = (
    "<b>{group}</b>\n\nОтметьте главы, по которым хотите получать вопросы. "
    "Выбор сохраняется сразу."
)
TOPICS_GROUP_BUTTON = "{name} — {selected} из {total}"
TOPICS_GROUP_ALL_SELECTED = "Отмечены все главы руководства."
TOPICS_GROUP_ALL_CLEARED = "Отметки со всех глав руководства сняты."
TOPICS_PAGE_LABEL = "стр. {page} из {pages}"
TOPICS_SAVED = "Выбор тем сохранён."
TOPICS_ALL_SELECTED = "Отмечены все темы банка."
TOPICS_RESET = "Выбор сброшен: используются все темы."
TOPICS_EMPTY_BANK = "В банке пока нет активных вопросов."

# --- лимиты --------------------------------------------------------------

LIMITS_STATE = (
    "<b>Дневные лимиты</b>\n\n"
    "Викторины: {quiz_left} из {quiz_limit}\n"
    "Случайные вопросы: {random_left} из {random_limit}\n\n"
    "Обновятся в {reset_at}."
)
LIMITS_DISABLED = "<b>Дневные лимиты</b>\n\nСейчас лимиты не действуют."
LIMIT_QUIZ_REACHED = (
    "Лимит запусков викторины на сегодня исчерпан: {limit} в сутки. "
    "Лимит обновится в {reset_at}."
)
LIMIT_RANDOM_REACHED = (
    "Лимит случайных вопросов на сегодня исчерпан: {limit} в сутки. "
    "Лимит обновится в {reset_at}."
)
LIMITS_NOT_COUNTED_NOTICE = (
    "Напоминаю: сейчас ваши ответы в личке не идут в общий зачёт — "
    "действует режим без лимитов для администраторов."
)

# --- статистика ----------------------------------------------------------

STATS_CARD = (
    "📊 <b>Ваша статистика</b>\n\n"
    "☀️ <b>Сегодня</b>\n"
    "❓ Попыток: {daily_attempts}  ✅ Верных: {daily_correct}\n"
    "⭐ Баллов: {daily_points}  🎯 Точность: {daily_accuracy}\n"
    "🥇 Место: {daily_rank}\n\n"
    "🗓 <b>За всё время</b>\n"
    "❓ Попыток: {total_attempts}  ✅ Верных: {total_correct}\n"
    "⭐ Баллов: {total_points}  🎯 Точность: {total_accuracy}\n"
    "🥇 Место: {total_rank}"
)
STATS_NEWCOMER = (
    "\n\nВы ещё не отвечали ни на один вопрос — начните с /quiz или /random."
)
STATS_SESSION_LINE = "\n\nТекущая сессия: {correct} верных из {answered}."

ACCURACY_UNDEFINED = "—"
RANK_UNDEFINED = "—"

#: Медали за первые три места, дальше — обычный номер с точкой.
RANK_MEDALS = ("🥇", "🥈", "🥉")
#: Место в карточке статистики — своё место среди участников периода.
STATS_PLACE = "{rank} из {total}"

LEADERBOARD_TODAY_TITLE = "<b>Таблица результатов за сегодня</b>"
LEADERBOARD_TOTAL_TITLE = "<b>Таблица результатов за всё время</b>"
LEADERBOARD_ROW = "{rank} {name} — ⭐ {points}  🎯 {accuracy}"
LEADERBOARD_SELF_ROW = "\n\nВы: {rank} {name} — ⭐ {points}  🎯 {accuracy}"
LEADERBOARD_EMPTY_TODAY = "Сегодня ещё никто не отвечал."
LEADERBOARD_EMPTY_TOTAL = "Результатов пока нет."

# --- групповой чат -------------------------------------------------------

CHAT_CONNECTED = (
    "Чат подключён. Вопросы будут публиковаться раз в {interval} мин "
    "с {window_start} до {window_end}.\n\n"
    "Опросы неанонимные — участники видят, кто как ответил: иначе ответы "
    "нельзя связать с участником и начислить баллы."
)
CHAT_ALREADY_CONNECTED = "Чат уже подключён."
CHAT_DISCONNECTED = "Чат отключён. Статистика участников сохранена."
CHAT_NOT_CONNECTED = "Этот чат не подключён к боту."
CHAT_NO_POLL_RIGHTS = (
    "Не могу подключить чат: у бота нет права отправлять опросы. "
    "Выдайте боту это право в настройках чата и повторите."
)
CHAT_NO_MESSAGE_RIGHTS = (
    "Не могу подключить чат: у бота нет права отправлять сообщения."
)
CHAT_ONLY_IN_GROUP = "Эта команда работает только в групповом чате."

TOPIC_LABEL_NAMED = "«{title}»"
TOPIC_LABEL_NUMBERED = "тема №{id}"
TOPIC_LABEL_GENERAL = "общая лента чата"
TOPIC_BOUND = (
    "Вопросы буду публиковать сюда: {topic}.\n\n"
    "Чтобы вернуть их в общую ленту, отправьте эту же команду вне темы."
)
TOPIC_CLEARED = "Вопросы буду публиковать в общую ленту чата."
TOPIC_LOST = (
    "Тема для вопросов в чате «{chat}» стала недоступна — удалена, закрыта "
    "или у бота нет права в ней писать. Вопрос опубликован в общую ленту, "
    "публикация в тему отключена."
)

# --- уведомления администраторам -----------------------------------------

NOTIFY_EMPTY_BANK = (
    "Публикация в чат «{chat}» пропущена: в заданных категориях нет активных вопросов."
)
NOTIFY_CHAT_UNAVAILABLE = (
    "Чат «{chat}» стал недоступен — публикации в него остановлены. "
    "Проверьте, что бот в чате и у него есть права."
)


def format_time(value: time) -> str:
    return value.strftime("%H:%M")


def accuracy(correct: int, attempts: int) -> str:
    """Точность как доля верных от попыток; при нуле попыток — прочерк."""
    if attempts <= 0:
        return ACCURACY_UNDEFINED
    return f"{correct * 100 / attempts:.0f}%"


def rank_label(rank: int) -> str:
    """Метка места: медаль за первые три места, дальше номер с точкой."""
    if 1 <= rank <= len(RANK_MEDALS):
        return RANK_MEDALS[rank - 1]
    return f"{rank}."


def option_block(order: Sequence[tuple[str, int]], options: Sequence[str]) -> str:
    """Список вариантов для тела сообщения: по строке на вариант.

    Порядок и буквы приходят готовыми — теми же, по которым собран ряд кнопок.
    Буква набирается жирным: ею же подписана кнопка под списком.
    """
    return "\n".join(
        f"<b>{label}.</b> {escape(options[index])}" for label, index in order
    )


def quiz_question_screen(number: int, total: int, text: str, options: str) -> str:
    """Экран вопроса сессии: шапка, вопрос в цитате, список вариантов."""
    return QUIZ_QUESTION.format(
        number=number, total=total, text=escape(text), options=options
    )


def random_question_screen(text: str, options: str) -> str:
    """То же для одиночного случайного вопроса."""
    return RANDOM_QUESTION.format(text=escape(text), options=options)


def answer_feedback(correct: str | None, explanation: str, reference: str) -> str:
    """Разбор ответа: вердикт, верный вариант при ошибке, пояснение, источник.

    `correct` — текст верного варианта; `None`, если участник ответил верно.

    Экранируется всё, что пришло из банка. Невалидная разметка отвергается
    Telegram целиком, и экран-якорь застыл бы на прежнем содержимом, поэтому
    подстановка сырого текста в разметку не допускается ни здесь, ни в
    `option_block`, ни в экранах вопроса.
    """
    text = (
        ANSWER_CORRECT
        if correct is None
        else ANSWER_WRONG.format(correct=escape(correct))
    )
    if explanation:
        text += ANSWER_EXPLANATION.format(explanation=escape(explanation))
    if reference:
        text += ANSWER_REFERENCE.format(reference=escape(reference))
    return text
