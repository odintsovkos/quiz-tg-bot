package ru.jrgroup.quiz_bot.bot.handler;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.telegram.telegrambots.bots.TelegramLongPollingBot;
import org.telegram.telegrambots.meta.TelegramBotsApi;
import org.telegram.telegrambots.meta.api.methods.polls.SendPoll;
import org.telegram.telegrambots.meta.api.methods.send.SendMessage;
import org.telegram.telegrambots.meta.api.objects.Message;
import org.telegram.telegrambots.meta.api.objects.Update;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.InlineKeyboardMarkup;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.ReplyKeyboard;
import org.telegram.telegrambots.meta.exceptions.TelegramApiException;
import ru.jrgroup.quiz_bot.bot.keyboard.KeyboardFactory;
import ru.jrgroup.quiz_bot.domain.Question;
import ru.jrgroup.quiz_bot.domain.State;
import ru.jrgroup.quiz_bot.domain.Topic;
import ru.jrgroup.quiz_bot.domain.User;
import ru.jrgroup.quiz_bot.service.*;

import java.util.List;
import java.util.Set;

/**
 * Обработчик обычных (не-командных) сообщений Telegram.
 * <p>
 * Реализует реакцию на нажатие клавиш главного меню ("Начать викторину" и др.),
 * а также дальнейший диалог с пользователем по состоянию сессии.
 * </p>
 *
 * <ul>
 *     <li>{@code handleMessage(Message message)} — основной метод обработки.</li>
 *     <li>Обеспечивает логику перехода между состояниями: ожидание выбора тем, начало викторины и т.п.</li>
 * </ul>
 *
 * <b>Важно:</b> Не отправляет сообщения напрямую, а делегирует это слою отправки/QuizService.
 */
@Component
public class MessageHandler {

	private static final Logger logger = LoggerFactory.getLogger(MessageHandler.class);

	private final UserSessionService userSessionService;
	private final UserService userService;
	private final QuizService quizService;
	private  final TopicService topicService;
	private final TopicSelectionService topicSelectionService;
	private final KeyboardFactory keyboardFactory;
	private final QuestionService questionService;
	private final BotSenderService botSenderService;

	public MessageHandler(UserSessionService userSessionService, UserService userService, QuizService quizService, TopicService topicService, TopicSelectionService topicSelectionService, KeyboardFactory keyboardFactory, QuestionService questionService, BotSenderService botSenderService) {
		this.userSessionService = userSessionService;
		this.userService = userService;
		this.quizService = quizService;
		this.topicService = topicService;
		this.topicSelectionService = topicSelectionService;
		this.keyboardFactory = keyboardFactory;
		this.questionService = questionService;
		this.botSenderService = botSenderService;
	}

	/**
	 * Обрабатывает любое не-командное сообщение пользователя.
	 *
	 * @param update состояние Telegram
	 */
	public void handleMessage(Update update, TelegramLongPollingBot bot) {
		Message message = update.getMessage();
		Long chatId = message.getChatId();
		Integer threadID = message.getMessageThreadId() != null ? message.getMessageThreadId() : 0;

		if (message == null || message.getFrom() == null) {
			logger.warn("Получено пустое сообщение или отсутствует отправитель");
			return;
		}

		Long userId = message.getFrom().getId();
		User user = userService.findByTelegramId(userId);
		String text = message.getText();

		logger.info("Получено сообщение от пользователя {}: {}", userId, text);

		if (text == null || text.trim().isEmpty()) {
			logger.warn("Пустое сообщение от пользователя {} проигнорировано", userId);
			return;
		}

		switch (text) {
			case "Начать викторину" -> handleStartQuiz(user, chatId, threadID, bot);
			case "Случайный вопрос" -> handleRandowQuestion(chatId, threadID, bot);
			case "Статистика" -> handleShowStats(user);
			case "Помощь" -> handleHelp(user);
			default -> handleFreeInput(user, text);
		}
	}

	private void handleRandowQuestion(Long chatId, Integer threadID, TelegramLongPollingBot bot) {
		logger.info("Пользователь запросил случайный вопрос в чате {}", chatId);

		Question randomQuestion = questionService.findRandomQuestion();

		if (randomQuestion == null) {
			botSenderService.sendText(bot, chatId, threadID, "Нет доступных вопросов для показа.", keyboardFactory.mainMenu());
			return;
		}

		logger.info("Отправляем случайный вопрос: {}", randomQuestion.getText());
		botSenderService.sendPoll(bot, chatId, threadID, randomQuestion);
	}

