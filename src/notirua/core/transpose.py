"""Transposition, key names, and pitch spelling (FR-6). Pure functions only."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from notirua.core.model import Part, Score, ScoreNote

LETTERS = "CDEFGAB"
NATURAL_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Preferred tonic spelling per pitch class (fewest accidentals; ties favour common usage).
MAJOR_TONICS = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MINOR_TONICS = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]


@dataclass(frozen=True)
class Key:
    tonic: str  # e.g. "F#", "Bb"
    mode: str  # "major" | "minor"

    @property
    def tonic_pc(self) -> int:
        return (NATURAL_PC[self.tonic[0]] + _alter(self.tonic[1:])) % 12

    @property
    def major_pc(self) -> int:
        """Pitch class of the relative major (minor keys share its signature)."""
        return self.tonic_pc if self.mode == "major" else (self.tonic_pc + 3) % 12

    def __str__(self) -> str:
        return f"{self.tonic} {self.mode}"


def _alter(acc: str) -> int:
    return acc.count("#") - acc.count("b")


def parse_key(text: str) -> Key:
    """Parse ``"G major"``, ``"f# minor"``, ``"Bbm"``, or ``"E-"`` (music21 flat)."""
    raw = text.strip().replace("-", "b").replace("♭", "b").replace("♯", "#")
    parts = raw.split()
    tonic = parts[0] if parts else "C"
    mode = parts[1].lower() if len(parts) > 1 else "major"
    if len(parts) == 1 and tonic.endswith("m") and len(tonic) > 1:
        tonic, mode = tonic[:-1], "minor"
    tonic = tonic[0].upper() + tonic[1:]
    if tonic[0] not in NATURAL_PC:
        raise ValueError(f"unknown key: {text!r}")
    if mode not in ("major", "minor"):
        mode = "minor" if mode.startswith("min") else "major"
    return Key(tonic, mode)


def key_for_pc(pc: int, mode: str) -> Key:
    names = MAJOR_TONICS if mode == "major" else MINOR_TONICS
    return Key(names[pc % 12], mode)


def transpose_key(key: Key, semitones: int) -> Key:
    return key_for_pc(key.tonic_pc + semitones, key.mode)


def interval_to(key: Key, target: Key) -> int:
    """Smallest move from ``key`` to ``target`` tonic, in [-6, +5] semitones."""
    diff = (target.tonic_pc - key.tonic_pc) % 12
    return diff - 12 if diff > 5 else diff


def uses_flats(key: Key) -> bool:
    return key_signature_accidentals(key) < 0


def key_signature_accidentals(key: Key) -> int:
    """Positive = number of sharps, negative = number of flats."""
    return sum(alter for _letter, alter in _scale(key)[:7])


def spell(pitch: int, key: Key) -> tuple[str, int, int]:
    """Spell a MIDI pitch as ``(letter, alteration, octave)`` for ``key``.

    Diatonic notes use the key's scale spelling; chromatic notes use sharps in
    sharp keys and flats in flat keys.
    """
    pc = pitch % 12
    scale = _scale(key)
    for letter, alter in scale:
        if (NATURAL_PC[letter] + alter) % 12 == pc:
            return letter, alter, _octave(pitch, letter, alter)
    flats = uses_flats(key)
    for letter in LETTERS:
        alter = -1 if flats else 1
        if (NATURAL_PC[letter] + alter) % 12 == pc:
            return letter, alter, _octave(pitch, letter, alter)
    for letter in LETTERS:  # natural (cancelling the key signature)
        if NATURAL_PC[letter] == pc:
            return letter, 0, _octave(pitch, letter, 0)
    raise AssertionError(pc)


def _octave(pitch: int, letter: str, alter: int) -> int:
    # B#3 sounds as C4 but is written in octave 3: use the unaltered letter's pitch.
    return (pitch - alter) // 12 - 1


def _scale(key: Key) -> list[tuple[str, int]]:
    # Keep the key's own spelling (C# major is not Db major); a minor key's
    # relative major sits a third (two letters) above its tonic.
    if key.mode == "major":
        major_letter = key.tonic[0]
    else:
        major_letter = LETTERS[(LETTERS.index(key.tonic[0]) + 2) % 7]
    start = LETTERS.index(major_letter)
    steps = [0, 2, 4, 5, 7, 9, 11]
    result = []
    for i, step in enumerate(steps):
        letter = LETTERS[(start + i) % 7]
        target = (key.major_pc + step) % 12
        alter = (target - NATURAL_PC[letter] + 6) % 12 - 6
        result.append((letter, alter))
    if key.mode == "minor":
        # Raised leading tone of harmonic minor is spelled from the same letter.
        tonic_letter = key.tonic[0]
        lead_letter = LETTERS[(LETTERS.index(tonic_letter) - 1) % 7]
        lead_pc = (key.tonic_pc - 1) % 12
        alter = (lead_pc - NATURAL_PC[lead_letter] + 6) % 12 - 6
        result.append((lead_letter, alter))
    return result


def transpose_notes(notes: Sequence[ScoreNote], semitones: int) -> list[ScoreNote]:
    return [replace(n, pitch=n.pitch + semitones, string=None, fret=None) for n in notes]


def transpose_score(score: Score, semitones: int) -> Score:
    """Transpose pitched parts; drums are untouched (FR-6). TAB is cleared for re-assignment."""
    if semitones == 0:
        return score
    parts = [
        p
        if p.stem == "drums"
        else Part(
            stem=p.stem,
            notes=transpose_notes(p.notes, semitones),
            tuning=p.tuning,
            staff=p.staff,
            hand=p.hand,
            warnings=list(p.warnings),
        )
        for p in score.parts
    ]
    key = str(transpose_key(parse_key(score.key), semitones))
    return replace(score, parts=parts, key=key)
