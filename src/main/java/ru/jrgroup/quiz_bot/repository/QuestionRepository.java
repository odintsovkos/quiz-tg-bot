package ru.jrgroup.quiz_bot.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import ru.jrgroup.quiz_bot.domain.Question;
import ru.jrgroup.quiz_bot.domain.Topic;

/**
 * JPA-репозиторий для вопросов.
 *
 * - Интерфейс extends JpaRepository<Question, Long>
 * - Методы поиска по теме (findByTopic)
 */

public interface QuestionRepository extends JpaRepository<Question, Long> {
	@Query(value = "SELECT * FROM questions ORDER BY random() LIMIT 1", nativeQuery = true)
	Question findRandomQuestion();
}
