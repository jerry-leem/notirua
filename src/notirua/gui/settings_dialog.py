"""Settings: general, components, storage, about (M4 scope, FR-8, FR-10)."""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from notirua import paths
from notirua import settings as settings_mod
from notirua.components.manager import ComponentManager, human_size
from notirua.core import cache, youtube
from notirua.gui.widgets import language_name
from notirua.i18n import _, available_languages, current_language


def licenses_file() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "docs" / "LICENSES.md"
    return Path(__file__).resolve().parents[3] / "docs" / "LICENSES.md"


def jobs_cache_dir() -> Path:
    return paths.cache_dir() / "jobs"


class SettingsDialog(QDialog):
    setup_requested = Signal()
    components_changed = Signal()

    def __init__(
        self,
        user: settings_mod.Settings,
        manager: ComponentManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.user = user
        self.manager = manager
        self.setWindowTitle(_("Settings"))
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.tabs.addTab(self._general_tab(), _("General"))
        self.tabs.addTab(self._components_tab(), _("Components"))
        self.tabs.addTab(self._storage_tab(), _("Storage"))
        self.tabs.addTab(self._about_tab(), _("About"))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self.resize(640, 480)

    # -- general -----------------------------------------------------------
    def _general_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.language = QComboBox()
        self.language.addItem(_("Same as the system"), None)
        for lang in available_languages():
            self.language.addItem(language_name(lang), lang)
        self.language.setCurrentIndex(max(0, self.language.findData(self.user.language)))
        self.language.currentIndexChanged.connect(self._language_changed)
        form.addRow(_("Language"), self.language)
        self.restart_note = QLabel(_("The new language is used after you restart Notirua."))
        self.restart_note.setWordWrap(True)
        self.restart_note.setVisible(False)
        form.addRow("", self.restart_note)
        self.paper = QComboBox()
        self.paper.addItem(_("Automatic"), None)
        self.paper.addItem("A4", "a4")
        self.paper.addItem(_("Letter"), "letter")
        self.paper.setCurrentIndex(max(0, self.paper.findData(self.user.paper)))
        self.paper.currentIndexChanged.connect(self._paper_changed)
        form.addRow(_("Paper"), self.paper)
        folder_row = QHBoxLayout()
        self.output_dir = QLineEdit(self.user.output_dir or "")
        self.output_dir.setReadOnly(True)
        self.output_dir.setAccessibleName(_("Save folder"))
        self.output_dir.setPlaceholderText(_("Ask every time"))
        choose = QPushButton(_("Change…"))
        choose.setAccessibleName(_("Change save folder"))
        choose.clicked.connect(self._choose_output)
        folder_row.addWidget(self.output_dir, 1)
        folder_row.addWidget(choose)
        form.addRow(_("Save folder"), folder_row)
        youtube_row = QHBoxLayout()
        self.youtube_dir = QLineEdit(self.user.youtube_dir or "")
        self.youtube_dir.setReadOnly(True)
        self.youtube_dir.setAccessibleName(_("Folder for audio saved from YouTube"))
        self.youtube_dir.setPlaceholderText(str(youtube.default_folder(None)))
        choose_youtube = QPushButton(_("Change…"))
        choose_youtube.setAccessibleName(_("Change the folder for audio saved from YouTube"))
        choose_youtube.clicked.connect(self._choose_youtube_dir)
        youtube_row.addWidget(self.youtube_dir, 1)
        youtube_row.addWidget(choose_youtube)
        form.addRow(_("Audio from YouTube"), youtube_row)
        return page

    def _language_changed(self) -> None:
        self.user.language = self.language.currentData()
        settings_mod.save(self.user)
        self.restart_note.setVisible((self.user.language or "") != current_language())

    def _paper_changed(self) -> None:
        self.user.paper = self.paper.currentData()
        settings_mod.save(self.user)

    def _choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, _("Choose a save folder"), self.user.output_dir or str(Path.home())
        )
        if folder:
            self.user.output_dir = folder
            self.output_dir.setText(folder)
            settings_mod.save(self.user)

    def _choose_youtube_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            _("Choose a folder for audio saved from YouTube"),
            self.user.youtube_dir or str(youtube.default_folder(None).parent),
        )
        if folder:
            self.user.youtube_dir = folder
            self.youtube_dir.setText(folder)
            settings_mod.save(self.user)

    # -- components --------------------------------------------------------
    def _components_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([_("Name"), _("Version"), _("Size"), _("Status")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setAccessibleName(_("Components"))
        layout.addWidget(self.table)
        self.location = QLabel()
        self.location.setWordWrap(True)
        layout.addWidget(self.location)
        row = QHBoxLayout()
        self.reinstall_button = QPushButton(_("Install again…"))
        self.reinstall_button.clicked.connect(self._reinstall)
        self.remove_button = QPushButton(_("Remove…"))
        self.remove_button.clicked.connect(self._remove)
        self.setup_button = QPushButton(_("Open setup…"))
        self.setup_button.clicked.connect(self._open_setup)
        row.addWidget(self.reinstall_button)
        row.addWidget(self.remove_button)
        row.addStretch(1)
        row.addWidget(self.setup_button)
        layout.addLayout(row)
        self._fill_components()
        return page

    def _fill_components(self) -> None:
        statuses = self.manager.status()
        self.table.setRowCount(len(statuses))
        for i, st in enumerate(statuses):
            values = [
                _(st.component.name_id),
                st.component.version,
                human_size(st.size_on_disk) if st.installed else "–",
                ("✓ " + _("Installed")) if st.installed else ("✗ " + _("Not installed")),
            ]
            for col, value in enumerate(values):
                self.table.setItem(i, col, QTableWidgetItem(value))
        if statuses and not self.table.selectedItems():
            self.table.selectRow(0)
        self.location.setText(_("Install location: {path}").format(path=self.manager.install_dir))

    def _selected_component(self) -> int | None:
        rows = {i.row() for i in self.table.selectedItems()}
        return rows.pop() if rows else None

    def _remove(self) -> None:
        row = self._selected_component()
        if row is None:
            return
        component = self.manager.components[row]
        answer = QMessageBox.question(
            self,
            _("Remove"),
            _("Remove {name}? You need it to make sheet music and can install it again.").format(
                name=_(component.name_id)
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.manager.remove(component)
            self._fill_components()
            self.components_changed.emit()

    def _reinstall(self) -> None:
        row = self._selected_component()
        if row is None:
            return
        component = self.manager.components[row]
        answer = QMessageBox.question(
            self,
            _("Install again"),
            _("Remove {name} and download it again?").format(name=_(component.name_id)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.manager.remove(component)
            self.components_changed.emit()
            self._open_setup()

    def _open_setup(self) -> None:
        self.setup_requested.emit()
        self.accept()

    # -- storage -----------------------------------------------------------
    def _storage_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.cache_size = QLabel()
        form.addRow(_("Saved intermediate results"), self.cache_size)
        clear = QPushButton(_("Clear…"))
        clear.setAccessibleName(_("Clear saved intermediate results"))
        clear.clicked.connect(self._clear_cache)
        form.addRow("", clear)
        self.cache_limit = QDoubleSpinBox()
        self.cache_limit.setRange(0.5, 100.0)
        self.cache_limit.setSingleStep(0.5)
        self.cache_limit.setSuffix(" GB")
        self.cache_limit.setValue(self.user.cache_limit_gb)
        self.cache_limit.valueChanged.connect(self._limit_changed)
        form.addRow(_("Keep at most"), self.cache_limit)
        note = QLabel(
            _("Saved results make transposing and trying again fast. Older ones are removed first.")
        )
        note.setWordWrap(True)
        form.addRow("", note)
        self._update_cache_size()
        return page

    def _update_cache_size(self) -> None:
        self.cache_size.setText(human_size(cache.cache_size(jobs_cache_dir())))

    def _clear_cache(self) -> None:
        answer = QMessageBox.question(
            self,
            _("Clear"),
            _("Delete all saved intermediate results? Your sheet music files are not touched."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            cache.clear(jobs_cache_dir())
            self._update_cache_size()

    def _limit_changed(self, value: float) -> None:
        self.user.cache_limit_gb = value
        settings_mod.save(self.user)

    # -- about -------------------------------------------------------------
    def _about_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        try:
            app_version = version("notirua")
        except PackageNotFoundError:
            app_version = "dev"
        layout.addWidget(QLabel(_("Notirua {version}").format(version=app_version)))
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setAccessibleName(_("Licenses"))
        path = licenses_file()
        if path.is_file():
            browser.setMarkdown(path.read_text(encoding="utf-8"))
        else:
            browser.setPlainText(_("The license list could not be found."))
        layout.addWidget(browser, 1)
        return page
