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


def test_out_of_range_notes_move_by_octaves_instead_of_being_dropped() -> None:
    # 30 (F#1) is below the low E string; 98 is above fret 22 on the high E string.
    result = assign_tab([n(0, 30), n(1, 98)], GUITAR, 22)
    assert not result.dropped
    assert [x.pitch for x in result.notes] == [42, 86]
    assert result.folded == 2


def test_folded_duplicate_merges_into_the_existing_note() -> None:
    # Bass bleed an octave below the guitar's E2 lands on the same E2 that is already there.
    result = assign_tab([n(0, 28, 40), ScoreNote(F(0), F(2), 40, 90)], GUITAR, 22)
    assert not result.dropped and result.merged == 1
    (note,) = result.notes
    assert note.pitch == 40 and note.velocity == 90 and note.duration == F(2)


def test_too_many_notes_shed_octave_doublings_first() -> None:
    # Seven notes for six strings: the doubled E (a likely overtone) goes, not the D.
    chord = [n(0, p) for p in (40, 47, 52, 56, 59, 62, 64)]
    result = assign_tab(chord, GUITAR, 22)
    assert len(result.dropped) == 1
    assert result.dropped[0].pitch % 12 == 4  # an E
    assert 62 in {x.pitch for x in result.notes}


def test_out_of_reach_chord_is_revoiced_before_dropping() -> None:
    # Open low E with a C six octaves up a 20th fret away: no string choice reaches both,
    # but the same C an octave lower fits one hand.
    chord = [n(0, 40), n(0, 52), n(0, 84)]
    result = assign_tab(chord, GUITAR, 22)
    assert not result.dropped
    assert result.revoiced == 1
    assert sorted(x.pitch % 12 for x in result.notes) == [0, 4, 4]


def test_bass_and_melody_are_kept_when_shedding() -> None:
    # A semitone cluster under a quiet bass E and a quiet top A: the cluster goes first.
    chord = [n(0, 40, 30), n(0, 41, 90), n(0, 42, 90), n(0, 43, 90), n(0, 44, 90), n(0, 81, 20)]
    result = assign_tab(chord, GUITAR, 22)
    kept = sorted(x.pitch for x in result.notes)
    assert kept[0] == 40, "the bass note stays"
    assert any(p % 12 == 9 for p in kept), "the melody A stays (possibly an octave lower)"


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
