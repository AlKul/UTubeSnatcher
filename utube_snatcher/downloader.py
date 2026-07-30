from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from yt_dlp import YoutubeDL

MediaKind = Literal["audio", "video"]


class DownloadError(RuntimeError):
    pass


class FileTooLargeError(DownloadError):
    pass


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
) -> DownloadedMedia:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_download_sync, url, kind, max_bytes),
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
    }


def _get_title_sync(url: str) -> str:
    options = _base_options()
    options["skip_download"] = True
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise DownloadError(f"Could not read video information: {exc}") from exc
    return str(info.get("title") or "YouTube video")


def _download_sync(url: str, kind: MediaKind, max_bytes: int) -> DownloadedMedia:
    tempdir = TemporaryDirectory(prefix="utube-snatcher-")
    output_template = str(Path(tempdir.name) / "%(title).120B-%(id)s.%(ext)s")
    options = _base_options()
    options.update(
        {
            "outtmpl": output_template,
            "max_filesize": max_bytes,
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
        raise DownloadError(f"Download failed: {exc}") from exc

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
