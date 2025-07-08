package ru.jrgroup.quiz_bot.domain;

/**
 * JPA-сущность "Ответ пользователя на вопрос".
 *
 * - id (Long)
 * - user (User)
 * - question (Question)
 * - selectedOption (int)
 * - isCorrect (boolean)
 * - answeredAt (Timestamp)
 *
 * Аннотации: @Entity, @Id, @ManyToOne(user), @ManyToOne(question)
 */

public class Answer {
}
