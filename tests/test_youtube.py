"""Saving audio from a YouTube link (0.5.0). No network: yt-dlp is replaced by a fake."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest

from notirua.core import mix
from notirua.core import youtube as yt
from notirua.core.errors import (
    Cancelled,
    InvalidYoutubeLinkError,
    TooLongError,
    YoutubeBotCheckError,
    YoutubeChangedError,
    YoutubeError,
    YoutubeLiveError,
    YoutubeNetworkError,
    YoutubeSignInError,
    YoutubeUnavailableError,
)
from notirua.core.progress import CancelToken, ProgressEvent

from .synth import encode, tone

ID = "dQw4w9WgXcQ"

needs_mp3 = pytest.mark.skipif("mp3" not in mix.available_formats(), reason="no MP3 encoder")


# -- the link ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        f"https://www.youtube.com/watch?v={ID}",
        f"  https://youtube.com/watch?v={ID}&t=42s  ",
        f"https://m.youtube.com/watch?v={ID}",
        f"https://music.youtube.com/watch?v={ID}&list=RDAMVM{ID}",
        f"https://www.youtube.com/watch?list=PLabc&v={ID}",
        f"https://youtu.be/{ID}",
        f"https://youtu.be/{ID}?si=abcDEF",
        f"https://www.youtube.com/shorts/{ID}",
        f"https://www.youtube.com/live/{ID}?feature=share",
        f"https://www.youtube.com/embed/{ID}",
        f"www.youtube.com/watch?v={ID}",
        f"youtu.be/{ID}",
        f"<https://youtu.be/{ID}>",
        f"“https://youtu.be/{ID}”",
        f"HTTPS://WWW.YOUTUBE.COM/watch?v={ID}",
    ],
)
def test_parse_link_accepts_video_links(text: str) -> None:
    link = yt.parse_link(text)
    assert link.video_id == ID
    assert link.url == f"https://www.youtube.com/watch?v={ID}"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "hello",
        "https://example.com/watch?v=" + ID,
        "https://www.youtube.com/",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/watch?v=" + ID + "extra",
        "https://www.youtube.com/playlist?list=PLabc",
        "https://www.youtube.com/@someone",
        "https://www.youtube.com/channel/UC1234567890123456789012",
        "ftp://www.youtube.com/watch?v=" + ID,
        "https://youtu.be/",
        "https://youtube.com.evil.example/watch?v=" + ID,
        "https://notyoutube.com/watch?v=" + ID,
        "two words https://youtu.be/" + ID,
    ],
)
def test_parse_link_rejects_everything_else(text: str) -> None:
    with pytest.raises(InvalidYoutubeLinkError):
        yt.parse_link(text)


def test_find_link_in_clipboard_text() -> None:
    assert yt.find_link(f"look at this: https://youtu.be/{ID}, it is great").video_id == ID
    assert yt.find_link(f"(https://www.youtube.com/watch?v={ID})").video_id == ID
    assert yt.find_link("https://www.youtube.com/playlist?list=PLabc") is None
    assert yt.find_link("nothing here") is None
    assert yt.find_link("") is None


# -- names and bit rates -------------------------------------------------------------
@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Song", "Song"),
        ("봄날 - BTS (방탄소년단) 'Spring Day'", "봄날 - BTS (방탄소년단) 'Spring Day'"),
        ('A/B: "C" | D? <E> *F* \\G', "A／B： ＂C＂ ｜ D？ ＜E＞ ＊F＊ ＼G"),
        ("  spaced   out \t title  ", "spaced out title"),
        ("ends with dots...", "ends with dots"),
        ("tab\x00and\x1fcontrol", "tabandcontrol"),
        ("CON", "CON_"),
        ("nul.txt", "nul.txt_"),
        ("", "YouTube"),
        ("...", "YouTube"),
    ],
)
def test_safe_filename(title: str, expected: str) -> None:
    assert yt.safe_filename(title) == expected


def test_safe_filename_is_short_and_nfc() -> None:
    name = yt.safe_filename("가" * 500)
    assert len(name) == yt.MAX_NAME_CHARS
    decomposed = "가"  # 가 as jamo
    assert yt.safe_filename(decomposed) == "가"


def test_unique_path_numbers_taken_names(tmp_path: Path) -> None:
    assert yt.unique_path(tmp_path, "song").name == "song.mp3"
    (tmp_path / "song.mp3").write_bytes(b"x")
    assert yt.unique_path(tmp_path, "song").name == "song (2).mp3"
    (tmp_path / "song (2).mp3").write_bytes(b"x")
    assert yt.unique_path(tmp_path, "song").name == "song (3).mp3"


def test_bitrates() -> None:
    assert yt.DEFAULT_BITRATE == 160
    assert yt.DEFAULT_BITRATE in yt.BITRATES
    assert {128, 160, 192, 256, 320} == set(yt.BITRATES)
    for kbps in yt.BITRATES:
        assert yt.check_bitrate(kbps) == kbps
    for bad in (0, 64, 161, 999):
        with pytest.raises(ValueError):
            yt.check_bitrate(bad)


# -- errors ------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("ERROR: [youtube] x: Sign in to confirm you’re not a bot", YoutubeBotCheckError),
        ("HTTP Error 429: Too Many Requests", YoutubeBotCheckError),
        (
            "ERROR: [youtube] x: Private video. Sign in if you've been granted access",
            YoutubeSignInError,
        ),
        ("Sign in to confirm your age. This video may be inappropriate", YoutubeSignInError),
        ("Join this channel to get access to members-only content", YoutubeSignInError),
        ("This live event will begin in 2 hours.", YoutubeLiveError),
        ("Video unavailable. This video is no longer available", YoutubeUnavailableError),
        ("The uploader has not made this video available in your country", YoutubeUnavailableError),
        ("<urlopen error [Errno -2] Name or service not known>", YoutubeNetworkError),
        ("Unable to download webpage: timed out", YoutubeNetworkError),
        ("n challenge solving failed: no JavaScript runtime", YoutubeChangedError),
        ("Requested format is not available", YoutubeChangedError),
        ("something nobody has seen before", YoutubeError),
    ],
)
def test_classify_error(message: str, expected: type[YoutubeError]) -> None:
    error = yt.classify_error(RuntimeError(message))
    assert type(error) is expected
    assert error.user_message()
    assert error.user_hint()


def test_classify_error_keeps_our_own_errors() -> None:
    err = TooLongError(limit=15)
    assert yt.classify_error(err) is err


def _info(**changes: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {"id": ID, "title": "Some Song", "duration": 200, "uploader": "Chan"}
    raw.update(changes)
    return raw


LINK = yt.YoutubeLink(ID)


def test_check_video_reads_title_and_length() -> None:
    info = yt.check_video(_info(), LINK, 900)
    assert (info.video_id, info.title, info.duration_s, info.uploader) == (
        ID,
        "Some Song",
        200.0,
        "Chan",
    )
    assert yt.check_video(_info(title="  "), LINK, 900).title == f"YouTube {ID}"


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"is_live": True}, YoutubeLiveError),
        ({"live_status": "is_upcoming"}, YoutubeLiveError),
        ({"availability": "private"}, YoutubeSignInError),
        ({"availability": "subscriber_only"}, YoutubeSignInError),
        ({"duration": 16 * 60}, TooLongError),
        ({"_type": "playlist"}, InvalidYoutubeLinkError),
    ],
)
def test_check_video_refuses(changes: dict[str, Any], expected: type[Exception]) -> None:
    with pytest.raises(expected):
        yt.check_video(_info(**changes), LINK, 900)


def test_check_video_accepts_exactly_the_limit() -> None:
    assert yt.check_video(_info(duration=900), LINK, 900).duration_s == 900.0
    with pytest.raises(YoutubeUnavailableError):
        yt.check_video(None, LINK, 900)


# -- a fake yt-dlp --------------------------------------------------------------------
class FakeYdl:
    """Stands in for ``yt_dlp.YoutubeDL``: serves ``info`` and writes a real m4a."""

    last_options: ClassVar[dict[str, Any]] = {}

    def __init__(self, options: dict[str, Any], info: dict[str, Any] | None = None,
                 fail: Exception | None = None, seconds: float = 3.0) -> None:  # fmt: skip
        FakeYdl.last_options = options
        self.options = options
        self.info = info if info is not None else _info()
        self.fail = fail
        self.seconds = seconds

    def __enter__(self) -> FakeYdl:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
        assert download is False
        assert url == f"https://www.youtube.com/watch?v={ID}"
        if self.fail is not None:
            raise self.fail
        return self.info

    def process_ie_result(self, info: dict[str, Any], download: bool = True) -> None:
        folder = Path(self.options["outtmpl"]).parent
        encode(folder / f"{info['id']}.m4a", tone(440, self.seconds), "m4a")
        total = 1000
        for done in (100, 500, 1000):
            for hook in self.options["progress_hooks"]:
                hook({"status": "downloading", "downloaded_bytes": done, "total_bytes": total})
        (folder / f"{info['id']}.m4a.part").write_bytes(b"")  # must be ignored


def client(**kwargs: Any) -> yt.YoutubeClient:
    return yt.YoutubeClient(ydl_factory=lambda options: FakeYdl(options, **kwargs))


@needs_mp3
def test_save_as_mp3_names_the_file_after_the_title(tmp_path: Path) -> None:
    import av

    events: list[ProgressEvent] = []
    saved = yt.save_as_mp3(
        f"https://youtu.be/{ID}",
        tmp_path / "out",
        client=client(info=_info(title='봄날: "Spring" | Day?')),
        progress=events.append,
    )
    assert saved.path == tmp_path / "out" / "봄날： ＂Spring＂ ｜ Day？.mp3"
    assert saved.title == '봄날: "Spring" | Day?'
    assert (saved.video_id, saved.bitrate_kbps) == (ID, 160)
    with av.open(str(saved.path)) as f:
        stream = f.streams.audio[0]
        assert stream.codec_context.name.startswith("mp3")
        assert stream.bit_rate == 160_000
        assert f.metadata.get("title") == '봄날: "Spring" | Day?'
    # the stages ran in order and ended at 100 %
    stages = [e.stage for e in events]
    assert stages.index("check") < stages.index("download") < stages.index("convert")
    assert events[-1].overall_fraction == pytest.approx(1.0)
    assert any(e.message_args.get("received") for e in events)
    # no temporary files are left behind
    assert [p.name for p in saved.path.parent.iterdir()] == [saved.path.name]


@needs_mp3
@pytest.mark.parametrize("kbps", yt.BITRATES)
def test_every_bitrate_is_written(tmp_path: Path, kbps: int) -> None:
    import av

    saved = yt.save_as_mp3(f"https://youtu.be/{ID}", tmp_path, kbps, client=client())
    with av.open(str(saved.path)) as f:
        assert f.streams.audio[0].bit_rate == kbps * 1000


@needs_mp3
def test_second_save_does_not_overwrite(tmp_path: Path) -> None:
    first = yt.save_as_mp3(f"https://youtu.be/{ID}", tmp_path, client=client())
    second = yt.save_as_mp3(f"https://youtu.be/{ID}", tmp_path, client=client())
    assert first.path.name == "Some Song.mp3"
    assert second.path.name == "Some Song (2).mp3"


def test_invalid_link_and_bitrate_fail_before_any_work(tmp_path: Path) -> None:
    def boom(_options: dict[str, Any]) -> Any:
        raise AssertionError("yt-dlp must not be used")

    with pytest.raises(InvalidYoutubeLinkError):
        yt.save_as_mp3("https://example.com", tmp_path, client=yt.YoutubeClient(ydl_factory=boom))
    with pytest.raises(ValueError):
        yt.save_as_mp3(
            f"https://youtu.be/{ID}", tmp_path, 100, client=yt.YoutubeClient(ydl_factory=boom)
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"info": _info(duration=16 * 60)}, TooLongError),
        ({"info": _info(is_live=True)}, YoutubeLiveError),
        ({"fail": RuntimeError("Private video. Sign in")}, YoutubeSignInError),
        ({"fail": RuntimeError("Video unavailable")}, YoutubeUnavailableError),
        ({"fail": OSError("<urlopen error timed out>")}, YoutubeNetworkError),
        ({"fail": RuntimeError("strange")}, YoutubeError),
    ],
)
def test_failures_become_user_facing_errors(
    tmp_path: Path, kwargs: dict[str, Any], expected: type[Exception]
) -> None:
    events: list[ProgressEvent] = []
    with pytest.raises(expected):
        yt.save_as_mp3(
            f"https://youtu.be/{ID}", tmp_path, client=client(**kwargs), progress=events.append
        )
    assert events[-1].stage_state == "failed"
    assert not [p for p in tmp_path.iterdir()]


def test_cancel_stops_the_download(tmp_path: Path) -> None:
    token = CancelToken()

    def cancel_midway(event: ProgressEvent) -> None:
        if event.stage == "download" and event.stage_fraction:
            token.cancel()

    with pytest.raises(Cancelled):
        yt.save_as_mp3(
            f"https://youtu.be/{ID}",
            tmp_path,
            client=client(),
            progress=cancel_midway,
            cancel=token,
        )
    assert not [p for p in tmp_path.iterdir()]


def test_options_never_fetch_extra_code_and_use_the_given_runtime(tmp_path: Path) -> None:
    runtime = tmp_path / "deno"
    c = yt.YoutubeClient(
        js_runtime=runtime, ydl_factory=lambda o: FakeYdl(o, fail=RuntimeError("stop"))
    )
    with pytest.raises(YoutubeError):
        c.fetch(LINK, tmp_path)
    options = FakeYdl.last_options
    assert options["js_runtimes"] == {"deno": {"path": str(runtime)}}
    assert options["remote_components"] == set()
    assert options["noplaylist"] is True
    assert "postprocessors" not in options  # no ffmpeg program is needed
    assert str(options["outtmpl"]).startswith(str(tmp_path))


def test_default_runtime_option_is_left_to_yt_dlp() -> None:
    assert yt.runtimes_option(None) is None
    c = yt.YoutubeClient(ydl_factory=lambda o: FakeYdl(o, fail=RuntimeError("stop")))
    with pytest.raises(YoutubeError):
        c.fetch(LINK, Path("."))
    assert "js_runtimes" not in FakeYdl.last_options


def test_find_js_runtime_prefers_the_component(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    component = tmp_path / "deno"
    component.write_bytes(b"x")
    monkeypatch.setattr(yt.shutil, "which", lambda _name: str(tmp_path / "path-deno"))
    assert yt.find_js_runtime(component) == component
    assert yt.find_js_runtime(tmp_path / "missing") == tmp_path / "path-deno"
    monkeypatch.setattr(yt.shutil, "which", lambda _name: None)
    assert yt.find_js_runtime(None) is None


def test_real_yt_dlp_accepts_our_options(tmp_path: Path) -> None:
    """The options are valid for the installed yt-dlp (no network is used)."""
    import yt_dlp

    quiet = yt._Quiet()
    c = yt.YoutubeClient(js_runtime=tmp_path / "deno", cache_dir=tmp_path / "cache")
    options = c._options(tmp_path, lambda _s: None, quiet)
    with yt_dlp.YoutubeDL(options) as ydl:
        assert ydl.params["noplaylist"] is True
        assert "deno" in ydl.params["js_runtimes"]


# -- the server refuses the audio (HTTP 503, 403): other ways in, and a proxy -------------------
@pytest.mark.parametrize(
    "message",
    [
        "ERROR: \n[download] Got error: HTTP Error 503: Service Unavailable. Giving up",
        "HTTP Error 403: Forbidden",
        "HTTP Error 502: Bad Gateway. Giving up after 5 retries",
        "ProxyError: Tunnel connection failed: 403 Forbidden",
    ],
)
def test_refusals_are_told_apart_from_a_bad_connection(message: str) -> None:
    from notirua.core.errors import YoutubeRefusedError

    error = yt.classify_error(RuntimeError(message))
    assert type(error) is YoutubeRefusedError
    assert "proxy" in error.user_hint()
    assert error.code == "E-YT-REFUSED"


def test_a_429_is_still_a_rate_limit() -> None:
    assert type(yt.classify_error(RuntimeError("HTTP Error 429: Too Many Requests"))) is (
        YoutubeBotCheckError
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("http://proxy.example.com:8080", "http://proxy.example.com:8080"),
        ("proxy.example.com:8080", "http://proxy.example.com:8080"),
        ("  10.1.2.3:3128 ", "http://10.1.2.3:3128"),
        ("https://user:p%40ss@proxy.corp:443", "https://user:p%40ss@proxy.corp:443"),
        ("socks5://127.0.0.1:1080", "socks5://127.0.0.1:1080"),
    ],
)
def test_check_proxy_accepts_proxy_addresses(text: str | None, expected: str | None) -> None:
    assert yt.check_proxy(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "proxy.example.com",
        "http://proxy.example.com",
        "ftp://proxy:21",
        "http://:8080",
        "a b:1",
        "://x:1",
    ],
)
def test_check_proxy_refuses_everything_else(text: str) -> None:
    with pytest.raises(ValueError):
        yt.check_proxy(text)


def test_proxy_passwords_stay_out_of_logs() -> None:
    assert yt.mask_proxy("http://bob:secret@proxy:8080") == "http://bob:***@proxy:8080"
    assert yt.mask_proxy("http://proxy:8080") == "http://proxy:8080"
    assert yt.mask_proxy(None) == "-"
    assert "secret" not in str(yt.system_proxies())


def test_the_proxy_reaches_yt_dlp_and_is_left_out_when_unset(tmp_path: Path) -> None:
    for proxy, expected in (("proxy.corp:8080", "http://proxy.corp:8080"), (None, None)):
        c = yt.YoutubeClient(proxy=proxy, ydl_factory=lambda o: FakeYdl(o, fail=RuntimeError("x")))
        with pytest.raises(YoutubeError):
            c.fetch(LINK, tmp_path)
        assert FakeYdl.last_options.get("proxy") == expected
    with pytest.raises(ValueError):
        yt.YoutubeClient(proxy="nonsense")


class RefusedYdl(FakeYdl):
    """Refuses the audio (HTTP 503) until ``works_from`` attempts have been made."""

    seen: ClassVar[list[dict[str, Any]]] = []
    works_from = 99

    def process_ie_result(self, info: dict[str, Any], download: bool = True) -> None:
        RefusedYdl.seen.append(self.options)
        folder = Path(self.options["outtmpl"]).parent
        (folder / f"{info['id']}.m4a.part").write_bytes(b"partial")
        if len(RefusedYdl.seen) < self.works_from:
            raise RuntimeError(
                "ERROR: \n[download] Got error: HTTP Error 503: Service Unavailable. Giving up"
            )
        super().process_ie_result(info, download)


def refused_client(works_from: int) -> yt.YoutubeClient:
    RefusedYdl.seen = []
    RefusedYdl.works_from = works_from
    return yt.YoutubeClient(ydl_factory=lambda o: RefusedYdl(o))


def test_refused_audio_is_retried_with_other_settings(tmp_path: Path) -> None:
    retries: list[int] = []
    _, path = refused_client(3).fetch(LINK, tmp_path, on_retry=retries.append)
    assert path.suffix == ".m4a" and path.parent == tmp_path
    assert retries == [2, 3]
    first, second, third = RefusedYdl.seen
    assert "source_address" not in first and "extractor_args" not in first
    assert second["source_address"] == "0.0.0.0"  # IPv4 only
    assert third["source_address"] == "0.0.0.0"
    assert third["extractor_args"]["youtube"]["player_client"] == ["tv", "web_embedded"]
    leftovers = [p.read_bytes() for p in tmp_path.glob("*.part")]
    assert b"partial" not in leftovers  # a failed attempt's partial file is removed


def test_a_working_first_try_is_not_repeated(tmp_path: Path) -> None:
    retries: list[int] = []
    refused_client(1).fetch(LINK, tmp_path, on_retry=retries.append)
    assert len(RefusedYdl.seen) == 1 and retries == []


def test_all_attempts_refused_ends_with_the_helpful_error(tmp_path: Path) -> None:
    from notirua.core.errors import YoutubeRefusedError

    with pytest.raises(YoutubeRefusedError):
        refused_client(99).fetch(LINK, tmp_path)
    assert len(RefusedYdl.seen) == len(yt.ATTEMPTS)


def test_other_errors_are_not_retried(tmp_path: Path) -> None:
    class Private(FakeYdl):
        calls: ClassVar[int] = 0

        def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
            Private.calls += 1
            raise RuntimeError("Private video. Sign in if you've been granted access")

    c = yt.YoutubeClient(ydl_factory=lambda o: Private(o))
    with pytest.raises(YoutubeSignInError):
        c.fetch(LINK, tmp_path)
    assert Private.calls == 1


@needs_mp3
def test_saving_says_when_it_tries_another_way(tmp_path: Path) -> None:
    events: list[ProgressEvent] = []
    saved = yt.save_as_mp3(
        f"https://youtu.be/{ID}", tmp_path, client=refused_client(2), progress=events.append
    )
    assert saved.path.is_file()
    assert any(e.message_id == yt.TRYING_AGAIN for e in events)
    assert events[-1].overall_fraction == pytest.approx(1.0)
