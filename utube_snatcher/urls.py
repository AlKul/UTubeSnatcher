from __future__ import annotations

from urllib.parse import parse_qs, urlparse

SUPPORTED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def extract_youtube_id(value: str) -> str | None:
    """Extract a canonical 11-character YouTube video id from a URL."""
    candidate = value.strip()
    if not candidate:
        return None

    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    host = parsed.hostname.lower() if parsed.hostname else ""
    if host not in SUPPORTED_HOSTS:
        return None

    video_id: str | None = None
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/", 1)[0]
    elif parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [None])[0]
    elif parsed.path.startswith(("/shorts/", "/embed/", "/live/")):
        parts = parsed.path.strip("/").split("/")
        video_id = parts[1] if len(parts) > 1 else None

    if (
        video_id
        and len(video_id) == 11
        and all(char.isalnum() or char in "_-" for char in video_id)
    ):
        return video_id
    return None


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"
