package ru.jrgroup.quiz_bot.domain;

/**
 * JPA-сущность "Вопрос".
 *
 * - id (Long)
 * - text (String) — текст вопроса
 * - options (List<String>) — варианты ответов
 * - correctOption (int) — индекс правильного ответа
 * - topic (Topic) — связь с темой
 *
 * Аннотации: @Entity, @Id, @ManyToOne(topic)
 */

public class Question {
}
