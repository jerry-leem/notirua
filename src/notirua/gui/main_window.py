"""Main window: setup → ① file → ② options → ③ progress → ④ result (FR-8).

Every long job runs in a :class:`Task`; this window only reacts to signals,
so the UI thread never waits on the core.
"""

from __future__ import annotations

import logging
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QDragEnterEvent, QDropEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from notirua import APP_NAME, APP_TITLE
from notirua import settings as settings_mod
from notirua.components.manager import (
    ComponentManager,
    human_size,
    optional_manager_from_settings,
)
from notirua.components.manifest import JS_RUNTIME
from notirua.core import youtube as yt
from notirua.core.errors import ComponentMissingError, InvalidYoutubeLinkError, NotiruaError
from notirua.core.pipeline import (
    INSTRUMENT_NAMES,
    SKIP_SILENT,
    JobOptions,
    JobResult,
    Pipeline,
    default_engines,
    export_score,
    inspect,
    safe_filename,
)
from notirua.core.progress import CancelToken, ProgressCallback, ProgressEvent
from notirua.gui.file_page import MAX_RECENT, FilePage
from notirua.gui.mix_dialog import MixDialog
from notirua.gui.options_page import OptionsPage
from notirua.gui.progress_page import ProgressPage
from notirua.gui.result_page import ResultPage
from notirua.gui.settings_dialog import SettingsDialog
from notirua.gui.setup_page import ManagerFactory, SetupPage, default_manager_factory
from notirua.gui.tasks import Task, Work
from notirua.gui.widgets import open_path
from notirua.i18n import N_, _, ngettext

log = logging.getLogger(__name__)

TRANSPOSE_DEBOUNCE_MS = 250
RuntimeManagerFactory = Callable[[settings_mod.Settings], ComponentManager]
YoutubeClientFactory = Callable[[Path | None], yt.YoutubeClient]
RUNTIME_STAGES = (
    ("download:deno", N_("Downloading the helper program")),
    ("install:deno", N_("Installing the helper program")),
)


def default_pipeline(user: settings_mod.Settings) -> Pipeline:
    return Pipeline(
        default_engines(user),
        stage_weights=user.stage_weights,
        cache_limit_bytes=int(user.cache_limit_gb * 1024**3),
    )


