package ru.jrgroup.quiz_bot.service;

import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

@Service
public class TopicSelectionService {
	private final Map<Long, Set<Long>> userTopicSelection = new HashMap<>();

	public Set<Long> getSelectedTopics(long userId) {
		return userTopicSelection.computeIfAbsent(userId, k -> new HashSet<>());
	}

	public void clearSelection(long userId) {
		userTopicSelection.remove(userId);
	}
}
