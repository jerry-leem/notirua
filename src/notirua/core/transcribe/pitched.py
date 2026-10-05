"""Pitched-instrument transcription with Basic Pitch ONNX (FR-3) and stem profiles (SPEC 6.1)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from importlib import resources
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from notirua.core.decode import AudioArray
from notirua.core.model import NoteEvent
from notirua.core.progress import CancelToken
from notirua.core.transcribe import _basic_pitch_vendor as bp

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class StemProfile:
    low: int
    high: int
    monophonic: bool = False
    max_polyphony: int | None = None


PROFILES: dict[str, StemProfile] = {
    "vocals": StemProfile(40, 88, monophonic=True),
    "bass": StemProfile(28, 67, monophonic=True),
    "guitar": StemProfile(40, 88, max_polyphony=6),
    "piano": StemProfile(21, 108),
    "other": StemProfile(0, 127),
}


@dataclass(frozen=True)
class PostprocessSettings:
    """Thresholds kept out of code so they can live in the settings file."""

    onset_thresh: float = 0.5
    frame_thresh: float = 0.3
    min_note_len_ms: float = 127.7
    min_duration_s: float = 0.06
    merge_gap_s: float = 0.03
    min_velocity: int = 12
    harmonic_ratio: float = 0.75  # overtone kept only if at least this loud vs. its root
    harmonic_onset_tol_s: float = 0.05


class PitchedTranscriber(Protocol):
    def transcribe(
        self,
        audio: AudioArray,
        sample_rate: int,
        stem: str,
        progress: Callable[[float], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> list[NoteEvent]: ...


def default_model_path() -> Path:
    return Path(str(resources.files("notirua.resources.models") / "basic_pitch_nmp.onnx"))


class BasicPitchTranscriber:
    def __init__(
        self,
        model_path: Path | None = None,
        settings: PostprocessSettings | None = None,
        accelerate: bool = False,
    ) -> None:
        from notirua.core.runtime import make_session

        self.model_path = model_path or default_model_path()
        self.settings = settings or PostprocessSettings()
        self._session: Any = make_session(self.model_path, accelerate=accelerate)

    def transcribe(
        self,
        audio: AudioArray,
        sample_rate: int,
        stem: str,
        progress: Callable[[float], None] | None = None,
        cancel: CancelToken | None = None,
        profile: StemProfile | None = None,
    ) -> list[NoteEvent]:
        import soxr

        mono = audio.mean(axis=0) if audio.ndim == 2 else audio
        mono22 = soxr.resample(mono.astype(np.float32), sample_rate, bp.AUDIO_SAMPLE_RATE)
        output = bp.run_inference(
            self._session,
            np.asarray(mono22, dtype=np.float32),
            progress=progress,
            check_cancel=cancel.raise_if_cancelled if cancel else None,
        )
        s = self.settings
        raw = bp.model_output_to_note_events(
            output,
            onset_thresh=s.onset_thresh,
            frame_thresh=s.frame_thresh,
            min_note_len_ms=s.min_note_len_ms,
        )
        events = [
            NoteEvent(start, end, pitch, round(127 * min(1.0, amp)))
            for start, end, pitch, amp in raw
            if end > start
        ]
        return postprocess(events, profile or PROFILES.get(stem, PROFILES["other"]), s)


def postprocess(
    events: Sequence[NoteEvent], profile: StemProfile, settings: PostprocessSettings
) -> list[NoteEvent]:
    """Apply SPEC 6.1: range filter, cleanup, merge, and polyphony limits."""
    notes = [
        e
        for e in events
        if profile.low <= e.pitch <= profile.high
        and e.end_s - e.start_s >= settings.min_duration_s
        and e.velocity >= settings.min_velocity
    ]
    notes = merge_repeated(notes, settings.merge_gap_s)
    notes = suppress_harmonics(notes, settings.harmonic_ratio, settings.harmonic_onset_tol_s)
    if profile.monophonic:
        notes = enforce_monophony(notes)
    elif profile.max_polyphony is not None:
        notes = limit_polyphony(notes, profile.max_polyphony)
    return sorted(notes, key=lambda n: (n.start_s, n.pitch))


HARMONIC_INTERVALS = (12, 19, 24, 28, 31)


def suppress_harmonics(
    notes: Sequence[NoteEvent], ratio: float, onset_tol_s: float
) -> list[NoteEvent]:
    """Drop quiet notes that start with a louder note 1-2 octaves (+fifth/third) below.

    Basic Pitch occasionally reports strong overtones as separate notes; real
    octave doublings are usually similarly loud and survive.
    """
    by_pitch: dict[int, list[NoteEvent]] = {}
    for m in notes:
        by_pitch.setdefault(m.pitch, []).append(m)
    kept: list[NoteEvent] = []
    for n in notes:
        is_overtone = any(
            abs(m.start_s - n.start_s) <= onset_tol_s
            and n.velocity <= ratio * m.velocity
            and n.end_s <= m.end_s + onset_tol_s
            for interval in HARMONIC_INTERVALS
            for m in by_pitch.get(n.pitch - interval, ())
        )
        if not is_overtone:
            kept.append(n)
    return kept


def merge_repeated(notes: Sequence[NoteEvent], gap_s: float) -> list[NoteEvent]:
    """Join same-pitch notes separated by a tiny gap (spurious re-triggers)."""
    by_pitch: dict[int, list[NoteEvent]] = {}
    for n in sorted(notes, key=lambda n: n.start_s):
        bucket = by_pitch.setdefault(n.pitch, [])
        if bucket and n.start_s - bucket[-1].end_s <= gap_s:
            last = bucket[-1]
            bucket[-1] = replace(
                last, end_s=max(last.end_s, n.end_s), velocity=max(last.velocity, n.velocity)
            )
        else:
            bucket.append(n)
    return [n for bucket in by_pitch.values() for n in bucket]


def enforce_monophony(notes: Sequence[NoteEvent]) -> list[NoteEvent]:
    """Keep one note at a time; on overlap the louder note wins, the other is trimmed."""
    result: list[NoteEvent] = []
    for n in sorted(notes, key=lambda n: (n.start_s, -n.velocity)):
        if not result or n.start_s >= result[-1].end_s:
            result.append(n)
            continue
        prev = result[-1]
        if n.velocity > prev.velocity:
            if n.start_s - prev.start_s >= 0.03:
                result[-1] = replace(prev, end_s=n.start_s)
            else:
                result.pop()
            result.append(n)
        elif n.end_s > prev.end_s and n.end_s - prev.end_s >= 0.06:
            result.append(replace(n, start_s=prev.end_s))
    return result


def limit_polyphony(notes: Sequence[NoteEvent], limit: int) -> list[NoteEvent]:
    """Drop the quietest notes whenever more than ``limit`` sound at once."""
    ordered = sorted(notes, key=lambda n: n.start_s)
    kept: list[NoteEvent] = []
    for n in ordered:
        sounding = [k for k in kept if k.end_s > n.start_s]
        if len(sounding) < limit:
            kept.append(n)
            continue
        quietest = min(sounding, key=lambda k: k.velocity)
        if quietest.velocity < n.velocity:
            kept.remove(quietest)
            kept.append(n)
    return kept
