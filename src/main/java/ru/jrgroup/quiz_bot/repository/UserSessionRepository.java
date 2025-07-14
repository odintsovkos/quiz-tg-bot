package ru.jrgroup.quiz_bot.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import ru.jrgroup.quiz_bot.domain.User;
import ru.jrgroup.quiz_bot.domain.UserSession;

import java.util.Optional;

/**
 * Репозиторий для управления сущностями UserSession.
 *
 * <p>
 * Основные методы:
 * <ul>
 *     <li>findByUser(User user) — получить сессию по пользователю</li>
 *     <li>findByUser_TelegramId(Long telegramId) — получить сессию по Telegram ID</li>
 * </ul>
 * </p>
 *
 * <b>Особенности:</b>
 * <ul>
 *     <li>Один пользователь может иметь только одну сессию (unique-constraint по user_id)</li>
 *     <li>Можно добавлять кастомные методы поиска по бизнес-логике</li>
 * </ul>
 */
@Repository
public interface UserSessionRepository extends JpaRepository<UserSession, Long> {
	/**
	 * Поиск сессии пользователя по объекту User.
	 *
	 * @param user пользователь
	 * @return Optional сессии (если есть)
	 */
	Optional<UserSession> findByUser(User user);

	/**
	 * Поиск сессии пользователя по Telegram ID.
	 *
	 * @param telegramId Telegram ID пользователя
	 * @return Optional сессии (если есть)
	 */
	Optional<UserSession> findByUser_TelegramId(Long telegramId);
}
