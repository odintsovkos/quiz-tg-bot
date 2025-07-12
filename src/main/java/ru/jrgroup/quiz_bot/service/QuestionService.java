package ru.jrgroup.quiz_bot.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import ru.jrgroup.quiz_bot.domain.Question;
import ru.jrgroup.quiz_bot.repository.QuestionRepository;
import ru.jrgroup.quiz_bot.repository.UserRepository;

@Service
public class QuestionService {
	private static final Logger logger = LoggerFactory.getLogger(QuestionService.class);
	private final QuestionRepository questionRepository;

	public QuestionService(QuestionRepository questionRepository, UserRepository userRepository) {
		this.questionRepository = questionRepository;
	}

	public Question findRandomQuestion() {
		return questionRepository.findRandomQuestion();
	}

}
