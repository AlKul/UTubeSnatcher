from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    max_upload_bytes: int = 49 * 1024 * 1024
    download_timeout_seconds: int = 600
    log_level: str = "INFO"

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
