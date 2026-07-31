from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from yt_dlp import YoutubeDL
from yt_dlp.networking.impersonate import ImpersonateTarget

MediaKind = Literal["audio", "video"]


class DownloadError(RuntimeError):
    pass


class FileTooLargeError(DownloadError):
    pass


class AuthenticationRequiredError(DownloadError):
    pass


class MediaUnavailableError(DownloadError):
    pass


class RateLimitedError(DownloadError):
    pass


class GeoRestrictedError(DownloadError):
    pass


ProgressCallback = Callable[[int], None]


@dataclass(frozen=True)
class DownloadedMedia:
    path: Path
    title: str
    kind: MediaKind
    _tempdir: TemporaryDirectory[str]

    def cleanup(self) -> None:
        self._tempdir.cleanup()


async def get_title(url: str) -> str:
    return await asyncio.to_thread(_get_title_sync, url)


async def download_media(
    url: str,
    kind: MediaKind,
    max_bytes: int,
    timeout_seconds: int,
    progress_callback: ProgressCallback | None = None,
    clip_range: tuple[int, int] | None = None,
) -> DownloadedMedia:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                _download_sync,
                url,
                kind,
                max_bytes,
                progress_callback,
                clip_range,
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        raise DownloadError("Download timed out") from exc


def _base_options() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "restrictfilenames": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "impersonate": ImpersonateTarget(client="chrome"),
    }


def _get_title_sync(url: str) -> str:
    options = _base_options()
    options["skip_download"] = True
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise _classified_error(exc) from exc
    return str(info.get("title") or "YouTube video")


def _download_sync(
    url: str,
    kind: MediaKind,
    max_bytes: int,
    progress_callback: ProgressCallback | None = None,
    clip_range: tuple[int, int] | None = None,
) -> DownloadedMedia:
    tempdir = TemporaryDirectory(prefix="utube-snatcher-")
    output_template = str(Path(tempdir.name) / "%(title).120B-%(id)s.%(ext)s")
    options = _base_options()
    options.update(
        {
            "outtmpl": output_template,
            "max_filesize": max_bytes,
        }
    )
    if progress_callback is not None:
        options["progress_hooks"] = [_progress_hook(progress_callback)]
    if clip_range is not None:
        start, end = clip_range
        options.update(
            {
                "download_sections": [f"*{start}-{end}"],
                "force_keyframes_at_cuts": True,
            }
        )

    if kind == "audio":
        options.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "128",
                    }
                ],
            }
        )
    else:
        limit = max_bytes
        options.update(
            {
                "format": (
                    f"best[ext=mp4][filesize<={limit}]/best[filesize<={limit}]/best[ext=mp4]/best"
                ),
                "merge_output_format": "mp4",
            }
        )

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            path = _find_output(Path(tempdir.name), ydl.prepare_filename(info), kind)
    except FileTooLargeError:
        tempdir.cleanup()
        raise
    except Exception as exc:
        tempdir.cleanup()
        raise _classified_error(exc) from exc

    if path.stat().st_size > max_bytes:
        tempdir.cleanup()
        raise FileTooLargeError("The smallest available file is still too large for Telegram.")

    return DownloadedMedia(
        path=path,
        title=str(info.get("title") or path.stem),
        kind=kind,
        _tempdir=tempdir,
    )


def _find_output(directory: Path, prepared_filename: str, kind: MediaKind) -> Path:
    prepared = Path(prepared_filename)
    candidates = list(directory.iterdir())
    if kind == "audio":
        mp3_files = [path for path in candidates if path.suffix.lower() == ".mp3"]
        if mp3_files:
            return mp3_files[0]
    elif prepared.exists():
        return prepared

    media_files = [
        path
        for path in candidates
        if path.is_file() and path.suffix.lower() not in {".part", ".ytdl"}
    ]
    if not media_files:
        raise FileTooLargeError("yt-dlp did not produce a file within the configured size limit")
    return max(media_files, key=lambda path: path.stat().st_mtime)


def _progress_hook(callback: ProgressCallback):
    def hook(data: dict) -> None:
        if data.get("status") != "downloading":
            return
        downloaded = int(data.get("downloaded_bytes") or 0)
        total = int(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
        if total > 0:
            callback(min(round(downloaded * 100 / total), 100))

    return hook


def _classified_error(exc: Exception) -> DownloadError:
    message = str(exc).lower()
    if any(
        marker in message
        for marker in (
            "login required",
            "sign in",
            "cookies",
            "private video",
            "private account",
        )
    ):
        return AuthenticationRequiredError("The source requires authentication")
    if any(
        marker in message
        for marker in (
            "429",
            "too many requests",
            "rate limit",
            "ip address is blocked",
        )
    ):
        return RateLimitedError("The source temporarily limited requests")
    if any(marker in message for marker in ("geo", "not available in your country")):
        return GeoRestrictedError("The media is unavailable in this region")
    if any(
        marker in message
        for marker in (
            "video unavailable",
            "post is unavailable",
            "not available",
            "removed",
            "unsupported url",
            "no video formats",
        )
    ):
        return MediaUnavailableError("The media is unavailable or unsupported")
    return DownloadError(f"Download failed: {exc}")
