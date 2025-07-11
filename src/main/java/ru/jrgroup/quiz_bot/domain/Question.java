package ru.jrgroup.quiz_bot.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

import java.util.ArrayList;
import java.util.List;

/**
 * JPA-сущность "Вопрос".
 * <p>
 * Описывает вопрос викторины, который может входить в разные викторины (Many-to-Many с {@link Quiz}).
 * Список вариантов ответа хранится в формате JSONB (PostgreSQL).
 * </p>
 *
 * <b>Поля:</b>
 * <ul>
 *   <li>id — уникальный идентификатор вопроса</li>
 *   <li>text — текст вопроса</li>
 *   <li>options — список вариантов ответа (JSONB)</li>
 *   <li>correctOption — индекс правильного ответа</li>
 *   <li>topic — тема, к которой относится вопрос</li>
 *   <li>quizzes — все викторины, в которые входит этот вопрос</li>
 * </ul>
 *
 * <b>Важно:</b> Индексация вариантов начинается с нуля.
 *
 * @author Константин
 */
@Entity
@Getter
@Setter
@Table(name = "questions")
public class Question {
	/**
	 * Уникальный идентификатор вопроса.
	 */
	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	/**
	 * Текст вопроса.
	 */
	@Column(nullable = false)
	private String text;

	/**
	 * Список вариантов ответа, хранящийся как JSONB.
	 */
	@Column(name = "options", columnDefinition = "jsonb", nullable = false)
	@Convert(converter = StringListJsonConverter.class)
	private List<String> options = new ArrayList<>();

	/**
	 * Индекс правильного ответа (от 0 до options.size()-1).
	 */
	@Column(name = "correct_option", nullable = false)
	private int correctOption;

	/**
	 * Тема, к которой относится вопрос.
	 */
	@ManyToOne(fetch = FetchType.LAZY)
	@JoinColumn(name = "topic_id")
	private Topic topic;

	/**
	 * Викторины, в которые входит данный вопрос.
	 */
	@ManyToMany(mappedBy = "questions")
	private List<Quiz> quizzes = new ArrayList<>();

	/**
	 * Конструктор без параметров для JPA.
	 */
	public Question() {}

	/**
	 * Конструктор для создания вопроса.
	 *
	 * @param text         текст вопроса
	 * @param options      варианты ответа
	 * @param correctOption индекс правильного ответа
	 * @param topic        тема вопроса
	 */
	public Question(String text, List<String> options, int correctOption, Topic topic) {
		this.text = text;
		this.options = options;
		this.correctOption = correctOption;
		this.topic = topic;
	}
}