class MainWindow(QMainWindow):
    def __init__(
        self,
        user: settings_mod.Settings,
        pipeline: Pipeline | None = None,
        manager_factory: ManagerFactory = default_manager_factory,
        runtime_manager_factory: RuntimeManagerFactory = optional_manager_from_settings,
        youtube_client_factory: YoutubeClientFactory | None = None,
    ) -> None:
        super().__init__()
        self.user = user
        self._pipeline = pipeline
        self.manager_factory = manager_factory
        self.runtime_manager_factory = runtime_manager_factory
        self.youtube_client_factory = youtube_client_factory or self._default_youtube_client
        self._youtube_request: tuple[yt.YoutubeLink, int, bool] | None = None
        self._retry_kind = "score"  # what "Try again" repeats: "score" or "youtube"
        self.saved_audio: yt.SavedAudio | None = None
        self.setWindowTitle(APP_TITLE)
        self.setAcceptDrops(True)
        self.job_task: Task | None = None
        self.render_task: Task | None = None
        self.side_tasks: list[Task] = []
        self.mix_dialog: MixDialog | None = None
        self.input_path: Path | None = None
        self.options: JobOptions | None = None
        self.result: JobResult | None = None
        self._run_number = 0
        self._workdir = Path(tempfile.mkdtemp(prefix="notirua-work-"))
        self._rerender_pending = False

        central = QWidget()
        outer = QVBoxLayout(central)
        header = QHBoxLayout()
        header.addWidget(QLabel(f"<b>{APP_NAME}</b>"))
        header.addStretch(1)
        self.settings_button = QPushButton("⚙ " + _("Settings"))
        self.settings_button.setAccessibleName(_("Settings"))
        self.settings_button.clicked.connect(self.open_settings)
        header.addWidget(self.settings_button)
        outer.addLayout(header)

        self.banner = QFrame()
        self.banner.setFrameShape(QFrame.Shape.StyledPanel)
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.addWidget(QLabel("ⓘ " + _("Components are needed to make sheet music.")), 1)
        self.banner_button = QPushButton(_("Install"))
        self.banner_button.clicked.connect(self.show_setup)
        banner_layout.addWidget(self.banner_button)
        self.banner.setVisible(False)
        outer.addWidget(self.banner)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.setup_page = SetupPage(user, manager_factory)
        self.setup_page.completed.connect(self._setup_completed)
        self.setup_page.postponed.connect(self._setup_postponed)
        self.file_page = FilePage()
        self.file_page.file_chosen.connect(self.open_file)
        self.file_page.youtube_requested.connect(self.start_youtube)
        self.file_page.youtube.load_settings(user)
        self.file_page.youtube.score_requested.connect(self.score_saved_audio)
        self.file_page.set_recent(user.recent_files)
        self.options_page = OptionsPage(user)
        self.options_page.start_requested.connect(self.start_job)
        self.options_page.back_requested.connect(self.show_file_page)
        self.progress_page = ProgressPage()
        self.progress_page.cancel_requested.connect(self.cancel_job)
        self.progress_page.retry_requested.connect(self.retry_job)
        self.progress_page.other_file_requested.connect(self._choose_other_file)
        self.result_page = ResultPage()
        self.result_page.transpose_changed.connect(self._transpose_changed)
        self.result_page.title_changed.connect(self._title_changed)
        self.result_page.save_all_requested.connect(self.save_all)
        self.result_page.export_requested.connect(self.export_file)
        self.result_page.stem_audio_requested.connect(self.stem_audio)
        self.result_page.mix_requested.connect(self.open_mix_dialog)
        self.result_page.new_file_requested.connect(self._choose_other_file)
        self.result_page.status.linkActivated.connect(lambda link: open_path(Path(link)))
        for page in (
            self.setup_page,
            self.file_page,
            self.options_page,
            self.progress_page,
            self.result_page,
        ):
            self.stack.addWidget(page)

        self._transpose_timer = QTimer(self)
        self._transpose_timer.setSingleShot(True)
        self._transpose_timer.timeout.connect(self._rerender)

        self._build_menus()

        self.tray: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.windowIcon(), self)

        self._restore_geometry()
        self.manager = manager_factory(user)
        if self.manager.needs_setup(user):
            self.show_setup()
        else:
            self.show_file_page()

    # -- pipeline -----------------------------------------------------------
    @property
    def pipeline(self) -> Pipeline:
        if self._pipeline is None:
            self._pipeline = default_pipeline(self.user)
        return self._pipeline

    def busy(self) -> bool:
        return self.job_task is not None and self.job_task.running

    # -- navigation --------------------------------------------------------
    def show_setup(self) -> None:
        self.banner.setVisible(False)
        self.setup_page.refresh()
        self.stack.setCurrentWidget(self.setup_page)
        self.setup_page.agree_button.setFocus()

    def _setup_completed(self) -> None:
        self.manager = self.manager_factory(self.user)
        self._pipeline = None  # engines look up component paths again
        self.banner.setVisible(False)
        if self.input_path is not None and self.options is not None:
            self.stack.setCurrentWidget(self.options_page)
        else:
            self.show_file_page()

    def _setup_postponed(self) -> None:
        self.banner.setVisible(True)
        self.show_file_page()

    def show_file_page(self) -> None:
        self.file_page.set_recent(self.user.recent_files)
        self.file_page.youtube.refresh_clipboard()
        self.stack.setCurrentWidget(self.file_page)
        self.file_page.pick_button.setFocus()

    def _shortcut_open(self) -> None:
        if not self.busy():
            self.file_page.choose_file()

    def _shortcut_save(self) -> None:
        if self.stack.currentWidget() is self.result_page and self.result is not None:
            self.save_all()

    def _choose_other_file(self) -> None:
        self.show_file_page()
        self.file_page.choose_file()

    def open_file(self, path: Path) -> None:
        if self.busy():
            return
        self.input_path = path
        self._remember_recent(path)
        duration, title, tracks = None, None, None
        try:
            info = inspect(path)
            duration, title = info.duration_s, info.title
            tracks = [(s.index, s.language) for s in info.streams]
        except NotiruaError as exc:
            # The progress screen explains the problem when the job starts.
            log.info("probe failed for %s: %s", path, exc)
        self.options_page.load_file(
            path,
            duration,
            title,
            self.user.paper or settings_mod.default_paper(),
            tracks,
        )
        self.stack.setCurrentWidget(self.options_page)

    def _remember_recent(self, path: Path) -> None:
        self.file_page.start_dir = str(path.parent)
        recent = [str(path), *(f for f in self.user.recent_files if f != str(path))]
        self.user.recent_files = recent[:MAX_RECENT]
        settings_mod.save(self.user)

    # -- drag and drop anywhere in the window (FR-8) -------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if self.busy() or not urls:
            return
        if urls[0].isLocalFile() or yt.find_link(urls[0].toString()) is not None:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if not urls:
            return
        if urls[0].isLocalFile():
            path = Path(urls[0].toLocalFile())
            if path.is_file():
                event.acceptProposedAction()
                self.open_file(path)
        elif (link := yt.find_link(urls[0].toString())) is not None:
            # A link dragged from the browser: fill the box, the user presses the button.
            event.acceptProposedAction()
            self.show_file_page()
            self.file_page.youtube.set_link(link.url)

    # -- saving audio from a YouTube link (0.5.0) --------------------------------
    def _shortcut_paste(self) -> None:
        if self.stack.currentWidget() is self.file_page and not self.busy():
            self.file_page.paste_link()

    def _default_youtube_client(self, runtime: Path | None) -> yt.YoutubeClient:
        """The proxy chosen in Settings (if any) is used; otherwise the system's."""
        try:
            return yt.YoutubeClient(runtime, proxy=self.user.proxy)
        except ValueError:  # a hand-edited settings file with a bad address
            log.warning("ignoring the proxy address in the settings: %r", self.user.proxy)
            return yt.YoutubeClient(runtime)

    def js_runtime_path(self) -> Path | None:
        """A Deno to run YouTube's player scripts: the downloaded one, or one on the PATH."""
        manager = self.runtime_manager_factory(self.user)
        try:
            entry: Path | None = manager.require(JS_RUNTIME.id)
        except ComponentMissingError:
            entry = None
        return yt.find_js_runtime(entry)

    def confirm_runtime_download(self) -> bool:
        """Ask before downloading Deno (consent first, like every other component)."""
        manager = self.runtime_manager_factory(self.user)
        plan = manager.plan([JS_RUNTIME])
        file = JS_RUNTIME.file_for(manager.platform_key)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(_("One more helper is needed"))
        box.setText(_("Reading YouTube links needs a small helper program."))
        box.setInformativeText(
            _(
                "{name}: {purpose}\n\nDownload: {size} (about {installed} on disk) from {source}.\n"
                "License: {license}.\n\nIt is downloaded once and kept. Nothing else is downloaded."
            ).format(
                name=_(JS_RUNTIME.name_id),
                purpose=_(JS_RUNTIME.purpose_id),
                size=human_size(plan.download_bytes),
                installed=human_size(plan.install_bytes),
                source=file.domain if file else "github.com",
                license=JS_RUNTIME.license_id,
            )
        )
        download = box.addButton(_("Download and continue"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(download)
        box.exec()
        return box.clickedButton() is download

    def start_youtube(self, text: str, kbps: int, make_score: bool) -> None:
        """Check the link, make sure the helper is there, save the audio, and go on."""
        if self.busy():
            return
        try:
            link = yt.parse_link(text)
            yt.check_bitrate(kbps)
        except (InvalidYoutubeLinkError, ValueError) as exc:
            self.show_file_page()
            if isinstance(exc, NotiruaError):
                QMessageBox.warning(
                    self, _("YouTube link"), f"{exc.user_message()}\n\n{exc.user_hint()}"
                )
            return
        self.user.youtube_bitrate = kbps
        self.user.youtube_make_score = make_score
        settings_mod.save(self.user)
        self._youtube_request = (link, kbps, make_score)
        self.file_page.youtube.hide_saved()
        self._retry_kind = "youtube"
        runtime = self.js_runtime_path()
        if runtime is None:
            if not self.confirm_runtime_download():
                self.show_file_page()
                return
            self._install_runtime()
            return
        self._run_youtube(runtime)

    def _install_runtime(self) -> None:
        manager = self.runtime_manager_factory(self.user)
        consent = manager.make_consent([JS_RUNTIME])

        def work(progress: ProgressCallback, cancel: CancelToken) -> None:
            manager.install([JS_RUNTIME], consent, progress=progress, cancel=cancel)

        self.progress_page.begin_stages(_("Getting the helper program"), RUNTIME_STAGES)
        self.stack.setCurrentWidget(self.progress_page)
        self.progress_page.cancel_button.setFocus()
        self._start_task(work, "runtime", self._runtime_installed, self._youtube_failed)

    def _runtime_installed(self, _result: object) -> None:
        self.job_task = None
        runtime = self.js_runtime_path()
        if runtime is None:  # the install said done but the file is not there
            self._youtube_failed(ComponentMissingError(name=JS_RUNTIME.id))
            return
        self._run_youtube(runtime)

    def _run_youtube(self, runtime: Path | None) -> None:
        assert self._youtube_request is not None
        link, kbps, _make_score = self._youtube_request
        out_dir = yt.default_folder(self.user.youtube_dir)
        client = self.youtube_client_factory(runtime)

        def work(progress: ProgressCallback, cancel: CancelToken) -> yt.SavedAudio:
            return yt.save_as_mp3(
                link, out_dir, kbps, client=client, progress=progress, cancel=cancel
            )

        self.progress_page.begin_stages(
            _("Saving the audio from YouTube"),
            [(spec.name, spec.message_id) for spec in yt.STAGES],
        )
        self.stack.setCurrentWidget(self.progress_page)
        self.progress_page.cancel_button.setFocus()
        self._start_task(work, "youtube", self._youtube_done, self._youtube_failed)

    def _start_task(
        self,
        work: Work,
        name: str,
        on_done: Callable[[Any], None],
        on_failed: Callable[[BaseException], None],
    ) -> None:
        task = Task(work, name, self)
        task.progress.connect(self._job_progress)
        task.succeeded.connect(on_done)
        task.failed.connect(on_failed)
        task.cancelled.connect(self._youtube_cancelled)
        self.job_task = task
        task.start()

    def _youtube_done(self, saved: yt.SavedAudio) -> None:
        self.job_task = None
        self.progress_page.panel.finish()
        self.progress_page.running = False
        self.saved_audio = saved
        self.setWindowTitle(APP_TITLE)
        assert self._youtube_request is not None
        if self._youtube_request[2]:
            # The audio is saved: carry on to the sheet music with the usual defaults.
            self.score_saved_audio(saved.path)
            self.options_page.start_button.click()
        else:
            # MP3 only (0.5.2): back to the first screen, which says where the file is.
            self._remember_recent(saved.path)
            self.show_file_page()
            self.file_page.youtube.show_saved(saved.path)
            self._notify(_("The audio is saved."), saved.title)

    def score_saved_audio(self, path: Path) -> None:
        """Open an MP3 saved from YouTube on the options screen."""
        self.file_page.youtube.hide_saved()
        self.open_file(path)
        self.options_page.show_saved_audio(path)

    def _youtube_failed(self, error: BaseException) -> None:
        self.job_task = None
        self.setWindowTitle(APP_TITLE)
        self.progress_page.show_error(error)
        message = error.user_message() if isinstance(error, NotiruaError) else str(error)
        self._notify(_("Saving the audio failed."), message)

    def _youtube_cancelled(self) -> None:
        self.job_task = None
        self.setWindowTitle(APP_TITLE)
        self.progress_page.running = False
        self.show_file_page()

    # -- the job -----------------------------------------------------------
    def _next_out_dir(self) -> Path:
        self._run_number += 1
        return self._workdir / f"run-{self._run_number}"

    def start_job(self, options: JobOptions) -> None:
        if self.input_path is None or self.busy():
            return
        if self.manager_factory(self.user).missing():
            self.options = options
            self.show_setup()
            return
        self._retry_kind = "score"
        self.options = options
        self.user.paper = options.paper
        self.user.guitar_tuning = options.guitar_tuning
        self.user.bass_tuning = options.bass_tuning
        settings_mod.save(self.user)
        self.result = None
        self.result_page.reset_transpose()
        path, out_dir = self.input_path, self._next_out_dir()
        title = options.title or path.stem

        def work(progress: ProgressCallback, cancel: CancelToken) -> JobResult:
            return self.pipeline.run(path, out_dir, options, progress=progress, cancel=cancel)

        # Clear the saved results only once; redraws and retries reuse the new ones.
        self.options = replace(options, fresh=False)
        self.progress_page.begin(title)
        self.stack.setCurrentWidget(self.progress_page)
        self.progress_page.cancel_button.setFocus()
        task = Task(work, "pipeline", self)
        task.progress.connect(self._job_progress)
        task.succeeded.connect(self._job_done)
        task.failed.connect(self._job_failed)
        task.cancelled.connect(self._job_cancelled)
        self.job_task = task
        task.start()

    def retry_job(self) -> None:
        if self._retry_kind == "youtube" and self._youtube_request is not None:
            link, kbps, make_score = self._youtube_request
            self.start_youtube(link.url, kbps, make_score)
        elif self.options is not None:
            self.start_job(self.options)

    def cancel_job(self) -> None:
        if self.job_task is not None:
            self.job_task.cancel()

    def _job_progress(self, event: ProgressEvent) -> None:
        self.progress_page.apply(event)
        self.setWindowTitle(f"{int(self.progress_page.panel.fraction * 100)}% — {APP_TITLE}")

    def _job_done(self, result: JobResult) -> None:
        self.progress_page.panel.finish()
        self.progress_page.running = False
        self.setWindowTitle(f"{result.title} — {APP_TITLE}")
        self.result = result
        self.result_page.show_result(result, original_key=result.score.key)
        self.stack.setCurrentWidget(self.result_page)
        self._notify(_("The sheet music is ready."), result.title)

    def _job_failed(self, error: BaseException) -> None:
        self.setWindowTitle(APP_TITLE)
        self.progress_page.show_error(error)
        message = error.user_message() if isinstance(error, NotiruaError) else str(error)
        self._notify(_("Making sheet music failed."), message)

    def _job_cancelled(self) -> None:
        self.setWindowTitle(APP_TITLE)
        self.progress_page.running = False
        self.stack.setCurrentWidget(self.options_page)
        self.options_page.start_button.setFocus()

    def _notify(self, title: str, message: str) -> None:
        """Dock/taskbar attention plus an OS notification when the window is in the back."""
        QApplication.alert(self)
        if self.tray is not None and not self.isActiveWindow():
            self.tray.show()
            self.tray.showMessage(title, message)

    # -- transposition (FR-6): only arrange and engrave run again ----------
    def _transpose_changed(self, _semitones: int) -> None:
        self._request_rerender()

    def _title_changed(self, title: str) -> None:
        """A new title is printed on every page and used in the file names."""
        if self.options is None:
            return
        self.options = replace(self.options, title=title.strip() or None)
        self._request_rerender()

    def _request_rerender(self) -> None:
        self._rerender_pending = True
        self._transpose_timer.start(TRANSPOSE_DEBOUNCE_MS)

    def _rerender(self) -> None:
        if self.options is None or self.input_path is None or not self._rerender_pending:
            return
        if self.render_task is not None and self.render_task.running:
            # Finish (or cancel) the running render first; we come back afterwards.
            self.render_task.cancel()
            self._transpose_timer.start(TRANSPOSE_DEBOUNCE_MS)
            return
        self._rerender_pending = False
        # Only arrange and engrave run again; earlier stages come from the cache.
        options = replace(self.options, transpose=self.result_page.semitones, target_key=None)
        path, out_dir = self.input_path, self._next_out_dir()

        def work(progress: ProgressCallback, cancel: CancelToken) -> JobResult:
            return self.pipeline.run(path, out_dir, options, progress=progress, cancel=cancel)

        self.result_page.set_busy(True)
        task = Task(work, "redraw", self)
        task.succeeded.connect(self._rerender_done)
        task.failed.connect(self._rerender_failed)
        task.cancelled.connect(lambda: self.result_page.set_busy(False))
        self.render_task = task
        task.start()

    def _rerender_done(self, result: JobResult) -> None:
        if self._rerender_pending:
            return  # a newer request is waiting; keep the busy bar
        self.result = result
        self.result_page.show_result(result)
        self.setWindowTitle(f"{result.title} — {APP_TITLE}")

    def _rerender_failed(self, error: BaseException) -> None:
        self.result_page.set_busy(False)
        message = error.user_message() if isinstance(error, NotiruaError) else str(error)
        self.result_page.status.setText("✗ " + message)

    # -- saving ------------------------------------------------------------
    def _ask_folder(self) -> Path | None:
        start = self.user.output_dir or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, _("Choose where to save"), start)
        if not folder:
            return None
        self.user.output_dir = folder
        settings_mod.save(self.user)
        return Path(folder)

    def save_all(self) -> None:
        result = self.result
        if result is None:
            return
        folder = self._ask_folder()
        if folder is None:
            return
        files = [*result.pdfs.values(), *([result.combined_pdf] if result.combined_pdf else [])]
        saved = [_copy_unique(f, folder) for f in files]
        self._saved_message(len(saved), folder)

    def _saved_message(self, count: int, folder: Path) -> None:
        text = ngettext("Saved {n} file.", "Saved {n} files.", count).format(n=count)
        self.result_page.status.setText(f'✓ {text} <a href="{folder}">{_("Open folder")}</a>')

    def export_file(self, fmt: str) -> None:
        result, options = self.result, self.options
        if result is None or options is None:
            return
        suffix = ".mid" if fmt == "midi" else ".musicxml"
        start = Path(self.user.output_dir or Path.home()) / f"{safe_filename(result.title)}{suffix}"
        name_filter = _("MIDI file (*.mid)") if fmt == "midi" else _("MusicXML file (*.musicxml)")
        target, _filter = QFileDialog.getSaveFileName(self, _("Save"), str(start), name_filter)
        if not target:
            return
        self.user.output_dir = str(Path(target).parent)
        settings_mod.save(self.user)
        score, pdf_language = result.score, options.pdf_language
        self._side_task(
            lambda _p, _c: export_score(score, fmt, Path(target), pdf_language),
            lambda _r: self._saved_message(1, Path(target).parent),
        )

    def stem_audio(self, stem: str, play: bool) -> None:
        path = self.input_path
        if path is None:
            return
        if play:
            target = self._workdir / "audio" / f"{stem}.wav"
        else:
            start = Path(self.user.output_dir or Path.home()) / (
                f"{safe_filename(self.result.title if self.result else path.stem)} - "
                f"{safe_filename(_(INSTRUMENT_NAMES[stem]))}.wav"
            )
            chosen, _filter = QFileDialog.getSaveFileName(
                self, _("Save"), str(start), _("WAV file (*.wav)")
            )
            if not chosen:
                return
            target = Path(chosen)
        pipeline = self.pipeline
        self._side_task(
            lambda _p, _c: pipeline.export_stem_audio(path, stem, target),
            (lambda r: open_path(r)) if play else (lambda r: self._saved_message(1, r.parent)),
        )

    def open_mix_dialog(self) -> None:
        """Make audio file: the chosen instruments as one MP3, M4A, or WAV file."""
        path, options, result = self.input_path, self.options, self.result
        if path is None or options is None or result is None:
            return
        silent = [s for s, reason in result.skipped.items() if reason == SKIP_SILENT]
        if self.mix_dialog is not None:
            self.mix_dialog.close()
            self.mix_dialog.deleteLater()
        self.mix_dialog = MixDialog(
            self.user, self.pipeline, path, options, result.title, silent, self._workdir, self
        )
        self.mix_dialog.open()

    def _side_task(self, work: Work, on_done: Callable[[Any], None]) -> None:
        task = Task(work, "side", self)
        task.succeeded.connect(on_done)
        task.failed.connect(
            lambda e: self.result_page.status.setText(
                "✗ " + (e.user_message() if isinstance(e, NotiruaError) else str(e))
            )
        )
        task.succeeded.connect(lambda _r, t=task: self._forget(t))
        task.failed.connect(lambda _e, t=task: self._forget(t))
        self.side_tasks.append(task)
        task.start()

    def _forget(self, task: Task) -> None:
        if task in self.side_tasks:
            self.side_tasks.remove(task)

    # -- settings ----------------------------------------------------------
    def open_settings(self, about: bool = False) -> None:
        dialog = SettingsDialog(self.user, self.manager_factory(self.user), self)
        dialog.setup_requested.connect(self.show_setup)
        dialog.components_changed.connect(self._components_changed)
        if about:
            dialog.tabs.setCurrentIndex(dialog.tabs.count() - 1)
        dialog.exec()

    # -- menus -------------------------------------------------------------
    def _build_menus(self) -> None:
        """File and Help menus. On macOS Qt moves Settings, Quit, and About into the
        application menu (by their roles); Windows and Linux show them in the window."""
        self.open_action = QAction(_("Open a music file…"), self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self._shortcut_open)
        self.save_action = QAction(_("Save all"), self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self._shortcut_save)
        for action in (self.open_action, self.save_action):
            action.setMenuRole(QAction.MenuRole.NoRole)
        self.settings_action = QAction(_("Settings…"), self)
        self.settings_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        self.settings_action.setShortcut(QKeySequence("Ctrl+,"))  # ⌘, on macOS
        self.settings_action.triggered.connect(lambda: self.open_settings())
        self.quit_action = QAction(_("Quit {name}").format(name=APP_NAME), self)
        self.quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        self.quit_action.setShortcut(QKeySequence("Ctrl+Q"))  # ⌘Q on macOS
        self.quit_action.triggered.connect(self.close)
        self.about_action = QAction(_("About {name}").format(name=APP_NAME), self)
        self.about_action.setMenuRole(QAction.MenuRole.AboutRole)
        self.about_action.triggered.connect(lambda: self.open_settings(about=True))

        # Ctrl+V (⌘V) on the first screen pastes a YouTube link from the clipboard.
        self.paste_shortcut = QShortcut(QKeySequence.StandardKey.Paste, self)
        self.paste_shortcut.activated.connect(self._shortcut_paste)

        bar = self.menuBar()
        # Kept as attributes: PySide may otherwise drop the wrappers of native menus.
        self.file_menu = QMenu(_("&File"), self)
        self.file_menu.addAction(self.open_action)
        self.file_menu.addAction(self.save_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.settings_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.quit_action)
        self.help_menu = QMenu(_("&Help"), self)
        self.help_menu.addAction(self.about_action)
        bar.addMenu(self.file_menu)
        bar.addMenu(self.help_menu)

        if sys.platform == "darwin":
            # Right-click on the Dock icon; macOS adds Quit there by itself.
            self.dock_menu = QMenu(self)
            self.dock_menu.addAction(self.open_action)
            self.dock_menu.addAction(self.settings_action)
            self.dock_menu.setAsDockMenu()

    def _components_changed(self) -> None:
        self._pipeline = None
        missing = bool(self.manager_factory(self.user).missing())
        self.banner.setVisible(missing and self.stack.currentWidget() is not self.setup_page)

    # -- window state --------------------------------------------------------
    def _restore_geometry(self) -> None:
        if self.user.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(self.user.window_geometry.encode()))
        else:
            self.resize(900, 680)

    def closeEvent(self, event: QCloseEvent) -> None:
        mix_task = self.mix_dialog.task if self.mix_dialog is not None else None
        running = [
            t
            for t in (
                self.job_task,
                self.render_task,
                self.setup_page.task,
                mix_task,
                *self.side_tasks,
            )
            if t is not None and t.running
        ]
        if running:
            answer = QMessageBox.question(
                self,
                APP_NAME,
                _("Work is still in progress. Stop it and quit?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.setup_page.cancel_install()
            for t in running:
                t.cancel()
            for t in running:
                t.wait(3.0)
        self.user.window_geometry = bytes(self.saveGeometry().toBase64().data()).decode()
        settings_mod.save(self.user)
        shutil.rmtree(self._workdir, ignore_errors=True)
        event.accept()


def _copy_unique(source: Path, folder: Path) -> Path:
    """Copy without overwriting: ``name.pdf``, ``name (2).pdf``, …"""
    target = folder / source.name
    n = 2
    while target.exists():
        target = folder / f"{source.stem} ({n}){source.suffix}"
        n += 1
    shutil.copy2(source, target)
    return target
