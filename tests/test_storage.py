import pytest

from utube_snatcher.storage import LimitReachedError, UsageStorage


def test_storage_tracks_users_and_downloads(tmp_path):
    storage = UsageStorage(tmp_path / "usage.sqlite3")
    storage.initialize()
    storage.upsert_user(42, "alex", "Alex")

    success_id = storage.start_download(42, "alex", "dQw4w9WgXcQ", "video")
    storage.finish_download(
        success_id,
        "success",
        bytes_sent=1024,
        duration_ms=250,
    )
    failed_id = storage.start_download(42, "alex", "abcdefghijk", "audio")
    storage.finish_download(
        failed_id,
        "download_error",
        duration_ms=100,
        error_code="DownloadError",
    )

    stats = storage.stats(7)
    assert stats.users == 1
    assert stats.downloads == 2
    assert stats.successful == 1
    assert stats.failed == 1
    assert stats.audio == 1
    assert stats.video == 1
    assert stats.bytes_sent == 1024
    assert stats.top_users == (("alex", 1),)


def test_storage_updates_changed_username(tmp_path):
    storage = UsageStorage(tmp_path / "usage.sqlite3")
    storage.initialize()
    storage.upsert_user(42, "old_name", "Alex")
    storage.upsert_user(42, "new_name", "Alex")

    event_id = storage.start_download(42, "new_name", "dQw4w9WgXcQ", "audio")
    storage.finish_download(event_id, "success")

    assert storage.stats().top_users == (("new_name", 1),)


def test_storage_accepts_user_without_username(tmp_path):
    storage = UsageStorage(tmp_path / "usage.sqlite3")
    storage.initialize()
    storage.upsert_user(99, None, "No Username")

    event_id = storage.start_download(99, None, "dQw4w9WgXcQ", "video")
    storage.finish_download(event_id, "success")

    assert storage.stats().top_users == (("id:99", 1),)


def test_storage_enforces_daily_limit_atomically(tmp_path):
    storage = UsageStorage(tmp_path / "usage.sqlite3")
    storage.initialize()
    storage.upsert_user(42, "alex", "Alex")

    storage.start_download(42, "alex", "dQw4w9WgXcQ", "video", daily_limit=1)

    with pytest.raises(LimitReachedError):
        storage.start_download(42, "alex", "abcdefghijk", "audio", daily_limit=1)


def test_storage_tracks_plan_block_and_maintenance(tmp_path):
    storage = UsageStorage(tmp_path / "usage.sqlite3")
    storage.initialize()
    storage.upsert_user(42, "alex", "Alex")

    assert storage.set_plan(42, "premium")
    assert storage.set_blocked(42, True)
    access = storage.user_access(42, free_limit=5, premium_limit=100)
    assert access.plan == "premium"
    assert access.is_blocked is True
    assert access.daily_limit == 100

    assert storage.maintenance_enabled() is False
    storage.set_maintenance(True)
    assert storage.maintenance_enabled() is True
