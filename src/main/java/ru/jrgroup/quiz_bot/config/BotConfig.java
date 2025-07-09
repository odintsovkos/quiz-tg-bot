package ru.jrgroup.quiz_bot.config;

import lombok.Getter;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Конфигурационный класс для хранения параметров Telegram-бота.
 *
 * <p>
 * Значения маппятся из application.properties с префиксом <b>bot</b>.
 * Класс сделан иммутабельным: только final-поля, только геттеры, только внедрение через конструктор.
 * </p>
 *
 * <p>
 * Пример application.properties:
 * <pre>
 * bot=
 *   name= my_bot_name
 *   token= 123456789:AAAbbbCccDDDeeeFffGgHhIiJjKkLlMmNnOo
 *   username= my_bot_username
 * </pre>
 * </p>
 */
@Getter
@ConfigurationProperties(prefix = "bot")
public class BotConfig {
    /** Имя бота (любое произвольное имя, для внутреннего использования). */
    private final String name;

    /** Токен Telegram Bot API. Никому не показывать! */
    private final String token;

    /** Username бота в Telegram (@username без @). */
    private final String username;

    /**
     * Конструктор для внедрения всех параметров через Spring Boot.
     *
     * @param name     имя бота
     * @param token    токен Telegram Bot API
     * @param username username Telegram-бота
     */
    public BotConfig(String name, String token, String username) {
        this.name = name;
        this.token = token;
        this.username = username;
    }

}
