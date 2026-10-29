"""The TikTok link flow of the window (0.6.0): download, then the options screen.

The download is a fake: no network.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from notirua import settings as settings_mod
from notirua.components.manager import ComponentManager
from notirua.core.errors import VideoUnavailableError
from notirua.core.fetch import Downloaded
from notirua.gui import main_window
from notirua.gui.main_window import MainWindow
from tests import synth
from tests.gui_fakes import FakeJob, make_pdf, no_components
from tests.test_gui import WAIT_MS, wait_result

TIKTOK = "https://www.tiktok.com/@name/video/6718335390845095173"


@pytest.fixture
def job(qapp: QApplication, tmp_path: Path) -> FakeJob:
    return FakeJob(tmp_path, make_pdf(tmp_path / "pages.pdf"))


@pytest.fixture
def song(tmp_path: Path) -> Path:
    audio = synth.to_stereo(synth.render_notes(synth.scale_notes(120), total_s=6.0))
    return synth.write_wav(tmp_path / "tiktok.wav", audio)


@pytest.fixture
def user(tmp_path: Path) -> settings_mod.Settings:
    return settings_mod.Settings(
        components_dir=str(tmp_path / "components"),
        consent=ComponentManager.make_consent([]),
    )


def make_window(qtbot: QtBot, user: settings_mod.Settings, job: FakeJob) -> MainWindow:
    window = MainWindow(user, pipeline=job.pipeline, manager_factory=no_components)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


def test_link_downloads_then_opens_options_with_its_title(
    qtbot: QtBot,
    user: settings_mod.Settings,
    job: FakeJob,
    song: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def fake_download(url: str, folder: Path, progress: Any, cancel: Any) -> Downloaded:
        seen.append(url)
        return Downloaded(path=song, title="BTS - Spring Day")

    monkeypatch.setattr(main_window, "download_with_progress", fake_download)
    window = make_window(qtbot, user, job)
    page = window.file_page
    page.tiktok_edit.setText(f"좋아요 {TIKTOK} 들어보세요")
    qtbot.mouseClick(page.tiktok_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.stack.currentWidget() is window.options_page, timeout=WAIT_MS)
    assert seen == [TIKTOK]
    assert window.options_page.title_edit.text() == "BTS - Spring Day"
    assert str(song) not in user.recent_files, "temporary downloads are not remembered"
    qtbot.mouseClick(window.options_page.start_button, Qt.MouseButton.LeftButton)
    wait_result(qtbot, window)


def test_link_from_another_site_is_explained(
    qtbot: QtBot, user: settings_mod.Settings, job: FakeJob
) -> None:
    window = make_window(qtbot, user, job)
    window.file_page.tiktok_edit.setText("https://www.example.com/watch?v=1")
    window.file_page.submit_tiktok()
    assert window.stack.currentWidget() is window.file_page
    assert "TikTok" in window.file_page.tiktok_status.text()


def test_failure_shows_the_reason_and_retry_downloads_again(
    qtbot: QtBot,
    user: settings_mod.Settings,
    job: FakeJob,
    song: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def fake_download(url: str, folder: Path, progress: Any, cancel: Any) -> Downloaded:
        calls.append(1)
        if len(calls) == 1:
            raise VideoUnavailableError("private")
        return Downloaded(path=song, title=None)

    monkeypatch.setattr(main_window, "download_with_progress", fake_download)
    window = make_window(qtbot, user, job)
    window.file_page.tiktok_edit.setText(TIKTOK)
    window.file_page.submit_tiktok()
    qtbot.waitUntil(lambda: window.progress_page.error_box.isVisible(), timeout=WAIT_MS)
    assert window.stack.currentWidget() is window.progress_page
    window.retry_job()
    qtbot.waitUntil(lambda: window.stack.currentWidget() is window.options_page, timeout=WAIT_MS)
    assert len(calls) == 2


def test_cancel_returns_to_the_first_screen(
    qtbot: QtBot,
    user: settings_mod.Settings,
    job: FakeJob,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_download(url: str, folder: Path, progress: Any, cancel: Any) -> Downloaded:
        while not cancel.cancelled:
            time.sleep(0.01)
        cancel.raise_if_cancelled()
        raise AssertionError("unreachable")

    monkeypatch.setattr(main_window, "download_with_progress", fake_download)
    window = make_window(qtbot, user, job)
    window.file_page.tiktok_edit.setText(TIKTOK)
    window.file_page.submit_tiktok()
    qtbot.waitUntil(lambda: window.busy(), timeout=WAIT_MS)
    window.cancel_job()
    qtbot.waitUntil(lambda: window.stack.currentWidget() is window.file_page, timeout=WAIT_MS)
