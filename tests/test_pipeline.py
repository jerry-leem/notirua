"""Pipeline contract tests with fake engines (no models, no LilyPond)."""

from __future__ import annotations

import itertools
import threading
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from notirua.core.decode import AudioArray
from notirua.core.errors import Cancelled
from notirua.core.model import STEMS, NoteEvent
from notirua.core.pipeline import STAGE_MESSAGES, Engines, JobOptions, Pipeline
from notirua.core.progress import CancelToken, ProgressEvent
from tests import synth

TERMINAL = {"done", "skipped", "failed"}


class Counter:
    def __init__(self) -> None:
        self.separate = 0
        self.transcribe = 0
        self.engrave = 0


class FakeSeparator:
    sources = STEMS

    def __init__(self, counter: Counter, delay: float = 0.0) -> None:
        self.counter = counter
        self.delay = delay

    def separate(
        self,
        audio: AudioArray,
        progress: Callable[[float], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> dict[str, AudioArray]:
        self.counter.separate += 1
        steps = 20
        for i in range(steps):
            if cancel is not None:
                cancel.raise_if_cancelled()
            time.sleep(self.delay / steps)
            if progress:
                progress((i + 1) / steps)
        silent = np.zeros_like(audio)
        return {s: (audio if s in ("piano", "guitar") else silent) for s in STEMS}


class FakeTranscriber:
    def __init__(self, counter: Counter) -> None:
        self.counter = counter

    def transcribe(
        self,
        audio: AudioArray,
        sample_rate: int,
        stem: str,
        progress: Callable[[float], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> list[NoteEvent]:
        self.counter.transcribe += 1
        if progress:
            progress(1.0)
        return [NoteEvent(1.0 + i * 0.5, 1.45 + i * 0.5, 60 + i, 90) for i in range(8)]


class FakeDrums:
    def transcribe(self, *args: object, **kwargs: object) -> list[NoteEvent]:
        return []


class FakeEngraver:
    def __init__(self, counter: Counter) -> None:
        self.counter = counter
        self.sources: list[str] = []

    def engrave(
        self, source: str, out_pdf: Path, cancel: CancelToken | None = None, timeout_s: float = 0
    ) -> Path:
        self.counter.engrave += 1
        self.sources.append(source)
        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        out_pdf.write_bytes(b"%PDF-1.4 fake")
        return out_pdf


def make_pipeline(tmp_path: Path, delay: float = 0.0) -> tuple[Pipeline, Counter, FakeEngraver]:
    counter = Counter()
    engraver = FakeEngraver(counter)
    engines = Engines(
        separator=lambda: FakeSeparator(counter, delay),
        pitched=lambda: FakeTranscriber(counter),
        drums=FakeDrums,
        engraver=lambda: engraver,
    )
    return Pipeline(engines, cache_root=tmp_path / "cache"), counter, engraver


@pytest.fixture
def song(tmp_path: Path) -> Path:
    audio = synth.to_stereo(synth.render_notes(synth.scale_notes(120), total_s=6.0))
    return synth.write_wav(tmp_path / "노래 song.wav", audio)


def test_progress_event_contract(tmp_path: Path, song: Path) -> None:
    pipeline, _c, _e = make_pipeline(tmp_path)
    events: list[tuple[float, ProgressEvent]] = []
    result = pipeline.run(
        song, tmp_path / "out", progress=lambda e: events.append((time.monotonic(), e))
    )

    fractions = [e.overall_fraction for _t, e in events]
    assert fractions == sorted(fractions), "overall progress must never go backwards"
    assert fractions[-1] == pytest.approx(1.0)

    seen: dict[str, list[str]] = {}
    for _t, e in events:
        seen.setdefault(e.stage, []).append(e.stage_state)
    assert set(seen) == set(STAGE_MESSAGES)
    for stage, states in seen.items():
        assert "running" in states, stage
        assert states[-1] in TERMINAL, stage

    gaps = [b - a for (a, _), (b, _) in itertools.pairwise(events)]
    assert max(gaps, default=0) < 1.0

    from notirua.i18n import _

    for _t, e in events:
        assert e.message_id in _catalog_ids(), e.message_id
        assert _(e.message_id)

    assert set(result.pdfs) == {"piano", "guitar"}
    assert result.combined_pdf is not None and result.combined_pdf.name == "노래 song.pdf"
    assert result.skipped["vocals"] == "No sound"


def _catalog_ids() -> set[str]:
    from babel.messages.pofile import read_po

    root = Path(__file__).resolve().parents[1] / "locales" / "notirua.pot"
    with root.open("rb") as fp:
        return {m.id for m in read_po(fp) if isinstance(m.id, str) and m.id}


def test_transpose_reuses_separation_and_transcription(tmp_path: Path, song: Path) -> None:
    pipeline, counter, _engraver = make_pipeline(tmp_path)
    pipeline.run(song, tmp_path / "a", JobOptions(stems=["piano"]))
    assert (counter.separate, counter.transcribe) == (1, 1)

    fresh, counter2, engraver2 = make_pipeline(tmp_path)  # new process, same cache
    started = time.monotonic()
    result = fresh.run(song, tmp_path / "b", JobOptions(stems=["piano"], transpose=2))
    assert (counter2.separate, counter2.transcribe) == (0, 0)
    assert counter2.engrave == 1
    assert time.monotonic() - started < 5.0
    assert result.score.key == "D major"
    assert "\\key d \\major" in engraver2.sources[0]


def test_target_key_selection(tmp_path: Path, song: Path) -> None:
    pipeline, _c, _e = make_pipeline(tmp_path)
    result = pipeline.run(song, tmp_path / "o", JobOptions(stems=["piano"], target_key="F major"))
    assert result.score.key == "F major"


def test_cancel_stops_quickly_and_leaves_no_outputs(tmp_path: Path, song: Path) -> None:
    pipeline, _c, _e = make_pipeline(tmp_path, delay=20.0)
    token = CancelToken()
    errors: list[BaseException] = []

    def work() -> None:
        try:
            pipeline.run(song, tmp_path / "out", cancel=token)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=work)
    thread.start()
    time.sleep(0.5)
    cancelled_at = time.monotonic()
    token.cancel()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert time.monotonic() - cancelled_at < 3.0
    assert errors and isinstance(errors[0], Cancelled)
    assert not (tmp_path / "out").exists()


def test_failure_marks_stage_and_keeps_cache(tmp_path: Path, song: Path) -> None:
    pipeline, _counter, engraver = make_pipeline(tmp_path)

    def broken(*_a: object, **_k: object) -> Path:
        raise RuntimeError("boom")

    engraver.engrave = broken  # type: ignore[method-assign]
    events: list[ProgressEvent] = []
    with pytest.raises(RuntimeError):
        pipeline.run(song, tmp_path / "o", progress=events.append)
    assert events[-1].stage == "engrave" and events[-1].stage_state == "failed"

    retry, counter2, _e = make_pipeline(tmp_path)
    retry.run(song, tmp_path / "o")
    assert counter2.separate == 0 and counter2.transcribe == 0


def test_unsafe_title_becomes_safe_filename(tmp_path: Path, song: Path) -> None:
    pipeline, _c, _e = make_pipeline(tmp_path)
    result = pipeline.run(song, tmp_path / "o", JobOptions(title='a/b:c*?"<>|', stems=["piano"]))
    assert result.pdfs["piano"].name == "a_b_c______ - Piano.pdf"


def test_pdf_labels_follow_pdf_language(tmp_path: Path, song: Path) -> None:
    pipeline, _c, engraver = make_pipeline(tmp_path)
    pipeline.run(song, tmp_path / "o", JobOptions(stems=["piano"], pdf_language="ko"))
    assert '"피아노"' in engraver.sources[0]
    assert "장조" in engraver.sources[0]


def test_job_stops_early_when_the_disk_is_full(
    tmp_path: Path, song: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from notirua.core import cache as cache_mod
    from notirua.core.errors import JobDiskSpaceError
    from notirua.core.pipeline import OUTPUT_RESERVE_BYTES

    pipeline, counter, _e = make_pipeline(tmp_path)
    # Enough for the PDFs, not for the separated audio of a first run.
    monkeypatch.setattr(cache_mod, "free_bytes", lambda _p: OUTPUT_RESERVE_BYTES + 1024)
    events: list[ProgressEvent] = []
    with pytest.raises(JobDiskSpaceError):
        pipeline.run(song, tmp_path / "out", progress=events.append)
    assert counter.separate == 0
    assert events[-1].stage == "decode" and events[-1].stage_state == "failed"

    monkeypatch.undo()
    pipeline.run(song, tmp_path / "out")
    # With the separation cached, a transposed run needs only room for the output.
    monkeypatch.setattr(cache_mod, "free_bytes", lambda _p: OUTPUT_RESERVE_BYTES + 1024)
    pipeline.run(song, tmp_path / "out2", JobOptions(transpose=2))
    assert counter.separate == 1
