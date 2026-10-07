"""``notirua youtube``, a link given to ``transcribe``, and ``setup --youtube`` (0.5.0)."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from notirua import cli
from notirua import settings as settings_mod
from notirua.components import manager as manager_mod
from notirua.core import mix
from notirua.core import youtube as yt
from tests.component_fakes import Handler, serve
from tests.test_js_runtime_component import _fake_deno
from tests.test_youtube import ID, FakeYdl, _info

URL = f"https://youtu.be/{ID}"
needs_mp3 = pytest.mark.skipif("mp3" not in mix.available_formats(), reason="no MP3 encoder")


@pytest.fixture(autouse=True)
def restore_argparse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(argparse, "_", argparse._)  # type: ignore[attr-defined]
    monkeypatch.setattr(argparse, "ngettext", argparse.ngettext)  # type: ignore[attr-defined]


@pytest.fixture
def fake_youtube(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A fake yt-dlp behind ``YoutubeClient`` and a Deno that is "installed"."""
    state: dict[str, Any] = {"kwargs": {}, "runtime": Path("/fake/deno")}
    real = yt.YoutubeClient

    def client(runtime: Path | None = None, **_kw: Any) -> yt.YoutubeClient:
        state["used_runtime"] = runtime
        return real(runtime, ydl_factory=lambda o: FakeYdl(o, **state["kwargs"]))

    monkeypatch.setattr(cli.yt, "YoutubeClient", client)
    monkeypatch.setattr(cli, "_youtube_runtime", lambda _user: state["runtime"])
    return state


