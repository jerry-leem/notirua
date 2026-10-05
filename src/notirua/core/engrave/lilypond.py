"""LilyPond source generation (SPEC 6.6). Pure functions; no music21 export involved.

User text (titles, labels) only ever enters the file through :func:`ly_string`,
which produces a quoted LilyPond string. Quoted strings are never evaluated as
Scheme, so escaping quotes and backslashes is enough to prevent injection.
"""

from __future__ import annotations

import math
import statistics
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction

from notirua.core.engrave.layout import Item, Measure, layout_part, measure_count
from notirua.core.model import Part, Score
from notirua.core.transpose import Key, parse_key, spell

LILYPOND_VERSION = "2.26.0"
LAST_PAGE_LABEL = "notirua-last-page"

GM_DRUMS: dict[int, str] = {
    35: "bda",
    36: "bd",
    37: "ss",
    38: "sn",
    40: "sne",
    41: "tomfl",
    42: "hh",
    43: "tomfh",
    44: "hhp",
    45: "tomml",
    46: "hho",
    47: "tommh",
    48: "tomh",
    49: "cymc",
    50: "tomh",
    51: "cymr",
    52: "cymch",
    53: "rb",
    55: "cyms",
    57: "cymcb",
    59: "cymrb",
}

_STRAIGHT_TOKENS: dict[Fraction, str] = {
    Fraction(4): "1",
    Fraction(3): "2.",
    Fraction(2): "2",
    Fraction(3, 2): "4.",
    Fraction(1): "4",
    Fraction(3, 4): "8.",
    Fraction(1, 2): "8",
    Fraction(1, 4): "16",
}
_TRIPLET_TOKENS: dict[Fraction, str] = {Fraction(1, 3): "8", Fraction(2, 3): "4"}


@dataclass(frozen=True)
class EngraveOptions:
    paper: str = "a4"
    tab_mode: str = "both"  # "both" | "tab" | "staff"
    instrument_names: dict[str, str] = field(default_factory=dict)  # translated, per stem
    info_line: str = ""  # translated "♩ = 120 · G major"
    footer_title: str | None = None


def ly_string(text: str) -> str:
    """Quote arbitrary text as a LilyPond string literal."""
    cleaned = "".join(
        " " if unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") and ch != "\u200d" else ch
        for ch in text
    )
    cleaned = cleaned.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{cleaned}"'


def pitch_name(pitch: int, key: Key) -> str:
    letter, alter, octave = spell(pitch, key)
    name = letter.lower() + ("is" * alter if alter > 0 else "es" * -alter)
    name = {"ees": "es", "aes": "as"}.get(name, name)
    marks = octave - 3
    return name + ("'" * marks if marks > 0 else "," * -marks)


def key_command(key: Key) -> str:
    tonic = key.tonic[0].lower()
    alter = key.tonic.count("#") - key.tonic.count("b")
    name = tonic + ("is" * alter if alter > 0 else "es" * -alter)
    name = {"ees": "es", "aes": "as"}.get(name, name)
    return f"\\key {name} \\{key.mode}"


def duration_token(beats: Fraction, triplet: bool = False) -> str:
    table = _TRIPLET_TOKENS if triplet else _STRAIGHT_TOKENS
    if beats in table:
        return table[beats]
    whole = beats / 4
    return f"1*{whole.numerator}/{whole.denominator}"


def full_rest_token(measure_beats: Fraction) -> str:
    return "R" + duration_token(measure_beats)


def _item_text(item: Item, key: Key, drums: bool, with_strings: bool) -> str:
    token = duration_token(item.duration, item.triplet)
    if item.is_rest:
        return "r" + token
    heads = []
    for h in item.heads:
        name = GM_DRUMS.get(h.pitch, "sn") if drums else pitch_name(h.pitch, key)
        string = f"\\{h.string}" if with_strings and h.string is not None else ""
        heads.append((name, string, "~" if h.tie else ""))
    if len(heads) == 1:
        # Single note: the duration comes before string number and tie (c'4\5~).
        name, string, tie = heads[0]
        return name + token + string + tie
    inner = " ".join(name + string + tie for name, string, tie in heads)
    return f"<{inner}>{token}"


