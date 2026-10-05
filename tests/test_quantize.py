from __future__ import annotations

from fractions import Fraction as F

from notirua.core.model import NoteEvent, ScoreNote
from notirua.core.quantize import (
    common_start,
    quantize,
    seconds_to_beats,
    shift,
    trim_overlaps_same_pitch,
)


def grid(bpm: float, n: int = 64, start: float = 0.0) -> list[float]:
    return [start + i * 60.0 / bpm for i in range(n)]


def ev(start: float, end: float, pitch: int = 60) -> NoteEvent:
    return NoteEvent(start, end, pitch, 80)


def test_on_beat_quarters() -> None:
    beats = grid(120)
    notes = quantize([ev(i * 0.5 + 0.01, i * 0.5 + 0.47) for i in range(4)], beats)
    assert [n.onset for n in notes] == [F(0), F(1), F(2), F(3)]
    assert all(n.duration == F(1) for n in notes)


def test_offbeat_eighths_and_sixteenths() -> None:
    beats = grid(120)
    # Eighth after the beat, then a sixteenth at 3/4 of beat 1.
    notes = quantize([ev(0.25, 0.49), ev(0.875, 0.99, 62)], beats)
    assert notes[0].onset == F(1, 2) and notes[0].duration == F(1, 2)
    assert notes[1].onset == F(7, 4) and notes[1].duration == F(1, 4)


def test_triplets_are_detected() -> None:
    beats = grid(60)  # one beat per second
    trip = [ev(t, t + 0.3, 60 + i) for i, t in enumerate([1.0, 1.333, 1.667])]
    notes = quantize(trip, beats)
    assert [n.onset for n in notes] == [F(1), F(4, 3), F(5, 3)]
    assert all(n.duration == F(1, 3) for n in notes)


def test_straight_beat_next_to_triplet_beat_stays_straight() -> None:
    beats = grid(60)
    events = [ev(0.0, 0.2), ev(0.25, 0.45, 62), ev(1.0, 1.3), ev(1.333, 1.6), ev(1.667, 1.9)]
    notes = quantize(events, beats)
    assert notes[1].onset == F(1, 4)
    assert notes[3].onset == F(4, 3)


def test_tempo_drift_follows_beat_grid() -> None:
    # Tempo speeds up from 100 to 140 BPM; notes sit exactly on tracked beats.
    times = [0.0]
    for i in range(1, 40):
        bpm = 100 + 40 * i / 39
        times.append(times[-1] + 60.0 / bpm)
    events = [ev(times[i] + 0.005, times[i + 1] - 0.02) for i in range(0, 38, 2)]
    notes = quantize(events, times)
    assert [n.onset for n in notes] == [F(i) for i in range(0, 38, 2)]


def test_seconds_to_beats_extrapolates() -> None:
    beats = [1.0, 1.5, 2.0]
    assert seconds_to_beats(0.5, beats) == -1.0
    assert seconds_to_beats(2.5, beats) == 3.0


def test_downbeat_offset_and_common_start() -> None:
    beats = grid(120)
    notes = quantize([ev(0.5, 0.9), ev(1.0, 1.4)], beats, downbeat_index=2)
    assert [n.onset for n in notes] == [F(-1), F(0)]
    start = common_start([notes], F(4))
    assert start == F(-4)
    shifted = shift(notes, start)
    assert [n.onset for n in shifted] == [F(3), F(4)]


def test_trim_overlaps_same_pitch() -> None:
    notes = [ScoreNote(F(0), F(2), 60), ScoreNote(F(1), F(1), 60)]
    trimmed = trim_overlaps_same_pitch(notes)
    assert trimmed[0].duration == F(1)
    assert trimmed[1].onset == F(1)
