import pytest

from utube_snatcher.config import Settings


def test_settings_require_token(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.setattr("utube_snatcher.config.load_dotenv", lambda: None)
    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        Settings.from_env()


def test_username_is_optional_by_default(monkeypatch):
    monkeypatch.setattr("utube_snatcher.config.load_dotenv", lambda: None)
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.delenv("REQUIRE_USERNAME", raising=False)
    assert Settings.from_env().require_username is False


def test_settings_parse_limits(monkeypatch):
    monkeypatch.setattr("utube_snatcher.config.load_dotenv", lambda: None)
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("MAX_UPLOAD_MB", "42")
    monkeypatch.setenv("DOWNLOAD_TIMEOUT_SECONDS", "15")
    monkeypatch.setenv("ADMIN_USER_IDS", "123, 456")
    monkeypatch.setenv("REQUIRE_USERNAME", "false")
    monkeypatch.setenv("FREE_DAILY_LIMIT", "7")
    monkeypatch.setenv("PREMIUM_DAILY_LIMIT", "200")
    monkeypatch.setenv("PORT", "9000")
    settings = Settings.from_env()
    assert settings.bot_token == "test-token"
    assert settings.max_upload_bytes == 42 * 1024 * 1024
    assert settings.download_timeout_seconds == 15
    assert settings.admin_user_ids == frozenset({123, 456})
    assert settings.require_username is False
    assert settings.free_daily_limit == 7
    assert settings.premium_daily_limit == 200
    assert settings.health_port == 9000


def test_settings_reject_invalid_admin_id(monkeypatch):
    monkeypatch.setattr("utube_snatcher.config.load_dotenv", lambda: None)
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("ADMIN_USER_IDS", "not-a-number")
    with pytest.raises(RuntimeError, match="ADMIN_USER_IDS"):
        Settings.from_env()
