"""Make audio file: mix chosen instruments into one MP3, M4A, or WAV file (0.4.0).

The dialog runs :meth:`Pipeline.export_mix` in a :class:`Task`, with a
progress bar and a way to stop, for both the preview and the saved file.
"""

from __future__ import annotations

import html
import itertools
from collections.abc import Collection
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from notirua import settings as settings_mod
from notirua.core import mix
from notirua.core.errors import NotiruaError
from notirua.core.model import STEMS
from notirua.core.pipeline import (
    INSTRUMENT_NAMES,
    JobOptions,
    MixResult,
    Pipeline,
    safe_filename,
)
from notirua.core.progress import CancelToken, ProgressCallback, ProgressEvent
from notirua.gui.tasks import Task
from notirua.gui.widgets import PROGRESS_STEPS, open_path, primary_button
from notirua.i18n import _, translate_progress

_preview_numbers = itertools.count(1)


class MixDialog(QDialog):
    def __init__(
        self,
        user: settings_mod.Settings,
        pipeline: Pipeline,
        input_path: Path,
        options: JobOptions,
        title: str,
        silent: Collection[str],
        workdir: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.user = user
        self.pipeline = pipeline
        self.input_path = input_path
        # Same time range and track as the sheet music; transposition never applies.
        self.options = replace(options, title=title, transpose=0, target_key=None, fresh=False)
        self.title = title
        self.silent = set(silent)
        self.workdir = workdir
        self.task: Task | None = None
        self.last_file: Path | None = None
        self.setWindowTitle(_("Make audio file"))
        layout = QVBoxLayout(self)
        intro = QLabel(
            _(
                "Choose the instruments to keep. They are put together into one audio file, "
                "for example a backing track without vocals."
            )
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        group = QGroupBox(_("Instruments"))
        grid = QGridLayout(group)
        self.checks: dict[str, QCheckBox] = {}
        for i, stem in enumerate(STEMS):
            name = _(INSTRUMENT_NAMES[stem])
            box = QCheckBox(name)
            if stem in self.silent:
                box.setEnabled(False)
                box.setText(_("{instrument} (no sound)").format(instrument=name))
            box.toggled.connect(self._refresh)
            grid.addWidget(box, i // 2, i % 2)
            self.checks[stem] = box
        layout.addWidget(group)

        quick = QHBoxLayout()
        self.no_vocals_button = QPushButton(_("Remove vocals (MR)"))
        self.no_vocals_button.clicked.connect(self.choose_backing_track)
        self.all_button = QPushButton(_("Select all"))
        self.all_button.clicked.connect(lambda: self.choose(STEMS))
        self.none_button = QPushButton(_("Clear all"))
        self.none_button.clicked.connect(lambda: self.choose(()))
        quick.addWidget(self.no_vocals_button)
        quick.addWidget(self.all_button)
        quick.addWidget(self.none_button)
        quick.addStretch(1)
        layout.addLayout(quick)

        form = QFormLayout()
        self.format_combo = QComboBox()
        for fmt in mix.available_formats():
            self.format_combo.addItem(_(mix.FORMAT_LABELS[fmt]), fmt)
        self.format_combo.setCurrentIndex(max(0, self.format_combo.findData(user.mix_format)))
        self.format_combo.setAccessibleName(_("File type"))
        form.addRow(_("File type"), self.format_combo)
        layout.addLayout(form)
        pitch_note = QLabel(
            _("The audio keeps its original key, even if you transposed the music.")
        )
        pitch_note.setWordWrap(True)
        layout.addWidget(pitch_note)

        self.busy = QWidget()
        busy_layout = QHBoxLayout(self.busy)
        busy_layout.setContentsMargins(0, 0, 0, 0)
        self.bar = QProgressBar()
        self.bar.setRange(0, PROGRESS_STEPS)
        self.bar.setTextVisible(False)
        self.bar.setAccessibleName(_("Making the audio file"))
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.stop_button = QPushButton(_("Cancel"))
        self.stop_button.clicked.connect(self.stop)
        busy_layout.addWidget(self.bar, 1)
        busy_layout.addWidget(self.stop_button)
        layout.addWidget(self.busy)
        layout.addWidget(self.message)
        self.busy.setVisible(False)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.RichText)
        self.status.linkActivated.connect(lambda link: open_path(Path(link)))
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        self.preview_button = QPushButton(_("Listen first"))
        self.preview_button.clicked.connect(self.preview)
        self.close_button = QPushButton(_("Close"))
        self.close_button.clicked.connect(self.reject)
        self.save_button = primary_button(_("Save…"))
        self.save_button.clicked.connect(self.save)
        buttons.addWidget(self.preview_button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)
        self.choose_backing_track()

    # -- choosing ------------------------------------------------------------
    def chosen(self) -> list[str]:
        return [s for s, box in self.checks.items() if box.isChecked() and box.isEnabled()]

    def choose(self, stems: Collection[str]) -> None:
        for stem, box in self.checks.items():
            box.setChecked(box.isEnabled() and stem in stems)

    def choose_backing_track(self) -> None:
        self.choose([s for s in STEMS if s != "vocals"])

    def fmt(self) -> str:
        return str(self.format_combo.currentData() or "wav")

    def _refresh(self) -> None:
        running = self.task is not None and self.task.running
        some = bool(self.chosen())
        self.save_button.setEnabled(some and not running)
        self.preview_button.setEnabled(some and not running)
        for widget in (self.no_vocals_button, self.all_button, self.none_button):
            widget.setEnabled(not running)
        self.format_combo.setEnabled(not running)

    def suggested_name(self) -> str:
        available = [s for s in STEMS if s not in self.silent]
        name = mix.mix_name(self.title, self.chosen(), available, _, INSTRUMENT_NAMES)
        return f"{safe_filename(name)}{mix.FORMATS[self.fmt()][0]}"

    # -- running -------------------------------------------------------------
    def preview(self) -> None:
        target = self.workdir / "audio" / f"mix-{next(_preview_numbers)}.wav"
        self._start(self.chosen(), "wav", target, play=True)

    def save(self) -> None:
        include, fmt = self.chosen(), self.fmt()
        if not include:
            return
        start = Path(self.user.output_dir or Path.home()) / self.suggested_name()
        chosen, _filter = QFileDialog.getSaveFileName(
            self, _("Save"), str(start), _(mix.FORMAT_FILTERS[fmt])
        )
        if not chosen:
            return
        target = Path(chosen)
        if target.suffix.lower() != mix.FORMATS[fmt][0]:
            target = target.with_name(target.name + mix.FORMATS[fmt][0])
        self.user.output_dir = str(target.parent)
        self.user.mix_format = fmt
        settings_mod.save(self.user)
        self._start(include, fmt, target, play=False)

    def _start(self, include: list[str], fmt: str, target: Path, play: bool) -> None:
        if not include or (self.task is not None and self.task.running):
            return
        pipeline, path, options = self.pipeline, self.input_path, self.options

        def work(progress: ProgressCallback, cancel: CancelToken) -> MixResult:
            return pipeline.export_mix(path, include, target, fmt, options, progress, cancel)

        task = Task(work, "mix", self)
        task.progress.connect(self._progress)
        task.succeeded.connect(lambda r, p=play: self._done(r, p))
        task.failed.connect(self._failed)
        task.cancelled.connect(self._cancelled)
        self.task = task
        self.status.clear()
        self.bar.setValue(0)
        self.message.setText(_("Making the audio file"))
        self.busy.setVisible(True)
        self.message.setVisible(True)
        task.start()
        self._refresh()

    def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()

    def _progress(self, event: ProgressEvent) -> None:
        self.bar.setValue(max(self.bar.value(), int(event.overall_fraction * PROGRESS_STEPS)))
        self.message.setText(translate_progress(event.message_id, event.message_args))

    def _finish(self) -> None:
        self.busy.setVisible(False)
        self.message.setVisible(False)
        self._refresh()

    def _done(self, result: MixResult, play: bool) -> None:
        self._finish()
        self.last_file = result.path
        if play:
            open_path(result.path)
            return
        text = html.escape(_("Saved {name}.").format(name=result.path.name))
        folder = html.escape(str(result.path.parent), quote=True)
        self.status.setText(f'✓ {text} <a href="{folder}">{_("Open folder")}</a>')

    def _failed(self, error: BaseException) -> None:
        self._finish()
        message = error.user_message() if isinstance(error, NotiruaError) else str(error)
        self.status.setText("✗ " + message)

    def _cancelled(self) -> None:
        self._finish()
        self.status.setText(_("Cancelled. Nothing was saved."))

    def _stop_and_wait(self) -> None:
        if self.task is not None and self.task.running:
            self.task.cancel()
            self.task.wait(3.0)

    def reject(self) -> None:
        self._stop_and_wait()
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._stop_and_wait()
        super().closeEvent(event)
