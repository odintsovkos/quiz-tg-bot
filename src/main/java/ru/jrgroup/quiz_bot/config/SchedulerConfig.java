package ru.jrgroup.quiz_bot.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * Конфигурация планировщика задач.
 *
 * - Аннотация @Configuration
 * - Настройка планировщика (Scheduler), если нужно что-то сложнее @Scheduled
 */
@Configuration
@EnableScheduling
public class SchedulerConfig {
}
