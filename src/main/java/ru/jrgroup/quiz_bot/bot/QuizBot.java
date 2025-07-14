package ru.jrgroup.quiz_bot.bot;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.telegram.telegrambots.bots.TelegramLongPollingBot;
import org.telegram.telegrambots.meta.api.methods.polls.SendPoll;
import org.telegram.telegrambots.meta.api.methods.send.SendMessage;
import org.telegram.telegrambots.meta.api.methods.updatingmessages.DeleteMessage;
import org.telegram.telegrambots.meta.api.objects.Message;
import org.telegram.telegrambots.meta.api.objects.Update;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.ReplyKeyboard;
import org.telegram.telegrambots.meta.exceptions.TelegramApiException;
import ru.jrgroup.quiz_bot.bot.handler.CallbackHandler;
import ru.jrgroup.quiz_bot.bot.handler.CommandHandler;
import ru.jrgroup.quiz_bot.bot.handler.MessageHandler;
import ru.jrgroup.quiz_bot.bot.handler.QuizHandler;
import ru.jrgroup.quiz_bot.config.BotConfig;
import ru.jrgroup.quiz_bot.domain.Question;

/**
 * Главный класс Telegram-бота викторины.
 * <p>
 * Реализует интеграцию с Telegram API (Long Polling) и маршрутизацию всех входящих обновлений
 * к соответствующим обработчикам:
 * <ul>
 *     <li>{@link CommandHandler} — обработка команд ("/start", "/help" и др.)</li>
 *     <li>{@link MessageHandler} — обработка обычных сообщений</li>
 *     <li>{@link CallbackHandler} — обработка inline callback-запросов</li>
 *     <li>{@link QuizHandler} — обработка опросов и логики викторины</li>
 * </ul>
 * <b>Внимание:</b> Этот класс не содержит бизнес-логики, а только маршрутизирует обновления!
 */
@Component
public class QuizBot extends TelegramLongPollingBot {

    private static final Logger logger = LoggerFactory.getLogger(QuizBot.class);

    private final BotConfig botConfig;
    @Autowired
    private CommandHandler commandHandler;
    @Autowired
    private MessageHandler messageHandler;
    @Autowired
    private CallbackHandler callbackHandler;
    @Autowired
    private QuizHandler quizHandler;

    /**
     * Конструктор QuizBot с внедрением зависимостей.
     *
     * @param botConfig       Конфигурация бота (токен, username и т.д.)
     */
    public QuizBot(BotConfig botConfig){
        this.botConfig = botConfig;
        logger.info("QuizBot инициализирован с username: {}", botConfig.getUsername());
    }

    /**
     * Главный метод обработки всех входящих событий от Telegram.
     * Делегирует выполнение соответствующим handler-ам (команды, сообщения, callback, опросы).
     *
     * @param update Объект обновления из Telegram (сообщение, команда, callback, опрос и др.)
     */
    @Override
    public void onUpdateReceived(Update update) {
        if (update == null) {
            logger.warn("Получено пустое update");
            return;
        }
        logger.debug("Получено новое обновление: {}", update);

        try {
            if (update.hasMessage() && update.getMessage().hasText()) {
                String messageText = update.getMessage().getText();
                Long userId = update.getMessage().getFrom().getId();
                Long chatId = update.getMessage().getChatId();
                String chatType = update.getMessage().getChat().getType();

                if (messageText.startsWith("/")) {
                    logger.info("Пользователь {} прислал команду: {}", userId, messageText);

                    if (!"private".equals(chatType)) {
                        logger.warn("Команды принимаются только в личных сообщениях! Пользователь {} прислал команду в чате типа: {}", userId, chatType);

                        SendMessage warning = SendMessage.builder()
                                .chatId(chatId)
                                .text("❗️Команды можно использовать только в личных сообщениях с ботом.")
                                .messageThreadId(update.getMessage().getMessageThreadId())
                                .build();
                        Message sentWarning = this.execute(warning);

                        new Thread(() -> {
                            try {
                                Thread.sleep(2000);
                                DeleteMessage deleteCommand = new DeleteMessage(chatId.toString(), update.getMessage().getMessageId());
                                this.execute(deleteCommand);
                                if (sentWarning != null) {
                                    DeleteMessage deleteWarning = new DeleteMessage(chatId.toString(), sentWarning.getMessageId());
                                    this.execute(deleteWarning);
                                }
                            } catch (Exception e) {
                                logger.error("Ошибка при удалении сообщений после задержки: {}", e.getMessage(), e);
                            }
                        }).start();

                        return;
                    }
                    commandHandler.handleCommand(update, this);

                } else {
                    logger.info("Пользователь {} прислал сообщение: {}", userId, messageText);
                    messageHandler.handleMessage(update, this);
                }
            }
            else if (update.hasCallbackQuery()) {
                String callbackData = update.getCallbackQuery().getData();
                Long userId = update.getCallbackQuery().getFrom().getId();
                logger.info("Пользователь {} выбрал callback: {}", userId, callbackData);
                callbackHandler.handleCallback(update, this);
            }
            else if (update.hasMessage() && update.getMessage().hasPoll()) {
                String pollQuestion = update.getMessage().getPoll().getQuestion();
                Long userId = update.getMessage().getFrom().getId();
                logger.info("Пользователь {} прислал опрос: {}", userId, pollQuestion);

                // quizHandler.handlePoll(update);
            }
            else {
                logger.warn("Получено неподдерживаемое обновление: {}", update);
            }
        } catch (Exception e) {
            logger.error("Ошибка при обработке обновления: {}", update, e);
        }
    }

    /**
     * Возвращает username бота (для Telegram API).
     *
     * @return username (например, "my_quiz_bot")
     */
    @Override
    public String getBotUsername() {
        logger.debug("Запрошен username бота");
        return botConfig.getUsername();
    }

    /**
     * Возвращает токен бота (для Telegram API).
     *
     * @return токен, взятый из конфигурации
     */
    @Override
    public String getBotToken() {
        // Не логируем токен в целях безопасности!
        return botConfig.getToken();
    }
}
