-- Пользователь
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL UNIQUE,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMP
);

-- Тема
CREATE TABLE topics (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT
);

-- Вопрос
CREATE TABLE questions (
    id BIGSERIAL PRIMARY KEY,
    text TEXT NOT NULL,
    options JSONB NOT NULL,
    correct_option INT NOT NULL,
    topic_id BIGINT REFERENCES topics(id) ON DELETE CASCADE
);

-- Ответ пользователя на вопрос
CREATE TABLE answers (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    question_id BIGINT REFERENCES questions(id) ON DELETE CASCADE,
    selected_option INT NOT NULL,
    is_correct BOOLEAN NOT NULL,
    answered_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Викторина
CREATE TABLE quizzes (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMP,
    score INT NOT NULL DEFAULT 0
);

-- Связь викторина <-> вопросы
CREATE TABLE quizzes_questions (
    quiz_id BIGINT REFERENCES quizzes(id) ON DELETE CASCADE,
    question_id BIGINT REFERENCES questions(id) ON DELETE CASCADE,
    PRIMARY KEY (quiz_id, question_id)
);

-- Рейтинг пользователя
CREATE TABLE ratings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    points INT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Сессия пользователя (текущее состояние)
CREATE TABLE user_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    current_quiz_id BIGINT REFERENCES quizzes(id) ON DELETE SET NULL,
    current_question_id BIGINT REFERENCES questions(id) ON DELETE SET NULL,
    state VARCHAR(50) NOT NULL,
    last_active_at TIMESTAMP NOT NULL DEFAULT NOW()
);