	/** Начало новой викторины */
	private void handleStartQuiz(User user, Long chatId, Integer threadID, TelegramLongPollingBot bot) {
		Set<Long> selectedTopicIds = userSessionService.getSelectedTopicIds(user);

		if (selectedTopicIds == null || selectedTopicIds.isEmpty()) {
			logger.info("Пользователь {} пытается начать викторину без выбранных тем. Переводим в SELECTING_TOPICS", user.getTelegramId());
			userSessionService.updateState(user, State.SELECTING_TOPICS);
			List<Topic> topics = topicService.findAll();
			Set<Long> selected = topicSelectionService.getSelectedTopics(user.getId());

			if (topics.isEmpty()) {
				botSenderService.sendText(bot, chatId, threadID, "Список тем пуст.", keyboardFactory.mainMenu());
				return;
			}
			InlineKeyboardMarkup keyboard = keyboardFactory.topicMultiSelect(topics, selected);
			String title = "Список тем:\nВыберите одну или несколько тем, затем нажмите 'Подтвердить'.";
			botSenderService.sendText(bot, chatId, threadID, title, keyboard);
			selectedTopicIds = topicSelectionService.getSelectedTopics(user.getId());
			userSessionService.updateState(user, State.QUIZ_ASKING);
		}
		logger.info("Пользователь {} начинает викторину по темам: {}", user.getTelegramId(), selectedTopicIds);

		quizService.startQuiz(user, selectedTopicIds);

		Question firstQuestion = userSessionService.getCurrentQuestion(user);

		// Тут необходимо вызвать метод отправки первого вопроса пользователю
		// Например: quizService.sendNextQuestion(user, firstQuestion);
		userSessionService.updateState(user, State.QUIZ_ASKING);
	}

	/** Показываем статистику */
	private void handleShowStats(User user) {
		// TODO: реализовать показ статистики через сервис
		logger.info("Пользователь {} запросил статистику", user.getTelegramId());
	}

	/** Показываем справку */
	private void handleHelp(User user) {
		// TODO: реализовать показ справки
		logger.info("Пользователь {} запросил справку", user.getTelegramId());
	}

	/** Обработка любого другого текста (например, ответов в процессе викторины) */
	private void handleFreeInput(User user, String text) {
		State state = userSessionService.getState(user);

		logger.debug("Пользователь {} в состоянии {} отправил текст: {}", user.getTelegramId(), state, text);

		// Пример: если пользователь в состоянии QIUZ_ASKING — значит это попытка ответа на вопрос
		if (state == State.QUIZ_ASKING) {
			quizService.processUserAnswer(user, userSessionService.getCurrentQuestion(user), Integer.parseInt(text));
		} else {
			logger.warn("Пользователь {} прислал сообщение вне процесса викторины: '{}'", user.getTelegramId(), text);
			// Можно отправить: "Не понимаю, воспользуйтесь меню"
		}
	}

	/**
	 * Универсальный метод для отправки текстовых сообщений.
	 *
	 * @param bot      бот
	 * @param chatId   id чата
	 * @param threadID id топика (для супергрупп)
	 * @param text     текст
	 * @param keyboard клавиатура (ReplyKeyboard или InlineKeyboardMarkup)
	 */
	private void sendText(TelegramLongPollingBot bot, Long chatId, Integer threadID, String text, ReplyKeyboard keyboard) {
		SendMessage message = new SendMessage();
		message.setChatId(chatId);
		message.setText(text);
		message.enableHtml(true);
		if (threadID != null && threadID != 0) {
			message.setMessageThreadId(threadID);
		}
		if (keyboard != null) {
			message.setReplyMarkup(keyboard);
		}

		try {
			bot.execute(message);
			logger.debug("Сообщение успешно отправлено в чат {} (thread: {})", chatId, threadID);
		} catch (Exception e) {
			logger.error("Ошибка при отправке сообщения в чат {} с threadID {}: {}", chatId, threadID, e.getMessage(), e);
		}
	}

	/**
	 * Отправляет опрос (Poll) с вопросом.
	 *
	 * @param bot      бот
	 * @param chatId   id чата
	 * @param threadID id топика
	 * @param question вопрос
	 */
	private void sendPoll(TelegramLongPollingBot bot, Long chatId, Integer threadID, Question question) {
		SendPoll poll = SendPoll.builder()
				.chatId(chatId.toString())
				.question(question.getText())
				.options(question.getOptions())
				.isAnonymous(false)
				.type("quiz")
				.correctOptionId(question.getCorrectOption())
				.messageThreadId(threadID)
				.build();

		try {
			bot.execute(poll);
			logger.debug("Опрос отправлен: '{}'", question.getText());
		} catch (TelegramApiException e) {
			logger.error("Ошибка при отправке опроса: {}", e.getMessage(), e);
		}
	}
}
