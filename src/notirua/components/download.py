"""Resumable, verified HTTP downloads with pause/cancel and proxy support (SPEC 7.2)."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from notirua.core.errors import (
    ChecksumMismatchError,
    DownloadError,
    PermissionDeniedError,
)
from notirua.core.progress import CancelToken

log = logging.getLogger(__name__)

CHUNK = 256 * 1024
TIMEOUT_S = 30


@dataclass(frozen=True)
class DownloadStatus:
    received: int
    total: int
    bytes_per_s: float
    eta_seconds: float | None


class PauseToken:
    def __init__(self) -> None:
        self._resume = threading.Event()
        self._resume.set()

    def pause(self) -> None:
        self._resume.clear()

    def resume(self) -> None:
        self._resume.set()

    @property
    def paused(self) -> bool:
        return not self._resume.is_set()

    def wait(self, timeout: float) -> bool:
        return self._resume.wait(timeout)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for block in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _opener() -> urllib.request.OpenerDirector:
    # ProxyHandler() reads HTTP(S)_PROXY / system proxy settings.
    return urllib.request.build_opener(urllib.request.ProxyHandler())


def download(
    url: str,
    dest: Path,
    *,
    expected_size: int,
    sha256: str,
    progress: Callable[[DownloadStatus], None] | None = None,
    cancel: CancelToken | None = None,
    pause: PauseToken | None = None,
    opener: urllib.request.OpenerDirector | None = None,
) -> Path:
    """Download ``url`` to ``dest`` via ``dest.part``, resuming partial files.

    The final file only appears after its SHA-256 matches. A mismatched file is
    deleted so the next attempt starts clean.
    """
    part = dest.with_name(dest.name + ".part")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise PermissionDeniedError(str(exc)) from exc

    if dest.is_file() and dest.stat().st_size == expected_size and sha256_file(dest) == sha256:
        return dest

    have = part.stat().st_size if part.is_file() else 0
    if have > expected_size:
        part.unlink()
        have = 0
    request = urllib.request.Request(url, headers={"User-Agent": "Notirua-components/1"})
    if have:
        request.add_header("Range", f"bytes={have}-")
    started = time.monotonic()
    start_bytes = have
    try:
        response = (opener or _opener()).open(request, timeout=TIMEOUT_S)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and have == expected_size:
            response = None
        else:
            raise DownloadError(f"HTTP {exc.code} for {url}") from exc
    except (TimeoutError, urllib.error.URLError, OSError) as exc:
        raise DownloadError(f"{type(exc).__name__}: {exc}") from exc

    if response is not None:
        with response:
            status = getattr(response, "status", 200)
            mode = "ab" if have and status == 206 else "wb"
            if mode == "wb":
                have = 0
                start_bytes = 0
            try:
                fp = part.open(mode)
            except PermissionError as exc:
                raise PermissionDeniedError(str(exc)) from exc
            with fp:
                while True:
                    if cancel is not None:
                        cancel.raise_if_cancelled()
                    if pause is not None and pause.paused:
                        fp.flush()
                        while not pause.wait(0.25):
                            if cancel is not None:
                                cancel.raise_if_cancelled()
                        started = time.monotonic()
                        start_bytes = have
                    try:
                        block = response.read(CHUNK)
                    except (TimeoutError, OSError) as exc:
                        raise DownloadError(f"connection lost: {exc}") from exc
                    if not block:
                        break
                    fp.write(block)
                    have += len(block)
                    if progress is not None:
                        elapsed = max(1e-6, time.monotonic() - started)
                        speed = (have - start_bytes) / elapsed
                        eta = (expected_size - have) / speed if speed > 0 and elapsed > 1 else None
                        progress(DownloadStatus(have, expected_size, speed, eta))

    if have != expected_size:
        raise DownloadError(f"incomplete download: {have} of {expected_size} bytes")
    actual = sha256_file(part)
    if actual != sha256:
        part.unlink(missing_ok=True)
        raise ChecksumMismatchError(f"expected {sha256}, got {actual}")
    part.replace(dest)
    return dest
