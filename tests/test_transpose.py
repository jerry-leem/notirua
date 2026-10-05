from __future__ import annotations

from fractions import Fraction as F

import pytest

from notirua.core.model import Part, Score, ScoreNote
from notirua.core.transpose import (
    interval_to,
    key_signature_accidentals,
    parse_key,
    spell,
    transpose_key,
    transpose_score,
)


@pytest.mark.parametrize(
    ("key", "steps", "expected", "accidentals"),
    [
        ("C major", 2, "D major", 2),
        ("C major", 1, "Db major", -5),
        ("G major", -2, "F major", -1),
        ("A minor", 3, "C minor", -3),
        ("E major", 2, "F# major", 6),
        ("D minor", 12, "D minor", -1),
    ],
)
def test_key_signature_changes(key: str, steps: int, expected: str, accidentals: int) -> None:
    new = transpose_key(parse_key(key), steps)
    assert str(new) == expected
    assert key_signature_accidentals(new) == accidentals


def test_parse_key_variants() -> None:
    assert str(parse_key("E- major")) == "Eb major"
    assert str(parse_key("f# minor")) == "F# minor"
    assert str(parse_key("Bbm")) == "Bb minor"


def test_enharmonic_spelling_follows_key() -> None:
    assert spell(61, parse_key("D major"))[:2] == ("C", 1)  # C#
    assert spell(61, parse_key("Ab major"))[:2] == ("D", -1)  # Db
    assert spell(66, parse_key("C major"))[:2] == ("F", 1)  # chromatic F# in C
    assert spell(70, parse_key("F major"))[:2] == ("B", -1)
    assert spell(56, parse_key("A minor"))[:2] == ("G", 1)  # raised leading tone


def test_octave_of_b_sharp_and_c_flat() -> None:
    assert spell(60, parse_key("C# major")) == ("B", 1, 3)
    assert spell(59, parse_key("Cb major")) == ("C", -1, 4)


def test_interval_to_target_key_picks_nearest() -> None:
    assert interval_to(parse_key("C major"), parse_key("G major")) == -5
    assert interval_to(parse_key("C major"), parse_key("F major")) == 5
    assert interval_to(parse_key("A minor"), parse_key("E minor")) == -5


def test_transpose_score_skips_drums() -> None:
    score = Score(
        "t",
        120,
        (4, 4),
        "C major",
        [
            Part("piano", [ScoreNote(F(0), F(1), 60)]),
            Part("drums", [ScoreNote(F(0), F(1), 36)]),
            Part(
                "guitar",
                [ScoreNote(F(0), F(1), 52, string=4, fret=2)],
                tuning=[40, 45, 50, 55, 59, 64],
            ),
        ],
    )
    up = transpose_score(score, 3)
    assert up.key == "Eb major"
    assert up.parts[0].notes[0].pitch == 63
    assert up.parts[1].notes[0].pitch == 36
    assert up.parts[2].notes[0].string is None  # TAB must be re-assigned
