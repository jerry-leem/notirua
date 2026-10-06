"""Screen ④: per-instrument tabs, PDF preview (QtPdf), transposition, saving (FR-6, FR-8)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from notirua.core.pipeline import (
    INSTRUMENT_NAMES,
    JobResult,
    key_label,
    keys_like,
    semitones_between,
    transposed_key,
)
from notirua.gui.widgets import format_duration, primary_button
from notirua.i18n import _, ngettext

MAX_TRANSPOSE = 12
# Re-render bars that would only flash are not shown (FR-11: no bar under 0.3 s).
BUSY_DELAY_MS = 300


class ResultPage(QWidget):
    transpose_changed = Signal(int)
    title_changed = Signal(str)
    save_all_requested = Signal()
    export_requested = Signal(str)  # "musicxml" | "midi"
    stem_audio_requested = Signal(str, bool)  # stem, play (True) or save (False)
    mix_requested = Signal()
    new_file_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.semitones = 0
        self.original_key = "C major"
        self.result: JobResult | None = None
        self._tab_files: list[tuple[str | None, Path]] = []
        self._elapsed_s = 0.0
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        title_label = QLabel(_("Song title"))
        top.addWidget(title_label)
        # Editable here too: a new title is redrawn on every page and used in file names.
        self.title_edit = QLineEdit()
        self.title_edit.setAccessibleName(_("Song title"))
        title_label.setBuddy(self.title_edit)
        font = self.title_edit.font()
        font.setPointSizeF(font.pointSizeF() * 1.1)
        font.setBold(True)
        self.title_edit.setFont(font)
        self.title_edit.editingFinished.connect(self._title_edited)
        top.addWidget(self.title_edit, 1)
        self.new_button = QPushButton(_("New file…"))
        self.new_button.clicked.connect(self.new_file_requested.emit)
        top.addWidget(self.new_button)
        layout.addLayout(top)
        self.summary = QLabel()
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary)
        self.skipped = QLabel()
        self.skipped.setWordWrap(True)
        layout.addWidget(self.skipped)

        self.tabs = QTabBar()
        self.tabs.setExpanding(False)
        self.tabs.setAccessibleName(_("Instruments"))
        self.tabs.currentChanged.connect(self._show_tab)
        layout.addWidget(self.tabs)

        body = QHBoxLayout()
        preview_box = QVBoxLayout()
        self.document = QPdfDocument(self)
        self.view = QPdfView()
        self.view.setDocument(self.document)
        self.view.setPageMode(QPdfView.PageMode.SinglePage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self.view.setAccessibleName(_("Sheet music preview"))
        self.view.setMinimumSize(320, 360)
        self.view.pageNavigator().currentPageChanged.connect(self._update_page_label)
        preview_box.addWidget(self.view, 1)
        nav = QHBoxLayout()
        nav.addStretch(1)
        self.prev_page = QPushButton("‹")
        self.prev_page.setAccessibleName(_("Previous page"))
        self.prev_page.clicked.connect(lambda: self._go_page(-1))
        self.page_label = QLabel()
        self.next_page = QPushButton("›")
        self.next_page.setAccessibleName(_("Next page"))
        self.next_page.clicked.connect(lambda: self._go_page(1))
        nav.addWidget(self.prev_page)
        nav.addWidget(self.page_label)
        nav.addWidget(self.next_page)
        nav.addStretch(1)
        preview_box.addLayout(nav)
        body.addLayout(preview_box, 1)

        side = QVBoxLayout()
        side.addWidget(QLabel(_("Transpose")))
        steps = QHBoxLayout()
        self.down = QPushButton("−")
        self.down.setAccessibleName(_("Down a semitone"))
        self.down.setToolTip(_("Down a semitone"))
        self.down.clicked.connect(lambda: self.set_semitones(self.semitones - 1))
        self.value = QLabel("0")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value.setMinimumWidth(self.value.fontMetrics().horizontalAdvance("+12") + 8)
        self.up = QPushButton("+")
        self.up.setAccessibleName(_("Up a semitone"))
        self.up.setToolTip(_("Up a semitone"))
        self.up.clicked.connect(lambda: self.set_semitones(self.semitones + 1))
        steps.addWidget(self.down)
        steps.addWidget(self.value)
        steps.addWidget(self.up)
        side.addLayout(steps)
        self.step_hint = QLabel(
            _("Each press moves a semitone (half step). Two presses make a whole step.")
        )
        self.step_hint.setWordWrap(True)
        side.addWidget(self.step_hint)
        key_row = QHBoxLayout()
        key_row.addWidget(QLabel(_("Key")))
        self.key_combo = QComboBox()
        self.key_combo.setAccessibleName(_("Key"))
        self.key_combo.activated.connect(self._key_chosen)
        key_row.addWidget(self.key_combo, 1)
        side.addLayout(key_row)
        self.busy = QWidget()
        busy_layout = QVBoxLayout(self.busy)
        busy_layout.setContentsMargins(0, 0, 0, 0)
        busy_bar = QProgressBar()
        busy_bar.setRange(0, 0)
        busy_bar.setTextVisible(False)
        busy_bar.setAccessibleName(_("Redrawing the sheet music"))
        busy_layout.addWidget(busy_bar)
        busy_layout.addWidget(QLabel(_("Redrawing the sheet music")))
        self.busy.setVisible(False)
        side.addWidget(self.busy)
        self.warnings = QLabel()
        self.warnings.setWordWrap(True)
        side.addWidget(self.warnings)
        self.drum_note = QLabel("ⓘ " + _("Drum sheet music is for reference only."))
        self.drum_note.setWordWrap(True)
        side.addWidget(self.drum_note)
        side.addStretch(1)
        side_widget = QWidget()
        side_widget.setLayout(side)
        side_widget.setMaximumWidth(260)
        body.addWidget(side_widget)
        layout.addLayout(body, 1)

        bottom = QHBoxLayout()
        self.listen_button = QPushButton(_("Hear each instrument"))
        self.listen_menu = QMenu(self.listen_button)
        self.listen_button.setMenu(self.listen_menu)
        self.wav_button = QPushButton(_("Save as WAV"))
        self.wav_menu = QMenu(self.wav_button)
        self.wav_button.setMenu(self.wav_menu)
        self.mix_button = QPushButton(_("Make audio file"))
        self.mix_button.setToolTip(
            _("Save only the instruments you choose as one audio file (MP3, M4A, WAV).")
        )
        self.mix_button.clicked.connect(self.mix_requested.emit)
        self.musicxml_button = QPushButton("MusicXML")
        self.musicxml_button.setAccessibleName(_("Save as MusicXML"))
        self.musicxml_button.clicked.connect(lambda: self.export_requested.emit("musicxml"))
        self.midi_button = QPushButton("MIDI")
        self.midi_button.setAccessibleName(_("Save as MIDI"))
        self.midi_button.clicked.connect(lambda: self.export_requested.emit("midi"))
        self.save_button = primary_button(_("Save all"))
        self.save_button.clicked.connect(self.save_all_requested.emit)
        bottom.addWidget(self.listen_button)
        bottom.addWidget(self.wav_button)
        bottom.addWidget(self.mix_button)
        bottom.addStretch(1)
        bottom.addWidget(self.musicxml_button)
        bottom.addWidget(self.midi_button)
        bottom.addWidget(self.save_button)
        layout.addLayout(bottom)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self._busy_timer = QTimer(self)
        self._busy_timer.setSingleShot(True)
        self._busy_timer.timeout.connect(lambda: self.busy.setVisible(True))

    # -- results -----------------------------------------------------------
    def show_result(self, result: JobResult, original_key: str | None = None) -> None:
        """Show a finished job; ``original_key`` is the key before transposition."""
        previous_tab = self._tab_files[self.tabs.currentIndex()][0] if self._tab_files else None
        page = self.view.pageNavigator().currentPage()
        first = self.result is None or original_key is not None
        self.result = result
        if original_key is not None:
            self.original_key = original_key
        files = [*result.pdfs.values(), *([result.combined_pdf] if result.combined_pdf else [])]
        if first:
            self._elapsed_s = result.elapsed_s  # redraws keep the original job time
        self.summary.setText(
            _("Done ({time}) · {count}").format(
                time=format_duration(self._elapsed_s),
                count=ngettext("{n} score", "{n} scores", len(files)).format(n=len(files)),
            )
        )
        if not self.title_edit.hasFocus() or first:
            self.title_edit.setText(result.title)
        skipped = [
            _("{instrument} ({reason})").format(instrument=_(INSTRUMENT_NAMES[s]), reason=_(reason))
            for s, reason in result.skipped.items()
        ]
        self.skipped.setText(
            _("Skipped: {list}").format(list=", ".join(skipped)) if skipped else ""
        )
        self.skipped.setVisible(bool(skipped))
        self._tab_files = []
        if result.combined_pdf:
            self._tab_files.append((None, result.combined_pdf))
        self._tab_files.extend(result.pdfs.items())
        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        for stem, _path in self._tab_files:
            self.tabs.addTab(_("All") if stem is None else _(INSTRUMENT_NAMES[stem]))
        index = next((i for i, (s, _p) in enumerate(self._tab_files) if s == previous_tab), 0)
        self.tabs.setCurrentIndex(index)
        self.tabs.blockSignals(False)
        self._show_tab(index, keep_page=None if first else page)
        stems = list(result.pdfs)
        for menu, play in ((self.listen_menu, True), (self.wav_menu, False)):
            menu.clear()
            for stem in stems:
                action = menu.addAction(_(INSTRUMENT_NAMES[stem]))
                action.triggered.connect(
                    lambda _c=False, s=stem, p=play: self.stem_audio_requested.emit(s, p)
                )
        self.listen_button.setEnabled(bool(stems))
        self.wav_button.setEnabled(bool(stems))
        self.warnings.setText("\n".join("⚠ " + _(w) for w in result.warnings))
        self.drum_note.setVisible("drums" in result.pdfs)
        self._refresh_transpose()
        self.set_busy(False)
        if first:
            self.save_button.setFocus()

    def _title_edited(self) -> None:
        text = self.title_edit.text().strip()
        if self.result is None:
            return
        if not text:
            self.title_edit.setText(self.result.title)  # an empty title is not allowed
            return
        if text != self.result.title:
            self.title_changed.emit(text)

    def _show_tab(self, index: int, keep_page: int | None = None) -> None:
        if not 0 <= index < len(self._tab_files):
            self.document.close()
            self._update_page_label()
            return
        self.document.load(str(self._tab_files[index][1]))
        page = min(keep_page or 0, max(0, self.document.pageCount() - 1))
        self.view.pageNavigator().jump(page, QPointF(), self.view.zoomFactor())
        self._update_page_label()

    def current_stem(self) -> str | None:
        index = self.tabs.currentIndex()
        return self._tab_files[index][0] if 0 <= index < len(self._tab_files) else None

    def page_count(self) -> int:
        return self.document.pageCount()

    def current_page(self) -> int:
        return self.view.pageNavigator().currentPage()

    def _go_page(self, delta: int) -> None:
        count = self.document.pageCount()
        if count == 0:
            return
        page = min(max(0, self.current_page() + delta), count - 1)
        self.view.pageNavigator().jump(page, QPointF(), self.view.zoomFactor())
        self._update_page_label()

    def _update_page_label(self, *_args: object) -> None:
        count = self.document.pageCount()
        current = self.current_page() + 1 if count else 0
        self.page_label.setText(f"{current} / {count}")
        self.page_label.setAccessibleName(
            _("Page {page} of {count}").format(page=current, count=count)
        )
        self.prev_page.setEnabled(current > 1)
        self.next_page.setEnabled(current < count)

    # -- transposition -----------------------------------------------------
    def _refresh_transpose(self) -> None:
        self.value.setText(f"{self.semitones:+d}" if self.semitones else "0")
        self.value.setAccessibleName(_("Transpose: {count} semitones").format(count=self.semitones))
        self.down.setEnabled(self.semitones > -MAX_TRANSPOSE)
        self.up.setEnabled(self.semitones < MAX_TRANSPOSE)
        self.key_combo.blockSignals(True)
        self.key_combo.clear()
        for k in keys_like(self.original_key):
            self.key_combo.addItem(key_label(k, _), k)
        current = transposed_key(self.original_key, self.semitones)
        self.key_combo.setCurrentIndex(max(0, self.key_combo.findData(current)))
        self.key_combo.blockSignals(False)

    def set_semitones(self, value: int) -> None:
        value = max(-MAX_TRANSPOSE, min(MAX_TRANSPOSE, value))
        if value == self.semitones:
            return
        self.semitones = value
        self._refresh_transpose()
        self.transpose_changed.emit(value)

    def _key_chosen(self, index: int) -> None:
        target = self.key_combo.itemData(index)
        if target:
            self.set_semitones(semitones_between(self.original_key, str(target)))

    def set_busy(self, busy: bool) -> None:
        if busy:
            self._busy_timer.start(BUSY_DELAY_MS)
        else:
            self._busy_timer.stop()
            self.busy.setVisible(False)

    def reset_transpose(self) -> None:
        self.semitones = 0
        self.result = None
        self.status.clear()
