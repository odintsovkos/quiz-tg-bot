package ru.jrgroup.quiz_bot.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import ru.jrgroup.quiz_bot.domain.Topic;

/**
 * JPA-репозиторий для тем.
 *
 * - Интерфейс extends JpaRepository<Topic, Long>
 */

public interface TopicRepository extends JpaRepository<Topic, Long> {

}
