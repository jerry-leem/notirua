"""Screen ①: choose a music file by dropping it anywhere or with a button (FR-8)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from notirua.gui.widgets import heading, primary_button
from notirua.i18n import _

AUDIO_PATTERNS = (
    "*.mp3 *.m4a *.aac *.wav *.flac *.ogg *.opus *.aif *.aiff *.wma *.mp4 *.mov *.mkv *.webm"
)
MAX_RECENT = 5


class FilePage(QWidget):
    file_chosen = Signal(Path)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        drop = QFrame()
        drop.setFrameShape(QFrame.Shape.StyledPanel)
        drop.setFrameShadow(QFrame.Shadow.Sunken)
        dl = QVBoxLayout(drop)
        dl.setContentsMargins(32, 32, 32, 32)
        note = QLabel("♫")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = note.font()
        font.setPointSizeF(font.pointSizeF() * 3)
        note.setFont(font)
        note.setAccessibleName(_("Music"))
        dl.addWidget(note)
        title = heading(_("Drop a music file here"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl.addWidget(title)
        dl.addSpacing(12)
        row = QHBoxLayout()
        row.addStretch(1)
        self.pick_button = primary_button(_("Choose a file…"))
        self.pick_button.clicked.connect(self.choose_file)
        row.addWidget(self.pick_button)
        row.addStretch(1)
        dl.addLayout(row)
        dl.addSpacing(12)
        formats = QLabel(_("MP3, M4A, WAV, FLAC, OGG, MP4 video, and more"))
        formats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        formats.setWordWrap(True)
        dl.addWidget(formats)
        layout.addWidget(drop)
        self.recent_row = QHBoxLayout()
        layout.addLayout(self.recent_row)
        layout.addStretch(1)
        self.start_dir = ""

    def set_recent(self, files: list[str]) -> None:
        while self.recent_row.count():
            item = self.recent_row.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        existing = [Path(f) for f in files if Path(f).is_file()][:MAX_RECENT]
        if not existing:
            return
        self.recent_row.addWidget(QLabel(_("Recent:")))
        for path in existing:
            button = QPushButton(path.name)
            button.setFlat(True)
            button.setToolTip(str(path))
            button.setAccessibleName(_("Open recent file {name}").format(name=path.name))
            button.clicked.connect(lambda _c=False, p=path: self.file_chosen.emit(p))
            self.recent_row.addWidget(button)
        self.recent_row.addStretch(1)

    def choose_file(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            _("Choose a music file"),
            self.start_dir,
            _("Music and video files ({patterns})").format(patterns=AUDIO_PATTERNS)
            + ";;"
            + _("All files (*)"),
        )
        if path:
            self.file_chosen.emit(Path(path))
