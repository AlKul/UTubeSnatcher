from utube_snatcher.bot import _human_bytes, _stats_days


def test_stats_days():
    assert _stats_days("/stats") == 7
    assert _stats_days("/stats 30d") == 30
    assert _stats_days("/stats invalid") == 7
    assert _stats_days("/stats 9999") == 365


def test_human_bytes():
    assert _human_bytes(0) == "0.0 Б"
    assert _human_bytes(1024) == "1.0 КБ"
    assert _human_bytes(5 * 1024 * 1024) == "5.0 МБ"
