from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

import pytest

from notirua.core.engrave.layout import layout_part, measure_count
from notirua.core.engrave.lilypond import (
    EngraveOptions,
    duration_token,
    ly_string,
    music_text,
    pitch_name,
    render_ly,
)
from notirua.core.model import Part, Score, ScoreNote
from notirua.core.transpose import parse_key

SNAPSHOTS = Path(__file__).parent / "snapshots"


def n(onset: F | int, dur: F | int, pitch: int, string: int | None = None) -> ScoreNote:
    return ScoreNote(F(onset), F(dur), pitch, 80, string=string)


@pytest.mark.parametrize(
    "title",
    [
        'He said "hi"',
        "back\\slash",
        '"} #(system "rm -rf /") {"',
        "$(display 1) #(exit)",
        "line\nbreak\ttab\x00nul",
        "\\markup { \\bold x }",
    ],
)
def test_ly_string_cannot_break_out(title: str) -> None:
    quoted = ly_string(title)
    assert quoted.startswith('"') and quoted.endswith('"')
    body = quoted[1:-1]
    # Every quote inside the literal is escaped, and no raw newline/control chars remain.
    i = 0
    while i < len(body):
        if body[i] == "\\":
            assert body[i + 1] in '\\"'
            i += 2
            continue
        assert body[i] != '"'
        assert body[i] not in "\n\r\t\x00"
        i += 1


def test_injection_title_in_full_document() -> None:
    evil = '"} #(system "touch /tmp/pwned") \\header { title = "'
    score = Score(evil, 120, (4, 4), "C major", [Part("vocals", [n(0, 1, 60)])])
    ly = render_ly(score, ["vocals"], EngraveOptions())
    assert '#(system "touch' not in ly
    assert f"  title = {ly_string(evil)}\n" in ly
    assert ly_string(evil) == '"\\"} #(system \\"touch /tmp/pwned\\") \\\\header { title = \\""'


def test_pitch_names_and_octaves() -> None:
    c = parse_key("C major")
    assert pitch_name(60, c) == "c'"
    assert pitch_name(48, c) == "c"
    assert pitch_name(36, c) == "c,"
    assert pitch_name(73, parse_key("A major")) == "cis''"
    assert pitch_name(63, parse_key("Bb major")) == "es'"
    assert pitch_name(68, parse_key("Eb major")) == "as'"


def test_duration_tokens() -> None:
    assert duration_token(F(1)) == "4"
    assert duration_token(F(3, 2)) == "4."
    assert duration_token(F(1, 3), triplet=True) == "8"
    assert duration_token(F(5)) == "1*5/4"


def test_ties_across_barline() -> None:
    measures = layout_part([n(3, 2, 60)], F(4), 2)
    text = music_text(measures, F(4), parse_key("C major"))
    assert text.splitlines()[0].strip() == "r2 r4 c'4~ |"
    assert text.splitlines()[1].strip() == "c'4 r4 r2 |"


def test_full_measure_rest_and_dotted_values() -> None:
    measures = layout_part([n(0, F(3, 2), 60), n(F(3, 2), F(1, 2), 62)], F(4), 2)
    text = music_text(measures, F(4), parse_key("C major"))
    assert text.splitlines()[0].strip() == "c'4. d'8 r2 |"
    assert text.splitlines()[1].strip() == "R1 |"


def test_triplet_bracket() -> None:
    notes = [n(F(k, 3), F(1, 3), 60 + k) for k in range(3)]
    text = music_text(layout_part(notes, F(4), 1), F(4), parse_key("C major"))
    assert text.startswith("\\tuplet 3/2 { c'8 cis'8 d'8 }")


def test_chord_with_partial_tie() -> None:
    notes = [n(0, 2, 60), n(0, 1, 64)]
    text = music_text(layout_part(notes, F(4), 1), F(4), parse_key("C major"))
    assert text.startswith("<c'~ e'>4 c'4 r2")


def test_tab_string_numbers() -> None:
    notes = [n(0, 1, 52, string=4), n(1, 1, 55, string=3), n(1, 1, 59, string=2)]
    text = music_text(layout_part(notes, F(4), 1), F(4), parse_key("C major"), with_strings=True)
    assert text.startswith("e4\\4 <g\\3 b\\2>4")


def test_measure_count() -> None:
    assert measure_count([[n(0, 1, 60)], [n(7, 2, 60)]], F(4)) == 3


def _demo_score() -> Score:
    return Score(
        "Snapshot 한글",
        96,
        (4, 4),
        "G major",
        [
            Part("vocals", [n(0, 1, 67), n(1, 1, 66), n(2, 2, 62)]),
            Part("guitar", [n(0, 1, 55, 3), n(1, 1, 59, 2)], tuning=[40, 45, 50, 55, 59, 64]),
            Part("piano", [n(0, 4, 74)], hand="right"),
            Part("piano", [n(0, 4, 43)], hand="left"),
            Part("drums", [n(0, 1, 36), n(0, 1, 42), n(1, 1, 38)]),
        ],
    )


def test_snapshot_document(request: pytest.FixtureRequest) -> None:
    opts = EngraveOptions(
        paper="letter",
        instrument_names={
            "vocals": "Vocals",
            "guitar": "Guitar",
            "piano": "Piano",
            "drums": "Drums",
        },
        info_line="♩ = 96 · G major",
    )
    ly = render_ly(_demo_score(), ["vocals", "guitar", "piano", "drums"], opts)
    snap = SNAPSHOTS / "demo_score.ly"
    if request.config.getoption("--update-snapshots") or not snap.exists():
        snap.parent.mkdir(exist_ok=True)
        snap.write_text(ly, encoding="utf-8")
    assert ly == snap.read_text(encoding="utf-8")


def test_combined_book_has_one_last_page_label() -> None:
    ly = render_ly(_demo_score(), ["vocals", "guitar", "drums"], EngraveOptions(), combined=True)
    assert ly.count("\\bookpart") == 3
    assert ly.count("\\label #'notirua-last-page") == 1
