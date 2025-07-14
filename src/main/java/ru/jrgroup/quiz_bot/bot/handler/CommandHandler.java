package ru.jrgroup.quiz_bot.bot.handler;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.telegram.telegrambots.bots.TelegramLongPollingBot;
import org.telegram.telegrambots.meta.api.methods.polls.SendPoll;
import org.telegram.telegrambots.meta.api.methods.send.SendMessage;
import org.telegram.telegrambots.meta.api.objects.Message;
import org.telegram.telegrambots.meta.api.objects.Update;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.InlineKeyboardMarkup;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.ReplyKeyboard;
import org.telegram.telegrambots.meta.exceptions.TelegramApiException;
import ru.jrgroup.quiz_bot.bot.QuizBot;
import ru.jrgroup.quiz_bot.bot.keyboard.KeyboardFactory;
import ru.jrgroup.quiz_bot.domain.Question;
import ru.jrgroup.quiz_bot.domain.Topic;
import ru.jrgroup.quiz_bot.domain.User;
import ru.jrgroup.quiz_bot.service.*;

import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Set;

/**
 * Обработчик текстовых команд Telegram.
 * <ul>
 *     <li>handleCommand(Update, TelegramLongPollingBot) — основная точка входа для всех команд.</li>
 *     <li>handleStartCommand — приветствие и показ меню.</li>
 *     <li>handleUsersCommand — выводит таблицу пользователей.</li>
 *     <li>handleHelpCommand — обработка команды /help.</li>
 *     <li>handleTopicsCommand — показ клавиатуры выбора тем.</li>
 *     <li>handleQuestionCommand — отправляет случайный вопрос-опрос.</li>
 *     <li>handleUnknownCommand — обработка неизвестной команды.</li>
 * </ul>
 */
@Component
public class CommandHandler {

	private static final Logger logger = LoggerFactory.getLogger(CommandHandler.class);

	private final UserService userService;
	private final TopicService topicService;
	private final QuestionService questionService;
	private final KeyboardFactory keyboardFactory;
	private final TopicSelectionService topicSelectionService;
	private final BotSenderService botSenderService;

	public CommandHandler(
			UserService userService,
			TopicService topicService,
			QuestionService questionService,
			KeyboardFactory keyboardFactory,
			TopicSelectionService topicSelectionService, BotSenderService botSenderService
	) {
		this.userService = userService;
		this.topicService = topicService;
		this.questionService = questionService;
		this.keyboardFactory = keyboardFactory;
		this.topicSelectionService = topicSelectionService;
		this.botSenderService = botSenderService;
	}

	/**
	 * Главная точка входа для обработки текстовых команд Telegram.
	 *
	 * @param update объект Telegram update
	 */
	public void handleCommand(Update update, TelegramLongPollingBot bot) {
		Message message = update.getMessage();
		Long userId = message.getFrom().getId();
		Long chatId = message.getChatId();
		Integer threadID = message.getMessageThreadId();

		userService.registerOrUpdateUser(message);

		String command = message.getText() != null ? message.getText().trim() : "";
		logger.info("Пользователь {} прислал команду: {}", userId, command);

		switch (command) {
			case "/start" -> handleStartCommand(chatId, threadID, bot);
			case "/users" -> handleUsersCommand(chatId, threadID, bot);
			case "/help" -> handleHelpCommand(chatId, threadID, bot);
			case "/topics" -> handleTopicsCommand(userId, chatId, threadID, bot);
			case "/question" -> handleQuestionCommand(chatId, threadID, bot);
			default -> handleUnknownCommand(command, chatId, threadID, bot);
		}
	}

	/**
	 * Обработка команды /start — приветствие и основное меню.
	 */
	private void handleStartCommand(Long chatId, Integer threadID, TelegramLongPollingBot bot) {
		String stringBuilder = """
				Добро пожаловать в Quiz Bot!
				Используйте /help для получения списка доступных команд.
				
				""";
		botSenderService.sendText(bot, chatId, threadID, stringBuilder, keyboardFactory.mainMenu());
	}