def music_text(
    measures: Sequence[Measure],
    measure_beats: Fraction,
    key: Key,
    drums: bool = False,
    with_strings: bool = False,
) -> str:
    """Render measures as LilyPond music, one bar per line."""
    lines = []
    for m in measures:
        if m.full_rest:
            lines.append(full_rest_token(measure_beats) + " |")
            continue
        parts: list[str] = []
        pos = Fraction(0)
        bracket: list[str] = []
        bracket_beat: int | None = None
        for item in m.items:
            beat = math.floor(pos)
            if item.triplet:
                if bracket and bracket_beat != beat:
                    parts.append("\\tuplet 3/2 { " + " ".join(bracket) + " }")
                    bracket = []
                bracket.append(_item_text(item, key, drums, with_strings))
                bracket_beat = beat
            else:
                if bracket:
                    parts.append("\\tuplet 3/2 { " + " ".join(bracket) + " }")
                    bracket = []
                parts.append(_item_text(item, key, drums, with_strings))
            pos += item.duration
        if bracket:
            parts.append("\\tuplet 3/2 { " + " ".join(bracket) + " }")
        lines.append(" ".join(parts) + " |")
    return "\n    ".join(lines)


def _tuning_text(tuning: Sequence[int]) -> str:
    c = Key("C", "major")
    return "\\stringTuning <" + " ".join(pitch_name(p, c) for p in tuning) + ">"


def _global(score: Score, key: Key | None, with_tempo: bool) -> str:
    """Meter, key (omitted for drums: pitch names are invalid in drummode), tempo."""
    num, den = score.time_signature
    tempo = f" \\tempo 4 = {round(score.tempo_bpm)}" if with_tempo else ""
    key_text = f" {key_command(key)}" if key is not None else ""
    return f"\\time {num}/{den}{key_text}{tempo}"


def _vocal_clef(part: Part) -> str:
    if not part.notes:
        return "treble"
    median = statistics.median(n.pitch for n in part.notes)
    return "treble_8" if median < 57 else "treble"


def staff_block(
    stem: str,
    parts: Sequence[Part],
    score: Score,
    key: Key,
    n_measures: int,
    options: EngraveOptions,
    first: bool,
    label: bool,
) -> str:
    """Return the ``\\new ...`` block for one instrument."""
    mb = score.measure_beats
    name = ly_string(options.instrument_names.get(stem, stem.title()))
    end = f" \\label #'{LAST_PAGE_LABEL}" if label else ""
    glob = _global(score, key, with_tempo=first)

    def music(part: Part, *, drums: bool = False, strings: bool = False) -> str:
        return music_text(layout_part(part.notes, mb, n_measures), mb, key, drums, strings)

    if stem == "piano":
        right = next((p for p in parts if p.hand == "right"), Part("piano", []))
        left = next((p for p in parts if p.hand == "left"), Part("piano", []))
        return (
            f"\\new PianoStaff \\with {{ instrumentName = {name} }} <<\n"
            f"  \\new Staff {{ \\clef treble {glob}\n    {music(right)}{end} }}\n"
            f"  \\new Staff {{ \\clef bass {_global(score, key, False)}\n    {music(left)} }}\n"
            ">>"
        )
    part = parts[0]
    if stem == "drums":
        glob = _global(score, None, with_tempo=first)
        return (
            f"\\new DrumStaff \\with {{ instrumentName = {name} }} \\drummode {{ {glob}\n"
            f"    {music(part, drums=True)}{end} }}"
        )
    if stem in ("guitar", "bass") and part.tuning:
        clef = "treble_8" if stem == "guitar" else "bass_8"
        body = music(part, strings=True)
        staff = (
            f'  \\new Staff \\with {{ \\omit StringNumber }} {{ \\clef "{clef}" {glob}\n'
            f"    {body}{end} }}\n"
        )
        tab_only = options.tab_mode == "tab"
        tab_glob = _global(score, key, with_tempo=first and tab_only)
        full = "\\tabFullNotation " if tab_only else ""
        tab_end = end if tab_only else ""
        tab = (
            f"  \\new TabStaff \\with {{ stringTunings = {_tuning_text(part.tuning)} }} "
            f"{{ {full}{tab_glob}\n"
            f"    {body}{tab_end} }}\n"
        )
        if options.tab_mode == "tab":
            return f"\\new StaffGroup \\with {{ instrumentName = {name} }} <<\n{tab}>>"
        if options.tab_mode == "staff":
            return f"\\new StaffGroup \\with {{ instrumentName = {name} }} <<\n{staff}>>"
        return f"\\new StaffGroup \\with {{ instrumentName = {name} }} <<\n{staff}{tab}>>"
    clef = _vocal_clef(part) if stem == "vocals" else "treble"
    return (
        f'\\new Staff \\with {{ instrumentName = {name} }} {{ \\clef "{clef}" {glob}\n'
        f"    {music(part)}{end} }}"
    )


