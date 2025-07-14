package ru.jrgroup.quiz_bot.domain;

import ru.jrgroup.quiz_bot.domain.Question;
import java.util.List;

public class QuizStats {
	private int total;
	private int correct;
	private List<Question> wrongQuestions;

	public QuizStats(int total, int correct, List<Question> wrongQuestions) {
		this.total = total;
		this.correct = correct;
		this.wrongQuestions = wrongQuestions;
	}

	public int getTotal() {
		return total;
	}

	public int getCorrect() {
		return correct;
	}

	public List<Question> getWrongQuestions() {
		return wrongQuestions;
	}
}