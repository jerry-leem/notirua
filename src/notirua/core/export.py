"""MIDI and MusicXML export (FR-7). MusicXML goes through music21 (SPEC 2)."""

from __future__ import annotations

import struct
from collections.abc import Mapping
from fractions import Fraction
from pathlib import Path

from notirua.core.model import Part, Score

TICKS_PER_BEAT = 480
DRUM_CHANNEL = 9
PROGRAMS = {"vocals": 53, "bass": 33, "guitar": 25, "piano": 0, "other": 48}


def _vlq(value: int) -> bytes:
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(out))


def _track(events: list[tuple[int, bytes]]) -> bytes:
    events.sort(key=lambda e: (e[0], e[1][0] & 0xF0 == 0x90))  # note-offs before note-ons
    data = bytearray()
    now = 0
    for tick, msg in events:
        data += _vlq(tick - now) + msg
        now = tick
    data += b"\x00\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(data)) + bytes(data)


def _ticks(beats: Fraction) -> int:
    return round(beats * TICKS_PER_BEAT)


def write_midi(score: Score, path: Path) -> Path:
    """Write a type-1 Standard MIDI File with one track per staff."""
    tempo_us = round(60_000_000 / max(score.tempo_bpm, 1.0))
    num, den = score.time_signature
    meta: list[tuple[int, bytes]] = [
        (0, b"\xff\x51\x03" + tempo_us.to_bytes(3, "big")),
        (0, b"\xff\x58\x04" + bytes([num, den.bit_length() - 1, 24, 8])),
    ]
    title = score.title.encode("utf-8")[:120]
    meta.append((0, b"\xff\x03" + _vlq(len(title)) + title))
    tracks = [_track(meta)]
    channel = 0
    for part in score.parts:
        if part.stem == "drums":
            ch = DRUM_CHANNEL
        else:
            ch = channel
            channel = channel + 1 if channel + 1 != DRUM_CHANNEL else channel + 2
            ch = min(ch, 15)
        events: list[tuple[int, bytes]] = []
        if part.stem != "drums":
            events.append((0, bytes([0xC0 | ch, PROGRAMS.get(part.stem, 0)])))
        for n in part.notes:
            vel = max(1, min(127, n.velocity))
            events.append((_ticks(n.onset), bytes([0x90 | ch, n.pitch & 0x7F, vel])))
            events.append((_ticks(n.onset + n.duration), bytes([0x80 | ch, n.pitch & 0x7F, 0])))
        tracks.append(_track(events))
    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), TICKS_PER_BEAT)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + b"".join(tracks))
    return path


def write_musicxml(score: Score, path: Path, names: Mapping[str, str]) -> Path:
    from music21 import instrument, key, metadata, meter, note, stream, tempo

    from notirua.core.transpose import parse_key

    s = stream.Score()
    s.insert(0, metadata.Metadata(title=score.title))
    k = parse_key(score.key)
    for part in score.parts:
        p = stream.Part()
        label = names.get(part.stem, part.stem.title())
        if part.hand:
            label = f"{label} ({'RH' if part.hand == 'right' else 'LH'})"
        inst = instrument.UnpitchedPercussion() if part.stem == "drums" else instrument.Instrument()
        inst.partName = label
        p.insert(0, inst)
        p.insert(0, meter.TimeSignature(f"{score.time_signature[0]}/{score.time_signature[1]}"))
        if part.stem != "drums":
            p.insert(0, key.Key(k.tonic.replace("b", "-"), k.mode))
        p.insert(0, _clef_for(part))
        if part is score.parts[0]:
            p.insert(0, tempo.MetronomeMark(number=round(score.tempo_bpm)))
        for n in part.notes:
            m21 = note.Note(n.pitch, quarterLength=n.duration)
            m21.volume.velocity = n.velocity
            p.insert(n.onset, m21)
        s.insert(0, p.makeMeasures() if part.notes else p)
    path.parent.mkdir(parents=True, exist_ok=True)
    s.write("musicxml", fp=str(path))
    return path


def _clef_for(part: Part) -> object:
    from music21 import clef

    if part.stem == "drums":
        return clef.PercussionClef()
    if part.hand == "left" or part.stem == "bass":
        return clef.BassClef()
    return clef.TrebleClef()
