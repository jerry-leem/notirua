"""Save the audio of a YouTube video as an MP3 file (0.5.0).

Steps (:func:`save_as_mp3`): check the link, read the video's page, download the
best audio stream, and encode it as MP3 at the chosen bit rate. The file is named
after the video's title. yt-dlp does the talking to YouTube; Notirua itself
encodes the MP3 with the LGPL FFmpeg it already bundles, so no ``ffmpeg`` program
is needed.

YouTube's player asks a script challenge before it hands out audio streams; yt-dlp
solves it with a JavaScript runtime (Deno), a small optional component that is
downloaded with the user's consent (``components/manifest.py``).

Only save audio you have the right to use. YouTube's terms of service and
copyright law apply.
"""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse

from notirua import paths
from notirua.core.decode import MAX_DURATION_S, decode
from notirua.core.errors import (
    Cancelled,
    InvalidYoutubeLinkError,
    NotiruaError,
    TooLongError,
    YoutubeBotCheckError,
    YoutubeChangedError,
    YoutubeError,
    YoutubeLiveError,
    YoutubeNetworkError,
    YoutubeRefusedError,
    YoutubeSignInError,
    YoutubeUnavailableError,
)
from notirua.core.mix import write_audio
from notirua.core.progress import CancelToken, ProgressCallback, ProgressReporter, StageSpec
from notirua.i18n import N_

log = logging.getLogger(__name__)

BITRATES = (128, 160, 192, 256, 320)  # kbps, constant bit rate MP3
DEFAULT_BITRATE = 160

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_WATCH_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}
_SHORT_HOSTS = {"youtu.be", "www.youtu.be"}
_ID_FIRST_SEGMENTS = {"shorts", "live", "embed", "v"}
_URL_IN_TEXT = re.compile(
    r"(?:https?://)?(?:[\w-]+\.)*(?:youtube(?:-nocookie)?\.com|youtu\.be)/\S+"
)

STAGES = (
    StageSpec("check", 1.0, N_("Checking the link")),
    StageSpec("download", 6.0, N_("Downloading the audio")),
    StageSpec("convert", 3.0, N_("Making the MP3 file")),
)
DOWNLOADING = N_("Downloading the audio: {received} of {total}")

_FULL_WIDTH = str.maketrans(
    {
        "<": "＜",
        ">": "＞",
        ":": "：",
        '"': "＂",
        "/": "／",
        "\\": "＼",
        "|": "｜",
        "?": "？",
        "*": "＊",
    }
)
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}  # fmt: skip
MAX_NAME_CHARS = 100


@dataclass(frozen=True)
class YoutubeLink:
    video_id: str

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


@dataclass(frozen=True)
class VideoInfo:
    video_id: str
    title: str
    duration_s: float | None
    uploader: str | None


@dataclass(frozen=True)
class SavedAudio:
    path: Path
    title: str
    video_id: str
    bitrate_kbps: int


# -- the link -----------------------------------------------------------------
def parse_link(text: str) -> YoutubeLink:
    """Check that ``text`` is the link of one YouTube video and return its id.

    Accepts watch, short (youtu.be), Shorts, live, and embed links, with or
    without ``https://``. A link with both a video and a playlist means the video.
    Playlists, channels, and other pages raise :class:`InvalidYoutubeLinkError`.
    """
    raw = text.strip().strip("<>\"'“”‘’").strip()
    if not raw or any(c.isspace() for c in raw):
        raise InvalidYoutubeLinkError("empty or contains spaces")
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parts = urlparse(raw)
        host = (parts.hostname or "").lower()
    except ValueError as exc:
        raise InvalidYoutubeLinkError(str(exc)) from exc
    if parts.scheme not in ("http", "https"):
        raise InvalidYoutubeLinkError(f"scheme {parts.scheme!r}")
    segments = [s for s in parts.path.split("/") if s]
    candidate: str | None = None
    if host in _SHORT_HOSTS:
        candidate = segments[0] if segments else None
    elif host in _WATCH_HOSTS:
        if segments and segments[0] == "watch":
            candidate = next(iter(parse_qs(parts.query).get("v", [])), None)
        elif len(segments) >= 2 and segments[0] in _ID_FIRST_SEGMENTS:
            candidate = segments[1]
    else:
        raise InvalidYoutubeLinkError(f"not a YouTube address: {host or raw!r}")
    if candidate is None or not VIDEO_ID.fullmatch(candidate):
        raise InvalidYoutubeLinkError(f"no video id in {text.strip()!r}")
    return YoutubeLink(candidate)


