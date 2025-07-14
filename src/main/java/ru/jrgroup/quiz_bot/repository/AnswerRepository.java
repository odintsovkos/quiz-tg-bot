package ru.jrgroup.quiz_bot.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import ru.jrgroup.quiz_bot.domain.Answer;

import java.util.List;

/**
 * JPA-репозиторий для ответов пользователей.
 *
 * - Интерфейс extends JpaRepository<Answer, Long>
 * - Методы поиска по пользователю и вопросу
 */

public interface AnswerRepository extends JpaRepository<Answer, Long> {
	/**
	 * Находит все ответы пользователя по его ID.
	 *
	 * @param userId ID пользователя
	 * @return Список ответов пользователя
	 */
	List<Answer> findByUserId(Long userId);

	/**
	 * Находит все ответы на заданный вопрос.
	 *
	 * @param questionId ID вопроса
	 * @return Список ответов на вопрос
	 */
	List<Answer> findByQuestionId(Long questionId);
}
