"""GUI tests with pytest-qt (SPEC 9.5, M4): setup consent paths, the four-screen flow,
cancel, failure, transposition, responsiveness, and keyboard-only use.

Engines are fakes and downloads go to a local HTTP server, so these run offline.
"""

from __future__ import annotations

import itertools
import socket
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDropEvent
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from pytestqt.qtbot import QtBot

from notirua import settings as settings_mod
from notirua.components import manager as manager_mod
from notirua.components import manifest
from notirua.components.manager import ComponentManager
from notirua.core.pipeline import Pipeline
from notirua.gui.main_window import MainWindow
from notirua.gui.widgets import STATE_ICONS, ProgressPanel
from tests import synth
from tests.component_fakes import Handler, fake_components
from tests.gui_fakes import FakeJob, make_pdf, no_components

WAIT_MS = 15_000


# -- fixtures ------------------------------------------------------------------
@pytest.fixture
def pdf_bytes(qapp: QApplication, tmp_path: Path) -> bytes:
    return make_pdf(tmp_path / "pages.pdf")


@pytest.fixture
def job(tmp_path: Path, pdf_bytes: bytes) -> FakeJob:
    return FakeJob(tmp_path, pdf_bytes)


@pytest.fixture
def song(tmp_path: Path) -> Path:
    audio = synth.to_stereo(synth.render_notes(synth.scale_notes(120), total_s=6.0))
    return synth.write_wav(tmp_path / "봄날 song.wav", audio)


@pytest.fixture
def ready_user(tmp_path: Path) -> settings_mod.Settings:
    """Settings for a machine where setup is already done."""
    return settings_mod.Settings(
        components_dir=str(tmp_path / "components"),
        consent=ComponentManager.make_consent([]),
    )


@pytest.fixture
def answer_yes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    asked: list[str] = []

    def question(_parent: object, _title: str, text: str, *_a: object) -> object:
        asked.append(text)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", question)
    return asked


def make_window(
    qtbot: QtBot,
    user: settings_mod.Settings,
    factory: Callable[[settings_mod.Settings], ComponentManager],
    pipeline: Pipeline | None = None,
) -> MainWindow:
    window = MainWindow(user, pipeline=pipeline, manager_factory=factory)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


def wait_result(qtbot: QtBot, window: MainWindow) -> None:
    qtbot.waitUntil(lambda: window.stack.currentWidget() is window.result_page, timeout=WAIT_MS)


# -- first-run setup (FR-10) -----------------------------------------------------
def fake_factory(base: str) -> Callable[[settings_mod.Settings], ComponentManager]:
    model, tool, _files = fake_components(base)

    def factory(user: settings_mod.Settings) -> ComponentManager:
        m = ComponentManager(user.components_path, platform_key="linux-x86_64")
        m.components = [model, tool]
        return m

    return factory


def check_all(window: MainWindow) -> None:
    for box in window.setup_page._checks.values():
        box.setChecked(True)


