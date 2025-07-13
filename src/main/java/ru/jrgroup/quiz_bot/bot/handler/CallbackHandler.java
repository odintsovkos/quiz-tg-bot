package ru.jrgroup.quiz_bot.bot.handler;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Обработчик callback-запросов Telegram (inline-кнопки).
 *
 * - Метод: handleCallback(CallbackQuery callback)
 * - Определяет дальнейшие действия пользователя после нажатия кнопок.
 */
@Component
public class CallbackHandler {

	private static final Logger logger = LoggerFactory.getLogger(CommandHandler.class);

}
