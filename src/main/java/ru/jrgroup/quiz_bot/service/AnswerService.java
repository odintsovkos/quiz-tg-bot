package ru.jrgroup.quiz_bot.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import ru.jrgroup.quiz_bot.domain.Answer;
import ru.jrgroup.quiz_bot.domain.Question;
import ru.jrgroup.quiz_bot.domain.User;
import ru.jrgroup.quiz_bot.repository.AnswerRepository;

import java.time.LocalDateTime;
import java.util.List;

@Service
public class AnswerService {
	private static final Logger logger = LoggerFactory.getLogger(AnswerService.class);

	private final AnswerRepository answerRepository;

	public AnswerService(AnswerRepository answerRepository) {
		this.answerRepository = answerRepository;
	}

	public void saveAnswer(User user, Question question, int selectedOption) {
		logger.info("Сохранение ответа пользователя {} на вопрос {}: выбран вариант {}", user.getUsername(), question.getId(), selectedOption);

		Answer answer = new Answer();
		answer.setUser(user);
		answer.setQuestion(question);
		answer.setSelectedOption(selectedOption);
		answer.setCorrect(question.getCorrectOption() == selectedOption);
		answer.setAnsweredAt(LocalDateTime.now());

		answerRepository.save(answer);
	}

	public List<Answer> getAnswersForUser(Long userId) {
		logger.info("Получение ответов для пользователя с ID {}", userId);
		return answerRepository.findByUserId(userId);
	}
}
