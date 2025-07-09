package ru.jrgroup.quiz_bot.config;

import lombok.Getter;
import lombok.Setter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.telegram.telegrambots.meta.TelegramBotsApi;
import org.telegram.telegrambots.updatesreceivers.DefaultBotSession;
import ru.jrgroup.quiz_bot.bot.QuizBot;

/**
 * Конфигурационный класс для хранения параметров Telegram-бота.
 *
 * <p>
 * Значения автоматически маппятся из {@code application.properties} с префиксом <b>bot</b>.<br>
 * Используется для передачи имени, токена и username Telegram-бота.
 * </p>
 *
 * <p><b>Пример application.properties:</b>
 * <pre>
 * bot.name=JavaQuiz
 * bot.token=123456789:AAAbbbCccDDDeeeFffGgHhIiJjKkLlMmNnOo
 * bot.username=my_bot_username
 * </pre>
 * </p>
 *
 * <p>
 * <b>Важно:</b> Для корректной работы Telegram-бота также производится ручная регистрация экземпляра {@link QuizBot}
 * в TelegramBots API (бин {@code telegramBotsApi}). Это требуется, если автоматическая регистрация Spring Boot Starter не работает.
 * </p>
 */
@Getter
@Setter
@ConfigurationProperties(prefix = "bot")
public class BotConfig {

    /** Имя бота (любое произвольное название, используется только внутри приложения) */
    private String name;

    /** Токен Telegram Bot API. <b>Не публикуйте токен в открытом доступе!</b> */
    private String token;

    /** Username бота в Telegram (без @) */
    private String username;

    /**
     * Бин для ручной регистрации Telegram-бота.
     * <p>
     * TelegramBots API требует ручной регистрации экземпляра бота,
     * если telegrambots-spring-boot-starter не регистрирует его автоматически.
     * </p>
     *
     * @param quizBot основной бин Telegram-бота
     * @return экземпляр TelegramBotsApi с зарегистрированным ботом
     * @throws Exception если при регистрации произойдёт ошибка
     */
    @Bean
    public TelegramBotsApi telegramBotsApi(QuizBot quizBot) throws Exception {
        Logger log = LoggerFactory.getLogger(BotConfig.class);
        try {
            TelegramBotsApi botsApi = new TelegramBotsApi(DefaultBotSession.class);
            botsApi.registerBot(quizBot);
            log.info("Telegram бот '{}' успешно зарегистрирован вручную через BotConfig!", quizBot.getBotUsername());
            return botsApi;
        } catch (Exception ex) {
            log.error("Ошибка при регистрации Telegram бота через BotConfig: {}", ex.getMessage(), ex);
            throw ex;
        }
    }
}
