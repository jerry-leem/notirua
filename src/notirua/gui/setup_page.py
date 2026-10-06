"""First-run setup: consent, download/install progress, failure and retry (FR-10, FR-11).

Nothing on this screen touches the network until the user presses
"Agree and install"; building the plan only reads the manifest and disk space.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from notirua import settings as settings_mod
from notirua.components.download import PauseToken
from notirua.components.manager import ComponentManager, SetupPlan, human_size
from notirua.components.manifest import Component
from notirua.core.progress import CancelToken, ProgressCallback
from notirua.gui.tasks import Task
from notirua.gui.widgets import ErrorBox, ProgressPanel, heading, primary_button
from notirua.i18n import _, ngettext

ManagerFactory = Callable[[settings_mod.Settings], ComponentManager]


def default_manager_factory(user: settings_mod.Settings) -> ComponentManager:
    return ComponentManager(user.components_path)


class SetupPage(QWidget):
    """Consent screen (0) and installing screen (0b) from the wireframes."""

    completed = Signal()
    postponed = Signal()

    def __init__(
        self,
        user: settings_mod.Settings,
        manager_factory: ManagerFactory = default_manager_factory,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.user = user
        self.manager_factory = manager_factory
        self.manager = manager_factory(user)
        self.task: Task | None = None
        self.pause_token: PauseToken | None = None
        self._todo: list[Component] = []
        self._checks: dict[str, QCheckBox] = {}

        self.stack = QStackedWidget()
        outer = QVBoxLayout(self)
        outer.addWidget(self.stack)

        # -- consent view --------------------------------------------------
        self.consent_view = QWidget()
        cv = QVBoxLayout(self.consent_view)
        self.title = heading()
        cv.addWidget(self.title)
        self.list_area = QWidget()
        self.list_layout = QGridLayout(self.list_area)
        self.list_layout.setColumnStretch(0, 1)
        cv.addWidget(self.list_area)
        self.check_hint = QLabel(_("Check each component to agree to its license."))
        self.check_hint.setWordWrap(True)
        cv.addWidget(self.check_hint)
        self.totals = QLabel()
        self.totals.setWordWrap(True)
        cv.addWidget(self.totals)
        location_row = QHBoxLayout()
        self.location = QLabel()
        self.location.setWordWrap(True)
        self.location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.change_location = QPushButton(_("Change…"))
        self.change_location.setAccessibleName(_("Change install location"))
        self.change_location.clicked.connect(self._choose_location)
        location_row.addWidget(self.location, 1)
        location_row.addWidget(self.change_location)
        cv.addLayout(location_row)
        self.space_error = QLabel()
        self.space_error.setWordWrap(True)
        cv.addWidget(self.space_error)
        offline = QLabel(
            "ⓘ "
            + _("The internet is used only for this download. Notirua works offline afterwards.")
        )
        offline.setWordWrap(True)
        cv.addWidget(offline)
        cv.addStretch(1)
        buttons = QHBoxLayout()
        self.bundle_button = QPushButton(_("Install from a bundle file…"))
        self.bundle_button.clicked.connect(self._choose_bundle)
        self.later_button = QPushButton(_("Not now"))
        self.later_button.clicked.connect(self.postponed.emit)
        self.agree_button = primary_button(_("Agree and install"))
        self.agree_button.clicked.connect(self._agree)
        buttons.addWidget(self.bundle_button)
        buttons.addStretch(1)
        buttons.addWidget(self.later_button)
        buttons.addWidget(self.agree_button)
        cv.addLayout(buttons)
        self.stack.addWidget(self.consent_view)

        # -- installing view -----------------------------------------------
        self.install_view = QWidget()
        self.install_layout = QVBoxLayout(self.install_view)
        self.install_layout.addWidget(heading(_("Installing components")))
        self.panel: ProgressPanel | None = None
        self.panel_holder = QVBoxLayout()
        self.install_layout.addLayout(self.panel_holder)
        self.error_box = ErrorBox()
        self.retry_button = self.error_box.add_action(primary_button(_("Try again")))
        self.retry_button.clicked.connect(self._retry)
        self.back_button = self.error_box.add_action(QPushButton(_("Back")))
        self.back_button.clicked.connect(self.refresh)
        self.error_box.setVisible(False)
        self.install_layout.addWidget(self.error_box)
        self.install_layout.addStretch(1)
        install_buttons = QHBoxLayout()
        install_buttons.addStretch(1)
        self.pause_button = QPushButton(_("Pause"))
        self.pause_button.clicked.connect(self._toggle_pause)
        self.cancel_button = QPushButton(_("Cancel"))
        self.cancel_button.clicked.connect(self._confirm_cancel)
        install_buttons.addWidget(self.pause_button)
        install_buttons.addWidget(self.cancel_button)
        self.install_layout.addLayout(install_buttons)
        self.stack.addWidget(self.install_view)

        self.refresh()

    # -- consent view ------------------------------------------------------
    def refresh(self) -> None:
        """Rebuild the consent view from the manifest and disk space (no network)."""
        self.manager = self.manager_factory(self.user)
        self._todo = self.manager.missing(required_only=False)
        shown = self._todo or list(self.manager.components)
        plan = self.manager.plan(self._todo)
        if self._todo:
            self.title.setText(
                ngettext(
                    "Notirua needs to download {count} component",
                    "Notirua needs to download {count} components",
                    len(self._todo),
                ).format(count=len(self._todo))
            )
        else:
            self.title.setText(_("Please review the component licenses"))
        self._build_rows(shown)
        self._update_plan(plan)
        self.stack.setCurrentWidget(self.consent_view)

    def _build_rows(self, components: list[Component]) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self._checks = {}
        for row, c in enumerate(components):
            f = c.file_for(self.manager.platform_key)
            check = QCheckBox(_(c.name_id))
            check.setChecked(False)  # never pre-checked (FR-10)
            check.toggled.connect(self._update_agree)
            self._checks[c.id] = check
            size = QLabel(human_size(f.size if f else 0))
            source = QLabel(f.domain if f else "")
            license_link = QPushButton(f"{c.license_id} ⓘ")
            license_link.setFlat(True)
            license_link.setAccessibleName(
                _("Show the license of {name}").format(name=_(c.name_id))
            )
            license_link.clicked.connect(
                lambda _checked=False, url=c.license_url: QDesktopServices.openUrl(QUrl(url))
            )
            purpose = QLabel(_(c.purpose_id))
            purpose.setWordWrap(True)
            purpose.setContentsMargins(24, 0, 0, 6)
            self.list_layout.addWidget(check, row * 2, 0)
            self.list_layout.addWidget(size, row * 2, 1)
            self.list_layout.addWidget(source, row * 2, 2)
            self.list_layout.addWidget(license_link, row * 2, 3)
            self.list_layout.addWidget(purpose, row * 2 + 1, 0, 1, 4)

    def _update_plan(self, plan: SetupPlan) -> None:
        self._plan = plan
        self.totals.setText(
            _(
                "Total download {download} · Space needed after install {install} · "
                "Free space {free}"
            ).format(
                download=human_size(plan.download_bytes),
                install=human_size(plan.install_bytes),
                free=human_size(plan.free_bytes),
            )
        )
        self.location.setText(_("Install location: {path}").format(path=plan.install_dir))
        if plan.enough_space:
            self.space_error.clear()
            self.space_error.setVisible(False)
        else:
            self.space_error.setText(
                "ⓧ "
                + _("There is not enough disk space. Free up space or choose another location.")
            )
            self.space_error.setStyleSheet("color: #c62828;")
            self.space_error.setVisible(True)
        self._update_agree()

    def _update_agree(self) -> None:
        required = [
            c
            for c in (self._todo or self.manager.components)
            if c.required and c.id in self._checks
        ]
        agreed = all(self._checks[c.id].isChecked() for c in required)
        self.agree_button.setEnabled(agreed and self._plan.enough_space)

    def selected(self) -> list[Component]:
        return [c for c in self._todo if self._checks.get(c.id, QCheckBox()).isChecked()]

    def _choose_location(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, _("Choose where to install components"), str(self.user.components_path)
        )
        if folder:
            self.user.components_dir = str(Path(folder))
            settings_mod.save(self.user)
            self.refresh()

    # -- actions -----------------------------------------------------------
    def _agree(self) -> None:
        """The only place consent is created in the GUI: the user pressed the button."""
        if not self.agree_button.isEnabled():
            return
        todo = self.selected()
        if not todo:
            self._record_consent(list(self.manager.components))
            self.completed.emit()
            return
        consent = self.manager.make_consent(todo)
        self.user.consent = consent
        settings_mod.save(self.user)
        self._components = todo
        self._start_install(
            [(f"download:{c.id}", c) for c in todo] + [(f"install:{c.id}", c) for c in todo],
            lambda progress, cancel: self.manager.install(
                todo, consent, progress=progress, cancel=cancel, pause=self.pause_token
            ),
            pausable=True,
        )

    def _choose_bundle(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, _("Choose a component bundle file"), "", _("Component bundle (*.zip)")
        )
        if not path:
            return
        bundle = Path(path)
        comps = list(self.manager.components)
        self._start_install(
            [(f"install:{c.id}", c) for c in comps],
            lambda progress, cancel: self.manager.install_from_bundle(
                bundle, progress=progress, cancel=cancel
            ),
            pausable=False,
        )

    def _start_install(
        self,
        stages: list[tuple[str, Component]],
        work: Callable[[ProgressCallback, CancelToken], Any],
        pausable: bool,
    ) -> None:
        order = sorted(stages, key=lambda s: ([c.id for _n, c in stages].index(s[1].id), s[0]))
        titles = []
        for name, c in order:
            if name.startswith("download:"):
                titles.append((name, _("Downloading {name}").format(name=_(c.name_id))))
            else:
                titles.append((name, _("Installing {name}").format(name=_(c.name_id))))
        if self.panel is not None:
            self.panel.setParent(None)
            self.panel.deleteLater()
        self.panel = ProgressPanel(titles)
        self.panel_holder.addWidget(self.panel)
        self.error_box.setVisible(False)
        self.pause_token = PauseToken() if pausable else None
        self.pause_button.setVisible(pausable)
        self.pause_button.setText(_("Pause"))
        self.cancel_button.setVisible(True)
        self._last_work = (stages, work, pausable)
        self.task = Task(work, "setup", self)
        self.task.progress.connect(self.panel.apply)
        self.task.succeeded.connect(self._on_installed)
        self.task.failed.connect(self._on_failed)
        self.task.cancelled.connect(self.refresh)
        self.stack.setCurrentWidget(self.install_view)
        self.task.start()

    def _toggle_pause(self) -> None:
        if self.pause_token is None:
            return
        if self.pause_token.paused:
            self.pause_token.resume()
            self.pause_button.setText(_("Pause"))
        else:
            self.pause_token.pause()
            self.pause_button.setText(_("Resume"))

    def _confirm_cancel(self) -> None:
        if self.task is None or not self.task.running:
            return
        answer = QMessageBox.question(
            self,
            _("Cancel"),
            _("Stop installing? Parts already downloaded are kept for next time."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.cancel_install()

    def cancel_install(self) -> None:
        if self.task is not None:
            self.task.cancel()
        if self.pause_token is not None:
            self.pause_token.resume()

    def _record_consent(self, components: list[Component]) -> None:
        self.user.consent = self.manager.make_consent(components)
        settings_mod.save(self.user)

    def _on_installed(self, _result: object) -> None:
        if self.panel is not None:
            self.panel.finish()
        self.manager = self.manager_factory(self.user)
        if not self.manager.missing():
            # Installed now or earlier (bundle); record the versions in use.
            self._record_consent(list(self.manager.components))
        self.completed.emit()

    def _on_failed(self, error: BaseException) -> None:
        self.error_box.show_error(error)
        self.error_box.setVisible(True)
        self.pause_button.setVisible(False)
        self.cancel_button.setVisible(False)
        self.retry_button.setFocus()

    def _retry(self) -> None:
        """Downloads resume from the partial file kept on disk."""
        stages, work, pausable = self._last_work
        self._start_install(stages, work, pausable)
