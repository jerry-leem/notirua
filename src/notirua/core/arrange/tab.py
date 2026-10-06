"""(string, fret) assignment by Viterbi search (SPEC 6.4). Pure functions only.

Strings are numbered like LilyPond: 1 is the highest-pitched string.
Tunings are MIDI pitches listed from the lowest string up.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass, replace
from fractions import Fraction

from notirua.core.model import ScoreNote

TUNINGS: dict[str, dict[str, list[int]]] = {
    "guitar": {
        "standard": [40, 45, 50, 55, 59, 64],
        "drop_d": [38, 45, 50, 55, 59, 64],
        "half_down": [39, 44, 49, 54, 58, 63],
    },
    "bass": {
        "standard": [28, 33, 38, 43],
        "five_string": [23, 28, 33, 38, 43],
        "drop_d": [26, 33, 38, 43],
        "half_down": [27, 32, 37, 42],
    },
}

MAX_FRET = {"guitar": 22, "bass": 20}


@dataclass(frozen=True)
class TabWeights:
    move: float = 1.0  # per fret of hand movement between chords
    span_limit: int = 4  # comfortable stretch inside a chord
    span_penalty: float = 25.0  # base penalty beyond span_limit
    span_step: float = 8.0  # extra per fret beyond the limit
    open_bonus: float = 0.6  # reward for open strings
    high_fret_start: int = 12
    high_fret: float = 0.4  # per fret above high_fret_start
    low_string_pref: float = 0.05  # mild preference for lower positions

    @classmethod
    def from_dict(cls, values: dict[str, float]) -> TabWeights:
        known = {k: v for k, v in values.items() if k in cls.__dataclass_fields__}
        return cls(**known)  # type: ignore[arg-type]


@dataclass(frozen=True)
class TabResult:
    notes: list[ScoreNote]
    dropped: list[ScoreNote]  # could not be fingered at all
    folded: int = 0  # out-of-range notes moved by octaves into range
    merged: int = 0  # notes that became a duplicate of another note in the chord
    revoiced: int = 0  # chords made playable by moving one note an octave


Position = tuple[int, int]  # (string index from lowest = 0, fret)


def parse_tuning(spec: str | Sequence[int], instrument: str) -> list[int]:
    """Accept a preset name or explicit MIDI pitches (lowest string first)."""
    if isinstance(spec, str):
        if "," in spec:
            return [int(p) for p in spec.split(",")]
        return list(TUNINGS[instrument][spec])
    return list(spec)


def positions_for(pitch: int, tuning: Sequence[int], max_fret: int) -> list[Position]:
    return [
        (s, pitch - open_pitch)
        for s, open_pitch in enumerate(tuning)
        if 0 <= pitch - open_pitch <= max_fret
    ]


def _chord_cost(assign: Sequence[Position], w: TabWeights) -> float:
    fretted = [f for _s, f in assign if f > 0]
    cost = 0.0
    if fretted:
        span = max(fretted) - min(fretted)
        if span > w.span_limit:
            cost += w.span_penalty + w.span_step * (span - w.span_limit)
        cost += sum(max(0, f - w.high_fret_start) * w.high_fret for f in fretted)
        cost += w.low_string_pref * (sum(fretted) / len(fretted))
    cost -= w.open_bonus * sum(1 for _s, f in assign if f == 0)
    return cost


def _hand(assign: Sequence[Position]) -> float | None:
    fretted = [f for _s, f in assign if f > 0]
    return sum(fretted) / len(fretted) if fretted else None


def _candidates(
    pitches: Sequence[int], tuning: Sequence[int], max_fret: int, w: TabWeights, limit: int
) -> list[tuple[tuple[Position, ...], float]]:
    """Every way to put the pitches on different strings, cheapest first."""
    options = [positions_for(p, tuning, max_fret) for p in pitches]
    if any(not o for o in options):
        return []
    found: list[tuple[tuple[Position, ...], float]] = []
    for combo in itertools.product(*options):
        strings = [s for s, _f in combo]
        if len(set(strings)) != len(strings):
            continue
        found.append((combo, _chord_cost(combo, w)))
    found.sort(key=lambda c: c[1])
    return found[:limit]


def fold_into_range(pitch: int, low: int, high: int) -> int:
    """Move a pitch by whole octaves until it lies in ``[low, high]`` (keeps the note name)."""
    while pitch < low:
        pitch += 12
    while pitch > high:
        pitch -= 12
    return pitch if pitch >= low else pitch + 12  # range narrower than an octave


def _shed_one(keep: list[ScoreNote]) -> ScoreNote:
    """The note a guitarist would leave out first.

    Octave doublings go first (often overtones the transcriber heard), then the
    quietest inner voice; the lowest (bass) and highest (melody) notes go last.
    """
    by_class: dict[int, list[ScoreNote]] = {}
    for note in keep:
        by_class.setdefault(note.pitch % 12, []).append(note)
    doubled = [
        note
        for group in by_class.values()
        if len(group) > 1
        for note in sorted(group, key=lambda n: n.pitch)[1:]  # keep the lowest of each name
    ]
    if doubled:
        return min(doubled, key=lambda n: (n.velocity, -n.pitch))
    ordered = sorted(keep, key=lambda n: n.pitch)
    inner = ordered[1:-1]
    return min(inner or ordered, key=lambda n: (n.velocity, -n.pitch))


Candidates = list[tuple[tuple[Position, ...], float]]


def _reachable(
    pitches: Sequence[int], tuning: Sequence[int], max_fret: int, w: TabWeights, limit: int
) -> Candidates:
    """Fingerings over every string choice, or [] if none is within a hand's reach."""
    cands = _candidates(pitches, tuning, max_fret, w, limit)
    # A fingering that needs a huge stretch is "unplayable" too.
    return cands if cands and cands[0][1] < w.span_penalty + w.span_step * 4 else []


