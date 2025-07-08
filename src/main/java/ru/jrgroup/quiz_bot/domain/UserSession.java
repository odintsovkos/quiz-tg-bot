package ru.jrgroup.quiz_bot.domain;

/**
 * JPA-сущность "Сессия пользователя" (текущее состояние).
 *
 * - id (Long)
 * - user (User)
 * - currentQuiz (Quiz)
 * - currentQuestion (Question)
 * - state (String)
 * - lastActiveAt (Timestamp)
 *
 * Аннотации: @Entity, @Id, @ManyToOne(user), @ManyToOne(currentQuiz)
 */

public class UserSession {
}