def find_link(text: str) -> YoutubeLink | None:
    """The first YouTube video link inside ``text`` (clipboard contents), or ``None``."""
    for match in _URL_IN_TEXT.finditer(text or ""):
        try:
            return parse_link(match.group(0).rstrip(".,;)]}>\"'"))
        except InvalidYoutubeLinkError:
            continue
    return None


# -- names and bit rates ------------------------------------------------------
def safe_filename(title: str, fallback: str = "YouTube") -> str:
    """A file name (without suffix) from a video title, valid on every platform.

    Characters Windows forbids become their full-width look-alikes (as yt-dlp does),
    control characters go, and reserved names and trailing dots are avoided.
    """
    name = unicodedata.normalize("NFC", title or "")
    name = "".join(c for c in name if c == " " or unicodedata.category(c)[0] != "C")
    name = name.translate(_FULL_WIDTH)
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > MAX_NAME_CHARS:
        name = name[:MAX_NAME_CHARS].rstrip()
    name = name.rstrip(" .")
    if not name:
        return fallback
    if name.split(".")[0].upper() in _RESERVED:
        name += "_"
    return name


def unique_path(folder: Path, stem: str, suffix: str = ".mp3") -> Path:
    """``<stem><suffix>``, or ``<stem> (2)<suffix>`` and so on if the name is taken."""
    path = folder / f"{stem}{suffix}"
    n = 2
    while path.exists():
        path = folder / f"{stem} ({n}){suffix}"
        n += 1
    return path


def check_bitrate(kbps: int) -> int:
    if kbps not in BITRATES:
        raise ValueError(f"bit rate {kbps} kbps is not one of {BITRATES}")
    return kbps


def default_folder(configured: str | None = None) -> Path:
    return Path(configured) if configured else paths.music_dir()


# -- yt-dlp -------------------------------------------------------------------
class _Quiet:
    """Keeps yt-dlp from printing; remembers its messages for the log."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        self.messages.append(msg)

    def error(self, msg: str) -> None:
        self.messages.append(msg)


_ERROR_PATTERNS: tuple[tuple[tuple[str, ...], type[YoutubeError]], ...] = (
    (("not a bot", "http error 429", "too many requests"), YoutubeBotCheckError),
    (
        (
            "sign in",
            "log in",
            "private video",
            "members-only",
            "members only",
            "join this channel",
            "age-restricted",
            "confirm your age",
        ),
        YoutubeSignInError,
    ),
    (("live event", "premieres in", "will begin in", "this live"), YoutubeLiveError),
    (
        (
            "http error 503",
            "http error 403",
            "http error 502",
            "http error 504",
            "service unavailable",
            "forbidden",
            "giving up after",
            "proxy",
        ),
        YoutubeRefusedError,
    ),
    (
        (
            "javascript runtime",
            "js runtime",
            "challenge",
            "requested format is not available",
            "unable to extract",
            "signature",
        ),
        YoutubeChangedError,
    ),
    (
        (
            "video unavailable",
            "no longer available",
            "has been removed",
            "is not available",
            "blocked it",
            "copyright",
            "terminated",
            "does not exist",
            "in your country",
            "not made this video available",
        ),
        YoutubeUnavailableError,
    ),
    (
        (
            "urlopen error",
            "timed out",
            "getaddrinfo",
            "name or service not known",
            "network is unreachable",
            "connection",
            "unable to download",
            "ssl",
        ),
        YoutubeNetworkError,
    ),
)


def classify_error(exc: BaseException) -> NotiruaError:
    """Turn a yt-dlp failure into one of our errors with a message the user can act on."""
    if isinstance(exc, NotiruaError):
        return exc
    text = re.sub(r"\x1b\[[0-9;]*m", "", str(exc))
    lowered = text.lower()
    for needles, error_type in _ERROR_PATTERNS:
        if any(n in lowered for n in needles):
            return error_type(text[:300])
    return YoutubeError(text[:300])


def runtimes_option(js_runtime: Path | None) -> dict[str, dict[str, str]] | None:
    """yt-dlp's ``js_runtimes`` setting for a Deno at ``js_runtime`` (``None``: its default)."""
    if js_runtime is None:
        return None
    return {"deno": {"path": str(js_runtime)}}


