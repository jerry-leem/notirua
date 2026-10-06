"""Screen ②: title, instruments, and folded advanced settings (FR-8)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from notirua import settings as settings_mod
from notirua.core.model import STEMS
from notirua.core.pipeline import (
    INSTRUMENT_NAMES,
    KEY_CHOICES,
    TUNING_CHOICES,
    TUNING_LABELS,
    JobOptions,
    key_label,
)
from notirua.gui.widgets import format_duration, language_name, primary_button
from notirua.i18n import N_, _, available_languages

TIME_SIGNATURES = [(4, 4), (3, 4), (2, 4), (6, 8), (12, 8)]
TAB_MODES = {
    "both": N_("Notation + TAB"),
    "staff": N_("Notation only"),
    "tab": N_("TAB only"),
}


class OptionsPage(QWidget):
    start_requested = Signal(object)  # JobOptions
    back_requested = Signal()

    def __init__(self, user: settings_mod.Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.user = user
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.back_button = QPushButton("←")
        self.back_button.setAccessibleName(_("Back to file selection"))
        self.back_button.setToolTip(_("Back to file selection"))
        self.back_button.clicked.connect(self.back_requested.emit)
        self.file_label = QLabel()
        header.addWidget(self.back_button)
        header.addWidget(self.file_label, 1)
        layout.addLayout(header)
        layout.addSpacing(8)

        form = QFormLayout()
        self.title_edit = QLineEdit()
        form.addRow(_("Song title"), self.title_edit)
        stems_row = QHBoxLayout()
        self.stem_checks: dict[str, QCheckBox] = {}
        for stem in STEMS:
            check = QCheckBox(_(INSTRUMENT_NAMES[stem]))
            check.setChecked(True)
            self.stem_checks[stem] = check
            stems_row.addWidget(check)
        stems_row.addStretch(1)
        stems_box = QVBoxLayout()
        stems_box.addLayout(stems_row)
        stems_note = QLabel(
            _("Instruments are found automatically; ones without sound are skipped.")
        )
        stems_note.setWordWrap(True)
        stems_box.addWidget(stems_note)
        form.addRow(_("Instruments"), stems_box)
        self.track = QComboBox()
        self.track_label = QLabel(_("Audio track"))
        form.addRow(self.track_label, self.track)
        self._form = form
        layout.addLayout(form)

        self.more_toggle = QToolButton()
        self.more_toggle.setText(_("More settings"))
        self.more_toggle.setCheckable(True)
        self.more_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.more_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.more_toggle.toggled.connect(self._toggle_more)
        layout.addWidget(self.more_toggle)
        self.more = QWidget()
        more = QFormLayout(self.more)
        more.setContentsMargins(24, 0, 0, 0)
        self.guitar_tuning = self._tuning_combo("guitar", user.guitar_tuning)
        more.addRow(_("Guitar tuning"), self.guitar_tuning)
        self.bass_tuning = self._tuning_combo("bass", user.bass_tuning)
        more.addRow(_("Bass tuning"), self.bass_tuning)
        self.time_signature = QComboBox()
        self.time_signature.addItem(_("Automatic"), None)
        for num, den in TIME_SIGNATURES:
            self.time_signature.addItem(f"{num}/{den}", (num, den))
        more.addRow(_("Time signature"), self.time_signature)
        self.tempo = QSpinBox()
        self.tempo.setRange(0, 300)
        self.tempo.setSpecialValueText(_("Automatic"))
        self.tempo.setSuffix(" " + _("BPM"))
        more.addRow(_("Tempo"), self.tempo)
        self.key = QComboBox()
        self.key.addItem(_("Automatic"), None)
        for k in KEY_CHOICES:
            self.key.addItem(key_label(k, _), k)
        more.addRow(_("Key"), self.key)
        self.downbeat = QSpinBox()
        self.downbeat.setRange(-7, 7)
        more.addRow(_("Move the first beat by (beats)"), self.downbeat)
        self.tab_mode = QComboBox()
        for value, label in TAB_MODES.items():
            self.tab_mode.addItem(_(label), value)
        more.addRow(_("Show"), self.tab_mode)
        self.paper = QComboBox()
        self.paper.addItem("A4", "a4")
        self.paper.addItem(_("Letter"), "letter")
        more.addRow(_("Paper"), self.paper)
        self.pdf_language = QComboBox()
        self.pdf_language.addItem(_("Same as the app"), None)
        for lang in available_languages():
            self.pdf_language.addItem(language_name(lang), lang)
        more.addRow(_("Language inside the PDF"), self.pdf_language)
        self.fresh = QCheckBox(_("Delete saved intermediate results and start over"))
        self.fresh.setToolTip(
            _("Use this when earlier results for this file look wrong. It takes longer.")
        )
        more.addRow(self.fresh)
        self.more.setVisible(False)
        layout.addWidget(self.more)
        layout.addStretch(1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.start_button = primary_button(_("Make sheet music"))
        self.start_button.clicked.connect(self._start)
        bottom.addWidget(self.start_button)
        layout.addLayout(bottom)
        self.path: Path | None = None

    def _tuning_combo(self, instrument: str, current: str) -> QComboBox:
        combo = QComboBox()
        for name in TUNING_CHOICES[instrument]:
            combo.addItem(_(TUNING_LABELS.get(name, name)), name)
        index = combo.findData(current)
        combo.setCurrentIndex(max(0, index))
        return combo

    def _toggle_more(self, shown: bool) -> None:
        self.more.setVisible(shown)
        self.more_toggle.setArrowType(Qt.ArrowType.DownArrow if shown else Qt.ArrowType.RightArrow)

    def load_file(
        self,
        path: Path,
        duration_s: float | None,
        title: str | None,
        paper: str,
        tracks: list[tuple[int, str | None]] | None = None,
    ) -> None:
        """``tracks`` lists (stream index, language) when the file has several audio tracks."""
        self.path = path
        self.track.clear()
        for number, (index, language) in enumerate(tracks or [], start=1):
            label = _("Track {number}").format(number=number)
            self.track.addItem(f"{label} ({language})" if language else label, index)
        several = self.track.count() > 1
        self._form.setRowVisible(self.track, several)
        length = f" · {format_duration(duration_s)}" if duration_s else ""
        self.file_label.setText(f"{path.name}{length}")
        self.title_edit.setText(title or path.stem)
        self.paper.setCurrentIndex(max(0, self.paper.findData(paper)))
        pdf_lang = self.pdf_language.findData(self.user.pdf_language)
        self.pdf_language.setCurrentIndex(max(0, pdf_lang))
        self.fresh.setChecked(False)
        self.start_button.setFocus()

    def options(self) -> JobOptions:
        stems = [s for s, c in self.stem_checks.items() if c.isChecked()]
        return JobOptions(
            title=self.title_edit.text().strip() or None,
            stems=None if len(stems) == len(STEMS) else stems,
            paper=str(self.paper.currentData()),
            guitar_tuning=str(self.guitar_tuning.currentData()),
            bass_tuning=str(self.bass_tuning.currentData()),
            time_signature=self.time_signature.currentData(),
            tempo_bpm=float(self.tempo.value()) or None,
            key=self.key.currentData(),
            downbeat_shift=self.downbeat.value(),
            tab_mode=str(self.tab_mode.currentData()),
            pdf_language=self.pdf_language.currentData(),
            stream_index=self.track.currentData() if self.track.count() > 1 else None,
            tab_weights=dict(self.user.tab_weights),
            fresh=self.fresh.isChecked(),
        )

    def _start(self) -> None:
        if not any(c.isChecked() for c in self.stem_checks.values()):
            for c in self.stem_checks.values():
                c.setChecked(True)
        self.start_requested.emit(self.options())
