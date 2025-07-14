package ru.jrgroup.quiz_bot.service;

import org.springframework.stereotype.Service;
import ru.jrgroup.quiz_bot.domain.*;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

@Service
public class QuizService {

	private final UserSessionService sessionService;
	private final QuestionService questionService;
	private final AnswerService answerService;

	public QuizService(UserSessionService sessionService, QuestionService questionService, AnswerService answerService) {
		this.sessionService = sessionService;
		this.questionService = questionService;
		this.answerService = answerService;
	}

	/**
	 * Инициализация новой викторины: выбор тем, подбор вопросов.
	 */
	public void startQuiz(User user, Set<Long> selectedTopicIds) {
		List<Question> questions = questionService.findRandomQuestionsByTopics(selectedTopicIds, 20);
		sessionService.startQuizSession(user.getId(), questions);
	}

	/**
	 * При получении ответа пользователя:
	 * - сохраняем ответ;
	 * - подготавливаем следующий вопрос;
	 * - если вопросов не осталось — финальный экран.
	 */
	public QuizProgress processUserAnswer(User user, Question question, int selectedOption) {
		answerService.saveAnswer(user, question, selectedOption);
		Question nextQuestion = sessionService.getNextQuestion(user.getId());
		if (nextQuestion != null) {
			return new QuizProgress(nextQuestion, false);
		} else {
			return new QuizProgress(null, true); // Викторина завершена
		}
	}

	/**
	 * Возвращает статистику: сколько правильных, список неправильных вопросов.
	 */
	public QuizStats getQuizStats(User user) {
		List<Answer> answers = answerService.getAnswersForUser(user.getId());
		int correct = (int) answers.stream().filter(Answer::isCorrect).count();
		List<Question> wrongQuestions = answers.stream()
				.filter(a -> !a.isCorrect())
				.map(Answer::getQuestion)
				.collect(Collectors.toList());
		return new QuizStats(answers.size(), correct, wrongQuestions);
	}
}

