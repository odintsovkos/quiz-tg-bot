# Один процесс: long polling и планировщик внутри него.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY data/questions ./data/questions

RUN pip install --no-cache-dir .

# Файл SQLite лежит на томе, поэтому переживает пересоздание контейнера.
ENV DB_PATH=/data/quizbot.sqlite3
VOLUME ["/data"]

# Миграции применяются при старте: схема всегда соответствует образу.
CMD ["sh", "-c", "python -m alembic upgrade head && python -m app.main"]