def test_no_network_before_agree(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []

    def guard(*args: object, **_kwargs: object) -> None:
        calls.append(args)
        raise OSError("network blocked by test")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
    monkeypatch.setattr(socket, "getaddrinfo", guard)
    user = settings_mod.Settings(components_dir=str(tmp_path / "c"))
    window = make_window(qtbot, user, fake_factory("http://downloads.invalid"))

    assert window.stack.currentWidget() is window.setup_page
    page = window.setup_page
    assert not page.agree_button.isEnabled(), "nothing is pre-checked"
    assert not any(c.isChecked() for c in page._checks.values())
    check_all(window)
    assert page.agree_button.isEnabled()
    assert calls == [], "no request before the button is pressed"
    assert user.consent is None

    qtbot.mouseClick(page.agree_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(page.error_box.isVisible, timeout=WAIT_MS)
    assert calls, "the download starts only after agreeing"
    assert user.consent is not None


def test_not_now_keeps_app_open_with_install_button(qtbot: QtBot, tmp_path: Path) -> None:
    user = settings_mod.Settings(components_dir=str(tmp_path / "c"))
    window = make_window(qtbot, user, fake_factory("http://downloads.invalid"))
    qtbot.mouseClick(window.setup_page.later_button, Qt.MouseButton.LeftButton)
    assert window.isVisible()
    assert window.stack.currentWidget() is window.file_page
    assert window.banner.isVisible()
    qtbot.mouseClick(window.banner_button, Qt.MouseButton.LeftButton)
    assert window.stack.currentWidget() is window.setup_page


def test_download_failure_then_retry_resumes(
    qtbot: QtBot,
    tmp_path: Path,
    server: str,
) -> None:
    factory = fake_factory(server)
    _m, _t, files = fake_components(server)
    Handler.files = files
    Handler.fail_after = 10_000
    user = settings_mod.Settings(components_dir=str(tmp_path / "c"))
    window = make_window(qtbot, user, factory)
    page = window.setup_page
    check_all(window)
    qtbot.mouseClick(page.agree_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(page.error_box.isVisible, timeout=WAIT_MS)
    assert "E-DOWNLOAD" in page.error_box.code.text()
    assert page.retry_button.isVisible()
    states = page.panel.stage_list if page.panel else None
    assert states is not None and "failed" in [states.state(s) for s in states.stages()]

    Handler.fail_after = None
    qtbot.mouseClick(page.retry_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.stack.currentWidget() is window.file_page, timeout=WAIT_MS)
    assert not factory(user).missing()
    assert ComponentManager.consent_is_current(user.consent, factory(user).components)


def test_checksum_mismatch_is_explained(
    qtbot: QtBot,
    tmp_path: Path,
    server: str,
) -> None:
    _m, _t, files = fake_components(server)
    Handler.files = {k: b"x" * len(v) for k, v in files.items()}
    window = make_window(
        qtbot, settings_mod.Settings(components_dir=str(tmp_path / "c")), fake_factory(server)
    )
    check_all(window)
    qtbot.mouseClick(window.setup_page.agree_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(window.setup_page.error_box.isVisible, timeout=WAIT_MS)
    assert "E-DOWNLOAD-CHECKSUM" in window.setup_page.error_box.code.text()


def test_not_enough_space_blocks_install(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Usage:
        free = 10

    monkeypatch.setattr(manager_mod.shutil, "disk_usage", lambda _p: Usage())
    window = make_window(
        qtbot,
        settings_mod.Settings(components_dir=str(tmp_path / "c")),
        fake_factory("http://downloads.invalid"),
    )
    check_all(window)
    assert not window.setup_page.agree_button.isEnabled()
    assert window.setup_page.space_error.isVisible()
    assert window.setup_page.space_error.text().startswith("ⓧ")


def test_offline_bundle_install(
    qtbot: QtBot,
    tmp_path: Path,
    server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _m, _t, files = fake_components(server)
    src = tmp_path / "src"
    src.mkdir()
    for name, data in files.items():
        (src / name.lstrip("/")).write_bytes(data)
    bundle = ComponentManager.build_bundle(
        {"model.onnx": src / "model.onnx", "tool.tar.gz": src / "tool.tar.gz"},
        tmp_path / "bundle.zip",
    )
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_a, **_k: (str(bundle), ""))
    user = settings_mod.Settings(components_dir=str(tmp_path / "c"))
    factory = fake_factory("http://downloads.invalid")
    window = make_window(qtbot, user, factory)
    qtbot.mouseClick(window.setup_page.bundle_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.stack.currentWidget() is window.file_page, timeout=WAIT_MS)
    assert not factory(user).missing()
    assert user.consent is not None


def test_consent_is_asked_again_after_manifest_change(
    qtbot: QtBot,
    tmp_path: Path,
    server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _m, _t, files = fake_components(server)
    Handler.files = files
    user = settings_mod.Settings(components_dir=str(tmp_path / "c"))
    factory = fake_factory(server)
    m = factory(user)
    consent = m.make_consent(m.components)
    m.install(m.components, consent)
    user.consent = consent
    assert make_window(qtbot, user, factory).stack.currentWidget().__class__.__name__ == "FilePage"

    monkeypatch.setattr(manager_mod, "MANIFEST_VERSION", manifest.MANIFEST_VERSION + 1)
    window = make_window(qtbot, user, factory)
    assert window.stack.currentWidget() is window.setup_page
    assert not window.setup_page.agree_button.isEnabled()
    check_all(window)
    qtbot.mouseClick(window.setup_page.agree_button, Qt.MouseButton.LeftButton)
    assert window.stack.currentWidget() is window.file_page
    assert user.consent is not None
    assert user.consent.manifest_version == manifest.MANIFEST_VERSION + 1


# -- the four screens (FR-8, FR-11) ---------------------------------------------
def drop_file(window: MainWindow, path: Path) -> None:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    event = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(event)


def test_drop_then_one_click_makes_sheet_music(
    qtbot: QtBot, ready_user: settings_mod.Settings, job: FakeJob, song: Path
) -> None:
    window = make_window(qtbot, ready_user, no_components, job.pipeline)
    assert window.stack.currentWidget() is window.file_page
    drop_file(window, song)  # click 1
    assert window.stack.currentWidget() is window.options_page
    assert window.options_page.title_edit.text() == "봄날 song"
    qtbot.mouseClick(window.options_page.start_button, Qt.MouseButton.LeftButton)  # click 2
    wait_result(qtbot, window)

    page = window.result_page
    assert page.tabs.count() == 3  # All, Guitar, Piano
    assert page.document.status() == QPdfDocument.Status.Ready
    assert page.page_count() == 2
    assert page.page_label.text() == "1 / 2"
    qtbot.mouseClick(page.next_page, Qt.MouseButton.LeftButton)
    assert page.current_page() == 1
    assert "Vocals" in page.skipped.text()
    assert window.progress_page.panel.fraction == 1.0
    assert str(song) in ready_user.recent_files


def test_transpose_only_redraws(
    qtbot: QtBot, ready_user: settings_mod.Settings, job: FakeJob, song: Path
) -> None:
    window = make_window(qtbot, ready_user, no_components, job.pipeline)
    window.open_file(song)
    window.options_page.start_button.click()
    wait_result(qtbot, window)
    first_key = window.result_page.key_combo.currentData()
    engraved = job.counter.engrave
    qtbot.mouseClick(window.result_page.up, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.result_page.up, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            job.counter.engrave > engraved
            and window.render_task is not None
            and not window.render_task.running
            and window.result is not None
            and window.result.score.key != first_key
        ),
        timeout=WAIT_MS,
    )
    qtbot.waitUntil(lambda: not window.result_page.busy.isVisible(), timeout=WAIT_MS)
    assert job.counter.separate == 1 and job.counter.transcribe == 2
    assert window.result_page.semitones == 2
    assert window.result_page.value.text() == "+2"
    assert window.result_page.key_combo.currentData() == window.result.score.key


def test_start_over_runs_everything_once_then_redraws_from_saved_results(
    qtbot: QtBot, ready_user: settings_mod.Settings, job: FakeJob, song: Path
) -> None:
    window = make_window(qtbot, ready_user, no_components, job.pipeline)
    window.open_file(song)
    window.options_page.start_button.click()
    wait_result(qtbot, window)
    assert job.counter.separate == 1

    window.open_file(song)
    assert not window.options_page.fresh.isChecked()
    window.options_page.fresh.setChecked(True)
    window.options_page.start_button.click()
    wait_result(qtbot, window)
    assert job.counter.separate == 2
    engraved = job.counter.engrave
    qtbot.mouseClick(window.result_page.up, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            job.counter.engrave > engraved
            and window.render_task is not None
            and not window.render_task.running
        ),
        timeout=WAIT_MS,
    )
    assert job.counter.separate == 2


def test_choosing_a_key_sets_semitones(
    qtbot: QtBot, ready_user: settings_mod.Settings, job: FakeJob, song: Path
) -> None:
    window = make_window(qtbot, ready_user, no_components, job.pipeline)
    window.open_file(song)
    window.options_page.start_button.click()
    wait_result(qtbot, window)
    page = window.result_page
    original = page.original_key
    index = (page.key_combo.currentIndex() + 5) % page.key_combo.count()
    page.key_combo.setCurrentIndex(index)
    page.key_combo.activated.emit(index)
    assert page.semitones != 0
    from notirua.core.pipeline import transposed_key

    assert transposed_key(original, page.semitones) == page.key_combo.itemData(index)


def test_cancel_returns_to_options_within_3s(
    qtbot: QtBot,
    ready_user: settings_mod.Settings,
    job: FakeJob,
    song: Path,
    answer_yes: list[str],
) -> None:
    job.delay = 30.0
    window = make_window(qtbot, ready_user, no_components, job.pipeline)
    window.open_file(song)
    window.options_page.start_button.click()
    qtbot.waitUntil(
        lambda: window.progress_page.panel.stage_list.state("separate") == "running",
        timeout=WAIT_MS,
    )
    started = time.monotonic()
    qtbot.mouseClick(window.progress_page.cancel_button, Qt.MouseButton.LeftButton)
    assert answer_yes, "cancel asks for confirmation"
    qtbot.waitUntil(lambda: window.stack.currentWidget() is window.options_page, timeout=3000)
    assert time.monotonic() - started < 3.0
    assert not window.busy()


def test_failure_marks_stage_and_retry_reuses_work(
    qtbot: QtBot, ready_user: settings_mod.Settings, job: FakeJob, song: Path
) -> None:
    job.engraver.fail = True
    window = make_window(qtbot, ready_user, no_components, job.pipeline)
    window.open_file(song)
    window.options_page.start_button.click()
    page = window.progress_page
    qtbot.waitUntil(page.error_box.isVisible, timeout=WAIT_MS)
    assert page.panel.stage_list.state("engrave") == "failed"
    assert page.panel.stage_list.text("engrave").startswith(STATE_ICONS["failed"])
    assert "E-ENGRAVE" in page.error_box.code.text()
    assert not page.error_box.details.isVisible(), "code and log folder start folded"
    assert page.retry_button.isDefault()

    job.engraver.fail = False
    qtbot.mouseClick(page.retry_button, Qt.MouseButton.LeftButton)
    wait_result(qtbot, window)
    assert job.counter.separate == 1, "finished stages come from the cache"


def test_unreadable_file_suggests_another_file(
    qtbot: QtBot, ready_user: settings_mod.Settings, job: FakeJob, tmp_path: Path
) -> None:
    bad = tmp_path / "not audio.mp3"
    bad.write_bytes(b"this is not audio" * 100)
    window = make_window(qtbot, ready_user, no_components, job.pipeline)
    window.open_file(bad)
    window.options_page.start_button.click()
    page = window.progress_page
    qtbot.waitUntil(page.error_box.isVisible, timeout=WAIT_MS)
    assert page.panel.stage_list.state("decode") == "failed"
    assert page.other_button.isDefault() and not page.retry_button.isDefault()
    assert "E-DECODE" in page.error_box.code.text()


def test_ui_thread_stays_responsive(
    qtbot: QtBot, ready_user: settings_mod.Settings, job: FakeJob, song: Path
) -> None:
    """SPEC 9.5: while a job runs, the UI thread never stalls for 100 ms."""
    job.delay = 1.5
    window = make_window(qtbot, ready_user, no_components, job.pipeline)
    ticks: list[float] = []

    def tick() -> None:
        # Only while the job runs; opening the finished result is not part of the job.
        if window.busy():
            ticks.append(time.monotonic())

    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(tick)
    window.open_file(song)
    timer.start()
    window.options_page.start_button.click()
    wait_result(qtbot, window)
    timer.stop()
    gaps = [b - a for a, b in itertools.pairwise(ticks)]
    assert len(gaps) > 50
    assert max(gaps) < 0.1, f"UI thread blocked for {max(gaps):.3f} s"


def test_keyboard_only_from_file_to_saving(
    qtbot: QtBot,
    ready_user: settings_mod.Settings,
    job: FakeJob,
    song: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "saved"
    out.mkdir()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_a, **_k: (str(song), ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_a, **_k: str(out))
    window = make_window(qtbot, ready_user, no_components, job.pipeline)
    window.activateWindow()

    def press_focused(expected: object) -> None:
        qtbot.waitUntil(lambda: QApplication.focusWidget() is expected, timeout=WAIT_MS)
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key.Key_Space)

    press_focused(window.file_page.pick_button)
    assert window.stack.currentWidget() is window.options_page
    press_focused(window.options_page.start_button)
    wait_result(qtbot, window)
    press_focused(window.result_page.save_button)
    saved = sorted(p.name for p in out.iterdir())
    assert len(saved) == 3 and all(n.endswith(".pdf") for n in saved)
    assert "Saved 3 files." in window.result_page.status.text()


def test_save_all_never_overwrites(
    qtbot: QtBot,
    ready_user: settings_mod.Settings,
    job: FakeJob,
    song: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "saved"
    out.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_a, **_k: str(out))
    window = make_window(qtbot, ready_user, no_components, job.pipeline)
    window.open_file(song)
    window.options_page.start_button.click()
    wait_result(qtbot, window)
    window.save_all()
    window.save_all()
    names = {p.name for p in out.iterdir()}
    assert len(names) == 6
    assert any(" (2).pdf" in n for n in names)
    assert ready_user.output_dir == str(out)


def test_missing_components_send_the_job_to_setup(
    qtbot: QtBot, tmp_path: Path, job: FakeJob, song: Path
) -> None:
    user = settings_mod.Settings(components_dir=str(tmp_path / "c"))
    window = make_window(qtbot, user, fake_factory("http://downloads.invalid"), job.pipeline)
    qtbot.mouseClick(window.setup_page.later_button, Qt.MouseButton.LeftButton)
    window.open_file(song)
    window.options_page.start_button.click()
    assert window.stack.currentWidget() is window.setup_page
    assert job.counter.separate == 0


# -- settings ------------------------------------------------------------------
@pytest.fixture
def no_answer(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.No)
    yield


def test_clearing_saved_results_asks_first(
    qtbot: QtBot, ready_user: settings_mod.Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from notirua.gui.settings_dialog import SettingsDialog, jobs_cache_dir

    item = jobs_cache_dir() / "abc" / "x.npy"
    item.parent.mkdir(parents=True)
    item.write_bytes(b"0" * 1000)
    dialog = SettingsDialog(ready_user, no_components(ready_user))
    qtbot.addWidget(dialog)
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.No)
    dialog._clear_cache()
    assert item.exists()
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    dialog._clear_cache()
    assert not item.exists()


def test_removing_a_component_asks_first(
    qtbot: QtBot,
    tmp_path: Path,
    server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from notirua.gui.settings_dialog import SettingsDialog

    _m, _t, files = fake_components(server)
    Handler.files = files
    user = settings_mod.Settings(components_dir=str(tmp_path / "c"))
    m = fake_factory(server)(user)
    m.install(m.components, m.make_consent(m.components))
    dialog = SettingsDialog(user, m)
    qtbot.addWidget(dialog)
    dialog.table.selectRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.No)
    dialog._remove()
    assert not m.missing()
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    with qtbot.waitSignal(dialog.components_changed):
        dialog._remove()
    assert m.missing()


def test_settings_remember_language_and_paper(
    qtbot: QtBot, ready_user: settings_mod.Settings
) -> None:
    from notirua.gui.settings_dialog import SettingsDialog

    dialog = SettingsDialog(ready_user, no_components(ready_user))
    qtbot.addWidget(dialog)
    dialog.language.setCurrentIndex(dialog.language.findData("ko"))
    dialog.paper.setCurrentIndex(dialog.paper.findData("letter"))
    saved = settings_mod.load()
    assert saved.language == "ko" and saved.paper == "letter"
    assert dialog.restart_note.isVisibleTo(dialog)


# -- widgets -------------------------------------------------------------------
def test_progress_panel_never_goes_back(qtbot: QtBot) -> None:
    from notirua.core.progress import ProgressEvent

    panel = ProgressPanel([("a", "Step A")])
    qtbot.addWidget(panel)
    panel.apply(ProgressEvent("t", "a", "running", 0.5, 0.6, "Step A"))
    panel.apply(ProgressEvent("t", "a", "running", 0.2, 0.3, "Step A"))
    assert panel.bar.value() == 600
    assert panel.stage_list.text("a").startswith(STATE_ICONS["running"])
    assert "In progress" in panel.stage_list._rows["a"].accessibleName()


# -- menus and title -------------------------------------------------------------
def test_title_shows_the_version(
    qtbot: QtBot, ready_user: settings_mod.Settings, job: FakeJob, song: Path
) -> None:
    import notirua

    window = make_window(qtbot, ready_user, no_components, job.pipeline)
    assert window.windowTitle() == f"Notirua {notirua.__version__}"
    window.open_file(song)
    window.options_page.start_button.click()
    wait_result(qtbot, window)
    assert window.windowTitle() == f"봄날 song — Notirua {notirua.__version__}"


def test_menus_hold_settings_and_quit(
    qtbot: QtBot,
    ready_user: settings_mod.Settings,
    job: FakeJob,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from notirua.gui.settings_dialog import SettingsDialog

    window = make_window(qtbot, ready_user, no_components, job.pipeline)
    roles = {a.menuRole() for a in window.file_menu.actions() + window.help_menu.actions()}
    assert QAction.MenuRole.PreferencesRole in roles  # macOS: application menu
    assert QAction.MenuRole.QuitRole in roles
    assert QAction.MenuRole.AboutRole in roles
    assert window.settings_action.shortcut().toString() == "Ctrl+,"
    assert window.quit_action.shortcut().toString() == "Ctrl+Q"

    opened: list[str] = []
    monkeypatch.setattr(
        SettingsDialog,
        "exec",
        lambda self: opened.append(self.tabs.tabText(self.tabs.currentIndex())),
    )
    window.settings_action.trigger()
    window.about_action.trigger()
    assert opened == ["General", "About"]

    window.quit_action.trigger()
    assert not window.isVisible()


def test_title_can_be_changed_on_the_result_screen(
    qtbot: QtBot, ready_user: settings_mod.Settings, job: FakeJob, song: Path
) -> None:
    import notirua

    window = make_window(qtbot, ready_user, no_components, job.pipeline)
    window.open_file(song)
    window.options_page.start_button.click()
    wait_result(qtbot, window)
    page = window.result_page
    assert page.title_edit.text() == "봄날 song"

    page.title_edit.setText("  ")
    page.title_edit.editingFinished.emit()
    assert page.title_edit.text() == "봄날 song", "an empty title is put back"

    page.title_edit.setText("새 제목")
    page.title_edit.editingFinished.emit()
    qtbot.waitUntil(
        lambda: window.result is not None and window.result.title == "새 제목", timeout=WAIT_MS
    )
    assert all(p.name.startswith("새 제목") for p in window.result.pdfs.values())
    assert window.windowTitle() == f"새 제목 — Notirua {notirua.__version__}"
    assert job.counter.separate == 1, "only the drawing is redone"

    # Transposing afterwards keeps the new title.
    qtbot.mouseClick(page.up, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            window.result is not None
            and page.semitones == 1
            and window.result.score.key != page.original_key
        ),
        timeout=WAIT_MS,
    )
    assert window.result.title == "새 제목"
