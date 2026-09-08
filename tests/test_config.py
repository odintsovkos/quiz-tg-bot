import pytest

from app.core.config import ConfigError, load_settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for name in ("BOT_TOKEN", "OWNER_ID", "DB_PATH", "LOG_LEVEL", "DEFAULT_TIMEZONE"):
        monkeypatch.delenv(name, raising=False)
    # .env из корня репозитория не должен влиять на тесты
    monkeypatch.chdir(tmp_path)


def test_missing_bot_token_names_the_parameter(monkeypatch):
    monkeypatch.setenv("OWNER_ID", "1")

    with pytest.raises(ConfigError) as exc:
        load_settings()

    assert "BOT_TOKEN" in str(exc.value)


def test_missing_owner_id_names_the_parameter(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:abc")

    with pytest.raises(ConfigError) as exc:
        load_settings()

    assert "OWNER_ID" in str(exc.value)


def test_defaults_are_applied(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("OWNER_ID", "42")

    settings = load_settings()

    assert settings.owner_id == 42
    assert settings.log_level == "INFO"
    assert settings.default_timezone == "Europe/Moscow"
    assert settings.database_url.startswith("sqlite+aiosqlite:///")


def test_invalid_log_level_is_rejected(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("OWNER_ID", "42")
    monkeypatch.setenv("LOG_LEVEL", "CHATTY")

    with pytest.raises(ConfigError) as exc:
        load_settings()

    assert "LOG_LEVEL" in str(exc.value)


def test_invalid_timezone_is_rejected(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("OWNER_ID", "42")
    monkeypatch.setenv("DEFAULT_TIMEZONE", "Mars/Olympus")

    with pytest.raises(ConfigError) as exc:
        load_settings()

    assert "DEFAULT_TIMEZONE" in str(exc.value)
