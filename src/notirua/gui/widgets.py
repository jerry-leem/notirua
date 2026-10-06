"""Shared widgets: stage list, progress panel, error box (FR-11, NFR-5)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from notirua import paths
from notirua.core.errors import NotiruaError
from notirua.core.progress import ProgressEvent, StageState
from notirua.i18n import N_, _, translate_progress

STATE_ICONS: dict[str, str] = {
    "pending": "·",
    "running": "▶",
    "done": "✓",
    "skipped": "–",
    "failed": "✗",
}
STATE_NAMES: dict[str, str] = {
    "pending": N_("Waiting"),
    "running": N_("In progress"),
    "done": N_("Done"),
    "skipped": N_("Skipped"),
    "failed": N_("Failed"),
}
PROGRESS_STEPS = 1000


def format_duration(seconds: float) -> str:
    seconds = max(0, round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def language_name(code: str) -> str:
    """A language's own name, e.g. ``ko`` -> ``한국어`` (falls back to the code)."""
    from babel import Locale, UnknownLocaleError

    try:
        name = Locale.parse(code).get_display_name(code)
    except (ValueError, UnknownLocaleError):
        return code
    return f"{name[:1].upper()}{name[1:]}" if name else code


def open_path(path: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def open_log_folder() -> None:
    folder = paths.log_dir()
    folder.mkdir(parents=True, exist_ok=True)
    open_path(folder)


def heading(text: str = "", scale: float = 1.3) -> QLabel:
    label = QLabel(text)
    font = QFont(label.font())
    font.setPointSizeF(font.pointSizeF() * scale)
    font.setBold(True)
    label.setFont(font)
    label.setWordWrap(True)
    return label


def primary_button(text: str) -> QPushButton:
    """The one most visible action of a screen (FR-8)."""
    button = QPushButton(text)
    button.setDefault(True)
    button.setAutoDefault(True)
    font = QFont(button.font())
    font.setBold(True)
    button.setFont(font)
    button.setMinimumHeight(button.sizeHint().height() + 8)
    return button


class StageList(QWidget):
    """One row per stage: icon plus text, never color alone (FR-8 accessibility)."""

    def __init__(self, stages: Sequence[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._titles: dict[str, str] = {}
        self._rows: dict[str, QLabel] = {}
        self._states: dict[str, StageState] = {}
        for name, title in stages:
            row = QLabel()
            row.setWordWrap(True)
            row.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(row)
            self._titles[name] = title
            self._rows[name] = row
            self.set_state(name, "pending")

    def stages(self) -> list[str]:
        return list(self._rows)

    def state(self, name: str) -> StageState:
        return self._states[name]

    def text(self, name: str) -> str:
        return self._rows[name].text()

    def set_state(self, name: str, state: StageState, detail: str | None = None) -> None:
        row = self._rows.get(name)
        if row is None:
            return
        self._states[name] = state
        text = detail if (detail and state == "running") else self._titles[name]
        if state == "skipped" and detail:
            text = f"{self._titles[name]} ({detail})"
        row.setText(f"{STATE_ICONS[state]}  {text}")
        row.setAccessibleName(f"{text}: {_(STATE_NAMES[state])}")
        font = QFont(row.font())
        font.setBold(state == "running")
        row.setFont(font)


class ProgressPanel(QWidget):
    """Overall bar, ETA, current step in plain words, and the stage list (FR-11)."""

    def __init__(self, stages: Sequence[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        bar_row = QHBoxLayout()
        self.bar = QProgressBar()
        self.bar.setRange(0, PROGRESS_STEPS)
        self.bar.setTextVisible(False)
        self.bar.setAccessibleName(_("Overall progress"))
        self.percent = QLabel("0%")
        self.eta = QLabel()
        bar_row.addWidget(self.bar, 1)
        bar_row.addWidget(self.percent)
        bar_row.addWidget(self.eta)
        layout.addLayout(bar_row)
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        layout.addSpacing(8)
        self.stage_list = StageList(stages)
        layout.addWidget(self.stage_list)
        self.fraction = 0.0

    def apply(self, event: ProgressEvent) -> None:
        self.fraction = max(self.fraction, event.overall_fraction)
        self.bar.setValue(int(self.fraction * PROGRESS_STEPS))
        pct = int(self.fraction * 100)
        self.percent.setText(f"{pct}%")
        self.bar.setAccessibleDescription(f"{pct}%")
        if event.eta_seconds is not None and event.eta_seconds > 0:
            self.eta.setText(_("about {time} left").format(time=format_duration(event.eta_seconds)))
        else:
            self.eta.clear()
        text = translate_progress(event.message_id, event.message_args)
        speed = event.message_args.get("speed")
        if event.stage_state == "running" and isinstance(speed, str):
            text = _("{message} · {speed}/s").format(message=text, speed=speed)
        self.message.setText(text)
        detail = text if event.stage_state == "running" else None
        if event.stage_state == "skipped":
            detail = translate_progress(event.message_id, event.message_args)
        self.stage_list.set_state(event.stage, event.stage_state, detail)

    def finish(self) -> None:
        self.fraction = 1.0
        self.bar.setValue(PROGRESS_STEPS)
        self.percent.setText("100%")
        self.eta.clear()


class ErrorBox(QFrame):
    """What went wrong and what to do; code and log folder folded away (FR-8, NFR-5)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        self.title = heading(scale=1.1)
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.hint)
        self.toggle = QToolButton()
        self.toggle.setText(_("Details"))
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.toggled.connect(self._on_toggle)
        layout.addWidget(self.toggle)
        self.details = QWidget()
        details_layout = QHBoxLayout(self.details)
        details_layout.setContentsMargins(16, 0, 0, 0)
        self.code = QLabel()
        self.code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.log_button = QPushButton(_("Open log folder"))
        self.log_button.clicked.connect(open_log_folder)
        details_layout.addWidget(self.code, 1)
        details_layout.addWidget(self.log_button)
        self.details.setVisible(False)
        layout.addWidget(self.details)
        self.action_row = QHBoxLayout()
        self.action_row.addStretch(1)
        layout.addLayout(self.action_row)
        self.error: BaseException | None = None

    def _on_toggle(self, shown: bool) -> None:
        self.details.setVisible(shown)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if shown else Qt.ArrowType.RightArrow)

    def add_action(self, button: QPushButton) -> QPushButton:
        self.action_row.addWidget(button)
        return button

    def show_error(self, error: BaseException) -> None:
        self.error = error
        if isinstance(error, NotiruaError):
            message, hint, code = error.user_message(), error.user_hint(), error.code
        else:
            fallback = NotiruaError()
            message, hint, code = fallback.user_message(), fallback.user_hint(), fallback.code
        self.title.setText(f"✗ {message}")
        self.hint.setText(hint)
        self.code.setText(_("Error code: {code}").format(code=code))
        self.toggle.setChecked(False)
