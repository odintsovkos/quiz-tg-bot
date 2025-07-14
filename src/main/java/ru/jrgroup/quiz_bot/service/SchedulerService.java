package ru.jrgroup.quiz_bot.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import ru.jrgroup.quiz_bot.bot.QuizBot;
import ru.jrgroup.quiz_bot.domain.Question;

/**
 * Сервис для периодической отправки случайных вопросов в групповой чат (тред).
 * <p>
 * Использует планировщик Spring для автоматического запуска по расписанию.
 * </p>
 */
@Service
public class SchedulerService {

    private static final Logger log = LoggerFactory.getLogger(SchedulerService.class);

    private final BotSenderService botSenderService;
    private final QuizBot quizBot;
    private final QuestionService questionService;

    @Value("${quiz.group.thread.id}")
    private Integer groupThreadId;

    @Value("${quiz.group.chat.id}")
    private Long chatId;

    @Value("${quiz.schedule.period}")
    private long period;

    /**
     * Конструктор SchedulerService.
     *
     * @param questionService сервис для получения вопросов
     */
    public SchedulerService(BotSenderService botSenderService, QuizBot quizBot, QuestionService questionService) {
		this.botSenderService = botSenderService;
		this.quizBot = quizBot;
		this.questionService = questionService;
    }

    /**
     * Периодически отправляет случайный вопрос в групповой чат.
     * <p>
     * Запускается ежедневно в 9:00 утра по серверному времени.
     * </p>
     */
    @Scheduled(fixedRateString = "${quiz.schedule.period}")
    public void sendDailyQuiz() {
        log.info("Начата рассылка ежедневного вопроса в групповой чат (id={})", groupThreadId);
        try {
            Question randomQuestion = questionService.findRandomQuestion();
            log.debug("Случайный вопрос выбран: {}", randomQuestion);

            botSenderService.sendPoll(quizBot, chatId, groupThreadId, randomQuestion);
            log.info("Вопрос успешно отправлен в чат id={}", groupThreadId);

        } catch (Exception e) {
            log.error("Ошибка при отправке вопроса в групповой чат id={}", groupThreadId, e);
        }
    }
}
