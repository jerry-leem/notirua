"""Internal score data model (SPEC 5.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

STEMS: tuple[str, ...] = ("vocals", "drums", "bass", "guitar", "piano", "other")
PITCHED_STEMS: tuple[str, ...] = ("vocals", "bass", "guitar", "piano", "other")


@dataclass(frozen=True)
class NoteEvent:
    """A transcribed note in seconds, before quantization."""

    start_s: float
    end_s: float
    pitch: int  # MIDI number; GM percussion number for drums
    velocity: int


@dataclass(frozen=True)
class ScoreNote:
    """A quantized note in beats from the start of the piece."""

    onset: Fraction
    duration: Fraction
    pitch: int
    velocity: int = 80
    string: int | None = None  # TAB assignment: 1 = highest string
    fret: int | None = None


@dataclass
class Part:
    stem: str
    notes: list[ScoreNote]
    tuning: list[int] | None = None  # MIDI pitches, lowest string first
    staff: str = "treble"  # "treble" | "treble_8" | "bass_8" | "piano" | "drums"
    hand: str | None = None  # "right" | "left" for piano halves
    warnings: list[str] = field(default_factory=list)


@dataclass
class Score:
    title: str
    tempo_bpm: float
    time_signature: tuple[int, int]
    key: str  # e.g. "G major"
    parts: list[Part]
    pickup_beats: Fraction = Fraction(0)

    @property
    def measure_beats(self) -> Fraction:
        num, den = self.time_signature
        return Fraction(num * 4, den)
