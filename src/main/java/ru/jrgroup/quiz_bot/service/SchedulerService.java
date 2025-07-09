package ru.jrgroup.quiz_bot.service;

import org.jvnet.hk2.annotations.Service;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Сервис для задач по расписанию.
 *
 * - scheduleDailyQuiz() — планирование ежедневной рассылки викторин
 * - sendQuizToAllUsers() — рассылка викторин всем пользователям
 */
@Service
public class SchedulerService {
    private static final Logger log = LoggerFactory.getLogger(SchedulerService.class);

    public void sendDailyQuiz() {
        log.info("The daily quiz has started sending out");
        try {

        } catch (Exception e) {
            log.error("Ошибка при отправке вопроса", e);
        }
    }
}
