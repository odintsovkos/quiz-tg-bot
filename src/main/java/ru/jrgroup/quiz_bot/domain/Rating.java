package ru.jrgroup.quiz_bot.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * JPA-сущность "Рейтинг пользователя".
 * <p>
 * Хранит итоговое количество очков пользователя и время последнего обновления рейтинга.
 * Предполагается, что для каждого пользователя существует только один объект {@code Rating}.
 * </p>
 *
 * <ul>
 *   <li>id (Long) — уникальный идентификатор рейтинга</li>
 *   <li>user (User) — пользователь, которому принадлежит рейтинг</li>
 *   <li>points (int) — суммарное количество очков</li>
 *   <li>updatedAt (LocalDateTime) — дата и время последнего обновления рейтинга</li>
 * </ul>
 *
 * <b>Особенности:</b>
 * <ul>
 *   <li>user уникален — один пользователь не может иметь несколько рейтингов.</li>
 *   <li>points не может быть отрицательным.</li>
 * </ul>
 *
 * @author Константин
 */
@Entity
@Getter
@Setter
@Table(name = "ratings", uniqueConstraints = @UniqueConstraint(columnNames = "user_id"))
public class Rating {

	/**
	 * Уникальный идентификатор рейтинга.
	 * Генерируется автоматически.
	 */
	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	/**
	 * Пользователь, которому принадлежит рейтинг.
	 * Один-ко-многим: один пользователь — один рейтинг.
	 */
	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "user_id", nullable = false, unique = true)
	private User user;

	/**
	 * Количество очков пользователя.
	 * Значение не может быть отрицательным.
	 */
	@Column(nullable = false)
	private int points;

	/**
	 * Дата и время последнего обновления рейтинга.
	 */
	@Column(nullable = false)
	private LocalDateTime updatedAt;

	/**
	 * Конструктор без параметров для JPA.
	 */
	public Rating() {}

	/**
	 * Конструктор для создания рейтинга.
	 *
	 * @param user      пользователь
	 * @param points    количество очков
	 * @param updatedAt дата и время обновления
	 */
	public Rating(User user, int points, LocalDateTime updatedAt) {
		this.user = user;
		this.points = points;
		this.updatedAt = updatedAt;
	}
}
