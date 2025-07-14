package ru.jrgroup.quiz_bot.domain;

import ru.jrgroup.quiz_bot.domain.Question;

public class QuizProgress {
	private Question question;
	private boolean finished;

	public QuizProgress(Question question, boolean finished) {
		this.question = question;
		this.finished = finished;
	}

	public Question getQuestion() {
		return question;
	}

	public boolean isFinished() {
		return finished;
	}
}