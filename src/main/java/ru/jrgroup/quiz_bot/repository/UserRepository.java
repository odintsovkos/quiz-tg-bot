package ru.jrgroup.quiz_bot.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import ru.jrgroup.quiz_bot.domain.User;

import java.util.List;
import java.util.Optional;

/**
 * JPA-репозиторий для пользователей.
 *
 * - Интерфейс extends JpaRepository<User, Long>
 * - Методы поиска по telegramId, username
 */

public interface UserRepository extends JpaRepository<User, Long> {
    Optional<User> findByTelegramId(Long telegramId);
    List<User> findAll();
    Optional<User> findByUsername(String username);
}
