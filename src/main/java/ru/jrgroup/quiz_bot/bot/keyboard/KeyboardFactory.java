package ru.jrgroup.quiz_bot.bot.keyboard;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.InlineKeyboardMarkup;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.ReplyKeyboardMarkup;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.buttons.InlineKeyboardButton;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.buttons.KeyboardButton;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.buttons.KeyboardRow;
import ru.jrgroup.quiz_bot.domain.Topic;

import java.util.*;

/**
 * Генератор клавиатур для Telegram сообщений.
 * <ul>
 *     <li>mainMenu() — главное меню</li>
 *     <li>topicSelection(List&lt;Topic&gt;) — выбор одной темы (2 колонки)</li>
 *     <li>topicMultiSelect(List&lt;Topic&gt;, Set&lt;Long&gt;) — множественный выбор тем с подтверждением</li>
 * </ul>
 */
@Component
public class KeyboardFactory {

	private static final Logger log = LoggerFactory.getLogger(KeyboardFactory.class);

	/**
	 * Создает главное меню для пользователя.
	 *
	 * @return ReplyKeyboardMarkup с основными командами
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

	/**
	 * Генерирует inline-клавиатуру для выбора одной темы.
	 * Темы отображаются в две колонки (максимум), по рядам.
	 *
	 * @param topics список тем
	 * @return InlineKeyboardMarkup для выбора темы
	 */
	public InlineKeyboardMarkup topicSelection(List<Topic> topics) {
		log.debug("Формируется inline-клавиатура для выбора темы ({} тем)", topics.size());
		int maxColumns = 2;
		int numRows = (topics.size() + maxColumns - 1) / maxColumns;
		List<List<InlineKeyboardButton>> rows = new ArrayList<>();

		for (int row = 0; row < numRows; row++) {
			List<InlineKeyboardButton> currentRow = new ArrayList<>(maxColumns);
			for (int col = 0; col < maxColumns; col++) {
				int idx = row + numRows * col;
				if (idx < topics.size()) {
					currentRow.add(createTopicButton(topics.get(idx)));
				}
			}
			rows.add(currentRow);
		}

		InlineKeyboardMarkup markup = new InlineKeyboardMarkup();
		markup.setKeyboard(rows);
		return markup;
	}

	/**
	 * Генерирует inline-клавиатуру с возможностью множественного выбора тем.
	 * Выбранные темы помечаются, добавляются кнопки "Подтвердить" и "Отмена".
	 *
	 * @param topics      список всех тем
	 * @param selectedIds id выбранных тем
	 * @return InlineKeyboardMarkup для множественного выбора
	 */
	public InlineKeyboardMarkup topicMultiSelect(List<Topic> topics, Set<Long> selectedIds) {
		log.debug("Формируется клавиатура множественного выбора тем (выбрано: {})", selectedIds != null ? selectedIds.size() : 0);
		List<List<InlineKeyboardButton>> rows = new ArrayList<>();
		for (Topic topic : topics) {
			InlineKeyboardButton btn = new InlineKeyboardButton();
			boolean selected = selectedIds != null && selectedIds.contains(topic.getId());
			btn.setText((selected ? "✅ " : "") + topic.getName());
			btn.setCallbackData("TOPIC_SELECT:" + topic.getId());
			rows.add(Collections.singletonList(btn));
		}

		// Кнопки подтверждения и отмены
		InlineKeyboardButton confirm = new InlineKeyboardButton("✅ Подтвердить");
		confirm.setCallbackData("TOPIC_CONFIRM");
		InlineKeyboardButton cancel = new InlineKeyboardButton("❌ Отмена");
		cancel.setCallbackData("TOPIC_CANCEL");
		rows.add(Arrays.asList(confirm, cancel));

		InlineKeyboardMarkup markup = new InlineKeyboardMarkup();
		markup.setKeyboard(rows);
		return markup;
	}

	/**
	 * Вспомогательный метод для создания кнопки выбора темы.
	 *
	 * @param topic тема
	 * @return InlineKeyboardButton
	 */
	private InlineKeyboardButton createTopicButton(Topic topic) {
		InlineKeyboardButton button = new InlineKeyboardButton();
		button.setText(topic.getName() != null ? topic.getName() : "Без названия");
		button.setCallbackData("TOPIC_SELECT:" + topic.getId());
		return button;
	}
}
