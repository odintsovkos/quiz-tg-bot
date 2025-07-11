-- Добавим пользователей
INSERT INTO users (telegram_id, username, first_name, last_name, created_at, last_active_at)
VALUES
    (1111, 'john_doe', 'John', 'Doe', NOW(), NOW());

-- Добавим темы
INSERT INTO topics (name, description)
VALUES
    ('Java', 'Вопросы по Java Core'),
    ('Spring Boot', 'Вопросы по Spring Boot');

-- Добавим вопросы
INSERT INTO questions (text, options, correct_option, topic_id)
VALUES
    (
        'Что такое полиморфизм в Java?',
        '["Механизм ООП, позволяющий использовать один интерфейс для разных типов данных", "Способ хранения нескольких значений в одной переменной", "Вид наследования"]',
        0,
        (SELECT id FROM topics WHERE name = 'Java')
    ),
    (
        'Какой файл нужен для настройки Spring Boot приложения?',
        '["application.yml", "spring.properties", "pom.xml"]',
        0,
        (SELECT id FROM topics WHERE name = 'Spring Boot')
    );

-- Добавим quiz (сеанс)
INSERT INTO quizzes (user_id, started_at, score)
VALUES (
    (SELECT id FROM users WHERE telegram_id = 1111),
    NOW(),
    1
);

-- Привяжем вопросы к викторине (many-to-many)
INSERT INTO quizzes_questions (quiz_id, question_id)
SELECT
    (SELECT id FROM quizzes LIMIT 1), id FROM questions;

-- Добавим ответ пользователя
INSERT INTO answers (user_id, question_id, selected_option, is_correct, answered_at)
VALUES
(
    (SELECT id FROM users WHERE telegram_id = 1111),
    (SELECT id FROM questions WHERE text LIKE 'Что такое полиморфизм%'),
    0,
    TRUE,
    NOW()
);

-- Добавим рейтинг
INSERT INTO ratings (user_id, points, updated_at)
VALUES
(
    (SELECT id FROM users WHERE telegram_id = 1111),
    10,
    NOW()
);

-- Добавим user_session
INSERT INTO user_sessions (user_id, current_quiz_id, current_question_id, state, last_active_at)
VALUES
(
    (SELECT id FROM users WHERE telegram_id = 1111),
    (SELECT id FROM quizzes LIMIT 1),
    (SELECT id FROM questions WHERE text LIKE 'Что такое полиморфизм%'),
    'IN_PROGRESS',
    NOW()
);
