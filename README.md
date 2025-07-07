# Quiz Telegram Bot

Бот для проведения интерактивных викторин в Telegram.  
Создан для совместного обучения, обмена знаниями и улучшения навыков программирования в команде JavaRush!

## Возможности

- Создание и прохождение викторин прямо в Telegram
- Подсчёт и отображение результатов участников
- Ежедневные рейтинги лучших игроков
- Добавление новых вопросов через JSON
- Простое управление через команды бота

## Как начать использовать

1. **Склонируйте репозиторий:**
    ```bash
    git clone https://github.com/odintsovkos/quiz-telegram-bot.git
    ```
2. **Перейдите в папку проекта:**
    ```bash
    cd quiz-telegram-bot
    ```
3. **Создайте и заполните файл настроек `.env` или `application.properties` (пример: укажите токен вашего Telegram-бота).**
4. **Соберите и запустите проект (на примере Maven):**
    ```bash
    mvn clean install
    java -jar target/quiz-telegram-bot.jar
    ```

## Требования

- Java 21+
- Maven
- Аккаунт Telegram и зарегистрированный Telegram Bot

## Пример формата вопроса (JSON)

```json
{
  "question": "Кто создал язык программирования Java?",
  "options": ["Microsoft", "James Gosling", "Linus Torvalds", "Guido van Rossum"],
  "answer": 1
}
