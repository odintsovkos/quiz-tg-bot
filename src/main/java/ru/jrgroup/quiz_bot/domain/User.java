package ru.jrgroup.quiz_bot.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PastOrPresent;
import lombok.Getter;
import lombok.Setter;


import java.time.LocalDateTime;

/**
 * JPA-сущность "Пользователь".
 * JPA-сущность "Пользователь", хранит основную информацию о пользователе.
 *
 * - id (Long)
 * - telegramId (Long)
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
    @NotNull
    private Long id;

    /**
     * Id пользователя в Telegram.
     */
    @NotNull
    private Long telegramId;

    /**
     * Username пользователя в Telegram (@username).
     * Не обязательно к заполнению, поэтому может быть null.
     */
    private String username;

    /**
     * Имя пользователя, указанное в Telegram.
     */
    @NotBlank
    private String firstName;

    /**
     * Фамилия пользователя, указанная в Telegram.
     * Не обязательно к заполнению, поэтому может быть null.
     */
    private String lastName;

    /**
     * Дата и время создания записи о пользователе.
     */
    @PastOrPresent
    private LocalDateTime createdAt;

    /**
     * Дата и время последней активности пользователя.
     */
    @PastOrPresent
    private LocalDateTime lastActiveAt;


    /**
     * Пустой конструктор для создания пользователя
     */
    public User() {
    }

    /**
     * Конструктор для создания пользователя с заданными данными.
     *
     * @param telegramId   Telegram ID пользователя
     * @param username     Имя пользователя в Telegram (username)
     * @param firstName    Имя пользователя
     * @param lastName     Фамилия пользователя
     * @param createdAt    Дата и время создания записи
     * @param lastActiveAt Дата и время последней активности пользователя
     * Необязательные поля могут содержать null.
     * Валидация обязательных полей выполняется через аннотации
     */

    public User(Long telegramId, String username, String firstName, String lastName,
                LocalDateTime createdAt, LocalDateTime lastActiveAt) {
        this.telegramId = telegramId;
        this.username = username;
        this.firstName = firstName;
        this.lastName = lastName;
        this.createdAt = createdAt;
        this.lastActiveAt = lastActiveAt;
    }

}