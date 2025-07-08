package ru.jrgroup.quiz_bot.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.Setter;


import java.time.LocalDateTime;

/**
 * JPA-сущность "Пользователь", хранит основную информацию о пользователе.
 *
 * - id (Long)
 * - telegramId (Long)
 * - username (String)
 * - firstName (String)
 * - lastName (String)
 * - createdAt (Timestamp)
 * - lastActiveAt (Timestamp)
 *
 * Аннотации: @Entity, @Id
 */

@Entity
@Table(name = "users")
@Getter
@Setter
public class User {

    /**
     * Id пользователя в базе данных.
     */
    @Id
    @GeneratedValue
    private Long id;

    /**
     * Id пользователя в Telegram.
     */
    private Long telegramId;

    /**
     * Username пользователя в Telegram (@username).
     * Не обязательно к заполнению, поэтому может быть null.
     */
    private String username;

    /**
     * Имя пользователя, указанное в Telegram.
     */
    private String firstName;

    /**
     * Фамилия пользователя, указанная в Telegram.
     * Не обязательно к заполнению, поэтому может быть null.
     */
    private String lastName;

    /**
     * Дата и время создания записи о пользователе.
     */
    private LocalDateTime createdAt;

    /**
     * Дата и время последней активности пользователя.
     */
    private LocalDateTime lastActiveAt;


    /**
     * Пустой конструктор для создания пользователя
    */
    public User() {
    }

    /**
     * Конструктор для создания пользователя с заданными данными.
     *
     * @param telegramId    Telegram ID пользователя
     * @param username      Имя пользователя в Telegram (username)
     * @param firstName     Имя пользователя
     * @param lastName      Фамилия пользователя
     * @param createdAt     Дата и время создания записи
     * @param lastActiveAt  Дата и время последней активности пользователя
     * Необязательные поля могут содержать null.
     */

    public User(Long telegramId, String username, String firstName, String lastName,
                LocalDateTime createdAt, LocalDateTime lastActiveAt) {
        if (telegramId == null) {
            throw new IllegalArgumentException("Telegram ID cannot be null.");
        }
        if (firstName == null || firstName.trim().isEmpty()) {
            throw new IllegalArgumentException("First name cannot be null.");
        }

        this.telegramId = telegramId;
        this.username = username;
        this.firstName = firstName;
        this.lastName = lastName;
        this.createdAt = createdAt;
        this.lastActiveAt = lastActiveAt;
    }

}
