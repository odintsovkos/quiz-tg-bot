package ru.jrgroup.quiz_bot.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import ru.jrgroup.quiz_bot.domain.Question;
import ru.jrgroup.quiz_bot.repository.QuestionRepository;

import java.util.List;
import java.util.Set;

@Service
public class QuestionService {
	private static final Logger logger = LoggerFactory.getLogger(QuestionService.class);
	private final QuestionRepository questionRepository;

	public QuestionService(QuestionRepository questionRepository) {
		this.questionRepository = questionRepository;
	}

	public Question findRandomQuestion() {
		return questionRepository.findRandomQuestion();
	}

	public List<Question> findRandomQuestionsByTopics(Set<Long> topicIds, int limit) {
		return questionRepository.findRandomByTopicIds(topicIds, limit);
	}

}
