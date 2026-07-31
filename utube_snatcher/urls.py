from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse, urlunparse

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}
INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com"}
TIKTOK_HOSTS = {
    "tiktok.com",
    "www.tiktok.com",
    "m.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
}
VK_HOSTS = {"vk.com", "www.vk.com", "m.vk.com", "vkvideo.ru", "www.vkvideo.ru"}


@dataclass(frozen=True)
class SourceRef:
    platform: str
    media_id: str
    url: str
    display_name: str


def parse_source_url(value: str) -> SourceRef | None:
    candidate = value.strip()
    if not candidate or any(char.isspace() for char in candidate):
        return None
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    host = parsed.hostname.lower()

    if host in YOUTUBE_HOSTS:
        video_id = _youtube_id(parsed)
        if video_id:
            return SourceRef(
                "youtube",
                video_id,
                canonical_url(video_id),
                "YouTube",
            )
        return None

    parts = [part for part in parsed.path.split("/") if part]
    if host in INSTAGRAM_HOSTS:
        if len(parts) >= 2 and parts[0].lower() in {"p", "reel", "reels", "tv"}:
            media_id = _safe_id(parts[1])
            if media_id:
                return SourceRef(
                    "instagram",
                    media_id,
                    _clean_url(parsed),
                    "Instagram",
                )
        return None

    if host in TIKTOK_HOSTS:
        match = re.search(r"/video/(\d+)", parsed.path)
        media_id = match.group(1) if match else _short_id(candidate)
        if match or host in {"vm.tiktok.com", "vt.tiktok.com"} or parsed.path.startswith("/t/"):
            return SourceRef("tiktok", media_id, _clean_url(parsed), "TikTok")
        return None

    if host in VK_HOSTS:
        match = re.search(r"(?:video|clip)(-?\d+_\d+)", f"{parsed.path}?{parsed.query}")
        if not match:
            match = re.search(r"wall(-?\d+_\d+)", parsed.path)
        if match:
            return SourceRef("vk", match.group(0), _clean_url(parsed, keep_query=True), "VK")
        return None

    return None


def extract_youtube_id(value: str) -> str | None:
    source = parse_source_url(value)
    return source.media_id if source and source.platform == "youtube" else None


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _youtube_id(parsed) -> str | None:
    host = parsed.hostname.lower()
    video_id: str | None = None
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/", 1)[0]
    elif parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [None])[0]
    elif parsed.path.startswith(("/shorts/", "/embed/", "/live/")):
        parts = parsed.path.strip("/").split("/")
        video_id = parts[1] if len(parts) > 1 else None
    return video_id if video_id and re.fullmatch(r"[\w-]{11}", video_id) else None


def _safe_id(value: str) -> str | None:
    return value if re.fullmatch(r"[\w-]{3,80}", value) else None


def _short_id(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _clean_url(parsed, *, keep_query: bool = False) -> str:
    return urlunparse(
        (
            "https",
            parsed.hostname.lower(),
            parsed.path.rstrip("/"),
            "",
            parsed.query if keep_query else "",
            "",
        )
    )
