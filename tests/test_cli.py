"""CLI entry behavior: plain `notirua` opens the window (setup first on a new machine)."""

from __future__ import annotations

import argparse
import sys

import pytest

from notirua import cli
from notirua import settings as settings_mod
from notirua.gui import app as gui_app


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    calls: list[str | None] = []

    def fake_main(_argv: object = None, language: str | None = None) -> int:
        calls.append(language)
        return 0

    # cli.main() rebinds these; monkeypatch restores them for the other tests.
    monkeypatch.setattr(argparse, "_", argparse._)  # type: ignore[attr-defined]
    monkeypatch.setattr(argparse, "ngettext", argparse.ngettext)  # type: ignore[attr-defined]
    monkeypatch.setattr(gui_app, "main", fake_main)
    monkeypatch.setattr(gui_app, "display_available", lambda: True)
    return calls


def test_no_command_opens_the_window(opened: list[str | None]) -> None:
    assert cli.main([]) == 0
    assert cli.main(["gui"]) == 0
    assert cli.main(["--lang", "ko"]) == 0
    assert opened == [None, None, "ko"]


def test_no_screen_prints_help_instead(
    opened: list[str | None],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(gui_app, "display_available", lambda: False)
    assert cli.main(["--lang", "en"]) == cli.EXIT_USAGE
    captured = capsys.readouterr()
    assert captured.out.startswith("usage: notirua")
    assert "No screen found" in captured.err
    assert opened == []


def test_display_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gui_app.sys, "platform", "linux")
    for var in ("QT_QPA_PLATFORM", "DISPLAY", "WAYLAND_DISPLAY"):
        monkeypatch.delenv(var, raising=False)
    assert not gui_app.display_available()
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert gui_app.display_available()
    monkeypatch.setattr(gui_app.sys, "platform", "darwin")
    monkeypatch.delenv("WAYLAND_DISPLAY")
    assert gui_app.display_available()


def test_first_run_creates_settings_and_starts_on_setup(
    qtbot: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QApplication

    shown: list[object] = []
    monkeypatch.setattr(QApplication, "exec", lambda _self: 0)
    monkeypatch.setattr("notirua.gui.main_window.MainWindow.show", lambda self: shown.append(self))
    assert not settings_mod.settings_path().exists()
    assert gui_app.main([]) == 0
    assert settings_mod.settings_path().is_file()
    window = shown[0]
    assert window.stack.currentWidget() is window.setup_page  # type: ignore[attr-defined]
    window.close()  # type: ignore[attr-defined]


def test_app_icon_has_every_size(qapp: object) -> None:
    icon = gui_app.app_icon()
    sizes = {s.width() for s in icon.availableSizes()}
    assert {16, 32, 64, 128, 256, 512, 1024} <= sizes


def test_version_flag(opened: list[str | None], capsys: pytest.CaptureFixture[str]) -> None:
    import notirua

    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"notirua {notirua.__version__}"
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert notirua.__version__ == pyproject["project"]["version"], "run `uv sync` after a bump"


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS menu bar name")
def test_macos_menu_bar_uses_the_app_name() -> None:
    from notirua.gui import macos

    assert macos.set_app_name("Notirua")
    assert macos.app_name() == "Notirua"


def test_redirected_output_in_a_narrow_code_page_does_not_crash(
    opened: list[str | None], monkeypatch: pytest.MonkeyPatch
) -> None:
    import io

    raw = io.BytesIO()
    narrow = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", narrow)
    assert cli.main(["--lang", "ko", "cache"]) == cli.EXIT_OK
    narrow.flush()
    assert b"?" in raw.getvalue()