	/**
	 * Обработка команды /help (выводит help).
	 */
	private void handleHelpCommand(Long chatId, Integer threadID, TelegramLongPollingBot bot) {
		String help = """
                <b>Доступные команды:</b>
                /start — начать работу с ботом
                /users — показать список пользователей
                /topics — выбрать темы викторины
                /question — получить случайный вопрос
                /help — справка
                """;
		botSenderService.sendText(bot, chatId, threadID, help, keyboardFactory.mainMenu());
	}

	/**
	 * Обработка команды /users — таблица пользователей.
	 */
	private void handleUsersCommand(Long chatId, Integer threadID, TelegramLongPollingBot bot) {
		List<User> users = userService.findAll();

		if (users.isEmpty()) {
			botSenderService.sendText(bot, chatId, threadID, "Нет зарегистрированных пользователей.", keyboardFactory.mainMenu());
			return;
		}

		DateTimeFormatter dtf = DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm:ss");
		StringBuilder sb = new StringBuilder();
		sb.append("<b>Список пользователей:</b>\n\n");
		sb.append(String.format("%-3s %-12s %-16s %-15s %-20s %-20s\n",
				"№", "ID", "Username", "First name", "Создан", "Последняя активность"));
		sb.append("--------------------------------------------------------------------------------------\n");

		int i = 1;
		for (User user : users) {
			sb.append(String.format(
					"%-3d %-12s %-16s %-15s %-20s %-20s\n",
					i++,
					user.getTelegramId(),
					user.getUsername() == null ? "(нет)" : user.getUsername(),
					user.getFirstName() == null ? "(нет)" : user.getFirstName(),
					user.getCreatedAt() == null ? "-" : user.getCreatedAt().format(dtf),
					user.getLastActiveAt() == null ? "-" : user.getLastActiveAt().format(dtf)
			));
		}

		botSenderService.sendText(bot, chatId, threadID, sb.toString(), keyboardFactory.mainMenu());
	}

	/**
	 * Обработка команды /topics — клавиатура с выбором тем (множественный выбор).
	 */
	private void handleTopicsCommand(Long userId, Long chatId, Integer threadID, TelegramLongPollingBot bot) {
		List<Topic> topics = topicService.findAll();
		Set<Long> selected = topicSelectionService.getSelectedTopics(userId);

		if (topics.isEmpty()) {
			botSenderService.sendText(bot, chatId, threadID, "Список тем пуст.", keyboardFactory.mainMenu());
			return;
		}
		InlineKeyboardMarkup keyboard = keyboardFactory.topicMultiSelect(topics, selected);
		String title = "Список тем:\nВыберите одну или несколько тем, затем нажмите 'Подтвердить'.";
		botSenderService.sendText(bot, chatId, threadID, title, keyboard);
	}

	/**
	 * Обработка команды /question — отправляет случайный вопрос через Telegram Poll.
	 */
	private void handleQuestionCommand(Long chatId, Integer threadID, TelegramLongPollingBot bot) {
		Question question = questionService.findRandomQuestion();
		if (question == null) {
			botSenderService.sendText(bot, chatId, threadID, "Вопросов не найдено.", keyboardFactory.mainMenu());
			return;
		}
		botSenderService.sendPoll(bot, chatId, threadID, question);
	}

	/**
	 * Обработка неизвестных команд.
	 */
	private void handleUnknownCommand(String command, Long chatId, Integer threadId, TelegramLongPollingBot bot) {
		logger.warn("Неизвестная команда: {}", command);
		String message = "Неизвестная команда: <b>" + command + "</b>\nИспользуйте /help для справки.";
		botSenderService.sendText(bot, chatId, threadId, message, keyboardFactory.mainMenu());
	}
}
