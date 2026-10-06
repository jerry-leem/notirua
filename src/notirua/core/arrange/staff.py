"""Per-stem staff arrangement (FR-4 table): clefs, TAB, piano hands."""

from __future__ import annotations

import itertools
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from fractions import Fraction

from notirua.core.arrange.piano import split_hands
from notirua.core.arrange.tab import MAX_FRET, TabWeights, assign_tab, fit_range, parse_tuning
from notirua.core.model import Part, ScoreNote
from notirua.core.quantize import trim_overlaps_same_pitch
from notirua.i18n import N_

log = logging.getLogger(__name__)

STAFF_FOR_STEM = {
    "vocals": "treble",
    "guitar": "treble_8",
    "bass": "bass_8",
    "piano": "piano",
    "drums": "drums",
    "other": "treble",
}


@dataclass(frozen=True)
class ArrangeOptions:
    guitar_tuning: str | Sequence[int] = "standard"
    bass_tuning: str | Sequence[int] = "standard"
    tab_weights: TabWeights = field(default_factory=TabWeights)


def drum_durations(notes: Sequence[ScoreNote], cap: Fraction = Fraction(1)) -> list[ScoreNote]:
    """Drum hits have no length; let each last until the next hit (at most ``cap``)."""
    onsets = sorted({n.onset for n in notes})
    following = {a: b for a, b in itertools.pairwise(onsets)}
    return [
        replace(n, duration=min(cap, following.get(n.onset, n.onset + cap) - n.onset))
        for n in notes
    ]


def arrange_part(stem: str, notes: Sequence[ScoreNote], options: ArrangeOptions) -> list[Part]:
    if stem == "drums":
        return [Part("drums", drum_durations(notes), staff="drums")]
    notes = trim_overlaps_same_pitch(notes)
    if stem == "piano":
        right, left = split_hands(notes)
        return [
            Part("piano", right, staff="piano", hand="right"),
            Part("piano", left, staff="piano", hand="left"),
        ]
    if stem in ("guitar", "bass"):
        spec = options.guitar_tuning if stem == "guitar" else options.bass_tuning
        tuning = parse_tuning(spec, stem)
        max_fret = MAX_FRET[stem]
        warnings: list[str] = []
        shifted, octaves = fit_range(notes, tuning, max_fret)
        if octaves:
            warnings.append(
                N_("Moved up one octave to fit the instrument.")
                if octaves > 0
                else N_("Moved down one octave to fit the instrument.")
            )
        result = assign_tab(shifted, tuning, max_fret, options.tab_weights)
        log.info(
            "%s: %d notes in, %d placed, %d moved by octaves into range, "
            "%d merged duplicates, %d chords re-voiced, %d left out",
            stem,
            len(notes),
            len(result.notes),
            result.folded,
            result.merged,
            result.revoiced,
            len(result.dropped),
        )
        if result.folded:
            warnings.append(
                N_("Some notes outside the instrument's range were moved by an octave.")
            )
        if result.dropped:
            log.warning(
                "%s: left out %d notes that cannot be played together", stem, len(result.dropped)
            )
            warnings.append(N_("Some notes that cannot be played together were left out."))
        return [
            Part(stem, result.notes, tuning=tuning, staff=STAFF_FOR_STEM[stem], warnings=warnings)
        ]
    return [Part(stem, list(notes), staff=STAFF_FOR_STEM.get(stem, "treble"))]
