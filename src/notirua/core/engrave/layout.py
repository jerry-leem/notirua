"""Turn quantized notes into notatable measures (SPEC 6.2 step 4). Pure functions only.

A part becomes one voice of chords: wherever the set of sounding pitches
changes, a new event starts; continuing pitches are tied. Events are then cut
at bar lines (and triplet beats) into durations that can be written.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from notirua.core.model import ScoreNote

F = Fraction

# Written durations in quarter-note beats, longest first, with the start
# alignment each one needs to be readable.
_STRAIGHT_VALUES: list[tuple[Fraction, Fraction]] = [
    (F(4), F(4)),
    (F(3), F(1)),
    (F(2), F(2)),
    (F(3, 2), F(1, 2)),
    (F(1), F(1)),
    (F(3, 4), F(1, 4)),
    (F(1, 2), F(1, 2)),
    (F(1, 4), F(1, 4)),
]


@dataclass(frozen=True)
class Head:
    pitch: int
    string: int | None
    tie: bool  # tied to the same pitch in the next item


@dataclass(frozen=True)
class Item:
    heads: tuple[Head, ...]  # empty = rest
    duration: Fraction  # sounding length in beats
    triplet: bool = False  # inside an eighth-note triplet bracket

    @property
    def is_rest(self) -> bool:
        return not self.heads


@dataclass(frozen=True)
class Measure:
    items: tuple[Item, ...]
    full_rest: bool = False


def triplet_beats(notes: Sequence[ScoreNote]) -> set[int]:
    beats: set[int] = set()
    for n in notes:
        for x in (n.onset, n.onset + n.duration):
            if (x * 4).denominator != 1:
                beats.add(math.floor(x))
    return beats


def _normalize(notes: Sequence[ScoreNote], trip: set[int]) -> list[ScoreNote]:
    """Snap every boundary to the grid of the beat it falls in."""

    def snap(x: Fraction) -> Fraction:
        step = F(1, 3) if math.floor(x) in trip else F(1, 4)
        return F(round(x / step)) * step

    out = []
    for n in notes:
        a = snap(n.onset)
        b = snap(n.onset + n.duration)
        if b <= a:
            b = a + (F(1, 3) if math.floor(a) in trip else F(1, 4))
        out.append(ScoreNote(a, b - a, n.pitch, n.velocity, n.string, n.fret))
    return out


def _split_straight(start: Fraction, end: Fraction, dotted: bool = True) -> list[Fraction]:
    pieces: list[Fraction] = []
    pos = start
    values = _STRAIGHT_VALUES if dotted else [v for v in _STRAIGHT_VALUES if v[0].numerator != 3]
    while pos < end:
        for value, align in values:
            if pos + value <= end and (pos % align) == 0:
                pieces.append(value)
                pos += value
                break
        else:  # off-grid remainder; should not happen after normalisation
            pieces.append(end - pos)
            pos = end
    return pieces


def _split(
    start: Fraction, end: Fraction, measure_start: Fraction, trip: set[int], rest: bool = False
) -> list[tuple[Fraction, bool]]:
    """Cut ``[start, end)`` (absolute beats, inside one measure) into writable pieces."""
    result: list[tuple[Fraction, bool]] = []
    pos = start
    while pos < end:
        beat = math.floor(pos)
        if beat in trip:
            stop = min(end, F(beat + 1))
            span = stop - pos
            if pos == beat and span == 1:
                result.append((F(1), False))
            else:
                # Inside the bracket: 1/3 -> eighth, 2/3 -> quarter.
                while span > 0:
                    piece = F(2, 3) if span >= F(2, 3) and (pos - beat) in (0, F(1, 3)) else F(1, 3)
                    piece = min(piece, span)
                    result.append((piece, True))
                    pos += piece
                    span -= piece
            pos = stop
            continue
        # Straight region: run until the next triplet beat or the end.
        stop = end
        nxt = beat + 1
        while nxt < end:
            if nxt in trip:
                stop = F(nxt)
                break
            nxt += 1
        rel_start = pos - measure_start
        # Rests avoid dotted values so beats stay visible (r4 r2, not r2.).
        for piece in _split_straight(rel_start, stop - measure_start, dotted=not rest):
            result.append((piece, False))
        pos = stop
    return result


def layout_part(
    notes: Sequence[ScoreNote], measure_beats: Fraction, n_measures: int
) -> list[Measure]:
    """Lay out notes (onsets >= 0) into exactly ``n_measures`` measures."""
    trip = triplet_beats(notes)
    notes = _normalize([n for n in notes if n.onset >= 0], trip)
    total = measure_beats * n_measures
    notes = [n for n in notes if n.onset < total]

    bounds: set[Fraction] = {F(0), total}
    bounds.update(measure_beats * i for i in range(1, n_measures))
    for n in notes:
        bounds.add(n.onset)
        bounds.add(min(total, n.onset + n.duration))
    points = sorted(bounds)

    # Sounding heads per elementary segment.
    segments: list[tuple[Fraction, Fraction, dict[int, ScoreNote], set[int]]] = []
    for a, b in itertools.pairwise(points):
        sounding = {n.pitch: n for n in notes if n.onset <= a < n.onset + n.duration}
        onsets = {p for p, n in sounding.items() if n.onset == a}
        segments.append((a, b, sounding, onsets))

    measures: list[list[Item]] = [[] for _ in range(n_measures)]
    for idx, (a, b, sounding, _onsets) in enumerate(segments):
        m = int(a // measure_beats)
        m_start = measure_beats * m
        next_seg = segments[idx + 1] if idx + 1 < len(segments) else None
        continuing = set()
        if next_seg is not None:
            _na, _nb, next_sounding, next_onsets = next_seg
            continuing = {p for p in sounding if p in next_sounding and p not in next_onsets}
        pieces = _split(a, b, m_start, trip, rest=not sounding)
        for k, (dur, in_trip) in enumerate(pieces):
            last = k == len(pieces) - 1
            heads = tuple(
                Head(p, sounding[p].string, tie=(not last) or (p in continuing))
                for p in sorted(sounding)
            )
            measures[m].append(Item(heads, dur, in_trip))

    result: list[Measure] = []
    for items in measures:
        if all(i.is_rest for i in items):
            result.append(Measure((), full_rest=True))
        else:
            result.append(Measure(tuple(items)))
    return result


def measure_count(parts: Sequence[Sequence[ScoreNote]], measure_beats: Fraction) -> int:
    end = F(0)
    for notes in parts:
        for n in notes:
            end = max(end, n.onset + n.duration)
    return max(1, math.ceil(end / measure_beats))
