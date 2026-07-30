from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    max_upload_bytes: int = 49 * 1024 * 1024
    download_timeout_seconds: int = 600
    log_level: str = "INFO"
    database_path: Path = Path("data/utube_snatcher.sqlite3")
    admin_user_ids: frozenset[int] = frozenset()
    require_username: bool = False
    free_daily_limit: int = 5
    premium_daily_limit: int = 100
    health_host: str = "0.0.0.0"
    health_port: int = 8080

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError(
                "BOT_TOKEN is not set. Copy .env.example to .env and add a new "
                "token issued by @BotFather."
            )

        max_upload_mb = _positive_int("MAX_UPLOAD_MB", 49)
        timeout = _positive_int("DOWNLOAD_TIMEOUT_SECONDS", 600)
        return cls(
            bot_token=token,
            max_upload_bytes=max_upload_mb * 1024 * 1024,
            download_timeout_seconds=timeout,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            database_path=Path(os.getenv("DATABASE_PATH", "data/utube_snatcher.sqlite3")),
            admin_user_ids=_integer_set("ADMIN_USER_IDS"),
            require_username=_boolean("REQUIRE_USERNAME", False),
            free_daily_limit=_positive_int("FREE_DAILY_LIMIT", 5),
            premium_daily_limit=_positive_int("PREMIUM_DAILY_LIMIT", 100),
            health_host=os.getenv("HEALTH_HOST", "0.0.0.0"),
            health_port=_positive_int("PORT", 8080),
        )


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be positive")
    return value


def _integer_set(name: str) -> frozenset[int]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return frozenset()
    try:
        return frozenset(int(item.strip()) for item in raw.split(",") if item.strip())
    except ValueError as exc:
        raise RuntimeError(f"{name} must contain comma-separated integers") from exc


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be true or false")
