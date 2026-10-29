"""TikTok link download: link detection, titles, errors, and cancel (no network)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest

from notirua.core.errors import (
    Cancelled,
    DownloadNetworkError,
    UnsupportedLinkError,
    VideoDownloadError,
    VideoUnavailableError,
)
from notirua.core.fetch import (
    download_audio,
    find_tiktok_url,
    is_tiktok_url,
    video_title,
)
from notirua.core.progress import CancelToken

URL = "https://www.tiktok.com/@name/video/6718335390845095173"


class FakeYdl:
    """Stands in for yt_dlp.YoutubeDL: writes a file and reports progress."""

    error: Exception | None = None
    info: ClassVar[dict[str, Any]] = {
        "title": "봄날 #fyp #음악",
        "track": "Spring Day",
        "artist": "BTS",
    }

    def __init__(self, options: dict[str, Any]) -> None:
        self.options = options

    def __enter__(self) -> FakeYdl:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def extract_info(self, url: str, download: bool) -> dict[str, Any]:
        assert download
        if self.error is not None:
            raise self.error
        target = Path(self.options["outtmpl"].replace("%(ext)s", "mp4"))
        target.write_bytes(b"video")
        for hook in self.options["progress_hooks"]:
            hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
        return {**self.info, "requested_downloads": [{"filepath": str(target)}]}


@pytest.mark.parametrize(
    "url",
    [
        URL,
        "https://vm.tiktok.com/ZMabc123/",
        "http://m.tiktok.com/v/1.html",
        "https://www.tiktok.com/t/ZT8abc/",
    ],
)
def test_tiktok_links_are_accepted(url: str) -> None:
    assert is_tiktok_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=1",
        "https://nottiktok.com/@a/video/1",
        "https://tiktok.com.evil.example/@a/video/1",
        "ftp://tiktok.com/x",
        "tiktok.com/@a/video/1",
        "",
    ],
)
def test_other_links_are_refused(url: str) -> None:
    assert not is_tiktok_url(url)


def test_link_is_found_inside_a_share_message() -> None:
    text = f"봄날 노래 좋아요 👉 {URL}. 꼭 들어보세요"
    assert find_tiktok_url(text) == URL
    assert find_tiktok_url("see https://example.com/a") is None


def test_title_prefers_the_song_over_the_caption() -> None:
    assert video_title({"title": "caption #a", "track": "Spring Day", "artist": "BTS"}) == (
        "BTS - Spring Day"
    )
    assert video_title({"title": "내 춤 #fyp #dance", "track": "original sound - me"}) == "내 춤"
    assert video_title({"title": "x" * 200}) == "x" * 80
    assert video_title({}) is None


def test_download_returns_file_and_title(tmp_path: Path) -> None:
    seen: list[float] = []
    got = download_audio(f"look: {URL}", tmp_path / "w", progress=seen.append, ydl_factory=FakeYdl)
    assert got.path == tmp_path / "w" / "tiktok.mp4"
    assert got.path.read_bytes() == b"video"
    assert got.title == "BTS - Spring Day"
    assert seen[0] == 0.5 and seen[-1] == 1.0


def test_download_rejects_other_sites_without_network(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedLinkError):
        download_audio("https://www.youtube.com/watch?v=1", tmp_path, ydl_factory=FakeYdl)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Video unavailable. This video is private", VideoUnavailableError),
        ("Unable to download webpage: timed out", DownloadNetworkError),
        ("Unsupported URL: https://x", UnsupportedLinkError),
        ("something odd", VideoDownloadError),
    ],
)
def test_failures_are_explained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, message: str, expected: type[Exception]
) -> None:
    monkeypatch.setattr(FakeYdl, "error", RuntimeError(message))
    with pytest.raises(expected) as caught:
        download_audio(URL, tmp_path, ydl_factory=FakeYdl)
    assert type(caught.value) is expected
    assert caught.value.user_message()


def test_cancel_stops_the_download(tmp_path: Path) -> None:
    cancel = CancelToken()
    cancel.cancel()
    with pytest.raises(Cancelled):
        download_audio(URL, tmp_path, cancel=cancel, ydl_factory=FakeYdl)
