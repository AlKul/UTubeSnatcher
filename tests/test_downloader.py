from pathlib import Path

import pytest

from utube_snatcher.downloader import FileTooLargeError, _find_output


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
