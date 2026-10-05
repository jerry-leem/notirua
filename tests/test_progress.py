from __future__ import annotations

import time

import pytest

from notirua.core.errors import Cancelled
from notirua.core.progress import CancelToken, ProgressEvent, ProgressReporter, StageSpec


def stages() -> list[StageSpec]:
    return [StageSpec("a", 1, "A"), StageSpec("b", 3, "B")]


def test_overall_progress_is_weighted_and_monotonic() -> None:
    events: list[ProgressEvent] = []
    rep = ProgressReporter("t", stages(), events.append, heartbeat_s=0)
    rep.start("a")
    rep.update("a", 0.5)
    rep.update("a", 0.2)  # going backwards must not lower progress
    rep.done("a")
    rep.start("b")
    rep.update("b", 0.5)
    rep.done("b")
    fractions = [e.overall_fraction for e in events]
    assert fractions == sorted(fractions)
    assert fractions[-1] == pytest.approx(1.0)
    assert events[3].overall_fraction == pytest.approx(0.25)


def test_skip_and_fail_states() -> None:
    events: list[ProgressEvent] = []
    rep = ProgressReporter("t", stages(), events.append, heartbeat_s=0)
    rep.skip("a")
    rep.start("b")
    rep.fail("b")
    assert rep.states == {"a": "skipped", "b": "failed"}
    assert events[0].stage_state == "skipped"


def test_heartbeat_repeats_last_event() -> None:
    events: list[ProgressEvent] = []
    with ProgressReporter("t", stages(), events.append, heartbeat_s=0.05) as rep:
        rep.start("a")
        time.sleep(0.3)
    assert len(events) >= 4
    assert all(e.stage == "a" for e in events)


def test_eta_hidden_early() -> None:
    clock = iter([0.0, 0.5, 10.0]).__next__
    events: list[ProgressEvent] = []
    rep = ProgressReporter("t", stages(), events.append, heartbeat_s=0, clock=clock)
    rep.update("a", 0.5)  # t=0.5s: too early for an estimate
    rep.done("a")  # t=10s, 25% done -> 30s left
    assert events[0].eta_seconds is None
    assert events[1].eta_seconds == pytest.approx(30.0)


def test_cancel_token() -> None:
    token = CancelToken()
    token.raise_if_cancelled()
    token.cancel()
    with pytest.raises(Cancelled):
        token.raise_if_cancelled()
