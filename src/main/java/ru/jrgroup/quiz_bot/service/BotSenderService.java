package ru.jrgroup.quiz_bot.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.telegram.telegrambots.bots.TelegramLongPollingBot;
import org.telegram.telegrambots.meta.api.methods.polls.SendPoll;
import org.telegram.telegrambots.meta.api.methods.send.SendMessage;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.ReplyKeyboard;
import org.telegram.telegrambots.meta.exceptions.TelegramApiException;
import ru.jrgroup.quiz_bot.domain.Question;

@Service
public class BotSenderService {

	private static final Logger logger = LoggerFactory.getLogger(BotSenderService.class);

	public BotSenderService() {
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
	public void sendText(TelegramLongPollingBot bot, Long chatId, Integer threadID, String text, ReplyKeyboard keyboard) {
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
	public void sendPoll(TelegramLongPollingBot bot, Long chatId, Integer threadID, Question question) {
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
