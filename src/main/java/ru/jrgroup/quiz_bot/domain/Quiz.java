package ru.jrgroup.quiz_bot.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * JPA-сущность "Викторина".
 * <p>
 * Описывает сессию викторины, связанную с пользователем и набором вопросов.
 * Реализована связь Many-to-Many с {@link Question} через промежуточную таблицу quizzes_questions.
 * </p>
 *
 * <b>Поля:</b>
 * <ul>
 *   <li>id — уникальный идентификатор викторины</li>
 *   <li>user — пользователь, проходящий викторину</li>
 *   <li>questions — список вопросов</li>
 *   <li>startedAt — время начала</li>
 *   <li>finishedAt — время завершения</li>
 *   <li>score — итоговый счёт</li>
 * </ul>
 *
 * @author Константин
 */
@Entity
@Getter
@Setter
@Table(name = "quizzes")
public class Quiz {
	/**
	 * Уникальный идентификатор викторины.
	 */
	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	/**
	 * Пользователь, проходящий викторину.
	 */
	@ManyToOne(fetch = FetchType.LAZY)
	@JoinColumn(name = "user_id")
	private User user;

	/**
	 * Список вопросов викторины (Many-to-Many).
	 */
	@ManyToMany
	@JoinTable(
			name = "quizzes_questions",
			joinColumns = @JoinColumn(name = "quiz_id"),
			inverseJoinColumns = @JoinColumn(name = "question_id")
	)
	private List<Question> questions = new ArrayList<>();

	/**
	 * Время начала викторины.
	 */
	@Column(name = "started_at")
	private LocalDateTime startedAt;

	/**
	 * Время завершения викторины.
	 */
	@Column(name = "finished_at")
	private LocalDateTime finishedAt;

	/**
	 * Итоговый счёт.
	 */
	@Column(nullable = false)
	private int score;

	/**
	 * Конструктор без параметров для JPA.
	 */
	public Quiz() {}

	/**
	 * Конструктор для создания викторины.
	 *
	 * @param user       пользователь
	 * @param questions  список вопросов
	 * @param startedAt  время начала
	 * @param finishedAt время завершения
	 * @param score      счёт
	 */
	public Quiz(User user, List<Question> questions, LocalDateTime startedAt, LocalDateTime finishedAt, int score) {
		this.user = user;
		this.questions = questions;
		this.startedAt = startedAt;
		this.finishedAt = finishedAt;
		this.score = score;
	}
}
