"""Progress events and cancellation shared by every long-running task (SPEC 5.6, FR-11)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Literal

from notirua.core.errors import Cancelled

StageState = Literal["pending", "running", "done", "skipped", "failed"]


@dataclass(frozen=True)
class ProgressEvent:
    task_id: str
    stage: str
    stage_state: StageState
    stage_fraction: float | None
    overall_fraction: float
    message_id: str
    message_args: dict[str, object] = field(default_factory=dict)
    eta_seconds: float | None = None


ProgressCallback = Callable[[ProgressEvent], None]


def _ignore(_event: ProgressEvent) -> None:
    return None


class CancelToken:
    """Thread-safe cancellation flag checked inside long loops."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise Cancelled()


@dataclass(frozen=True)
class StageSpec:
    name: str
    weight: float
    message_id: str


class ProgressReporter:
    """Turns per-stage progress into monotonic overall progress events.

    Stage weights come from measured durations (SPEC 5.6). A heartbeat thread
    re-emits the latest event so listeners hear from us at least once a second
    even while a single opaque step (model load, external process) is running.
    """

    MIN_ETA_ELAPSED_S = 3.0
    MIN_ETA_FRACTION = 0.05

    def __init__(
        self,
        task_id: str,
        stages: Sequence[StageSpec],
        callback: ProgressCallback | None = None,
        heartbeat_s: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not stages:
            raise ValueError("at least one stage is required")
        self.task_id = task_id
        self._stages = {s.name: s for s in stages}
        self._order = [s.name for s in stages]
        total = sum(max(s.weight, 0.0) for s in stages) or 1.0
        self._weights = {s.name: max(s.weight, 0.0) / total for s in stages}
        self._fractions: dict[str, float] = dict.fromkeys(self._order, 0.0)
        self._states: dict[str, StageState] = dict.fromkeys(self._order, "pending")
        self._callback = callback or _ignore
        self._clock = clock
        self._started = clock()
        self._overall = 0.0
        self._last: ProgressEvent | None = None
        self._lock = threading.Lock()
        self._heartbeat_s = heartbeat_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self) -> ProgressReporter:
        self.start_heartbeat()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop_heartbeat()

    def start_heartbeat(self) -> None:
        if self._thread is not None or self._heartbeat_s <= 0:
            return
        self._thread = threading.Thread(target=self._beat, name="progress-heartbeat", daemon=True)
        self._thread.start()

    def stop_heartbeat(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _beat(self) -> None:
        while not self._stop.wait(self._heartbeat_s):
            with self._lock:
                last = self._last
                if last is None:
                    continue
                event = replace(last, eta_seconds=self._eta())
            self._callback(event)

    # -- reporting ---------------------------------------------------------
    @property
    def states(self) -> dict[str, StageState]:
        return dict(self._states)

    @property
    def overall(self) -> float:
        return self._overall

    def _eta(self) -> float | None:
        elapsed = self._clock() - self._started
        if elapsed < self.MIN_ETA_ELAPSED_S or self._overall < self.MIN_ETA_FRACTION:
            return None
        if self._overall >= 1.0:
            return 0.0
        return elapsed * (1.0 - self._overall) / self._overall

    def _emit(
        self,
        stage: str,
        state: StageState,
        stage_fraction: float | None,
        message_id: str | None,
        message_args: dict[str, object] | None,
    ) -> None:
        with self._lock:
            done = sum(self._weights[n] * self._fractions[n] for n in self._order)
            self._overall = min(1.0, max(self._overall, done))
            event = ProgressEvent(
                task_id=self.task_id,
                stage=stage,
                stage_state=state,
                stage_fraction=stage_fraction,
                overall_fraction=self._overall,
                message_id=message_id or self._stages[stage].message_id,
                message_args=dict(message_args or {}),
                eta_seconds=self._eta(),
            )
            self._last = event
        self._callback(event)

    def start(self, stage: str, message_id: str | None = None, **args: object) -> None:
        self._states[stage] = "running"
        self._emit(stage, "running", None, message_id, args)

    def update(
        self,
        stage: str,
        fraction: float | None,
        message_id: str | None = None,
        **args: object,
    ) -> None:
        if fraction is not None:
            fraction = min(1.0, max(0.0, fraction))
            self._fractions[stage] = max(self._fractions[stage], fraction)
        self._emit(stage, "running", fraction, message_id, args)

    def done(self, stage: str, message_id: str | None = None, **args: object) -> None:
        self._fractions[stage] = 1.0
        self._states[stage] = "done"
        self._emit(stage, "done", 1.0, message_id, args)

    def skip(self, stage: str, message_id: str | None = None, **args: object) -> None:
        self._fractions[stage] = 1.0
        self._states[stage] = "skipped"
        self._emit(stage, "skipped", None, message_id, args)

    def fail(self, stage: str, message_id: str | None = None, **args: object) -> None:
        self._states[stage] = "failed"
        self._emit(stage, "failed", None, message_id, args)

    def sub(self, stage: str) -> Callable[[float], None]:
        """Return a ``fraction -> None`` helper bound to one stage."""

        def report(fraction: float) -> None:
            self.update(stage, fraction)

        return report
