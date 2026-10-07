"""The YouTube link flow of the window (0.5.0): paste, validate, save the MP3, go on to the score.

yt-dlp and the pipeline engines are fakes and downloads use a local server: no network.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QMessageBox
from pytestqt.qtbot import QtBot

from notirua import settings as settings_mod
from notirua.components.manager import ComponentManager, OptionalComponentManager
from notirua.components.manifest import JS_RUNTIME
from notirua.core import mix
from notirua.core import youtube as yt
from notirua.gui.main_window import MainWindow
from tests.component_fakes import Handler, serve
from tests.gui_fakes import FakeJob, make_pdf, no_components
from tests.test_gui import WAIT_MS, wait_result
from tests.test_js_runtime_component import _fake_deno
from tests.test_youtube import ID, FakeYdl, _info

URL = f"https://www.youtube.com/watch?v={ID}"

needs_mp3 = pytest.mark.skipif("mp3" not in mix.available_formats(), reason="no MP3 encoder")


@pytest.fixture
def pdf_bytes(qapp: QApplication, tmp_path: Path) -> bytes:
    return make_pdf(tmp_path / "pages.pdf")


@pytest.fixture
def job(tmp_path: Path, pdf_bytes: bytes) -> FakeJob:
    return FakeJob(tmp_path, pdf_bytes)


@pytest.fixture
def user(tmp_path: Path) -> settings_mod.Settings:
    return settings_mod.Settings(
        components_dir=str(tmp_path / "components"),
        consent=ComponentManager.make_consent([]),
    )


@pytest.fixture
def server() -> Iterator[str]:
    yield from serve()


def make_window(
    qtbot: QtBot,
    user: settings_mod.Settings,
    job: FakeJob,
    client_kwargs: Callable[[], dict[str, Any]] | None = None,
    runtime: Path | None = Path("/fake/deno"),
) -> MainWindow:
    calls: list[int] = []

    def factory(_runtime: Path | None) -> yt.YoutubeClient:
        calls.append(1)
        extra = client_kwargs() if client_kwargs else {}
        return yt.YoutubeClient(ydl_factory=lambda options: FakeYdl(options, **extra))

    window = MainWindow(
        user, pipeline=job.pipeline, manager_factory=no_components, youtube_client_factory=factory
    )
    window.js_runtime_path = lambda: runtime  # type: ignore[method-assign]
    window.client_calls = calls  # type: ignore[attr-defined]
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


def enter_link(window: MainWindow, text: str = URL) -> None:
    window.file_page.youtube.link_edit.setText(text)


# -- the box ------------------------------------------------------------------------
def test_the_first_screen_explains_links(
    qtbot: QtBot, user: settings_mod.Settings, job: FakeJob
) -> None:
    window = make_window(qtbot, user, job)
    box = window.file_page.youtube
    assert window.stack.currentWidget() is window.file_page
    assert box.link_edit.placeholderText() == "Paste a YouTube link"
    assert not box.save_button.isEnabled()
    assert box.make_score.isChecked()
    assert box.save_button.text() == "Save audio and make sheet music"
    box.make_score.setChecked(False)
    assert box.save_button.text() == "Save audio"
    assert [box.quality.itemData(i) for i in range(box.quality.count())] == [
        128,
        160,
        192,
        256,
        320,
    ]
    assert box.quality.currentData() == 160


@pytest.mark.parametrize(
    "text", ["hello", "https://example.com/watch?v=" + ID, "https://youtu.be/"]
)
def test_invalid_links_are_refused_while_typing(
    qtbot: QtBot, user: settings_mod.Settings, job: FakeJob, text: str
) -> None:
    window = make_window(qtbot, user, job)
    box = window.file_page.youtube
    enter_link(window, text)
    assert not box.save_button.isEnabled()
    assert "not a link to a single YouTube video" in box.status.text()
    enter_link(window, URL)
    assert box.save_button.isEnabled()
    assert box.status.text().startswith("✓")
    enter_link(window, "")
    assert not box.save_button.isEnabled()


def test_clipboard_link_is_offered_and_pasted(
    qtbot: QtBot, user: settings_mod.Settings, job: FakeJob
) -> None:
    clipboard = QApplication.clipboard()
    clipboard.setText(f"Listen: https://youtu.be/{ID}?si=abc, nice")
    window = make_window(qtbot, user, job)
    box = window.file_page.youtube
    window.show_file_page()
    assert "clipboard" in box.status.text()
    assert box.paste_from_clipboard()
    assert box.link_edit.text() == URL
    assert box.save_button.isEnabled()
    # Ctrl+V on the first screen does the same
    enter_link(window, "")
    window._shortcut_paste()
    assert box.link_edit.text() == URL
    # nothing useful in the clipboard
    enter_link(window, "")
    clipboard.setText("just some text")
    assert not box.paste_from_clipboard()
    assert "no YouTube link in the clipboard" in box.status.text()
    assert box.link_edit.text() == ""


def test_dropping_a_link_fills_the_box(
    qtbot: QtBot, user: settings_mod.Settings, job: FakeJob
) -> None:
    window = make_window(qtbot, user, job)
    mime = QMimeData()
    mime.setUrls([QUrl(f"https://youtu.be/{ID}")])
    event = QDropEvent(
        QPointF(5, 5),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(event)
    assert window.file_page.youtube.link_edit.text() == URL
    assert window.stack.currentWidget() is window.file_page
    assert not window.client_calls  # type: ignore[attr-defined]  # nothing starts by itself


# -- saving the audio and going on ---------------------------------------------------------
@needs_mp3
def test_link_to_score_in_one_go(
    qtbot: QtBot, user: settings_mod.Settings, job: FakeJob, tmp_path: Path
) -> None:
    import av

    window = make_window(qtbot, user, job, lambda: {"info": _info(title="봄날: Spring Day")})
    box = window.file_page.youtube
    enter_link(window)
    box.quality.setCurrentIndex(box.quality.findData(320))
    box.save_button.click()
    wait_result(qtbot, window)
    folder = tmp_path / "user-music"
    saved = folder / "봄날： Spring Day.mp3"
    assert saved.is_file()
    with av.open(str(saved)) as f:
        assert f.streams.audio[0].bit_rate == 320_000
    assert window.saved_audio is not None and window.saved_audio.path == saved
    assert window.input_path == saved
    assert window.result is not None
    assert window.result.title == "봄날: Spring Day"  # the MP3's title tag
    assert job.counter.separate == 1  # the sheet music really was made (separation ran once)
    assert user.youtube_bitrate == 320 and user.youtube_make_score is True
    assert settings_mod.load().youtube_bitrate == 320
    assert str(saved) in user.recent_files


@needs_mp3
def test_audio_only_stops_at_the_options_screen(
    qtbot: QtBot, user: settings_mod.Settings, job: FakeJob, tmp_path: Path
) -> None:
    window = make_window(qtbot, user, job)
    box = window.file_page.youtube
    enter_link(window)
    box.make_score.setChecked(False)
    box.save_button.click()
    qtbot.waitUntil(lambda: window.stack.currentWidget() is window.options_page, timeout=WAIT_MS)
    assert window.options_page.saved_note.isVisible()
    assert "Some Song.mp3" in window.options_page.saved_note.text()
    assert (tmp_path / "user-music" / "Some Song.mp3").is_file()
    assert job.counter.separate == 0  # no score yet: the user chooses the options first
    assert user.youtube_make_score is False
    window.options_page.start_button.click()
    wait_result(qtbot, window)
    assert job.counter.separate == 1


@needs_mp3
def test_a_custom_folder_is_used(
    qtbot: QtBot, user: settings_mod.Settings, job: FakeJob, tmp_path: Path
) -> None:
    user.youtube_dir = str(tmp_path / "my songs")
    window = make_window(qtbot, user, job)
    enter_link(window)
    window.file_page.youtube.save_button.click()
    wait_result(qtbot, window)
    assert (tmp_path / "my songs" / "Some Song.mp3").is_file()


def test_failure_shows_the_reason_and_try_again_repeats(
    qtbot: QtBot, user: settings_mod.Settings, job: FakeJob
) -> None:
    attempts: list[int] = []

    def kwargs() -> dict[str, Any]:
        attempts.append(1)
        return {"fail": RuntimeError("Private video. Sign in")} if len(attempts) == 1 else {}

    window = make_window(qtbot, user, job, kwargs)
    enter_link(window)
    window.file_page.youtube.make_score.setChecked(False)
    window.file_page.youtube.save_button.click()
    qtbot.waitUntil(lambda: window.progress_page.error_box.isVisible(), timeout=WAIT_MS)
    assert window.stack.currentWidget() is window.progress_page
    assert "sign in" in window.progress_page.error_box.title.text()
    assert not window.busy()
    window.progress_page.retry_button.click()
    qtbot.waitUntil(lambda: window.stack.currentWidget() is window.options_page, timeout=WAIT_MS)
    assert len(attempts) == 2


def test_invalid_link_never_reaches_the_network(
    qtbot: QtBot, user: settings_mod.Settings, job: FakeJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text, *_a: shown.append(text))
    window = make_window(qtbot, user, job)
    window.start_youtube("https://example.com", 160, True)
    assert shown and "not a link to a single YouTube video" in shown[0]
    assert window.stack.currentWidget() is window.file_page
    assert not window.client_calls  # type: ignore[attr-defined]
    window.start_youtube(URL, 100, True)  # a bit rate that is not offered
    assert not window.client_calls  # type: ignore[attr-defined]


def test_cancel_returns_to_the_first_screen(
    qtbot: QtBot, user: settings_mod.Settings, job: FakeJob, tmp_path: Path
) -> None:
    class Slow(FakeYdl):
        def process_ie_result(self, info: dict[str, Any], download: bool = True) -> None:
            for _ in range(200):  # the hook raises as soon as the user cancels
                for hook in self.options["progress_hooks"]:
                    hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 10})
                time.sleep(0.02)

    window = MainWindow(
        user,
        pipeline=job.pipeline,
        manager_factory=no_components,
        youtube_client_factory=lambda _r: yt.YoutubeClient(ydl_factory=lambda o: Slow(o)),
    )
    window.js_runtime_path = lambda: Path("/fake/deno")  # type: ignore[method-assign]
    qtbot.addWidget(window)
    window.show()
    enter_link(window)
    window.file_page.youtube.save_button.click()
    qtbot.waitUntil(lambda: window.stack.currentWidget() is window.progress_page, timeout=WAIT_MS)
    qtbot.waitUntil(lambda: window.progress_page.panel.fraction > 0, timeout=WAIT_MS)
    window.progress_page.confirm_cancel = False
    window.progress_page.cancel_button.click()
    qtbot.waitUntil(lambda: window.stack.currentWidget() is window.file_page, timeout=WAIT_MS)
    assert not window.busy()
    assert not list((tmp_path / "user-music").glob("*.mp3"))


# -- the helper program (Deno) -----------------------------------------------------------
def test_declining_the_helper_downloads_nothing(
    qtbot: QtBot, user: settings_mod.Settings, job: FakeJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = make_window(qtbot, user, job, runtime=None)
    asked: list[bool] = []
    window.confirm_runtime_download = lambda: asked.append(True) or False  # type: ignore[method-assign]
    window.runtime_manager_factory = lambda _u: pytest.fail("must not install")  # type: ignore[assignment,return-value]
    window.start_youtube(URL, 160, True)
    assert asked == [True]
    assert window.stack.currentWidget() is window.file_page
    assert not window.client_calls  # type: ignore[attr-defined]


@needs_mp3
def test_accepting_the_helper_installs_it_and_goes_on(
    qtbot: QtBot, user: settings_mod.Settings, job: FakeJob, server: str, tmp_path: Path
) -> None:
    deno, files = _fake_deno(server)
    Handler.files.update(files)
    window = make_window(qtbot, user, job, runtime=None)
    manager = OptionalComponentManager(tmp_path / "components", "linux-x86_64")
    manager.components = [deno]
    window.runtime_manager_factory = lambda _u: manager
    # make_window faked the lookup; use the real one now, on the fake component
    del window.js_runtime_path
    import notirua.gui.main_window as mw

    mw.JS_RUNTIME = deno  # type: ignore[misc]
    try:
        window.confirm_runtime_download = lambda: True  # type: ignore[method-assign]
        window.file_page.youtube.make_score.setChecked(False)
        enter_link(window)
        window.file_page.youtube.save_button.click()
        qtbot.waitUntil(
            lambda: window.stack.currentWidget() is window.options_page, timeout=WAIT_MS
        )
    finally:
        mw.JS_RUNTIME = JS_RUNTIME  # type: ignore[misc]
    assert manager.require("deno").is_file()
    assert (tmp_path / "user-music" / "Some Song.mp3").is_file()
    assert window.client_calls == [1]  # type: ignore[attr-defined]


def test_the_consent_dialog_names_size_license_and_source(
    qtbot: QtBot, user: settings_mod.Settings, job: FakeJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = make_window(qtbot, user, job, runtime=None)
    window.runtime_manager_factory = lambda u: OptionalComponentManager(
        u.components_path, "windows-x86_64"
    )
    seen: dict[str, str] = {}

    def fake_exec(box: QMessageBox) -> int:
        seen["text"] = box.text() + "\n" + box.informativeText()
        seen["buttons"] = ", ".join(b.text() for b in box.buttons())
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    assert window.confirm_runtime_download() is False  # nothing was clicked
    text = seen["text"]
    assert "Helper program (Deno)" in text
    assert "MIT" in text and "github.com" in text
    assert "40.7 MB" in text  # the pinned download size of the Windows build
    assert "Download and continue" in seen["buttons"]


# -- the proxy ------------------------------------------------------------------------------
def test_the_window_uses_the_proxy_from_the_settings(
    qtbot: QtBot, user: settings_mod.Settings
) -> None:
    window = MainWindow(user, manager_factory=no_components)
    qtbot.addWidget(window)
    assert window.youtube_client_factory(None).proxy is None
    user.proxy = "proxy.corp:8080"
    assert window.youtube_client_factory(None).proxy == "http://proxy.corp:8080"
    user.proxy = "garbage"  # a hand-edited settings file must not stop the window
    assert window.youtube_client_factory(None).proxy is None


def test_settings_dialog_saves_a_valid_proxy_and_refuses_a_bad_one(
    qtbot: QtBot, user: settings_mod.Settings
) -> None:
    from notirua.gui.settings_dialog import SettingsDialog

    dialog = SettingsDialog(user, no_components(user))
    qtbot.addWidget(dialog)
    dialog.proxy.setText("proxy.corp:8080")
    dialog.proxy.editingFinished.emit()
    assert user.proxy == "http://proxy.corp:8080"
    assert dialog.proxy.text() == "http://proxy.corp:8080"
    assert settings_mod.load().proxy == "http://proxy.corp:8080"
    dialog.proxy.setText("not a proxy")
    dialog.proxy.editingFinished.emit()
    assert user.proxy == "http://proxy.corp:8080"  # unchanged
    assert "not a proxy address" in dialog.proxy_note.text()
    dialog.proxy.setText("")
    dialog.proxy.editingFinished.emit()
    assert user.proxy is None
    assert settings_mod.load().proxy is None
