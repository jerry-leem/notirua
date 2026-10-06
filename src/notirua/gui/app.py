"""GUI entry point: `notirua` with no command, `notirua gui`, or `notirua-gui`."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from notirua import settings as settings_mod
from notirua.i18n import resolve_language, set_language


def install_qt_translations(app: QApplication, language: str) -> QTranslator | None:
    """Translate Qt's own dialogs and buttons (qtbase catalogs shipped with PySide6)."""
    translator = QTranslator(app)
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(QLocale(language), "qtbase", "_", folder):
        app.installTranslator(translator)
        return translator
    return None


ICONS = Path(__file__).resolve().parents[1] / "resources" / "icons"


def app_icon() -> QIcon:
    """The window and Dock/taskbar icon, every size drawn by packaging/make_icon.py."""
    icon = QIcon()
    for png in sorted(ICONS.glob("notirua-*.png")):
        icon.addFile(str(png))
    return icon


def display_available() -> bool:
    """False on Linux sessions without a screen (SSH, CI), where Qt would abort."""
    if not sys.platform.startswith("linux") or os.environ.get("QT_QPA_PLATFORM"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def main(argv: Sequence[str] | None = None, language: str | None = None) -> int:
    """Open the window. The first run (no settings file or no consent) starts on setup."""
    from notirua.core.logging_setup import configure
    from notirua.gui.main_window import APP_NAME, MainWindow

    configure()
    app = QApplication.instance() or QApplication(list(argv if argv is not None else sys.argv))
    assert isinstance(app, QApplication)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setWindowIcon(app_icon())
    if not settings_mod.settings_path().is_file():
        settings_mod.save(settings_mod.Settings())
    user = settings_mod.load()
    active = set_language(resolve_language(language or user.language))
    install_qt_translations(app, active)
    window = MainWindow(user)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