@needs_mp3
def test_youtube_saves_an_mp3_with_the_default_quality(
    fake_youtube: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import av

    assert cli.main(["--lang", "en", "youtube", URL]) == cli.EXIT_OK
    saved = tmp_path / "user-music" / "Some Song.mp3"
    assert saved.is_file()
    assert f"Saved: {saved}" in capsys.readouterr().out
    with av.open(str(saved)) as f:
        assert f.streams.audio[0].bit_rate == 160_000
    assert fake_youtube["used_runtime"] == Path("/fake/deno")


@needs_mp3
def test_youtube_bitrate_and_folder_options(fake_youtube: dict[str, Any], tmp_path: Path) -> None:
    import av

    out = tmp_path / "my music"
    assert cli.main(["youtube", URL, "--bitrate", "128", "--out", str(out)]) == cli.EXIT_OK
    with av.open(str(out / "Some Song.mp3")) as f:
        assert f.streams.audio[0].bit_rate == 128_000


@needs_mp3
def test_the_saved_quality_setting_is_the_default(
    fake_youtube: dict[str, Any], tmp_path: Path
) -> None:
    import av

    user = settings_mod.load()
    user.youtube_bitrate = 320
    settings_mod.save(user)
    assert cli.main(["youtube", URL, "--out", str(tmp_path)]) == cli.EXIT_OK
    with av.open(str(tmp_path / "Some Song.mp3")) as f:
        assert f.streams.audio[0].bit_rate == 320_000


def test_unsupported_bitrate_is_a_usage_error(
    fake_youtube: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["youtube", URL, "--bitrate", "100"])
    assert exc.value.code == 2
    assert "128" in capsys.readouterr().err


@pytest.mark.parametrize("text", ["hello", "https://example.com/x", "https://youtu.be/"])
def test_invalid_link_is_a_usage_error(
    fake_youtube: dict[str, Any], capsys: pytest.CaptureFixture[str], text: str
) -> None:
    assert cli.main(["--lang", "en", "youtube", text]) == cli.EXIT_USAGE
    err = capsys.readouterr().err
    assert "not a link to a single YouTube video" in err
    assert "What to do:" in err


def test_missing_helper_says_how_to_install_it(
    fake_youtube: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    fake_youtube["runtime"] = None
    assert cli.main(["--lang", "en", "youtube", URL]) == cli.EXIT_SETUP
    assert "notirua setup --youtube" in capsys.readouterr().err


def test_youtube_errors_print_message_hint_and_code(
    fake_youtube: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    fake_youtube["kwargs"] = {"fail": RuntimeError("Private video. Sign in")}
    assert cli.main(["--lang", "en", "youtube", URL]) == cli.EXIT_ERROR
    err = capsys.readouterr().err
    assert "needs you to sign in" in err
    assert "E-YT-SIGN-IN" in err


def test_too_long_video_is_refused(
    fake_youtube: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    fake_youtube["kwargs"] = {"info": _info(duration=3600)}
    assert cli.main(["--lang", "en", "youtube", URL]) == cli.EXIT_ERROR
    assert "longer than 15 minutes" in capsys.readouterr().err


# -- a link given to `transcribe` ------------------------------------------------------------
@needs_mp3
def test_transcribe_source_from_a_link(fake_youtube: dict[str, Any], tmp_path: Path) -> None:
    args = argparse.Namespace(file=URL, audio_out=tmp_path / "audio", bitrate=192, title=None)
    assert cli._use_youtube_source(args, settings_mod.Settings()) is None
    assert args.file == tmp_path / "audio" / "Some Song.mp3"
    assert args.file.is_file()
    assert args.title == "Some Song"


def test_transcribe_source_keeps_real_files_and_plain_text(
    fake_youtube: dict[str, Any], tmp_path: Path
) -> None:
    song = tmp_path / "song.wav"
    song.write_bytes(b"x")
    args = argparse.Namespace(file=str(song), audio_out=None, bitrate=None, title=None)
    assert cli._use_youtube_source(args, settings_mod.Settings()) is None
    assert args.file == str(song)
    args = argparse.Namespace(file="missing.wav", audio_out=None, bitrate=None, title="T")
    assert cli._use_youtube_source(args, settings_mod.Settings()) is None
    assert args.file == "missing.wav"  # the usual "File not found" follows
    # a file whose name looks like a link still wins
    odd = tmp_path / "https:youtu.be"
    odd.write_bytes(b"x")


def test_transcribe_source_stops_when_the_helper_is_missing(
    fake_youtube: dict[str, Any], tmp_path: Path
) -> None:
    fake_youtube["runtime"] = None
    args = argparse.Namespace(file=URL, audio_out=None, bitrate=None, title=None)
    assert cli._use_youtube_source(args, settings_mod.Settings()) == cli.EXIT_SETUP


def test_transcribe_with_a_link_needs_the_main_components_first(
    fake_youtube: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """The MP3 is not downloaded when the sheet music could not be made anyway."""
    assert cli.main(["--lang", "en", "transcribe", URL]) == cli.EXIT_SETUP
    assert "Some components are not installed" in capsys.readouterr().err
    assert "used_runtime" not in fake_youtube


# -- setup --youtube ----------------------------------------------------------------------------
@pytest.fixture
def server() -> Iterator[str]:
    yield from serve()


def test_setup_youtube_installs_the_helper(
    server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    deno, files = _fake_deno(server)
    Handler.files.update(files)

    def factory(user: settings_mod.Settings | None = None) -> manager_mod.OptionalComponentManager:
        m = manager_mod.OptionalComponentManager(tmp_path / "components", "linux-x86_64")
        m.components = [deno]
        return m

    monkeypatch.setattr(manager_mod, "optional_manager_from_settings", factory)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr("notirua.components.manifest.JS_RUNTIME", deno)
    # no consent given: nothing is downloaded
    assert cli.main(["--lang", "en", "setup", "--youtube"]) == cli.EXIT_USAGE
    assert not (tmp_path / "components" / "deno").exists()
    assert "--accept-licenses" in capsys.readouterr().err
    assert cli.main(["--lang", "en", "setup", "--youtube", "--accept-licenses"]) == cli.EXIT_OK
    assert (tmp_path / "components" / "deno" / "deno").is_file()
    assert "The helper program is installed." in capsys.readouterr().out
    # second run: already there
    assert cli.main(["--lang", "en", "setup", "--youtube"]) == cli.EXIT_OK
    assert "is installed" in capsys.readouterr().out


def test_components_lists_the_helper(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--lang", "en", "components"]) == cli.EXIT_OK
    lines = capsys.readouterr().out.splitlines()
    assert any(line.startswith("deno") and "not installed" in line for line in lines)
    assert any(line.startswith("htdemucs_6s") for line in lines)


def test_check_reports_a_working_installation(
    fake_youtube: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--lang", "en", "youtube", "--check"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "✓ yt-dlp:" in out and "✓ yt-dlp-ejs:" in out and "✓ certifi:" in out
    assert "✓ deno:" in out  # the fake helper
    fake_youtube["runtime"] = None
    assert cli.main(["--lang", "en", "youtube", "--check"]) == cli.EXIT_OK  # Deno is optional
    assert "– deno: -" in capsys.readouterr().out


def test_check_fails_when_a_part_is_missing(
    fake_youtube: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import builtins

    real_import = builtins.__import__

    def no_certifi(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "certifi":
            raise ImportError("no certifi")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_certifi)
    assert cli.main(["--lang", "en", "youtube", "--check"]) == cli.EXIT_ERROR
    assert "✗ certifi:" in capsys.readouterr().out


def test_youtube_without_a_link_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--lang", "en", "youtube"]) == cli.EXIT_USAGE
    assert "Give the link" in capsys.readouterr().err


def test_proxy_option_and_setting_reach_the_client(
    fake_youtube: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str | None] = []
    real = cli.yt.YoutubeClient

    def client(runtime: Path | None = None, proxy: str | None = None, **_kw: Any) -> Any:
        seen.append(proxy)
        return real(runtime, ydl_factory=lambda o: FakeYdl(o, **fake_youtube["kwargs"]))

    monkeypatch.setattr(cli.yt, "YoutubeClient", client)
    assert cli.main(["youtube", URL, "--out", str(tmp_path)]) == cli.EXIT_OK
    assert cli.main(["youtube", URL, "--out", str(tmp_path), "--proxy", "proxy.corp:8080"]) == 0
    user = settings_mod.load()
    user.proxy = "http://saved.corp:3128"
    settings_mod.save(user)
    assert cli.main(["youtube", URL, "--out", str(tmp_path)]) == cli.EXIT_OK
    assert seen == [None, "proxy.corp:8080", "http://saved.corp:3128"]


def test_a_bad_proxy_address_is_a_usage_error(
    fake_youtube: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--lang", "en", "youtube", URL, "--proxy", "nonsense"]) == cli.EXIT_USAGE
    assert "not a proxy address" in capsys.readouterr().err
