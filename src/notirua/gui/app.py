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
from notirua.gui import macos
from notirua.i18n import N_, _, resolve_language, set_language

# Qt's standard button texts, for languages that have no qtbase catalog (for example Vietnamese).
STANDARD_BUTTONS = {
    "OK": N_("OK"),
    "Cancel": N_("Cancel"),
    "Close": N_("Close"),
    "Yes": N_("Yes"),
    "&Yes": N_("Yes"),
    "No": N_("No"),
    "&No": N_("No"),
}


class StandardButtonTranslator(QTranslator):
    """Translates Qt's standard buttons from Notirua's own catalog."""

    def translate(
        self, context: str, sourceText: str, disambiguation: str | None = None, n: int = -1
    ) -> str:
        if context == "QPlatformTheme" and sourceText in STANDARD_BUTTONS:
            return _(STANDARD_BUTTONS[sourceText])
        return ""


def install_qt_translations(app: QApplication, language: str) -> QTranslator:
    """Translate Qt's own dialogs and buttons (qtbase catalogs shipped with PySide6)."""
    translator = QTranslator(app)
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if not translator.load(QLocale(language), "qtbase", "_", folder):
        translator = StandardButtonTranslator(app)
    app.installTranslator(translator)
    return translator


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
    from notirua import APP_NAME, __version__
    from notirua.core.logging_setup import configure
    from notirua.gui.main_window import MainWindow

    configure()
    if QApplication.instance() is None:
        macos.set_app_name(APP_NAME)
    app = QApplication.instance() or QApplication(list(argv if argv is not None else sys.argv))
    assert isinstance(app, QApplication)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
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
