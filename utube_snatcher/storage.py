from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class UsageStats:
    users: int
    downloads: int
    successful: int
    failed: int
    audio: int
    video: int
    bytes_sent: int
    top_users: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class UserAccess:
    plan: str
    is_blocked: bool
    used_today: int
    daily_limit: int

    @property
    def remaining(self) -> int:
        return max(self.daily_limit - self.used_today, 0)


class LimitReachedError(RuntimeError):
    pass


class UsageStorage:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    plan TEXT NOT NULL DEFAULT 'free',
                    is_blocked INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS download_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    video_id TEXT NOT NULL,
                    media_kind TEXT NOT NULL CHECK(media_kind IN ('audio', 'video')),
                    status TEXT NOT NULL,
                    bytes_sent INTEGER,
                    duration_ms INTEGER,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    finished_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );

                CREATE INDEX IF NOT EXISTS idx_download_events_created_at
                    ON download_events(created_at);
                CREATE INDEX IF NOT EXISTS idx_download_events_user_id
                    ON download_events(user_id);

                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            connection.execute(
                """
                UPDATE download_events
                SET status = 'interrupted', error_code = 'process_restart',
                    finished_at = ?
                WHERE status = 'started'
                """,
                (_now(),),
            )

    def upsert_user(
        self,
        user_id: int,
        username: str | None,
        full_name: str,
    ) -> None:
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO users (
                    user_id, username, full_name, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    full_name = excluded.full_name,
                    last_seen_at = excluded.last_seen_at
                """,
                (user_id, username, full_name, now, now),
            )

    def start_download(
        self,
        user_id: int,
        username: str | None,
        video_id: str,
        media_kind: str,
        daily_limit: int | None = None,
    ) -> int:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if daily_limit is not None:
                used = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM download_events
                    WHERE user_id = ? AND created_at >= ?
                    """,
                    (user_id, _day_start()),
                ).fetchone()[0]
                if int(used) >= daily_limit:
                    raise LimitReachedError("Daily download limit reached")
            cursor = connection.execute(
                """
                INSERT INTO download_events (
                    user_id, username, video_id, media_kind, status, created_at
                ) VALUES (?, ?, ?, ?, 'started', ?)
                """,
                (user_id, username, video_id, media_kind, _now()),
            )
            return int(cursor.lastrowid)

    def user_access(
        self,
        user_id: int,
        *,
        free_limit: int,
        premium_limit: int,
    ) -> UserAccess:
        with self._connect() as connection:
            user = connection.execute(
                "SELECT plan, is_blocked FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            used = connection.execute(
                """
                SELECT COUNT(*)
                FROM download_events
                WHERE user_id = ? AND created_at >= ?
                """,
                (user_id, _day_start()),
            ).fetchone()[0]
        plan = str(user[0]) if user else "free"
        is_blocked = bool(user[1]) if user else False
        daily_limit = premium_limit if plan == "premium" else free_limit
        return UserAccess(
            plan=plan,
            is_blocked=is_blocked,
            used_today=int(used),
            daily_limit=daily_limit,
        )

    def set_plan(self, user_id: int, plan: str) -> bool:
        if plan not in {"free", "premium"}:
            raise ValueError("Unknown plan")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET plan = ? WHERE user_id = ?",
                (plan, user_id),
            )
            return cursor.rowcount > 0

    def set_blocked(self, user_id: int, blocked: bool) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET is_blocked = ? WHERE user_id = ?",
                (int(blocked), user_id),
            )
            return cursor.rowcount > 0

    def maintenance_enabled(self) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'maintenance'"
            ).fetchone()
        return bool(row and row[0] == "1")

    def set_maintenance(self, enabled: bool) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO app_settings (key, value)
                VALUES ('maintenance', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                ("1" if enabled else "0",),
            )

    def finish_download(
        self,
        event_id: int,
        status: str,
        *,
        bytes_sent: int | None = None,
        duration_ms: int | None = None,
        error_code: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE download_events
                SET status = ?, bytes_sent = ?, duration_ms = ?,
                    error_code = ?, finished_at = ?
                WHERE id = ?
                """,
                (status, bytes_sent, duration_ms, error_code, _now(), event_id),
            )

    def stats(self, days: int = 7) -> UsageStats:
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(DISTINCT user_id),
                    COUNT(*),
                    SUM(status = 'success'),
                    SUM(status != 'success' AND status != 'started'),
                    SUM(media_kind = 'audio'),
                    SUM(media_kind = 'video'),
                    COALESCE(SUM(bytes_sent), 0)
                FROM download_events
                WHERE created_at >= ?
                """,
                (since,),
            ).fetchone()
            top_rows = connection.execute(
                """
                SELECT
                    COALESCE(MAX(username), 'id:' || user_id),
                    COUNT(*) AS downloads
                FROM download_events
                WHERE created_at >= ? AND status = 'success'
                GROUP BY user_id
                ORDER BY downloads DESC
                LIMIT 5
                """,
                (since,),
            ).fetchall()

        return UsageStats(
            users=int(row[0] or 0),
            downloads=int(row[1] or 0),
            successful=int(row[2] or 0),
            failed=int(row[3] or 0),
            audio=int(row[4] or 0),
            video=int(row[5] or 0),
            bytes_sent=int(row[6] or 0),
            top_users=tuple((str(item[0]), int(item[1])) for item in top_rows),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _day_start() -> str:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
