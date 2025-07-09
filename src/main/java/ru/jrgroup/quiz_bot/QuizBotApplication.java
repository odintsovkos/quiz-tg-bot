package ru.jrgroup.quiz_bot;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

/**
 * Главный класс Spring Boot приложения.
 * Точка входа для запуска QuizBot.
 *
 * - Аннотация @SpringBootApplication
 * - Содержит метод public static void main(String[] args)
 */
@SpringBootApplication
@ConfigurationPropertiesScan
public class QuizBotApplication {

	public static void main(String[] args) {
		SpringApplication.run(QuizBotApplication.class, args);
	}

}
