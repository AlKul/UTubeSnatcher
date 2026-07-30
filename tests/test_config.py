import pytest

from utube_snatcher.config import Settings


def test_settings_require_token(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.setattr("utube_snatcher.config.load_dotenv", lambda: None)
    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        Settings.from_env()


def test_settings_parse_limits(monkeypatch):
    monkeypatch.setattr("utube_snatcher.config.load_dotenv", lambda: None)
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("MAX_UPLOAD_MB", "42")
    monkeypatch.setenv("DOWNLOAD_TIMEOUT_SECONDS", "15")
    settings = Settings.from_env()
    assert settings.bot_token == "test-token"
    assert settings.max_upload_bytes == 42 * 1024 * 1024
    assert settings.download_timeout_seconds == 15
