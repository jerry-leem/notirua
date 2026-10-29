"""Fetch the sound of a TikTok video by its link, so it can be turned into sheet music.

Only public TikTok links are accepted. The video is saved to a work folder and
then read like any other video file (decode.py); nothing is kept after the job.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from notirua.core.errors import (
    Cancelled,
    DownloadNetworkError,
    UnsupportedLinkError,
    VideoDownloadError,
    VideoUnavailableError,
)
from notirua.core.progress import CancelToken

log = logging.getLogger(__name__)

TIKTOK_HOSTS = ("tiktok.com", "tiktokv.com", "tiktokcdn.com")
MAX_DOWNLOAD_BYTES = 300 * 1024 * 1024
_URL = re.compile(r"https?://[^\s<>\"'“”‘’]+", re.IGNORECASE)
_HASHTAG = re.compile(r"\s*[#＃]\S+")
_GENERIC_SOUND = re.compile(
    r"^(original sound|오리지널 사운드|원본 사운드|オリジナル楽曲)", re.IGNORECASE
)
_UNAVAILABLE_HINTS = ("private", "unavailable", "removed", "not available", "deleted", "login")
_NETWORK_HINTS = ("unable to download", "timed out", "connection", "resolve", "network", "proxy")

# progress callback: fraction in 0..1
Progress = Callable[[float], None]


@dataclass(frozen=True)
class Downloaded:
    path: Path
    title: str | None


def is_tiktok_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme in ("http", "https") and any(
        host == h or host.endswith("." + h) for h in TIKTOK_HOSTS
    )


def find_tiktok_url(text: str) -> str | None:
    """The TikTok link inside ``text``, which may be a whole share message."""
    for match in _URL.finditer(text):
        candidate = match.group(0).rstrip(".,;)]}>")
        if is_tiktok_url(candidate):
            return candidate
    return None


def _clean(text: object, limit: int = 80) -> str | None:
    if not isinstance(text, str):
        return None
    cleaned = " ".join(_HASHTAG.sub("", text).split())
    return cleaned[:limit].rstrip() or None


def video_title(info: dict[str, Any]) -> str | None:
    """A song-like name: the sound's title if it has one, else the caption."""
    track = _clean(info.get("track"))
    if track and not _GENERIC_SOUND.match(track):
        artist = _clean(info.get("artist") or ", ".join(info.get("artists") or []))
        return f"{artist} - {track}" if artist else track
    return _clean(info.get("title")) or track


def _classify(message: str) -> VideoDownloadError:
    lowered = message.lower()
    if "unsupported url" in lowered:
        return UnsupportedLinkError(message)
    if any(h in lowered for h in _UNAVAILABLE_HINTS):
        return VideoUnavailableError(message)
    if any(h in lowered for h in _NETWORK_HINTS):
        return DownloadNetworkError(message)
    return VideoDownloadError(message)


def download_audio(
    url: str,
    dest_dir: Path,
    *,
    progress: Progress | None = None,
    cancel: CancelToken | None = None,
    ydl_factory: Callable[[dict[str, Any]], Any] | None = None,
) -> Downloaded:
    """Download the video behind ``url`` into ``dest_dir`` and return its file and title."""
    link = find_tiktok_url(url)
    if link is None:
        raise UnsupportedLinkError(url)
    dest_dir.mkdir(parents=True, exist_ok=True)

    def hook(status: dict[str, Any]) -> None:
        if cancel is not None:
            cancel.raise_if_cancelled()
        if progress is None or status.get("status") != "downloading":
            return
        total = status.get("total_bytes") or status.get("total_bytes_estimate")
        if total:
            progress(min(1.0, float(status.get("downloaded_bytes") or 0) / float(total)))

    options: dict[str, Any] = {
        "format": "bestaudio/best",
        "outtmpl": str(dest_dir / "tiktok.%(ext)s"),  # ASCII name: titles can be anything
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 20,
        "retries": 3,
        "max_filesize": MAX_DOWNLOAD_BYTES,
        "progress_hooks": [hook],
    }
    if ydl_factory is None:
        import yt_dlp

        ydl_factory = yt_dlp.YoutubeDL
    try:
        with ydl_factory(options) as ydl:
            info = ydl.extract_info(link, download=True)
            if info is None:
                raise VideoUnavailableError("no video information")
            files = [Path(d["filepath"]) for d in info.get("requested_downloads") or []]
            if not files:
                files = [Path(ydl.prepare_filename(info))]
    except Cancelled:
        raise
    except VideoDownloadError:
        raise
    except Exception as exc:
        if cancel is not None and cancel.cancelled:
            raise Cancelled() from exc
        log.info("download failed: %s", exc)
        raise _classify(str(exc)) from exc
    if cancel is not None:
        cancel.raise_if_cancelled()
    path = next((f for f in files if f.is_file()), None)
    if path is None:
        raise VideoDownloadError("downloaded file is missing")
    if progress is not None:
        progress(1.0)
    return Downloaded(path=path, title=video_title(info))
