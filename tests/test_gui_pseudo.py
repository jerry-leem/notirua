"""Pseudo-locale screen check (SPEC 9.4): with every string ~40% longer, nothing on the
main screens is clipped, and no visible English text bypassed gettext."""

from __future__ import annotations

import importlib.util
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QAbstractButton, QApplication, QLabel, QWidget
from pytestqt.qtbot import QtBot

from notirua import i18n
from notirua import settings as settings_mod
from notirua.components.manager import ComponentManager
from notirua.core.errors import CorruptFileError
from notirua.gui.main_window import MainWindow
from notirua.gui.settings_dialog import SettingsDialog
from tests import synth
from tests.component_fakes import fake_components
from tests.gui_fakes import FakeJob, make_pdf, no_components

ROOT = Path(__file__).resolve().parents[1]
WINDOW = (900, 680)  # the default window size
# Visible text that is not translated on purpose: names, formats, numbers, paths.
ALLOWED = re.compile(
    r"^(Notirua|MusicXML|MIDI|A4|BPM|[‹›←−+♫]|[\d\s/.:+%\-]*|"
    r".*\.wav( · [\d:]+)?|[\w.-]+\.(co|com|org|invalid)|[\w.-]+ ⓘ|htdemucs.*|"
    # Qt's own standard buttons are translated by the qtbase catalogs, not ours.
    r"Close)$"
)


@pytest.fixture
def pseudo(tmp_path: Path) -> Iterator[None]:
    spec = importlib.util.spec_from_file_location(
        "make_pseudo_locale", ROOT / "scripts" / "make_pseudo_locale.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    locales = tmp_path / "locales"
    module.build(ROOT / "locales" / "notirua.pot", locales / "en_XA" / "LC_MESSAGES" / "notirua.po")
    i18n.set_locales_dir(locales)
    assert i18n.set_language("en_XA") == "en_XA"
    yield


def visible_text_widgets(root: QWidget) -> list[QWidget]:
    found: list[QWidget] = []
    for widget in root.findChildren(QWidget):
        if widget.isVisibleTo(root) and isinstance(widget, QLabel | QAbstractButton):
            found.append(widget)
    return found


def problems(root: QWidget) -> list[str]:
    issues = []
    for widget in visible_text_widgets(root):
        text = widget.text().replace("&", "")
        if not text.strip():
            continue
        if isinstance(widget, QLabel) and widget.wordWrap():
            pass
        elif widget.width() < widget.minimumSizeHint().width():
            need = widget.minimumSizeHint().width()
            issues.append(f"clipped: {text!r} ({widget.width()} < {need})")
        plain = re.sub(r"<[^>]+>", "", text).strip()
        if "[" not in plain and re.search(r"[A-Za-z]{3,}", plain) and not ALLOWED.match(plain):
            issues.append(f"not translated: {plain!r}")
    return issues


def show(qtbot: QtBot, widget: QWidget, size: tuple[int, int] = WINDOW) -> None:
    widget.resize(*size)
    widget.show()
    qtbot.waitExposed(widget)
    QApplication.processEvents()


def test_setup_screen_fits(qtbot: QtBot, pseudo: None, tmp_path: Path) -> None:
    model, tool, _files = fake_components("http://downloads.invalid")

    def factory(user: settings_mod.Settings) -> ComponentManager:
        m = ComponentManager(user.components_path, platform_key="linux-x86_64")
        m.components = [model, tool]
        return m

    window = MainWindow(settings_mod.Settings(components_dir="/c"), manager_factory=factory)
    qtbot.addWidget(window)
    show(qtbot, window)
    assert window.stack.currentWidget() is window.setup_page
    assert problems(window) == []


def test_main_screens_fit(qtbot: QtBot, pseudo: None, tmp_path: Path) -> None:
    job = FakeJob(tmp_path, make_pdf(tmp_path / "pages.pdf"))
    audio = synth.to_stereo(synth.render_notes(synth.scale_notes(120), total_s=6.0))
    song = synth.write_wav(tmp_path / "song.wav", audio)
    user = settings_mod.Settings(consent=ComponentManager.make_consent([]))
    window = MainWindow(user, pipeline=job.pipeline, manager_factory=no_components)
    qtbot.addWidget(window)
    show(qtbot, window)
    assert problems(window) == [], "file screen"

    window.open_file(song)
    window.options_page.more_toggle.setChecked(True)
    QApplication.processEvents()
    assert problems(window) == [], "options screen"

    window.options_page.start_button.click()
    QApplication.processEvents()
    assert problems(window) == [], "progress screen"
    qtbot.waitUntil(lambda: window.stack.currentWidget() is window.result_page, timeout=15_000)
    QApplication.processEvents()
    assert problems(window) == [], "result screen"

    window.result_page.mix_button.click()
    dialog = window.mix_dialog
    assert dialog is not None
    show(qtbot, dialog, (dialog.sizeHint().width(), dialog.sizeHint().height()))
    dialog.busy.setVisible(True)
    QApplication.processEvents()
    assert problems(dialog) == [], "make audio file"
    dialog.close()

    window.progress_page.show_error(CorruptFileError())
    window.progress_page.error_box.toggle.setChecked(True)
    window.stack.setCurrentWidget(window.progress_page)
    QApplication.processEvents()
    assert problems(window) == [], "error box"


def test_settings_fit(qtbot: QtBot, pseudo: None) -> None:
    user = settings_mod.Settings()
    dialog = SettingsDialog(user, no_components(user))
    qtbot.addWidget(dialog)
    show(qtbot, dialog, (640, 480))
    for index in range(dialog.tabs.count()):
        dialog.tabs.setCurrentIndex(index)
        QApplication.processEvents()
        assert problems(dialog) == [], dialog.tabs.tabText(index)
