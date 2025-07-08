package ru.jrgroup.quiz_bot.domain;

/**
 * JPA-сущность "Викторина" (сеанс пользователя).
 *
 * - id (Long)
 * - user (User)
 * - questions (List<Question>)
 * - startedAt (Timestamp)
 * - finishedAt (Timestamp)
 * - score (int)
 *
 * Аннотации: @Entity, @Id, @ManyToOne(user), @OneToMany(questions)
 */

public class Quiz {
}
