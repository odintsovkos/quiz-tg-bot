package ru.jrgroup.quiz_bot.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * JPA-сущность "Сессия пользователя".
 * <p>
 * Хранит текущее состояние пользователя в рамках взаимодействия с ботом:
 * активная викторина, текущий вопрос, состояние пользователя, время последней активности.
 * Используется для восстановления и управления прогрессом пользователя между действиями.
 * </p>
 *
 * <ul>
 *   <li>id (Long) — уникальный идентификатор сессии</li>
 *   <li>user (User) — пользователь, которому принадлежит сессия</li>
 *   <li>currentQuiz (Quiz) — активная викторина (может быть null, если не начата)</li>
 *   <li>currentQuestion (Question) — текущий вопрос (может быть null)</li>
 *   <li>state (String) — строковое описание состояния (например, "WAITING_ANSWER", "IN_MENU")</li>
 *   <li>lastActiveAt (LocalDateTime) — время последнего действия пользователя</li>
 * </ul>
 *
 * <b>Особенности:</b>
 * <ul>
 *   <li>Один пользователь может иметь только одну сессию (реализуется через unique-constraint по user_id).</li>
 *   <li>state — произвольная строка, может быть заменена на enum для безопасности типов.</li>
 * </ul>
 *
 * @author Константин
 */
@Entity
@Getter
@Setter
@Table(name = "user_sessions", uniqueConstraints = @UniqueConstraint(columnNames = "user_id"))
public class UserSession {

	/**
	 * Уникальный идентификатор сессии.
	 * Генерируется автоматически.
	 */
	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	/**
	 * Пользователь, которому принадлежит сессия.
	 * Один пользователь — одна сессия.
	 */
	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "user_id", nullable = false, unique = true)
	private User user;

	/**
	 * Активная викторина пользователя (может быть null, если викторина не начата).
	 */
	@ManyToOne(fetch = FetchType.LAZY)
	@JoinColumn(name = "current_quiz_id")
	private Quiz currentQuiz;

	/**
	 * Текущий вопрос в викторине (может быть null).
	 */
	@ManyToOne(fetch = FetchType.LAZY)
	@JoinColumn(name = "current_question_id")
	private Question currentQuestion;

	/**
	 * Текущее состояние пользователя (например, "IN_QUIZ", "WAITING_ANSWER").
	 * Желательно использовать Enum, чтобы ограничить возможные значения.
	 */
	@Column(nullable = false)
	private String state;

	/**
	 * Время последнего действия пользователя в рамках сессии.
	 */
	@Column(nullable = false)
	private LocalDateTime lastActiveAt;

	/**
	 * Конструктор без параметров для JPA.
	 */
	public UserSession() {}

	/**
	 * Конструктор для создания новой сессии.
	 *
	 * @param user            пользователь
	 * @param currentQuiz     активная викторина
	 * @param currentQuestion текущий вопрос
	 * @param state           состояние пользователя
	 * @param lastActiveAt    время последнего действия
	 */
	public UserSession(User user, Quiz currentQuiz, Question currentQuestion, String state, LocalDateTime lastActiveAt) {
		this.user = user;
		this.currentQuiz = currentQuiz;
		this.currentQuestion = currentQuestion;
		this.state = state;
		this.lastActiveAt = lastActiveAt;
	}
}
