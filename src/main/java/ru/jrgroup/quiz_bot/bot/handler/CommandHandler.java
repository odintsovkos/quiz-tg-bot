package ru.jrgroup.quiz_bot.bot.handler;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.telegram.telegrambots.bots.TelegramLongPollingBot;
import org.telegram.telegrambots.meta.api.methods.polls.SendPoll;
import org.telegram.telegrambots.meta.api.methods.send.SendMessage;
import org.telegram.telegrambots.meta.api.objects.Message;
import org.telegram.telegrambots.meta.api.objects.Update;
import org.telegram.telegrambots.meta.exceptions.TelegramApiException;
import ru.jrgroup.quiz_bot.domain.Question;
import ru.jrgroup.quiz_bot.domain.Topic;
import ru.jrgroup.quiz_bot.domain.User;
import ru.jrgroup.quiz_bot.service.QuestionService;
import ru.jrgroup.quiz_bot.service.TopicService;
import ru.jrgroup.quiz_bot.service.UserService;

import java.time.format.DateTimeFormatter;
import java.util.List;

/**
 * Обработчик текстовых команд Telegram.
 *
 * - Метод: handleCommand(Message message)
 * - Может содержать map "команда -> функция"
 * - Вызывает бизнес-логику через сервисы.
 */

@Component
public class CommandHandler {

	private static final Logger logger = LoggerFactory.getLogger(CommandHandler.class);
	private final UserService userService;
	private final TopicService topicService;
	private final QuestionService questionService;

	public CommandHandler(UserService userService, TopicService topicService, QuestionService questionService) {
		this.userService = userService;
		this.topicService = topicService;
		this.questionService = questionService;
	}

	public void handleCommand(Update update, TelegramLongPollingBot bot) {
		Message message = update.getMessage();
		Long chatId = message.getChatId();
		Integer threadID = message.getMessageThreadId();

		userService.registerOrUpdateUser(message);

		switch (message.getText()) {
			case "/users":
				handleUsersCommand(chatId, threadID, bot);
				break;
			case "/help":
				handleUnknownCommand("/help", chatId, threadID, bot);
				break;
			case "/topics":
				handleTopicsCommand(chatId, threadID, bot);
				break;
			case "/question":
				handleQuestionCommand(chatId, threadID, bot);
				break;
			default:
				handleUnknownCommand(message.getText(), chatId, threadID, bot);
		}
	}

	private void handleQuestionCommand(Long chatId, Integer threadID, TelegramLongPollingBot bot) {
		Question question = questionService.findRandomQuestion();

		sendPoll(bot, chatId, threadID, question);
	}

	private void handleTopicsCommand(Long chatId, Integer threadID, TelegramLongPollingBot bot) {
		List<Topic> topics = topicService.findAll();

		if (topics.isEmpty()) {
			sendText(bot, chatId, threadID, "Список тем пуст.");
			return;
		}

		StringBuilder sb = new StringBuilder();
		sb.append("Список тем:\n\n");
		int i = 1;
		for (Topic topic : topics) {
			sb.append("№ ").append(i++).append("\n")
					.append(topic.getName()).append(" - ")
					.append(topic.getDescription()).append("\n");
		}

		sendText(bot, chatId, threadID, sb.toString());
	}

	private void handleUnknownCommand(String command, Long chatId, Integer threadId, TelegramLongPollingBot bot) {
		String message = "Неизвестная команда: " + command + ". Используйте /help для справки.";
		sendText(bot, chatId, threadId, message);
	}

	private void handleUsersCommand(Long chatId, Integer threadID, TelegramLongPollingBot bot) {
		List<User> users = userService.findAll();

		if (users.isEmpty()) {
			sendText(bot, chatId, threadID, "Нет зарегистрированных пользователей.");
			return;
		}

		DateTimeFormatter dtf = DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm:ss");
		StringBuilder sb = new StringBuilder();
		sb.append("Список пользователей:\n\n");

		int i = 1;
		for (User user : users) {
			sb.append("№ ").append(i++).append("\n")
					.append("ID: ").append(user.getTelegramId()).append("\n")
					.append("Username: ").append(user.getUsername() == null ? "(нет)" : user.getUsername()).append("\n")
					.append("First name: ").append(user.getFirstName() == null ? "(нет)" : user.getFirstName()).append("\n")
					.append("Last name: ").append(user.getLastName() == null ? "(нет)" : user.getLastName()).append("\n")
					.append("Created at: ").append(user.getCreatedAt() == null ? "-" : user.getCreatedAt().format(dtf)).append("\n")
					.append("Last active: ").append(user.getLastActiveAt() == null ? "-" : user.getLastActiveAt().format(dtf)).append("\n")
					.append("------\n");
		}

		sendText(bot, chatId, threadID, sb.toString());
	}



	private void sendText(TelegramLongPollingBot bot, Long chatId, Integer threadID, String text) {
		SendMessage message = new SendMessage();
		message.setChatId(chatId);
		message.setText(text);
		if (threadID != null && threadID != 0) {
			message.setMessageThreadId(threadID);
		}

		try {
			bot.execute(message);
		} catch (Exception e) {
			logger.error("Ошибка при отправке сообщения в чат {} с threadID {}: {}", chatId, threadID, e.getMessage(), e);
		}
	}

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
		} catch (TelegramApiException e) {
			logger.error(e.getMessage());
		}

	}
}
