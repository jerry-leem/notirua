from __future__ import annotations

from fractions import Fraction as F

from notirua.core.arrange.tab import (
    TUNINGS,
    assign_tab,
    fit_range,
    parse_tuning,
    positions_for,
)
from notirua.core.model import ScoreNote
from notirua.core.transpose import transpose_notes

GUITAR = TUNINGS["guitar"]["standard"]


def n(onset: float, pitch: int, velocity: int = 80) -> ScoreNote:
    return ScoreNote(F(onset), F(1), pitch, velocity)


def frets(result_notes: list[ScoreNote]) -> list[tuple[int | None, int | None]]:
    return [(x.string, x.fret) for x in result_notes]


def test_every_assignment_sounds_the_right_pitch() -> None:
    notes = [n(i, p) for i, p in enumerate([40, 45, 52, 57, 64, 69, 76])]
    result = assign_tab(notes, GUITAR, 22)
    for note in result.notes:
        assert note.string is not None and note.fret is not None
        assert GUITAR[6 - note.string] + note.fret == note.pitch


def test_c_major_scale_stays_in_low_position() -> None:
    scale = [48, 50, 52, 53, 55, 57, 59, 60]
    result = assign_tab([n(i, p) for i, p in enumerate(scale)], GUITAR, 22)
    assert max(x.fret or 0 for x in result.notes) <= 5
    assert not result.dropped


def test_open_e_major_chord_uses_open_strings() -> None:
    chord = [n(0, p) for p in (40, 47, 52, 56, 59, 64)]
    result = assign_tab(chord, GUITAR, 22)
    assert sorted(frets(result.notes)) == sorted([(6, 0), (5, 2), (4, 2), (3, 1), (2, 0), (1, 0)])


def test_one_note_per_string() -> None:
    chord = [n(0, p) for p in (48, 52, 55, 60)]
    result = assign_tab(chord, GUITAR, 22)
    strings = [x.string for x in result.notes]
    assert len(strings) == len(set(strings))


def test_unplayable_chord_drops_quietest_notes() -> None:
    # Two semitone clusters an octave+ apart beyond any hand span plus too many notes.
    chord = [
        n(0, 40, 90),
        n(0, 41, 30),
        n(0, 42, 90),
        n(0, 43, 20),
        n(0, 44, 90),
        n(0, 45, 90),
        n(0, 46, 90),
    ]
    result = assign_tab(chord, GUITAR, 22)
    assert result.dropped
    assert min(d.velocity for d in result.dropped) <= 30
    strings = [x.string for x in result.notes]
    assert len(strings) == len(set(strings)) <= 6


def test_out_of_range_notes_are_dropped() -> None:
    result = assign_tab([n(0, 30)], GUITAR, 22)
    assert not result.notes and len(result.dropped) == 1


def test_drop_d_tuning_low_d_is_open() -> None:
    tuning = parse_tuning("drop_d", "guitar")
    result = assign_tab([n(0, 38)], tuning, 22)
    assert frets(result.notes) == [(6, 0)]


def test_custom_tuning_from_midi_numbers() -> None:
    tuning = parse_tuning("38,45,50,55,57,62", "guitar")  # DADGAD
    assert positions_for(62, tuning, 22)[-1] == (5, 0)


def test_five_string_bass() -> None:
    tuning = parse_tuning("five_string", "bass")
    result = assign_tab([n(0, 23)], tuning, 20)
    assert frets(result.notes) == [(5, 0)]


def test_transpose_then_reassign() -> None:
    notes = [n(i, p) for i, p in enumerate([40, 45, 50])]
    up = transpose_notes(notes, 2)
    assert all(x.string is None for x in up)
    result = assign_tab(up, GUITAR, 22)
    for note in result.notes:
        assert GUITAR[6 - (note.string or 0)] + (note.fret or 0) == note.pitch


def test_fit_range_shifts_whole_part_by_octaves() -> None:
    low = [n(0, 30), n(1, 35)]
    shifted, octaves = fit_range(low, GUITAR, 22)
    assert octaves == 1
    assert [x.pitch for x in shifted] == [42, 47]
    same, zero = fit_range([n(0, 50)], GUITAR, 22)
    assert zero == 0 and same[0].pitch == 50
