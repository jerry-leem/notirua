"""Seconds -> beats -> grid quantization (SPEC 6.2). Pure functions only."""

from __future__ import annotations

import bisect
import math
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from notirua.core.model import NoteEvent, ScoreNote

STRAIGHT = Fraction(1, 4)  # sixteenth-note grid, in quarter-note beats
TRIPLET = Fraction(1, 3)  # eighth-note triplet grid


@dataclass(frozen=True)
class QuantizeOptions:
    triplet_ratio: float = 0.6  # use triplets when their error is below this share
    min_triplet_onsets: int = 2


def seconds_to_beats(t: float, beat_times: Sequence[float]) -> float:
    """Piecewise-linear map from seconds to (fractional) beat index.

    Times outside the tracked grid are extrapolated with the nearest interval,
    so tempo drift inside the song is followed exactly.
    """
    n = len(beat_times)
    if n == 0:
        raise ValueError("beat grid is empty")
    if n == 1:
        return t - beat_times[0]
    i = bisect.bisect_right(beat_times, t) - 1
    i = min(max(i, 0), n - 2)
    t0, t1 = beat_times[i], beat_times[i + 1]
    span = t1 - t0 if t1 > t0 else 1e-9
    return i + (t - t0) / span


def _snap(x: float, step: Fraction) -> Fraction:
    return Fraction(round(x / step)) * step


def _grid_error(xs: Sequence[float], step: Fraction) -> float:
    return sum(abs(x - float(_snap(x, step))) for x in xs)


def choose_grids(
    positions: Sequence[float], options: QuantizeOptions = QuantizeOptions()
) -> dict[int, Fraction]:
    """For each beat that contains onsets, pick the straight or triplet grid."""
    per_beat: dict[int, list[float]] = {}
    for x in positions:
        per_beat.setdefault(math.floor(x + 1e-9), []).append(x)
    grids: dict[int, Fraction] = {}
    for beat, xs in per_beat.items():
        inside = [x for x in xs if abs(x - round(x)) > 0.06]  # off-beat onsets decide
        if len(inside) < options.min_triplet_onsets:
            grids[beat] = STRAIGHT
            continue
        straight = _grid_error(inside, STRAIGHT)
        triplet = _grid_error(inside, TRIPLET)
        grids[beat] = TRIPLET if triplet < options.triplet_ratio * straight else STRAIGHT
    return grids


def snap_to_grid(x: float, grids: dict[int, Fraction]) -> Fraction:
    beat = math.floor(x + 1e-9)
    step = grids.get(beat, STRAIGHT)
    snapped = _snap(x, step)
    # Snapping can push into the next beat; that is fine (it lands on the beat).
    return snapped


def quantize(
    events: Sequence[NoteEvent],
    beat_times: Sequence[float],
    downbeat_index: int = 0,
    options: QuantizeOptions = QuantizeOptions(),
) -> list[ScoreNote]:
    """Quantize notes to beats measured from the first downbeat (may be negative)."""
    if not events:
        return []
    onsets = [seconds_to_beats(e.start_s, beat_times) - downbeat_index for e in events]
    offsets = [seconds_to_beats(e.end_s, beat_times) - downbeat_index for e in events]
    grids = choose_grids(onsets, options)
    # Offsets use the grid of the beat they end in; reuse onset grids when present.
    notes: list[ScoreNote] = []
    for e, on, off in zip(events, onsets, offsets, strict=True):
        start = snap_to_grid(on, grids)
        end = snap_to_grid(off, grids)
        step = grids.get(math.floor(start), STRAIGHT)
        if end <= start:
            end = start + step
        notes.append(
            ScoreNote(onset=start, duration=end - start, pitch=e.pitch, velocity=e.velocity)
        )
    return dedupe(notes)


def dedupe(notes: Sequence[ScoreNote]) -> list[ScoreNote]:
    """Merge notes that collapsed onto the same onset and pitch."""
    best: dict[tuple[Fraction, int], ScoreNote] = {}
    for n in notes:
        key = (n.onset, n.pitch)
        cur = best.get(key)
        if cur is None or n.duration > cur.duration:
            best[key] = n
    return sorted(best.values(), key=lambda n: (n.onset, n.pitch))


def trim_overlaps_same_pitch(notes: Sequence[ScoreNote]) -> list[ScoreNote]:
    """A pitch cannot sound twice at once: cut the earlier note at the next onset."""
    by_pitch: dict[int, list[ScoreNote]] = {}
    for n in sorted(notes, key=lambda n: (n.onset, n.pitch)):
        by_pitch.setdefault(n.pitch, []).append(n)
    result: list[ScoreNote] = []
    for seq in by_pitch.values():
        for a, b in zip(seq, [*seq[1:], None], strict=True):
            if b is not None and a.onset + a.duration > b.onset:
                a = ScoreNote(a.onset, b.onset - a.onset, a.pitch, a.velocity, a.string, a.fret)
            if a.duration > 0:
                result.append(a)
    return sorted(result, key=lambda n: (n.onset, n.pitch))


def common_start(parts: Sequence[Sequence[ScoreNote]], measure_beats: Fraction) -> Fraction:
    """First measure boundary at or before the earliest note across all parts."""
    firsts = [n.onset for notes in parts for n in notes[:1]]
    if not firsts:
        return Fraction(0)
    earliest = min(firsts)
    return Fraction(math.floor(earliest / measure_beats)) * measure_beats


def shift(notes: Sequence[ScoreNote], offset: Fraction) -> list[ScoreNote]:
    return [
        ScoreNote(n.onset - offset, n.duration, n.pitch, n.velocity, n.string, n.fret)
        for n in notes
    ]
