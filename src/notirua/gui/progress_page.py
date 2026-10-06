"""Screen ③: progress of a job, with cancel and the error box on failure (FR-11, NFR-5)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout, QWidget

from notirua.core.errors import DecodeError
from notirua.core.pipeline import STAGE_MESSAGES
from notirua.core.progress import ProgressEvent
from notirua.gui.widgets import ErrorBox, ProgressPanel, heading
from notirua.i18n import _


class ProgressPage(QWidget):
    cancel_requested = Signal()
    retry_requested = Signal()
    other_file_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.layout_ = QVBoxLayout(self)
        self.title = heading()
        self.layout_.addWidget(self.title)
        self.panel = ProgressPanel([])
        self.layout_.addWidget(self.panel)
        self.error_box = ErrorBox()
        self.retry_button = self.error_box.add_action(QPushButton(_("Try again")))
        self.retry_button.clicked.connect(self.retry_requested.emit)
        self.other_button = self.error_box.add_action(QPushButton(_("Choose another file")))
        self.other_button.clicked.connect(self.other_file_requested.emit)
        self.error_box.setVisible(False)
        self.layout_.addWidget(self.error_box)
        self.layout_.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_button = QPushButton(_("Cancel"))
        self.cancel_button.clicked.connect(self._confirm_cancel)
        row.addWidget(self.cancel_button)
        self.layout_.addLayout(row)
        self.running = False
        self.confirm_cancel = True

    def begin(self, title: str) -> None:
        self.title.setText(_("Making sheet music for {title}").format(title=title))
        stages = [(name, _(message)) for name, message in STAGE_MESSAGES.items()]
        new_panel = ProgressPanel(stages)
        self.layout_.replaceWidget(self.panel, new_panel)
        self.panel.deleteLater()
        self.panel = new_panel
        self.error_box.setVisible(False)
        self.cancel_button.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.running = True

    def apply(self, event: ProgressEvent) -> None:
        self.panel.apply(event)

    def _confirm_cancel(self) -> None:
        if not self.running:
            return
        if self.confirm_cancel:
            answer = QMessageBox.question(
                self,
                _("Cancel"),
                _("Stop making sheet music? Finished steps are kept for next time."),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.cancel_button.setEnabled(False)
        self.cancel_requested.emit()

    def show_error(self, error: BaseException) -> None:
        self.running = False
        self.cancel_button.setVisible(False)
        self.error_box.show_error(error)
        # A file that cannot be read will not get better by retrying.
        decode_problem = isinstance(error, DecodeError)
        for button, primary in (
            (self.other_button, decode_problem),
            (self.retry_button, not decode_problem),
        ):
            button.setDefault(primary)
            font = button.font()
            font.setBold(primary)
            button.setFont(font)
        (self.other_button if decode_problem else self.retry_button).setFocus()
        self.error_box.setVisible(True)
