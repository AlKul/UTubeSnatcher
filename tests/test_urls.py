import pytest

from utube_snatcher.urls import canonical_url, extract_youtube_id, parse_source_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=10", "dQw4w9WgXcQ"),
        ("youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://example.com/watch?v=dQw4w9WgXcQ", None),
        ("not a url", None),
    ],
)
def test_extract_youtube_id(url, expected):
    assert extract_youtube_id(url) == expected


def test_canonical_url():
    assert canonical_url("dQw4w9WgXcQ") == ("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


@pytest.mark.parametrize(
    ("url", "platform", "media_id"),
    [
        ("https://www.instagram.com/reel/ABC_def12/", "instagram", "ABC_def12"),
        (
            "https://www.tiktok.com/@creator/video/7521234567890123456",
            "tiktok",
            "7521234567890123456",
        ),
        ("https://vm.tiktok.com/ZMshort/", "tiktok", None),
        ("https://vk.com/video-123_456", "vk", "video-123_456"),
        ("https://vk.com/wall-123_456", "vk", "wall-123_456"),
    ],
)
def test_parse_social_source(url, platform, media_id):
    source = parse_source_url(url)
    assert source is not None
    assert source.platform == platform
    if media_id is not None:
        assert source.media_id == media_id


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/video/123",
        "https://instagram.com/some-profile",
        "https://tiktok.com/@creator",
        "https://vk.com/feed",
    ],
)
def test_rejects_unsupported_social_urls(url):
    assert parse_source_url(url) is None
