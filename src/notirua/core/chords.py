"""Chord symbols from the transcribed notes (shown above every score). Pure functions only.

Each measure (or each half of an even measure) gets a pitch-class profile from
every pitched part, weighted by how long each note sounds. The profile is
matched against a few basic chord shapes; the lowest sounding note favours the
chord built on it. A half-measure chord is used only when it explains its half
clearly better than the whole-measure chord, and a symbol is kept only where
the chord changes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from notirua.core.model import Part

# Chord quality -> intervals above the root. Order breaks ties: simpler first.
QUALITIES: dict[str, tuple[int, ...]] = {
    "": (0, 4, 7),
    "m": (0, 3, 7),
    "7": (0, 4, 7, 10),
    "m7": (0, 3, 7, 10),
    "maj7": (0, 4, 7, 11),
    "dim": (0, 3, 6),
}
PART_WEIGHTS = {"vocals": 0.5}  # a melody passes through non-chord notes
SEVENTH_PENALTY = 0.06  # a four-note chord must earn its extra note
BASS_BONUS = 0.12
MIN_FIT = 0.45  # share of the profile a chord must explain to be named
HALF_GAIN = 0.12  # how much better a half-measure chord must fit


@dataclass(frozen=True)
class Chord:
    onset: Fraction  # beats from the start of the score
    duration: Fraction
    root: int  # pitch class, 0 = C
    quality: str  # a key of QUALITIES


def _profile(
    parts: Sequence[Part], start: Fraction, end: Fraction
) -> tuple[list[float], int | None]:
    """Pitch-class weights in ``[start, end)``, summing to 1, and the lowest pitch class."""
    weights = [0.0] * 12
    bass: dict[int, float] = {}
    for part in parts:
        if part.stem == "drums":
            continue
        scale = PART_WEIGHTS.get(part.stem, 1.0)
        for n in part.notes:
            overlap = min(end, n.onset + n.duration) - max(start, n.onset)
            if overlap <= 0:
                continue
            weights[n.pitch % 12] += scale * float(overlap)
            bass[n.pitch] = bass.get(n.pitch, 0.0) + float(overlap)
    total = sum(weights)
    if total <= 0:
        return weights, None
    # The lowest note that lasts long enough to be heard as the bass.
    longest = max(bass.values())
    low = min(p for p, w in bass.items() if w >= 0.25 * longest)
    return [w / total for w in weights], low % 12


def _fit(profile: Sequence[float], bass: int | None, root: int, quality: str) -> float:
    tones = {(root + i) % 12 for i in QUALITIES[quality]}
    inside = sum(profile[pc] for pc in tones)
    score = inside - (1.0 - inside)
    if len(tones) > 3:
        score -= SEVENTH_PENALTY
    if bass == root:
        score += BASS_BONUS
    return score


def best_chord(profile: Sequence[float], bass: int | None) -> tuple[int, str, float] | None:
    """Return ``(root, quality, fit)`` for the best matching chord, or ``None``."""
    if bass is None:
        return None
    best: tuple[int, str, float] | None = None
    for root in range(12):
        if profile[root] <= 0:
            continue  # a chord is not named after a root that is not played
        for quality in QUALITIES:
            score = _fit(profile, bass, root, quality)
            if best is None or score > best[2]:
                best = (root, quality, score)
    if best is None:
        return None
    tones = {(best[0] + i) % 12 for i in QUALITIES[best[1]]}
    if sum(profile[pc] for pc in tones) < MIN_FIT:
        return None
    return best


def _window(parts: Sequence[Part], start: Fraction, end: Fraction) -> tuple[int, str, float] | None:
    profile, bass = _profile(parts, start, end)
    return best_chord(profile, bass)


def detect_chords(parts: Sequence[Part], measure_beats: Fraction, n_measures: int) -> list[Chord]:
    """Chords over ``n_measures`` measures, one entry per change."""
    found: list[tuple[Fraction, int, str]] = []
    for m in range(n_measures):
        start = measure_beats * m
        end = start + measure_beats
        whole = _window(parts, start, end)
        pieces: list[tuple[Fraction, tuple[int, str, float] | None]] = [(start, whole)]
        if measure_beats.denominator == 1 and measure_beats.numerator % 2 == 0:
            mid = start + measure_beats / 2
            halves = [_window(parts, start, mid), _window(parts, mid, end)]
            if all(h is not None for h in halves) and _halves_win(parts, whole, halves, start, mid):
                pieces = [(start, halves[0]), (mid, halves[1])]
        for onset, chord in pieces:
            if chord is not None:
                found.append((onset, chord[0], chord[1]))

    total = measure_beats * n_measures
    chords: list[Chord] = []
    for i, (onset, root, quality) in enumerate(found):
        if chords and (chords[-1].root, chords[-1].quality) == (root, quality):
            continue
        nxt = next(
            (o for o, r, q in found[i + 1 :] if (r, q) != (root, quality)),
            total,
        )
        chords.append(Chord(onset, nxt - onset, root, quality))
    return chords


def _halves_win(
    parts: Sequence[Part],
    whole: tuple[int, str, float] | None,
    halves: Sequence[tuple[int, str, float] | None],
    start: Fraction,
    mid: Fraction,
) -> bool:
    """Split the measure only when its halves hold different, clearly better chords."""
    first, second = halves
    assert first is not None and second is not None
    if (first[0], first[1]) == (second[0], second[1]):
        return False
    if whole is None:
        return True
    end = mid + (mid - start)
    gain = 0.0
    for (a, b), half in zip(((start, mid), (mid, end)), halves, strict=True):
        assert half is not None
        profile, bass = _profile(parts, a, b)
        gain += half[2] - _fit(profile, bass, whole[0], whole[1])
    return gain / 2 > HALF_GAIN
