"""Run core work off the UI thread and deliver results through Qt signals (FR-8, SPEC 5.6).

The core calls its progress callback from worker threads. Signals emitted
there reach slots of objects living in the UI thread through queued
connections, so widgets are only touched on the UI thread.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal

from notirua.core.errors import Cancelled
from notirua.core.progress import CancelToken, ProgressCallback, ProgressEvent

log = logging.getLogger(__name__)

Work = Callable[[ProgressCallback, CancelToken], Any]


class Task(QObject):
    """One background job. Emits exactly one of ``succeeded``, ``failed``, ``cancelled``."""

    progress = Signal(object)  # ProgressEvent
    succeeded = Signal(object)
    failed = Signal(object)  # Exception
    cancelled = Signal()

    def __init__(self, work: Work, name: str = "task", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._work = work
        self._name = name
        self.cancel_token = CancelToken()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("a task can only be started once")
        self._thread = threading.Thread(target=self._run, name=f"notirua-{self._name}", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self.cancel_token.cancel()

    def wait(self, timeout: float | None = None) -> bool:
        if self._thread is None:
            return True
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _emit_progress(self, event: ProgressEvent) -> None:
        self.progress.emit(event)

    def _run(self) -> None:
        try:
            result = self._work(self._emit_progress, self.cancel_token)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:
            if self.cancel_token.cancelled:
                self.cancelled.emit()
                return
            log.exception("%s failed", self._name)
            self.failed.emit(exc)
        else:
            if self.cancel_token.cancelled:
                self.cancelled.emit()
            else:
                self.succeeded.emit(result)
