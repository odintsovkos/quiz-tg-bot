package ru.jrgroup.quiz_bot.domain;

import jakarta.persistence.*;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.Setter;

/**
 * JPA-сущность "Тема".
 * <p>
 * Сущность хранит информацию о теме вопросов, которые могут использоваться в системе (например, в опросах или тестах).
 * Каждая тема содержит уникальный идентификатор, название и (опционально) описание.
 * </p>
 *
 * <p>
 * Пример использования:
 * <pre>{@code
 * Topic topic = new Topic("Java", "Вопросы по Java SE и Java EE");
 * }</pre>
 * </p>
 *
 * <p>
 * Аннотации:
 * <ul>
 *   <li>{@link Entity} - помечает класс как JPA-сущность</li>
 *   <li>{@link Table} - определяет таблицу "topics" в базе данных</li>
 * </ul>
 * </p>
 *
 * @author Константин
 */
@Entity
@Getter
@Setter
@Table(name = "topics")
public class Topic {

	/**
	 * Уникальный идентификатор темы.
	 * Генерируется автоматически при создании новой записи в таблице "topics".
	 */
	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	@NotNull
	private Long id;

	/**
	 * Название темы.
	 * Не может быть {@code null}.
	 */
	@NotNull
	private String name;

	/**
	 * Описание темы.
	 * Может быть {@code null} или пустым.
	 */
	private String description;

	/**
	 * Конструктор без параметров для JPA.
	 * Используется фреймворком Hibernate при создании сущности из БД.
	 */
	public Topic() {}

	/**
	 * Конструктор с параметрами для создания новой темы.
	 *
	 * @param name        название темы (обязательное, не {@code null})
	 * @param description описание темы (опционально)
	 */
	public Topic(String name, String description) {
		this.name = name;
		this.description = description;
	}
}
