package ru.jrgroup.quiz_bot.service;

import org.springframework.stereotype.Service;
import ru.jrgroup.quiz_bot.domain.Topic;
import ru.jrgroup.quiz_bot.repository.TopicRepository;

import java.util.List;

/**
 * Сервис для работы с темами и категориями.
 *
 * - getAllTopics() — список всех тем
 * - getTopicById(Long id) — тема по id
 * - getQuestionsByTopic(Long topicId) — вопросы по теме
 */

@Service
public class TopicService {
	private final TopicRepository topicRepository;

	public TopicService(TopicRepository topicRepository) {
		this.topicRepository = topicRepository;
	}

	public List<Topic> findAll() {
		return topicRepository.findAll();
	}
}
