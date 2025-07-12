package ru.jrgroup.quiz_bot.bot;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.telegram.telegrambots.bots.TelegramLongPollingBot;
import org.telegram.telegrambots.meta.api.objects.Update;
import ru.jrgroup.quiz_bot.bot.handler.CallbackHandler;
import ru.jrgroup.quiz_bot.bot.handler.CommandHandler;
import ru.jrgroup.quiz_bot.bot.handler.MessageHandler;
import ru.jrgroup.quiz_bot.bot.handler.QuizHandler;
import ru.jrgroup.quiz_bot.config.BotConfig;

/**
 * Главный класс Telegram-бота викторины.
 *
 * <p>Реализует интеграцию с Telegram API (Long Polling) и маршрутизацию всех входящих обновлений
 * к соответствующим обработчикам:
 * <ul>
 *   <li>{@link CommandHandler} — обработка команд ("/start", "/help" и др.)</li>
 *   <li>{@link MessageHandler} — обработка обычных сообщений</li>
 *   <li>{@link CallbackHandler} — обработка inline callback-запросов</li>
 *   <li>{@link QuizHandler} — обработка опросов и логики викторины</li>
 * </ul>
 * <p>
 * Конфигурация (username, token) берется из {@link BotConfig}.
 * <br>
 * <b>Внимание:</b> Этот класс не содержит бизнес-логики, а только маршрутизирует обновления!
 * </p>
 */
@Component
public class QuizBot extends TelegramLongPollingBot {

    private static final Logger log = LoggerFactory.getLogger(QuizBot.class);

    private final BotConfig botConfig;
    private final CommandHandler commandHandler;
    private final MessageHandler messageHandler;
    private final CallbackHandler callbackHandler;
    private final QuizHandler quizHandler;

    /**
     * Инъекция зависимостей через конструктор.
     *
     * @param botConfig       Конфигурация бота (токен, username и т.д.)
     * @param commandHandler  Обработчик команд ("/start", "/help", и др.)
     * @param messageHandler  Обработчик обычных сообщений
     * @param callbackHandler Обработчик callback-запросов (inline-кнопки)
     * @param quizHandler     Обработчик опросов и логики викторины
     */
    public QuizBot(BotConfig botConfig,
                   CommandHandler commandHandler,
                   MessageHandler messageHandler,
                   CallbackHandler callbackHandler,
                   QuizHandler quizHandler) {
        this.botConfig = botConfig;
        this.commandHandler = commandHandler;
        this.messageHandler = messageHandler;
        this.callbackHandler = callbackHandler;
        this.quizHandler = quizHandler;
        log.info("QuizBot инициализирован с username: {}", botConfig.getUsername());
    }

    /**
     * Главный метод обработки всех входящих событий от Telegram.
     * <p>
     * Делегирует выполнение соответствующим handler-ам (команды, сообщения, callback, опросы).
     *
     * @param update Объект обновления из Telegram (сообщение, команда, callback, опрос и др.)
     */
    @Override
    public void onUpdateReceived(Update update) {
        log.debug("Получено новое обновление: {}", update);
        try {
            if (update.hasMessage() && update.getMessage().hasText()) {
                String messageText = update.getMessage().getText();
                Long userId = update.getMessage().getFrom().getId();
                if (messageText.startsWith("/")) {
                    log.info("Пользователь {} прислал команду: {}", userId, messageText);
                    commandHandler.handleCommand(update, this);
                } else {
                    log.info("Пользователь {} прислал сообщение: {}", userId, messageText);

//TODO                    messageHandler.handleMessage(update);

                }
            } else if (update.hasCallbackQuery()) {
                String callbackData = update.getCallbackQuery().getData();
                Long userId = update.getCallbackQuery().getFrom().getId();
                log.info("Пользователь {} выбрал callback: {}", userId, callbackData);
//TODO                callbackHandler.handleCallback(update);
            } else if (update.hasMessage() && update.getMessage().hasPoll()) {
                String pollQuestion = update.getMessage().getPoll().getQuestion();
                Long userId = update.getMessage().getFrom().getId();
                log.info("Пользователь {} прислал опрос: {}", userId, pollQuestion);
//TODO                quizHandler.handlePoll(update);
            } else {
                log.warn("Получено неподдерживаемое обновление: {}", update);
            }
        } catch (Exception e) {
            log.error("Ошибка при обработке обновления: {}", update, e);
        }
    }

    /**
     * Возвращает username бота (для Telegram API).
     *
     * @return username (например, "my_quiz_bot")
     */
    @Override
    public String getBotUsername() {
        log.debug("Запрошен username бота");
        return botConfig.getUsername();
    }

    /**
     * Возвращает токен бота (для Telegram API).
     *
     * @return токен, взятый из конфигурации
     */
    @Override
    public String getBotToken() {
        return botConfig.getToken();
    }
}
