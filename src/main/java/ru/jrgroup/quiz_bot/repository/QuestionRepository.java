package ru.jrgroup.quiz_bot.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import ru.jrgroup.quiz_bot.domain.Question;

import java.util.List;
import java.util.Set;

/**
 * JPA-репозиторий для вопросов.
 *
 * - Интерфейс extends JpaRepository<Question, Long>
 * - Методы поиска по теме (findByTopic)
 */

public interface QuestionRepository extends JpaRepository<Question, Long> {
	@Query(value = "SELECT * FROM questions ORDER BY random() LIMIT 1", nativeQuery = true)
	Question findRandomQuestion();

	@Query(value = "SELECT * FROM question WHERE topic_id IN (:topicIds) ORDER BY RAND() LIMIT :limit", nativeQuery = true)
	List<Question> findRandomByTopicIds(@Param("topicIds") Set<Long> topicIds, @Param("limit") int limit);
}
