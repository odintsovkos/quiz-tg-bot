package ru.jrgroup.quiz_bot.bot.handler;

import org.springframework.stereotype.Component;

/**
 * Специализированный обработчик для логики викторин.
 *
 * - Метод: sendQuiz(Long chatId, Quiz quiz) — отправка викторины
 * - Метод: processAnswer(Long chatId, Integer answerId) — обработка ответа пользователя
 * - Генерирует и отправляет клавиатуры с вариантами ответов.
 */

@Component
public class QuizHandler {
}
