package ru.jrgroup.quiz_bot.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.telegram.telegrambots.meta.api.objects.Message;
import ru.jrgroup.quiz_bot.domain.User;
import ru.jrgroup.quiz_bot.repository.UserRepository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

/**
 * Сервис для работы с пользователями Telegram-бота.
 *
 * <ul>
 *   <li>Регистрирует или обновляет пользователя по Telegram ID при каждом новом сообщении</li>
 *   <li>Обеспечивает поиск пользователя по username и telegramId</li>
 *   <li>Позволяет сохранить/обновить пользователя и получить список всех пользователей</li>
 *   <li>Логирует все ключевые действия на трёх уровнях (INFO, WARN, ERROR)</li>
 * </ul>
 */
@Service
public class UserService {

	private static final Logger logger = LoggerFactory.getLogger(UserService.class);

	private final UserRepository userRepository;

	/**
	 * Внедрение репозитория пользователей.
	 * @param userRepository бин UserRepository
	 */
	public UserService(UserRepository userRepository) {
		this.userRepository = userRepository;
	}

	/**
	 * Поиск пользователя по username.
	 * @param username username Telegram пользователя
	 * @return User найденный пользователь
	 * @throws IllegalArgumentException если пользователь не найден
	 */
	public User findByUsername(String username) {
		logger.debug("Поиск пользователя по username: {}", username);
		return userRepository.findByUsername(username)
				.orElseThrow(() -> {
					logger.warn("Пользователь с username '{}' не найден", username);
					return new IllegalArgumentException("Пользователь с username " + username + " не найден");
				});
	}

	/**
	 * Сохраняет/обновляет пользователя.
	 * @param user объект пользователя для сохранения
	 */
	public void save(User user) {
		logger.info("Сохранение пользователя с Telegram ID: {}", user.getTelegramId());
		userRepository.save(user);
	}

	/**
	 * Получает список всех пользователей.
	 * @return список пользователей
	 */
	public List<User> findAll() {
		logger.debug("Запрошен список всех пользователей");
		return userRepository.findAll();
	}

	/**
	 * Регистрирует нового пользователя или обновляет время последней активности,
	 * если пользователь уже есть в базе. Если пользователь новый — создает его на основе Message.
	 * Логирует оба сценария.
	 *
	 * @param message входящее сообщение из Telegram
	 */
	public void registerOrUpdateUser(Message message) {
		Long telegramId = message.getFrom().getId();

		// Ищем по telegramId (а не по id в базе!)
		Optional<User> userOpt = userRepository.findByTelegramId(telegramId);

		if (userOpt.isEmpty()) {
			User newUser = new User();
			newUser.setTelegramId(telegramId);
			newUser.setFirstName(message.getFrom().getFirstName());
			newUser.setLastName(message.getFrom().getLastName());
			newUser.setUsername(message.getFrom().getUserName());
			newUser.setCreatedAt(LocalDateTime.now());
			newUser.setLastActiveAt(LocalDateTime.now());
			userRepository.save(newUser);
			logger.info("Зарегистрирован новый пользователь: {} (username: {})", telegramId, newUser.getUsername());
		} else {
			User existingUser = userOpt.get();
			existingUser.setLastActiveAt(LocalDateTime.now());
			userRepository.save(existingUser);
			logger.debug("Обновлена активность пользователя: {} (username: {})", telegramId, existingUser.getUsername());
		}
	}

	/**
	 * Поиск пользователя по Telegram ID.
	 * @param telegramId Telegram ID пользователя
	 * @return Optional<User>
	 */
	public Optional<User> findByTelegramId(Long telegramId) {
		logger.debug("Поиск пользователя по Telegram ID: {}", telegramId);
		return userRepository.findByTelegramId(telegramId);
	}
}
