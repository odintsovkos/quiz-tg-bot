package ru.jrgroup.quiz_bot.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.jrgroup.quiz_bot.domain.*;
import ru.jrgroup.quiz_bot.repository.UserSessionRepository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/**
 * Сервис для управления сессиями пользователей.
 * <p>
 * Реализует бизнес-логику создания, поиска, обновления и удаления сессий пользователя.
 * Использует {@link UserSessionRepository} для доступа к базе данных.
 *
 * <ul>
 *   <li>getOrCreateSession(User user) — получить или создать сессию пользователя</li>
 *   <li>updateState(User user, String state) — обновить состояние сессии</li>
 *   <li>setCurrentQuizAndQuestion(User user, Quiz quiz, Question question) — обновить текущую викторину/вопрос</li>
 *   <li>clearSession(User user) — сбросить состояние сессии</li>
 * </ul>
 * </p>
 */
@Service
public class UserSessionService {

	private static final Logger logger = LoggerFactory.getLogger(UserSessionService.class);

	private final UserSessionRepository sessionRepository;

	public UserSessionService(UserSessionRepository sessionRepository) {
		this.sessionRepository = sessionRepository;
	}

	/**
	 * Найти существующую сессию пользователя или создать новую (если отсутствует).
	 *
	 * @param user пользователь
	 * @return UserSession объект сессии
	 */
	@Transactional
	public UserSession getOrCreateSession(User user) {
		Optional<UserSession> sessionOpt = sessionRepository.findByUser(user);
		if (sessionOpt.isPresent()) {
			logger.debug("Сессия пользователя {} найдена", user.getTelegramId());
			return sessionOpt.get();
		}
		UserSession newSession = new UserSession(
				user,
				null,
				null,
				State.IN_MENU,
				LocalDateTime.now()
		);
		UserSession saved = sessionRepository.save(newSession);
		logger.info("Создана новая сессия для пользователя {}", user.getTelegramId());
		return saved;
	}

	/**
	 * Получить сессию по Telegram ID пользователя (если существует).
	 */
	public Optional<UserSession> findByTelegramId(Long telegramId) {
		return sessionRepository.findByUser_TelegramId(telegramId);
	}

	/**
	 * Обновить состояние сессии пользователя.
	 *
	 * @param user  пользователь
	 * @param state новое состояние (например, "WAITING_ANSWER")
	 */
	@Transactional
	public void updateState(User user, State state) {
		UserSession session = getOrCreateSession(user);
		session.setState(state);
		session.setLastActiveAt(LocalDateTime.now());
		sessionRepository.save(session);
		logger.debug("Обновлено состояние сессии для пользователя {} на '{}'", user.getTelegramId(), state);
	}

	/**
	 * Обновить текущую викторину и вопрос в сессии пользователя.
	 */
	@Transactional
	public void setCurrentQuizAndQuestion(User user, Quiz quiz, Question question) {
		UserSession session = getOrCreateSession(user);
		session.setCurrentQuiz(quiz);
		session.setCurrentQuestion(question);
		session.setLastActiveAt(LocalDateTime.now());
		sessionRepository.save(session);
		logger.debug("Установлены quiz/question для сессии пользователя {}", user.getTelegramId());
	}

	/**
	 * Сбросить сессию пользователя (удалить quiz, question, вернуть state в IN_MENU).
	 */
	@Transactional
	public void clearSession(User user) {
		Optional<UserSession> sessionOpt = sessionRepository.findByUser(user);
		if (sessionOpt.isPresent()) {
			UserSession session = sessionOpt.get();
			session.setCurrentQuiz(null);
			session.setCurrentQuestion(null);
			session.setState(State.IN_MENU);
			session.setLastActiveAt(LocalDateTime.now());
			sessionRepository.save(session);
			logger.info("Сброшена сессия для пользователя {}", user.getTelegramId());
		}
	}

	/**
	 * Полностью удалить сессию пользователя (по необходимости).
	 */
	@Transactional
	public void deleteSession(User user) {
		sessionRepository.findByUser(user).ifPresent(session -> {
			sessionRepository.delete(session);
			logger.info("Удалена сессия пользователя {}", user.getTelegramId());
		});
	}

	public void startQuizSession(Long id, List<Question> questions) {
		Optional<UserSession> sessionOpt = sessionRepository.findById(id);
		if (sessionOpt.isPresent()) {
			UserSession session = sessionOpt.get();
			Quiz quiz = new Quiz();
			quiz.setQuestions(questions);
			quiz.setUser(session.getUser());
			quiz.setStartedAt(LocalDateTime.now());
			quiz.setFinishedAt(null);
			quiz.setScore(0);
			session.setCurrentQuiz(quiz);
			session.setCurrentQuestion(questions.getFirst());
			session.setState(State.QUIZ_ASKING);
			session.setLastActiveAt(LocalDateTime.now());
			sessionRepository.save(session);
			logger.info("Начата викторина для пользователя {}", id);
		} else {
			logger.warn("Не найдена сессия для пользователя с ID {}", id);
		}
	}

	public Question getNextQuestion(Long id) {
		Optional<UserSession> sessionOpt = sessionRepository.findById(id);
		if (sessionOpt.isPresent()) {
			UserSession session = sessionOpt.get();
			List<Question> questions = session.getCurrentQuiz().getQuestions();
			int currentIndex = questions.indexOf(session.getCurrentQuestion());
			if (currentIndex < questions.size() - 1) {
				Question nextQuestion = questions.get(currentIndex + 1);
				session.setCurrentQuestion(nextQuestion);
				session.setLastActiveAt(LocalDateTime.now());
				sessionRepository.save(session);
				return nextQuestion;
			} else {
				logger.info("Викторина завершена для пользователя {}", id);
				return null;
			}
		} else {
			logger.warn("Не найдена сессия для пользователя с ID {}", id);
			return null;
		}
	}

	public Set<Long> getSelectedTopicIds(User user) {
		if (user == null) {
			logger.warn("Попытка получить выбранные темы для null пользователя");
			return Set.of();
		}
		Optional<UserSession> sessionOpt = sessionRepository.findByUser(user);
		if (sessionOpt.isPresent()) {
			UserSession session = sessionOpt.get();
			Set<Long> selectedTopicIds = session.getSelectedTopicIds();
			logger.debug("Выбранные темы для пользователя {}: {}", user.getTelegramId(), selectedTopicIds);
			return selectedTopicIds;
		} else {
			logger.warn("Не найдена сессия для пользователя {}", user.getTelegramId());
			return Set.of();
		}
	}

	public Question getCurrentQuestion(User user) {
		UserSession session = sessionRepository.findByUser(user).get();
		return session != null ? session.getCurrentQuestion() : null;
	}

	/**
	 * Получить текущее состояние пользователя из сессии.
	 *
	 * @param user пользователь
	 * @return текущее состояние (State) или State.IN_MENU по умолчанию
	 */
	public State getState(User user) {
		if (user == null) {
			logger.warn("Попытка получить состояние для null пользователя");
			return State.IN_MENU;
		}
		Optional<UserSession> sessionOpt = sessionRepository.findByUser(user);
		if (sessionOpt.isPresent()) {
			State state = sessionOpt.get().getState();
			logger.debug("Текущее состояние пользователя {}: {}", user.getTelegramId(), state);
			return state;
		} else {
			logger.info("Сессия для пользователя {} не найдена, возвращается состояние по умолчанию", user.getTelegramId());
			return State.IN_MENU;
		}
	}

}

