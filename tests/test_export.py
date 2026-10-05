from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

from notirua.core.export import write_midi, write_musicxml
from notirua.core.model import Part, Score, ScoreNote


def score() -> Score:
    return Score(
        "Export 테스트",
        90,
        (3, 4),
        "D major",
        [
            Part("piano", [ScoreNote(F(0), F(1), 62), ScoreNote(F(1), F(2), 66)], hand="right"),
            Part("drums", [ScoreNote(F(0), F(1), 36)]),
        ],
    )


def test_midi_structure(tmp_path: Path) -> None:
    path = write_midi(score(), tmp_path / "x.mid")
    data = path.read_bytes()
    assert data[:4] == b"MThd"
    assert data.count(b"MTrk") == 3  # tempo track + 2 parts
    assert b"\xff\x51\x03" in data  # tempo
    assert b"\x99\x24" in data  # note-on, channel 10, kick (36)


def test_musicxml_round_trip(tmp_path: Path) -> None:
    from music21 import converter

    path = write_musicxml(score(), tmp_path / "x.musicxml", {"piano": "Piano", "drums": "Drums"})
    parsed = converter.parse(str(path))
    pitches = [n.pitch.midi for n in parsed.parts[0].recurse().notes]
    assert pitches == [62, 66]
    assert "<work-title>Export 테스트</work-title>" in path.read_text(encoding="utf-8")
