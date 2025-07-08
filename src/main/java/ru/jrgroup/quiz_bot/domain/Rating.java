package ru.jrgroup.quiz_bot.domain;

/**
 * JPA-сущность "Рейтинг пользователя".
 *
 * - id (Long)
 * - user (User)
 * - points (int)
 * - updatedAt (Timestamp)
 *
 * Аннотации: @Entity, @Id, @ManyToOne(user)
 */

public class Rating {
}