def _paper(score_title: str, paper: str) -> str:
    footer = ly_string(f"{score_title} — ")
    size = "letter" if paper.lower() == "letter" else "a4"
    return (
        "\\paper {\n"
        f'  #(set-paper-size "{size}")\n'
        "  print-page-number = ##f\n"
        "  oddHeaderMarkup = \\markup \\null\n"
        "  evenHeaderMarkup = \\markup \\null\n"
        "  oddFooterMarkup = \\markup \\fill-line { \\concat {\n"
        f'    {footer} \\fromproperty #\'page:page-number-string " / " '
        f'\\page-ref #\'{LAST_PAGE_LABEL} "00" "?" }} }}\n'
        "  evenFooterMarkup = \\oddFooterMarkup\n"
        "}\n"
    )


def _header(title: str, subtitle: str | None, info: str) -> str:
    lines = [f"  title = {ly_string(title)}"]
    if subtitle:
        lines.append(f"  subtitle = {ly_string(subtitle)}")
    if info:
        lines.append(f"  subsubtitle = {ly_string(info)}")
    lines.append("  tagline = ##f")
    return "\\header {\n" + "\n".join(lines) + "\n}\n"


def _parts_by_stem(score: Score, stems: Sequence[str]) -> list[tuple[str, list[Part]]]:
    groups: dict[str, list[Part]] = {}
    for p in score.parts:
        groups.setdefault(p.stem, []).append(p)
    return [(s, groups[s]) for s in stems if s in groups]


def render_ly(
    score: Score,
    stems: Sequence[str],
    options: EngraveOptions,
    combined: bool = False,
) -> str:
    """One instrument per page set; with ``combined`` every instrument is a book part."""
    key = parse_key(score.key)
    groups = _parts_by_stem(score, stems)
    n_measures = measure_count([p.notes for p in score.parts], score.measure_beats)
    title = options.footer_title or score.title
    out = [f'\\version "{LILYPOND_VERSION}"\n', _paper(title, options.paper)]
    if not groups:
        raise ValueError("no parts to engrave")
    if not combined:
        names = [options.instrument_names.get(s, s.title()) for s, _p in groups]
        out.append(_header(score.title, " · ".join(names), options.info_line))
        blocks = [
            staff_block(s, ps, score, key, n_measures, options, first=i == 0, label=i == 0)
            for i, (s, ps) in enumerate(groups)
        ]
        out.append("\\score {\n  <<\n" + "\n".join(blocks) + "\n  >>\n  \\layout { }\n}\n")
        return "".join(out)
    out.append(_header(score.title, None, options.info_line))
    out.append("\\book {\n")
    for i, (s, ps) in enumerate(groups):
        last = i == len(groups) - 1
        block = staff_block(s, ps, score, key, n_measures, options, first=True, label=last)
        sub = ly_string(options.instrument_names.get(s, s.title()))
        out.append(
            "\\bookpart {\n"
            f"  \\header {{ subtitle = {sub} }}\n"
            f"  \\score {{\n  <<\n{block}\n  >>\n  \\layout {{ }}\n  }}\n"
            "}\n"
        )
    out.append("}\n")
    return "".join(out)
