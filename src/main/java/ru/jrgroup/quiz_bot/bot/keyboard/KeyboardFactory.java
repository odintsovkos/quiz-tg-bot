package ru.jrgroup.quiz_bot.bot.keyboard;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.ReplyKeyboardMarkup;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.buttons.KeyboardButton;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.buttons.KeyboardRow;

import java.util.ArrayList;
import java.util.List;

/**
 * Генератор клавиатур для Telegram сообщений.
 *
 * - mainMenu() — главное меню
 * - quizOptions(Question question) — inline-клавиатура для ответов на викторины
 * - topicSelection(List<Topic> topics) — выбор темы для пользователя
 */
@Component
public class KeyboardFactory {

	private static final Logger log = LoggerFactory.getLogger(KeyboardFactory.class);

	/**
	 * Создает главное меню (ReplyKeyboardMarkup).
	 *
	 * @return главное меню
	 */
	public ReplyKeyboardMarkup mainMenu() {
		log.debug("Формируется главное меню");
		ReplyKeyboardMarkup keyboard = new ReplyKeyboardMarkup();
		List<KeyboardRow> rows = new ArrayList<>();

		KeyboardRow row1 = new KeyboardRow();
		row1.add(new KeyboardButton("Старт"));
		row1.add(new KeyboardButton("Статистика"));
		rows.add(row1);

		KeyboardRow row2 = new KeyboardRow();
		row2.add(new KeyboardButton("Помощь"));
		rows.add(row2);

		keyboard.setKeyboard(rows);
		keyboard.setResizeKeyboard(true);
		keyboard.setOneTimeKeyboard(false);
		return keyboard;
	}
}