YdlFactory = Callable[[dict[str, Any]], Any]


def _default_factory(options: dict[str, Any]) -> Any:
    import yt_dlp

    return yt_dlp.YoutubeDL(options)


PROXY_SCHEMES = ("http", "https", "socks4", "socks4a", "socks5", "socks5h")

# The ways to ask YouTube, in order. The first is yt-dlp's own choice. A stream address is tied
# to the address that asked for it, so the second forces IPv4 for every request; the third also
# asks as the TV and embedded players, which need no proof-of-origin token.
ATTEMPTS: tuple[dict[str, Any], ...] = (
    {},
    {"source_address": "0.0.0.0"},
    {
        "source_address": "0.0.0.0",
        "extractor_args": {"youtube": {"player_client": ["tv", "web_embedded"]}},
    },
)
TRYING_AGAIN = N_("Downloading the audio: trying another way")


def check_proxy(text: str | None) -> str | None:
    """A proxy address for yt-dlp, or ``None`` when ``text`` is empty (use the system's proxy).

    ``host:port`` becomes ``http://host:port``. Raises ``ValueError`` for anything that is not
    an http, https, or socks proxy address.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    if any(c.isspace() for c in raw):
        raise ValueError(f"a proxy address has no spaces: {text!r}")
    if "://" not in raw:
        raw = "http://" + raw
    try:
        parts = urlparse(raw)
        port = parts.port
    except ValueError as exc:
        raise ValueError(f"not a proxy address: {text!r}") from exc
    if parts.scheme.lower() not in PROXY_SCHEMES or not parts.hostname or port is None:
        raise ValueError(f"a proxy address looks like http://host:port, not {text!r}")
    return raw


def mask_proxy(address: str | None) -> str:
    """The proxy address without its password, for logs."""
    if not address:
        return "-"
    parts = urlparse(address)
    if parts.password is None:
        return address
    netloc = f"{parts.username}:***@{parts.hostname}" + (f":{parts.port}" if parts.port else "")
    return urlunparse(parts._replace(netloc=netloc))


def system_proxies() -> dict[str, str]:
    """The proxies Python finds in the environment and (on Windows) the system settings."""
    import urllib.request

    return {scheme: mask_proxy(url) for scheme, url in urllib.request.getproxies().items()}


def format_summary(raw: dict[str, Any] | None) -> list[str]:
    """A few audio formats of ``raw`` for the log: id, protocol, host, client."""
    found = []
    for fmt in (raw or {}).get("formats", []) or []:
        if fmt.get("vcodec") not in (None, "none") or fmt.get("acodec") in (None, "none"):
            continue
        host = urlparse(str(fmt.get("url") or "")).hostname or "-"
        client = fmt.get("__yt_dlp_client", "-")
        found.append(f"{fmt.get('format_id')}:{fmt.get('protocol')}:{host}:{client}")
    return found[:4]


class YoutubeClient:
    """Reads a video's page and downloads its audio (yt-dlp behind a small interface)."""

    def __init__(
        self,
        js_runtime: Path | None = None,
        cache_dir: Path | None = None,
        ydl_factory: YdlFactory = _default_factory,
        proxy: str | None = None,
    ) -> None:
        self.js_runtime = js_runtime
        self.proxy = check_proxy(proxy)
        self.cache_dir = cache_dir if cache_dir is not None else paths.cache_dir() / "yt-dlp"
        self._factory = ydl_factory

    def _options(
        self,
        work_dir: Path,
        hook: Callable[[dict[str, Any]], None],
        log_: _Quiet,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": str(work_dir / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "logger": log_,
            "progress_hooks": [hook],
            "retries": 5,
            "fragment_retries": 3,
            "socket_timeout": 20,
            "cachedir": str(self.cache_dir),
            "remote_components": set(),  # the scripts come with yt-dlp-ejs; never fetch more
        }
        runtimes = runtimes_option(self.js_runtime)
        if runtimes is not None:
            options["js_runtimes"] = runtimes
        if self.proxy is not None:  # else yt-dlp uses the system's proxy settings
            options["proxy"] = self.proxy
        options.update(overrides or {})
        return options

    def fetch(
        self,
        link: YoutubeLink,
        work_dir: Path,
        *,
        max_duration_s: float = MAX_DURATION_S,
        on_info: Callable[[VideoInfo], None] | None = None,
        on_bytes: Callable[[int, int | None], None] | None = None,
        on_retry: Callable[[int], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> tuple[VideoInfo, Path]:
        """Read the page, check the video, and download its audio into ``work_dir``.

        When YouTube's server refuses the audio (HTTP 403/5xx), the next way in ``ATTEMPTS`` is
        tried; any other problem stops at once.
        """
        cancel = cancel or CancelToken()

        def hook(status: dict[str, Any]) -> None:
            cancel.raise_if_cancelled()
            if status.get("status") == "downloading" and on_bytes is not None:
                total = status.get("total_bytes") or status.get("total_bytes_estimate")
                on_bytes(int(status.get("downloaded_bytes") or 0), int(total) if total else None)

        for number, overrides in enumerate(ATTEMPTS, start=1):
            cancel.raise_if_cancelled()
            if number > 1 and on_retry is not None:
                on_retry(number)
            quiet = _Quiet()
            raw: dict[str, Any] | None = None
            try:
                with self._factory(self._options(work_dir, hook, quiet, overrides)) as ydl:
                    raw = ydl.extract_info(link.url, download=False)
                    cancel.raise_if_cancelled()
                    info = check_video(raw, link, max_duration_s)
                    if on_info is not None and number == 1:
                        on_info(info)
                    ydl.process_ie_result(raw, download=True)
            except Cancelled:
                raise
            except NotiruaError:
                raise
            except Exception as exc:
                if cancel.cancelled:
                    raise Cancelled() from exc
                error = classify_error(exc)
                log.warning(
                    "yt-dlp attempt %d/%d failed for %s (%s): %s | formats %s | proxy %s | "
                    "system proxies %s | %s",
                    number,
                    len(ATTEMPTS),
                    link.video_id,
                    type(error).__name__,
                    str(exc).replace("\n", " ")[:200],
                    format_summary(raw),
                    mask_proxy(self.proxy),
                    system_proxies(),
                    quiet.messages[-3:],
                )
                if isinstance(error, YoutubeRefusedError) and number < len(ATTEMPTS):
                    for leftover in work_dir.glob(f"{link.video_id}.*"):
                        leftover.unlink(missing_ok=True)
                    continue
                raise error from exc
            break
        cancel.raise_if_cancelled()
        return info, find_download(work_dir, link.video_id)


def check_video(raw: dict[str, Any] | None, link: YoutubeLink, max_duration_s: float) -> VideoInfo:
    """Refuse live streams and videos that are too long; read the title."""
    if not raw:
        raise YoutubeUnavailableError("no information")
    if raw.get("_type") == "playlist":
        raise InvalidYoutubeLinkError("playlist")
    if raw.get("is_live") or raw.get("live_status") in ("is_live", "is_upcoming"):
        raise YoutubeLiveError(str(raw.get("live_status")))
    availability = raw.get("availability")
    if availability in ("private", "needs_auth", "subscriber_only", "premium_only"):
        raise YoutubeSignInError(str(availability))
    duration = raw.get("duration")
    if duration and float(duration) > max_duration_s + 0.5:
        raise TooLongError(limit=int(max_duration_s // 60))
    title = str(raw.get("title") or "").strip()
    return VideoInfo(
        video_id=str(raw.get("id") or link.video_id),
        title=title or f"YouTube {link.video_id}",
        duration_s=float(duration) if duration else None,
        uploader=(str(raw["uploader"]) if raw.get("uploader") else None),
    )


def find_download(work_dir: Path, video_id: str) -> Path:
    """The finished audio file yt-dlp left in ``work_dir`` (partial files do not count)."""
    found = sorted(
        p
        for p in work_dir.glob(f"{video_id}.*")
        if p.is_file() and p.suffix not in (".part", ".ytdl", ".temp")
    )
    if not found:
        raise YoutubeError("the download left no audio file")
    return found[0]


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


# -- the whole job ---------------------------------------------------------------
def save_as_mp3(
    link: str | YoutubeLink,
    out_dir: Path,
    bitrate_kbps: int = DEFAULT_BITRATE,
    *,
    client: YoutubeClient | None = None,
    progress: ProgressCallback | None = None,
    cancel: CancelToken | None = None,
) -> SavedAudio:
    """Check the link, download the audio, and save ``<title>.mp3`` in ``out_dir``.

    Raises :class:`NotiruaError` subclasses (all user-facing): an invalid link, a
    video that is private, live, removed, or too long, a network problem, or
    :class:`Cancelled`.
    """
    parsed = link if isinstance(link, YoutubeLink) else parse_link(link)
    kbps = check_bitrate(bitrate_kbps)
    client = client or YoutubeClient()
    cancel = cancel or CancelToken()
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="notirua-yt-"))
    with ProgressReporter("youtube", STAGES, progress) as rep:
        try:
            rep.start("check")

            def on_info(info: VideoInfo) -> None:
                rep.done("check")
                rep.start("download")

            def on_bytes(done: int, total: int | None) -> None:
                if total:
                    rep.update(
                        "download",
                        done / total,
                        DOWNLOADING,
                        received=_human(done),
                        total=_human(total),
                    )

            def on_retry(_number: int) -> None:
                rep.update("download", None, TRYING_AGAIN)

            info, raw_file = client.fetch(
                parsed,
                work_dir,
                on_info=on_info,
                on_bytes=on_bytes,
                on_retry=on_retry,
                cancel=cancel,
            )
            rep.done("download")
            rep.start("convert")
            audio = decode(
                raw_file,
                progress=lambda f: rep.update("convert", f * 0.5),
                cancel=cancel,
            )
            name = safe_filename(info.title, fallback=f"YouTube {info.video_id}")
            target = unique_path(out_dir, name)
            write_audio(
                target,
                audio,
                "mp3",
                progress=lambda f: rep.update("convert", 0.5 + f * 0.5),
                cancel=cancel,
                bit_rate=kbps * 1000,
                tags={"title": info.title},
            )
            rep.done("convert")
        except Cancelled:
            raise
        except Exception as exc:
            running = next((s for s, st in rep.states.items() if st == "running"), "check")
            rep.fail(running)
            if isinstance(exc, NotiruaError):
                raise
            raise classify_error(exc) from exc
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
    log.info("saved %s (%s, %d kbps)", target, info.video_id, kbps)
    return SavedAudio(target, info.title, info.video_id, kbps)


def js_runtime_candidates(component_entry: Path | None) -> Iterable[Path]:
    """Where a Deno may be: the downloaded component first, then ``deno`` on the PATH."""
    if component_entry is not None and component_entry.is_file():
        yield component_entry
    found = shutil.which("deno")
    if found:
        yield Path(found)


def find_js_runtime(component_entry: Path | None) -> Path | None:
    return next(iter(js_runtime_candidates(component_entry)), None)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def installation_check(js_runtime: Path | None = None) -> list[Check]:
    """Offline check that everything YouTube support needs came with this copy of Notirua.

    The helper program (Deno) is optional and listed last; it is not a failure when missing.
    """
    checks: list[Check] = []
    try:
        import yt_dlp
        from yt_dlp.extractor.youtube import YoutubeIE

        checks.append(Check("yt-dlp", YoutubeIE is not None, yt_dlp.version.__version__))
    except Exception as exc:  # a broken bundle can fail in many ways
        checks.append(Check("yt-dlp", False, str(exc)[:200]))
    try:
        from importlib import resources

        import yt_dlp_ejs
        import yt_dlp_ejs.yt.solver

        scripts = [p.name for p in resources.files("yt_dlp_ejs.yt.solver").iterdir()]
        found = [name for name in ("core.min.js", "lib.min.js") if name in scripts]
        checks.append(Check("yt-dlp-ejs", len(found) == 2, f"{yt_dlp_ejs.version}: {len(found)}/2"))
    except Exception as exc:
        checks.append(Check("yt-dlp-ejs", False, str(exc)[:200]))
    try:
        import certifi

        bundle = Path(certifi.where())
        checks.append(Check("certifi", bundle.is_file(), str(bundle)))
    except Exception as exc:
        checks.append(Check("certifi", False, str(exc)[:200]))
    checks.append(Check("deno", js_runtime is not None, str(js_runtime or "-")))
    return checks
