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
