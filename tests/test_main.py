import asyncio

from app.core.config import Settings
from app.core.container import build_application
from app.main import main, run


def _session_closed(bot) -> bool:
    """У aiogram нет публичного признака — смотрим на нижележащую сессию aiohttp."""
    inner = getattr(bot.session, "_session", None)
    return inner is None or inner.closed


def make_settings(tmp_path) -> Settings:
    return Settings(
        BOT_TOKEN="123:fake",
        OWNER_ID=1,
        DB_PATH=tmp_path / "quizbot.sqlite3",
    )


async def prepared_settings(tmp_path) -> Settings:
    """Настройки и созданная схема — в проде её создаёт `alembic upgrade head`."""
    from app.core.db import create_engine
    from app.models import Base

    settings = make_settings(tmp_path)
    engine = create_engine(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    return settings


def test_main_reports_missing_configuration(monkeypatch, tmp_path, capsys):
    for name in ("BOT_TOKEN", "OWNER_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)

    assert main() == 2
    assert "BOT_TOKEN" in capsys.readouterr().err


async def test_shutdown_releases_resources(tmp_path):
    application = build_application(await prepared_settings(tmp_path))
    await application.start()
    assert application.scheduler.running

    await application.shutdown()

    assert not application.scheduler.running
    assert _session_closed(application.bot)
    # повторное закрытие движка не должно падать
    await application.engine.dispose()


async def test_run_stops_on_signal_event(tmp_path, monkeypatch):
    """Сигнал остановки завершает опрос и освобождает ресурсы."""
    settings = await prepared_settings(tmp_path)
    application = build_application(settings)
    monkeypatch.setattr("app.main.build_application", lambda _settings: application)

    polling_started = asyncio.Event()
    stop_called = asyncio.Event()

    async def fake_polling(*_args, **_kwargs):
        polling_started.set()
        await stop_called.wait()

    async def fake_stop_polling():
        stop_called.set()

    monkeypatch.setattr(application.dispatcher, "start_polling", fake_polling)
    monkeypatch.setattr(application.dispatcher, "stop_polling", fake_stop_polling)

    captured: list[asyncio.Event] = []
    original_event = asyncio.Event

    def capture_event():
        event = original_event()
        captured.append(event)
        return event

    monkeypatch.setattr("app.main.asyncio.Event", capture_event)

    task = asyncio.create_task(run(settings))
    await asyncio.wait_for(polling_started.wait(), timeout=5)
    captured[0].set()
    await asyncio.wait_for(task, timeout=5)

    assert stop_called.is_set()
    assert not application.scheduler.running
    assert _session_closed(application.bot)


async def test_owner_gets_the_owner_role_on_start(tmp_path):
    """Спека `bot-core`: владелец из конфигурации получает роль при запуске."""
    from app.core.db import create_session_factory
    from app.models import UserRole
    from app.services.users import UserService

    application = build_application(await prepared_settings(tmp_path))
    try:
        await application.start()
        factory = create_session_factory(application.engine)
        async with factory() as session:
            owner = await UserService(session).get(1)
        assert owner.role is UserRole.OWNER
    finally:
        await application.shutdown()


def test_bad_token_gives_a_clear_message(monkeypatch, tmp_path, capsys):
    """Отклонённый Telegram токен — не трассировка, а внятная строка."""
    from aiogram.exceptions import TelegramUnauthorizedError
    from aiogram.methods import GetMe

    monkeypatch.setenv("BOT_TOKEN", "123:fake")
    monkeypatch.setenv("OWNER_ID", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "quizbot.sqlite3"))
    monkeypatch.chdir(tmp_path)

    def explode(coroutine):
        coroutine.close()  # иначе останется незапущенная корутина
        raise TelegramUnauthorizedError(method=GetMe(), message="Unauthorized")

    monkeypatch.setattr("app.main.asyncio.run", explode)

    assert main() == 2
    error = capsys.readouterr().err
    assert "BOT_TOKEN" in error
    assert "Traceback" not in error