def _revoice(
    keep: list[ScoreNote], tuning: Sequence[int], max_fret: int, w: TabWeights, limit: int
) -> tuple[list[ScoreNote], Candidates] | None:
    """Move one note by an octave (same note name) so the chord fits under one hand.

    Tried before leaving a note out: the harmony stays, only the voicing changes.
    The bass and melody notes are moved last.
    """
    low, high = min(tuning), max(tuning) + max_fret
    ordered = sorted(keep, key=lambda n: n.pitch)
    priority = ordered[1:-1] + ordered[-1:] + ordered[:1] if len(ordered) > 1 else ordered
    pitches = {n.pitch for n in keep}
    best: tuple[float, list[ScoreNote], Candidates] | None = None
    for note in priority:
        for shift in (-12, 12):
            pitch = note.pitch + shift
            if not low <= pitch <= high or pitch in pitches:
                continue
            trial = sorted(
                (replace(n, pitch=pitch) if n is note else n for n in keep), key=lambda n: n.pitch
            )
            cands = _reachable([n.pitch for n in trial], tuning, max_fret, w, limit)
            if cands and (best is None or cands[0][1] < best[0]):
                best = (cands[0][1], trial, cands)
        if best is not None:
            return best[1], best[2]
    return None


def _playable_subset(
    notes: list[ScoreNote], tuning: Sequence[int], max_fret: int, w: TabWeights, limit: int
) -> tuple[list[ScoreNote], list[ScoreNote], Candidates, int]:
    """Make the chord playable: other strings first, then another octave, then shed notes.

    Returns (kept notes, left-out notes, fingerings, number of notes re-voiced).
    """
    keep = [n for n in notes if positions_for(n.pitch, tuning, max_fret)]
    dropped = [n for n in notes if n not in keep]
    revoiced = 0
    while len(keep) > len(tuning):  # more notes than strings
        victim = _shed_one(keep)
        keep.remove(victim)
        dropped.append(victim)
    while keep:
        cands = _reachable([n.pitch for n in keep], tuning, max_fret, w, limit)
        if cands:
            return keep, dropped, cands, revoiced
        moved = _revoice(keep, tuning, max_fret, w, limit)
        if moved is not None:
            return moved[0], dropped, moved[1], revoiced + 1
        victim = _shed_one(keep)
        keep.remove(victim)
        dropped.append(victim)
    return [], dropped, [], revoiced


