package ru.jrgroup.quiz_bot.bot;

import org.springframework.stereotype.Component;
import org.telegram.telegrambots.bots.TelegramLongPollingBot;
import org.telegram.telegrambots.meta.api.objects.Update;

/**
 * Класс Telegram-бота.
 * Реализует интеграцию с Telegram API через TelegramLongPollingBot или TelegramWebhookBot.
 *
 * - Переопределяет методы onUpdateReceived, getBotUsername, getBotToken.
 * - Делегирует обработку команд и сообщений handler-ам.
 * - Инъецирует handler-ы и сервисы.
 */

@Component
public class QuizBot extends TelegramLongPollingBot {
    @Override
    public void onUpdateReceived(Update update) {

    }

    @Override
    public String getBotUsername() {
        return "";
    }
}
