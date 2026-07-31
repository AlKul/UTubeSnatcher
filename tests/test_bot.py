from utube_snatcher.bot import (
    _command_argument,
    _format_time,
    _human_bytes,
    _human_duration,
    _parse_clip_range,
    _stats_days,
)


def test_stats_days():
    assert _stats_days("/stats") == 7
    assert _stats_days("/stats 30d") == 30
    assert _stats_days("/stats invalid") == 7
    assert _stats_days("/stats 9999") == 365


def test_human_bytes():
    assert _human_bytes(0) == "0.0 Б"
    assert _human_bytes(1024) == "1.0 КБ"
    assert _human_bytes(5 * 1024 * 1024) == "5.0 МБ"


def test_command_argument():
    assert _command_argument("/maintenance") == ""
    assert _command_argument("/maintenance ON") == "on"


def test_parse_clip_range_accepts_common_formats():
    assert _parse_clip_range("01:20–02:45") == (80, 165)
    assert _parse_clip_range("с 1:20 до 2:45") == (80, 165)
    assert _parse_clip_range("90-150") == (90, 150)
    assert _parse_clip_range("00:01:20 00:02:45") == (80, 165)


def test_parse_clip_range_rejects_invalid_or_excessive_ranges():
    assert _parse_clip_range("02:45-01:20") is None
    assert _parse_clip_range("1:99-2:30") is None
    assert _parse_clip_range("0-4001") is None
    assert _parse_clip_range("только 01:20") is None


def test_clip_time_labels():
    assert _format_time(80) == "01:20"
    assert _format_time(3723) == "01:02:03"
    assert _human_duration(85) == "1 мин 25 сек"
