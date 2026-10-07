"""The YouTube link box of screen ①: paste a link, choose the quality, save the audio (0.5.0).

Two buttons: save the MP3 only (0.5.2), or save it and go on to the sheet music.
"""

from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QClipboard
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from notirua import settings as settings_mod
from notirua.core import youtube as yt
from notirua.core.errors import InvalidYoutubeLinkError
from notirua.gui.widgets import heading, open_path
from notirua.i18n import N_, _

QUALITY_LABELS = {
    128: N_("{kbps} kbps (smaller file)"),
    160: N_("{kbps} kbps (recommended)"),
    192: N_("{kbps} kbps"),
    256: N_("{kbps} kbps"),
    320: N_("{kbps} kbps (best sound)"),
}


class YoutubeBox(QFrame):
    """Emits ``requested(link text, kbps, make sheet music too)`` for a valid link.

    After an MP3-only save, :meth:`show_saved` says where the file is and offers
    ``score_requested(path)`` to make the sheet music from it later.
    """

    requested = Signal(str, int, bool)
    score_requested = Signal(Path)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.addWidget(heading(_("Or use a YouTube link"), scale=1.1))
        hint = QLabel(
            _(
                "Copy a video's link, then paste it here. Notirua saves the audio as an MP3 file "
                "named after the video."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        row = QHBoxLayout()
        self.link_edit = QLineEdit()
        self.link_edit.setPlaceholderText(_("Paste a YouTube link"))
        self.link_edit.setAccessibleName(_("YouTube link"))
        self.link_edit.setClearButtonEnabled(True)
        self.link_edit.textChanged.connect(self._text_changed)
        self.link_edit.returnPressed.connect(self._submit)
        row.addWidget(self.link_edit, 1)
        self.paste_button = QPushButton(_("Paste"))
        self.paste_button.setAccessibleName(_("Paste the link from the clipboard"))
        self.paste_button.clicked.connect(self.paste_from_clipboard)
        row.addWidget(self.paste_button)
        layout.addLayout(row)

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        options = QHBoxLayout()
        options.addWidget(QLabel(_("Quality")))
        self.quality = QComboBox()
        self.quality.setAccessibleName(_("Quality of the MP3 file"))
        for kbps in yt.BITRATES:
            self.quality.addItem(_(QUALITY_LABELS[kbps]).format(kbps=kbps), kbps)
        self.quality.setCurrentIndex(self.quality.findData(yt.DEFAULT_BITRATE))
        options.addWidget(self.quality)
        options.addStretch(1)
        layout.addLayout(options)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.audio_button = QPushButton(_("Save MP3 only"))
        self.audio_button.setAccessibleName(_("Save the audio as an MP3 file only"))
        self.audio_button.clicked.connect(lambda: self._submit(make_score=False))
        buttons.addWidget(self.audio_button)
        self.save_button = QPushButton(_("Save MP3 and make sheet music"))
        self.save_button.clicked.connect(lambda: self._submit(make_score=True))
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)

        saved_row = QHBoxLayout()
        self.saved_note = QLabel()
        self.saved_note.setWordWrap(True)
        self.saved_note.linkActivated.connect(lambda folder: open_path(Path(folder)))
        saved_row.addWidget(self.saved_note, 1)
        self.score_button = QPushButton(_("Make sheet music from it"))
        self.score_button.clicked.connect(self._score_saved)
        saved_row.addWidget(self.score_button)
        layout.addLayout(saved_row)
        self._saved_path: Path | None = None
        self.saved_note.setVisible(False)
        self.score_button.setVisible(False)

        notice = QLabel(
            _(
                "Only use videos you have the right to use. YouTube's terms of service and "
                "copyright law apply."
            )
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.make_score = True  # what Enter in the link box does: the button used last
        self._update_buttons()

    # -- state ---------------------------------------------------------------------
    def load_settings(self, user: settings_mod.Settings) -> None:
        index = self.quality.findData(user.youtube_bitrate)
        self.quality.setCurrentIndex(
            index if index >= 0 else self.quality.findData(yt.DEFAULT_BITRATE)
        )
        self.make_score = user.youtube_make_score
        self._update_buttons()

    def link(self) -> yt.YoutubeLink | None:
        try:
            return yt.parse_link(self.link_edit.text())
        except InvalidYoutubeLinkError:
            return None

    def set_link(self, text: str) -> None:
        self.link_edit.setText(text)
        self.link_edit.setFocus()

    def _update_buttons(self) -> None:
        valid = self.link() is not None
        for button, makes_score in ((self.save_button, True), (self.audio_button, False)):
            button.setEnabled(valid)
            button.setDefault(makes_score == self.make_score)

    def show_saved(self, path: Path) -> None:
        """After an MP3-only save: say where the file is, offer the sheet music."""
        folder = html.escape(str(path.parent), quote=True)
        self.saved_note.setText(
            "✓ "
            + _("Audio saved: {name} — {link}").format(
                name=html.escape(path.name),
                link=f'<a href="{folder}">' + _("Open the folder") + "</a>",
            )
        )
        self._saved_path = path
        self.saved_note.setVisible(True)
        self.score_button.setVisible(True)

    def hide_saved(self) -> None:
        self._saved_path = None
        self.saved_note.setVisible(False)
        self.score_button.setVisible(False)

    def _score_saved(self) -> None:
        if self._saved_path is not None:
            self.score_requested.emit(self._saved_path)

    def _text_changed(self, text: str) -> None:
        valid = self.link() is not None
        self._update_buttons()
        if not text.strip():
            self.status.clear()
            self.refresh_clipboard()
        elif valid:
            self.status.setText("✓ " + _("This looks like a YouTube video link."))
        else:
            self.status.setText(
                "✗ "
                + _(InvalidYoutubeLinkError.message_id)
                + " "
                + _(InvalidYoutubeLinkError.hint_id)
            )

    # -- clipboard ---------------------------------------------------------------
    def _clipboard_text(self) -> str:
        clipboard: QClipboard = QApplication.clipboard()
        return clipboard.text() if clipboard is not None else ""

    def refresh_clipboard(self) -> None:
        """Tell the user when the clipboard already holds a YouTube link (empty box only)."""
        if self.link_edit.text().strip():
            return
        if yt.find_link(self._clipboard_text()) is not None:
            self.status.setText(_("A YouTube link is in the clipboard. Press “Paste”."))
        else:
            self.status.clear()

    def paste_from_clipboard(self) -> bool:
        """Put the clipboard's YouTube link into the box. Returns whether one was found."""
        link = yt.find_link(self._clipboard_text())
        if link is None:
            self.status.setText("✗ " + _("There is no YouTube link in the clipboard."))
            self.link_edit.setFocus()
            return False
        self.link_edit.setText(link.url)
        (self.save_button if self.make_score else self.audio_button).setFocus()
        return True

    # -- go ------------------------------------------------------------------------
    def _submit(self, make_score: bool | None = None) -> None:
        """Save the audio; ``make_score`` is None for Enter (repeat the last button)."""
        if self.link() is None:
            return
        if make_score is not None:
            self.make_score = make_score
            self._update_buttons()
        self.requested.emit(
            self.link_edit.text().strip(), int(self.quality.currentData()), self.make_score
        )