def assign_tab(
    notes: Sequence[ScoreNote],
    tuning: Sequence[int],
    max_fret: int,
    weights: TabWeights = TabWeights(),
    beam: int = 48,
) -> TabResult:
    """Assign every note a (string, fret) minimising total fingering cost."""
    if not notes:
        return TabResult([], [])
    # Notes the instrument cannot reach (stray bleed or overtones from the
    # separated track) keep their note name and move by octaves into range.
    low, high = min(tuning), max(tuning) + max_fret
    folded = 0
    by_onset: dict[Fraction, list[ScoreNote]] = {}
    for n in sorted(notes, key=lambda n: (n.onset, n.pitch)):
        pitch = fold_into_range(n.pitch, low, high)
        if pitch != n.pitch:
            folded += 1
            n = replace(n, pitch=pitch)
        by_onset.setdefault(n.onset, []).append(n)

    chords: list[list[ScoreNote]] = []
    chord_cands: list[list[tuple[tuple[Position, ...], float]]] = []
    dropped: list[ScoreNote] = []
    merged = 0
    revoiced = 0
    for onset in sorted(by_onset):
        # Distinct pitches only: a duplicate sounds the same note, so it merges
        # into the louder copy and keeps the longer duration.
        seen: dict[int, ScoreNote] = {}
        for n in by_onset[onset]:
            other = seen.get(n.pitch)
            if other is None:
                seen[n.pitch] = n
                continue
            merged += 1
            louder = n if n.velocity > other.velocity else other
            seen[n.pitch] = replace(louder, duration=max(n.duration, other.duration))
        group = sorted(seen.values(), key=lambda n: n.pitch)
        keep, lost, cands, moved = _playable_subset(group, tuning, max_fret, weights, beam)
        dropped.extend(lost)
        revoiced += moved
        if keep:
            chords.append(keep)
            chord_cands.append(cands)

    if not chords:
        return TabResult([], dropped, folded, merged, revoiced)

    # Viterbi over chord fingerings.
    n_strings = len(tuning)
    prev_cost = [c for _a, c in chord_cands[0]]
    back: list[list[int]] = [[-1] * len(chord_cands[0])]
    for t in range(1, len(chords)):
        cur_cost: list[float] = []
        cur_back: list[int] = []
        prev_hands = [_hand(a) for a, _c in chord_cands[t - 1]]
        for assign, local in chord_cands[t]:
            hand = _hand(assign)
            best = float("inf")
            arg = 0
            for j, pc in enumerate(prev_cost):
                ph = prev_hands[j]
                move = 0.0 if hand is None or ph is None else abs(hand - ph) * weights.move
                total = pc + move
                if total < best:
                    best, arg = total, j
            cur_cost.append(best + local)
            cur_back.append(arg)
        prev_cost = cur_cost
        back.append(cur_back)

    idx = min(range(len(prev_cost)), key=prev_cost.__getitem__)
    choice = [0] * len(chords)
    for t in range(len(chords) - 1, -1, -1):
        choice[t] = idx
        idx = back[t][idx]

    out: list[ScoreNote] = []
    for t, group in enumerate(chords):
        assign, _cost = chord_cands[t][choice[t]]
        for note, (s, f) in zip(group, assign, strict=True):
            out.append(replace(note, string=n_strings - s, fret=f))
    return TabResult(
        sorted(out, key=lambda n: (n.onset, n.pitch)), dropped, folded, merged, revoiced
    )


def fit_range(
    notes: Sequence[ScoreNote], tuning: Sequence[int], max_fret: int
) -> tuple[list[ScoreNote], int]:
    """Shift the whole part by octaves so it fits the instrument (FR-6).

    Returns the shifted notes and the octave shift applied (0 if none).
    """
    if not notes:
        return list(notes), 0
    low, high = min(tuning), max(tuning) + max_fret
    lo = min(n.pitch for n in notes)
    hi = max(n.pitch for n in notes)
    shift = 0
    while lo + 12 * shift < low and hi + 12 * (shift + 1) <= high + 12:
        shift += 1
    while hi + 12 * shift > high and lo + 12 * (shift - 1) >= low - 12:
        shift -= 1
    if shift == 0:
        return list(notes), 0
    return [replace(n, pitch=n.pitch + 12 * shift) for n in notes], shift
