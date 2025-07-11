package ru.jrgroup.quiz_bot.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * JPA-сущность "Ответ пользователя на вопрос".
 * <p>
 * Хранит информацию о том, какой пользователь какой вариант ответа выбрал на конкретный вопрос викторины,
 * был ли этот ответ правильным, а также время совершения выбора.
 * </p>
 *
 * <ul>
 *   <li>id (Long) — уникальный идентификатор ответа</li>
 *   <li>user (User) — пользователь, давший ответ</li>
 *   <li>question (Question) — вопрос, на который дан ответ</li>
 *   <li>selectedOption (int) — индекс выбранного варианта</li>
 *   <li>isCorrect (boolean) — флаг правильности ответа</li>
 *   <li>answeredAt (LocalDateTime) — дата и время ответа</li>
 * </ul>
 *
 * <b>Особенности:</b>
 * <ul>
 *   <li>Один пользователь может ответить на один вопрос только один раз в рамках одной викторины.</li>
 *   <li>selectedOption — индекс из массива вариантов ответа (от 0 до options.size()-1).</li>
 * </ul>
 *
 * @author Константин
 */
@Entity
@Getter
@Setter
@Table(name = "answers")
public class Answer {

	/**
	 * Уникальный идентификатор ответа.
	 * Генерируется автоматически.
	 */
	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	/**
	 * Пользователь, который дал ответ.
	 * Связь многие-к-одному с {@link User}.
	 */
	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "user_id")
	private User user;

	/**
	 * Вопрос, на который был дан ответ.
	 * Связь многие-к-одному с {@link Question}.
	 */
	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "question_id")
	private Question question;

	/**
	 * Индекс выбранного пользователем варианта ответа.
	 * Значение от 0 до количества вариантов ответа - 1.
	 */
	@Column(nullable = false)
	private int selectedOption;

	/**
	 * Был ли ответ пользователя правильным.
	 */
	@Column(nullable = false)
	private boolean isCorrect;

	/**
	 * Дата и время, когда был дан ответ.
	 */
	@Column(nullable = false)
	private LocalDateTime answeredAt;

	/**
	 * Конструктор без параметров для JPA.
	 */
	public Answer() {}

	/**
	 * Конструктор для создания ответа с заданными параметрами.
	 *
	 * @param user           пользователь
	 * @param question       вопрос
	 * @param selectedOption выбранный вариант
	 * @param isCorrect      правильность ответа
	 * @param answeredAt     дата и время ответа
	 */
	public Answer(User user, Question question, int selectedOption, boolean isCorrect, LocalDateTime answeredAt) {
		this.user = user;
		this.question = question;
		this.selectedOption = selectedOption;
		this.isCorrect = isCorrect;
		this.answeredAt = answeredAt;
	}
}
