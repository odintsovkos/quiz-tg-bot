package ru.jrgroup.quiz_bot.bot.handler;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.telegram.telegrambots.bots.TelegramLongPollingBot;
import org.telegram.telegrambots.meta.api.methods.send.SendMessage;
import org.telegram.telegrambots.meta.api.methods.updatingmessages.DeleteMessage;
import org.telegram.telegrambots.meta.api.methods.updatingmessages.EditMessageReplyMarkup;
import org.telegram.telegrambots.meta.api.objects.Update;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.InlineKeyboardMarkup;
import org.telegram.telegrambots.meta.exceptions.TelegramApiException;
import ru.jrgroup.quiz_bot.bot.keyboard.KeyboardFactory;
import ru.jrgroup.quiz_bot.domain.Topic;
import ru.jrgroup.quiz_bot.service.TopicSelectionService;
import ru.jrgroup.quiz_bot.service.TopicService;

import java.util.List;
import java.util.Set;

/**
 * Обработчик callback-запросов Telegram (inline-кнопки).
 * <ul>
 *     <li>Обрабатывает выбор темы (множественный выбор).</li>
 *     <li>Обрабатывает подтверждение и отмену выбора тем.</li>
 *     <li>Логирует все пользовательские действия и ошибки.</li>
 * </ul>
 *
 * Используется для поддержки многошагового выбора тем викторины.
 */
@Component
public class CallbackHandler {

	private static final Logger logger = LoggerFactory.getLogger(CallbackHandler.class);

	private final TopicSelectionService topicSelectionService;
	private final TopicService topicService;
	private final KeyboardFactory keyboardFactory;

	public CallbackHandler(
			TopicSelectionService topicSelectionService,
			TopicService topicService,
			KeyboardFactory keyboardFactory
	) {
		this.topicSelectionService = topicSelectionService;
		this.topicService = topicService;
		this.keyboardFactory = keyboardFactory;
	}

	/**
	 * Главный обработчик callback-запросов от Telegram (inline-кнопки).
	 *
	 * @param update update с callback-запросом
	 * @param bot    экземпляр TelegramLongPollingBot для ответов
	 */
	public void handleCallback(Update update, TelegramLongPollingBot bot) {
		if (update == null || update.getCallbackQuery() == null) {
			logger.warn("Получено пустое update или без callbackQuery");
			return;
		}

		String data = update.getCallbackQuery().getData();
		Long userId = update.getCallbackQuery().getFrom().getId();
		Long chatId = update.getCallbackQuery().getMessage().getChatId();
		Integer messageId = update.getCallbackQuery().getMessage().getMessageId();

		logger.debug("Получен callback от пользователя {}: '{}'", userId, data);

		try {
			if (data.startsWith("TOPIC_SELECT:")) {
				handleTopicSelect(data, userId, chatId, messageId, bot);
			} else if ("TOPIC_CONFIRM".equals(data)) {
				handleTopicConfirm(userId, chatId, messageId, bot);
			} else if ("TOPIC_CANCEL".equals(data)) {
				handleTopicCancel(userId, chatId, messageId, bot);
			} else {
				logger.warn("Неизвестное значение callback data: {}", data);
				sendTextSilent(bot, chatId, "Неизвестное действие.");
			}
		} catch (Exception e) {
			logger.error("Ошибка при обработке callback от пользователя {}: {}", userId, e.getMessage(), e);
			sendTextSilent(bot, chatId, "Произошла ошибка. Попробуйте ещё раз.");
		}
	}

	/**
	 * Обработка множественного выбора темы — меняет состояние выбранных тем и обновляет клавиатуру.
	 */
	private void handleTopicSelect(String data, Long userId, Long chatId, Integer messageId, TelegramLongPollingBot bot) throws TelegramApiException {
		Long topicId;
		try {
			topicId = Long.parseLong(data.substring("TOPIC_SELECT:".length()));
		} catch (NumberFormatException ex) {
			logger.error("Ошибка парсинга topicId в callback: {}", data, ex);
			sendTextSilent(bot, chatId, "Некорректный идентификатор темы.");
			return;
		}

		Set<Long> selected = topicSelectionService.getSelectedTopics(userId);
		boolean wasSelected = selected.contains(topicId);
		if (wasSelected) {
			selected.remove(topicId);
			logger.debug("Пользователь {} снял выделение с темы {}", userId, topicId);
		} else {
			selected.add(topicId);
			logger.debug("Пользователь {} выбрал тему {}", userId, topicId);
		}

		List<Topic> topics = topicService.findAll();
		InlineKeyboardMarkup keyboard = keyboardFactory.topicMultiSelect(topics, selected);

		EditMessageReplyMarkup editMarkup = new EditMessageReplyMarkup();
		editMarkup.setChatId(chatId);
		editMarkup.setMessageId(messageId);
		editMarkup.setReplyMarkup(keyboard);

		bot.execute(editMarkup);
	}

	/**
	 * Обработка подтверждения выбора тем — сообщает пользователю результат и удаляет сообщение с клавиатурой.
	 */
	private void handleTopicConfirm(Long userId, Long chatId, Integer messageId, TelegramLongPollingBot bot) {
		Set<Long> selected = topicSelectionService.getSelectedTopics(userId);
		logger.info("Пользователь {} подтвердил выбор тем: {}", userId, selected);

		String msg = selected.isEmpty()
				? "Вы не выбрали ни одной темы."
				: "Вы выбрали темы с ID: " + selected;

		sendTextSilent(bot, chatId, msg);
		topicSelectionService.clearSelection(userId);

		deleteMessageSilent(bot, chatId, messageId);
	}

	/**
	 * Обработка отмены выбора тем — очищает выбор и удаляет сообщение с клавиатурой.
	 */
	private void handleTopicCancel(Long userId, Long chatId, Integer messageId, TelegramLongPollingBot bot) {
		logger.info("Пользователь {} отменил выбор тем", userId);

		topicSelectionService.clearSelection(userId);
		sendTextSilent(bot, chatId, "Выбор тем отменён.");

		deleteMessageSilent(bot, chatId, messageId);
	}

	/**
	 * Безопасно удаляет сообщение с клавиатурой из чата.
	 */
	private void deleteMessageSilent(TelegramLongPollingBot bot, Long chatId, Integer messageId) {
		try {
			DeleteMessage deleteMessage = new DeleteMessage();
			deleteMessage.setChatId(chatId);
			deleteMessage.setMessageId(messageId);
			bot.execute(deleteMessage);
			logger.debug("Удалено сообщение с клавиатурой (chatId={}, messageId={})", chatId, messageId);
		} catch (TelegramApiException e) {
			logger.error("Ошибка при удалении сообщения (chatId={}, messageId={}): {}", chatId, messageId, e.getMessage(), e);
		}
	}

	/**
	 * Безопасно отправляет текстовое сообщение в чат.
	 */
	private void sendTextSilent(TelegramLongPollingBot bot, Long chatId, String text) {
		try {
			SendMessage send = SendMessage.builder()
					.chatId(chatId.toString())
					.text(text)
					.build();
			bot.execute(send);
		} catch (TelegramApiException e) {
			logger.error("Не удалось отправить сообщение в чат {}: {}", chatId, e.getMessage(), e);
		}
	}
}
