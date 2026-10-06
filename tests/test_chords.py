from __future__ import annotations

from fractions import Fraction as F

from notirua.core.chords import Chord, detect_chords
from notirua.core.engrave.lilypond import (
    EngraveOptions,
    chord_names_block,
    chord_root_name,
    render_ly,
)
from notirua.core.model import Part, Score, ScoreNote
from notirua.core.transpose import parse_key, transpose_score


def n(onset: F | int, dur: F | int, pitch: int) -> ScoreNote:
    return ScoreNote(F(onset), F(dur), pitch, 80)


def block(onset: int, dur: int, bass: int, upper: list[int]) -> list[ScoreNote]:
    return [n(onset, dur, bass), *(n(onset, dur, p) for p in upper)]


def names(chords: list[Chord]) -> list[tuple[F, int, str]]:
    return [(c.onset, c.root, c.quality) for c in chords]


def _progression() -> list[Part]:
    notes = [
        *block(0, 4, 48, [60, 64, 67]),  # C
        *block(4, 4, 45, [60, 64, 69]),  # Am
        *block(8, 4, 41, [60, 65, 69]),  # F
        *block(12, 4, 43, [59, 62, 65, 67]),  # G7
    ]
    return [Part("piano", notes)]


def test_detects_basic_progression() -> None:
    chords = detect_chords(_progression(), F(4), 4)
    assert names(chords) == [(F(0), 0, ""), (F(4), 9, "m"), (F(8), 5, ""), (F(12), 7, "7")]
    assert [c.duration for c in chords] == [F(4)] * 4


def test_qualities() -> None:
    parts = [
        Part(
            "piano",
            [
                *block(0, 4, 48, [63, 67, 70]),  # Cm7
                *block(4, 4, 41, [64, 69, 72]),  # Fmaj7
                *block(8, 4, 47, [62, 65]),  # Bdim
            ],
        )
    ]
    assert names(detect_chords(parts, F(4), 3)) == [
        (F(0), 0, "m7"),
        (F(4), 5, "maj7"),
        (F(8), 11, "dim"),
    ]


def test_symbol_only_where_the_chord_changes() -> None:
    notes = [*block(0, 4, 48, [64, 67]), *block(4, 4, 48, [60, 64, 67]), *block(8, 4, 43, [62, 71])]
    chords = detect_chords([Part("piano", notes)], F(4), 3)
    assert names(chords) == [(F(0), 0, ""), (F(8), 7, "")]
    assert chords[0].duration == F(8)


def test_half_measure_change() -> None:
    notes = [*block(0, 2, 48, [64, 67]), *block(2, 2, 43, [62, 71])]
    assert names(detect_chords([Part("piano", notes)], F(4), 1)) == [(F(0), 0, ""), (F(2), 7, "")]


def test_passing_notes_do_not_split_the_measure() -> None:
    piano = Part("piano", block(0, 4, 48, [60, 64, 67]))
    melody = Part("vocals", [n(0, 1, 72), n(1, 1, 74), n(2, 1, 76), n(3, 1, 77)])
    assert names(detect_chords([piano, melody], F(4), 1)) == [(F(0), 0, "")]


def test_drums_and_silence_give_no_chords() -> None:
    drums = Part("drums", [n(0, 1, 36), n(1, 1, 38), n(2, 1, 42)])
    assert detect_chords([drums], F(4), 2) == []
    assert detect_chords([Part("piano", [])], F(4), 2) == []


def test_chord_line_names_each_chord_once() -> None:
    chords = [Chord(F(1), F(6), 0, "m"), Chord(F(7), F(1), 7, "7")]
    text = chord_names_block(chords, parse_key("C minor"), F(4))
    assert text.endswith("s4 c2.:m s2. g4:7 }")


def test_chord_root_spelling_follows_the_key() -> None:
    assert chord_root_name(10, parse_key("F major")) == "bes"
    assert chord_root_name(6, parse_key("G major")) == "fis"
    # Chromatic roots use the plain letter when there is one (C, not B#).
    assert chord_root_name(0, parse_key("E major")) == "c"
    assert chord_root_name(8, parse_key("Eb major")) == "as"


def test_every_score_starts_with_the_chords() -> None:
    parts = [*_progression(), Part("drums", [n(0, 1, 36)])]
    score = Score("t", 100, (4, 4), "C major", parts)
    single = render_ly(score, ["drums"], EngraveOptions())
    assert single.index("\\new ChordNames") < single.index("\\new DrumStaff")
    assert "c1 a1:m f1 g1:7 }" in single
    book = render_ly(score, ["piano", "drums"], EngraveOptions(), combined=True)
    assert book.count("\\new ChordNames") == 2
    up = render_ly(transpose_score(score, 2), ["piano"], EngraveOptions())
    assert "d1 b1:m g1 a1:7 }" in up
