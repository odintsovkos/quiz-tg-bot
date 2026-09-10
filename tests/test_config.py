import pytest

from app.core.config import ConfigError, load_settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for name in (
        "BOT_TOKEN",
        "OWNER_ID",
        "DB_PATH",
        "LOG_LEVEL",
        "DEFAULT_TIMEZONE",
        "MIN_INTERVAL_MINUTES",
        "MAX_INTERVAL_MINUTES",
    ):
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
    assert settings.min_interval_minutes == 5
    assert settings.max_interval_minutes == 24 * 60
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


def test_interval_bounds_are_configurable(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("OWNER_ID", "42")
    monkeypatch.setenv("MIN_INTERVAL_MINUTES", "30")
    monkeypatch.setenv("MAX_INTERVAL_MINUTES", "600")

    settings = load_settings()

    assert settings.min_interval_minutes == 30
    assert settings.max_interval_minutes == 600


def test_lower_interval_bound_above_upper_is_rejected(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("OWNER_ID", "42")
    monkeypatch.setenv("MIN_INTERVAL_MINUTES", "600")
    monkeypatch.setenv("MAX_INTERVAL_MINUTES", "300")

    with pytest.raises(ConfigError) as exc:
        load_settings()

    assert "MAX_INTERVAL_MINUTES" in str(exc.value)


def test_zero_lower_interval_bound_is_rejected(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("OWNER_ID", "42")
    monkeypatch.setenv("MIN_INTERVAL_MINUTES", "0")

    with pytest.raises(ConfigError) as exc:
        load_settings()

    assert "MIN_INTERVAL_MINUTES" in str(exc.value)


def test_upper_interval_bound_above_a_day_is_rejected(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("OWNER_ID", "42")
    monkeypatch.setenv("MAX_INTERVAL_MINUTES", "2880")

    with pytest.raises(ConfigError) as exc:
        load_settings()

    assert "MAX_INTERVAL_MINUTES" in str(exc.value)
