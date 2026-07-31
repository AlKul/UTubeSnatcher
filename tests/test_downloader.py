from pathlib import Path

import pytest

from utube_snatcher.downloader import (
    AuthenticationRequiredError,
    FileTooLargeError,
    MediaUnavailableError,
    RateLimitedError,
    _classified_error,
    _find_output,
    _progress_hook,
)


def test_find_output_reports_missing_file_as_size_error(tmp_path):
    with pytest.raises(FileTooLargeError):
        _find_output(tmp_path, str(tmp_path / "missing.mp4"), "video")


def test_find_output_prefers_converted_mp3(tmp_path):
    source = tmp_path / "audio.webm"
    converted = tmp_path / "audio.mp3"
    source.write_bytes(b"source")
    converted.write_bytes(b"converted")

    assert _find_output(tmp_path, str(source), "audio") == converted


def test_find_output_uses_prepared_video_path(tmp_path):
    video = Path(tmp_path / "video.mp4")
    video.write_bytes(b"video")

    assert _find_output(tmp_path, str(video), "video") == video


def test_progress_hook_reports_percentage():
    values = []
    hook = _progress_hook(values.append)
    hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
    hook({"status": "finished", "downloaded_bytes": 100, "total_bytes": 100})
    assert values == [50]


def test_clip_options_are_forwarded_to_ytdlp(monkeypatch, tmp_path):
    captured = {}

    class FakeYdl:
        def __init__(self, options):
            captured.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def extract_info(self, url, download):
            output = tmp_path / "clip.mp4"
            output.write_bytes(b"clip")
            return {"title": "Clip", "id": "id", "ext": "mp4"}

        def prepare_filename(self, info):
            return str(tmp_path / "clip.mp4")

    monkeypatch.setattr("utube_snatcher.downloader.YoutubeDL", FakeYdl)
    from utube_snatcher.downloader import _download_sync

    media = _download_sync(
        "https://example.test/video",
        "video",
        1024,
        clip_range=(80, 165),
    )
    try:
        assert captured["download_sections"] == ["*80-165"]
        assert captured["force_keyframes_at_cuts"] is True
    finally:
        media.cleanup()


@pytest.mark.parametrize(
    ("message", "error_type"),
    [
        ("Login required, use cookies", AuthenticationRequiredError),
        ("HTTP Error 429: Too Many Requests", RateLimitedError),
        ("Video unavailable", MediaUnavailableError),
    ],
)
def test_classifies_download_errors(message, error_type):
    assert isinstance(_classified_error(RuntimeError(message)), error_type)
