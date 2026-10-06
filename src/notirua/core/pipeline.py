"""Pipeline orchestration (SPEC 5.1): decode → separate → transcribe → analyze →
quantize → arrange (→ transpose) → engrave → export.

GUI and CLI call only this module. Every stage reports progress and checks the
cancel token; finished stages are cached so retries and transposition reuse
them (SPEC 5.4, FR-6, FR-11).
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np

from notirua import paths
from notirua.core import cache as cache_mod
from notirua.core.analyze import Analysis, analyze
from notirua.core.arrange.staff import ArrangeOptions, arrange_part
from notirua.core.arrange.tab import TUNINGS, TabWeights
from notirua.core.decode import SAMPLE_RATE, AudioArray, AudioInfo, decode, probe
from notirua.core.engrave.lilypond import EngraveOptions, render_ly
from notirua.core.engrave.render import Engraver
from notirua.core.errors import Cancelled, NotiruaError
from notirua.core.model import PITCHED_STEMS, STEMS, Part, Score, ScoreNote
from notirua.core.progress import (
    CancelToken,
    ProgressCallback,
    ProgressReporter,
    StageSpec,
)
from notirua.core.quantize import common_start, quantize, shift
from notirua.core.separate import Separator, is_silent, noise_gate
from notirua.core.transcribe.drums import DrumSettings, DrumTranscriber
from notirua.core.transcribe.pitched import PitchedTranscriber, PostprocessSettings
from notirua.core.transpose import (
    MAJOR_TONICS,
    MINOR_TONICS,
    interval_to,
    parse_key,
    transpose_key,
    transpose_notes,
)
from notirua.i18n import N_, translator
from notirua.settings import DEFAULT_STAGE_WEIGHTS

log = logging.getLogger(__name__)

INSTRUMENT_NAMES = {
    "vocals": N_("Vocals"),
    "drums": N_("Drums"),
    "bass": N_("Bass"),
    "guitar": N_("Guitar"),
    "piano": N_("Piano"),
    "other": N_("Other"),
}
MAJOR_KEY = N_("{tonic} major")
MINOR_KEY = N_("{tonic} minor")
INFO_LINE = N_("♩ = {bpm} · {key}")

STAGE_MESSAGES = {
    "decode": N_("Reading the audio file"),
    "separate": N_("Splitting the song into instruments"),
    "transcribe": N_("Listening for notes"),
    "analyze": N_("Finding the beat, tempo, and key"),
    "quantize": N_("Fitting notes to the beat"),
    "arrange": N_("Arranging staves and tablature"),
    "engrave": N_("Drawing the sheet music"),
    "export": N_("Saving files"),
}
STAGE_CACHED = N_("Reusing earlier results")
TRANSCRIBE_STEM = N_("Listening for {instrument} notes ({index}/{count})")
ENGRAVE_STEM = N_("Drawing {instrument} sheet music ({index}/{count})")
SKIP_SILENT = N_("No sound")
SKIP_NOT_SELECTED = N_("Not selected")

TUNING_LABELS = {
    "standard": N_("Standard"),
    "drop_d": N_("Drop D"),
    "half_down": N_("Half step down"),
    "five_string": N_("5-string"),
}
TUNING_CHOICES: dict[str, list[str]] = {inst: list(t) for inst, t in TUNINGS.items()}
KEY_CHOICES: list[str] = [f"{t} major" for t in MAJOR_TONICS] + [f"{t} minor" for t in MINOR_TONICS]

_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass
class JobOptions:
    title: str | None = None
    stems: list[str] | None = None  # None = every instrument that has sound
    transpose: int = 0
    target_key: str | None = None
    paper: str = "a4"
    guitar_tuning: str = "standard"
    bass_tuning: str = "standard"
    time_signature: tuple[int, int] | None = None
    tempo_bpm: float | None = None
    key: str | None = None
    downbeat_shift: int = 0
    tab_mode: str = "both"
    per_stem_pdfs: bool = True
    combined_pdf: bool = True
    export_musicxml: bool = False
    export_midi: bool = False
    pdf_language: str | None = None
    stream_index: int | None = None
    start_s: float | None = None
    end_s: float | None = None
    tab_weights: dict[str, float] = field(default_factory=dict)


@dataclass
class JobResult:
    title: str
    score: Score
    pdfs: dict[str, Path]
    combined_pdf: Path | None
    other_files: list[Path]
    skipped: dict[str, str]  # stem -> reason message id
    warnings: list[str]
    elapsed_s: float
    stems_audio: dict[str, Path] = field(default_factory=dict)


@dataclass
class Engines:
    """Lazily created back ends; tests inject fakes."""

    separator: Callable[[], Separator]
    pitched: Callable[[], PitchedTranscriber]
    drums: Callable[[], DrumTranscriber]
    engraver: Callable[[], Engraver]


def default_engines(settings: Any = None) -> Engines:
    from notirua.components.manager import manager_from_settings

    manager = manager_from_settings(settings)

    def separator() -> Separator:
        from notirua.core.separate import DemucsOnnxSeparator

        return DemucsOnnxSeparator(manager.require("htdemucs_6s"))

    def pitched() -> PitchedTranscriber:
        from notirua.core.transcribe.pitched import BasicPitchTranscriber

        return BasicPitchTranscriber()

    def drums() -> DrumTranscriber:
        from notirua.core.transcribe.drums import RuleBasedDrumTranscriber

        return RuleBasedDrumTranscriber()

    def engraver() -> Engraver:
        from notirua.core.engrave.render import LilyPondEngraver

        return LilyPondEngraver(manager.require("lilypond"))

    return Engines(separator, pitched, drums, engraver)


def safe_filename(name: str, max_len: int = 120) -> str:
    cleaned = _FORBIDDEN.sub("_", name).strip().rstrip(".")
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if cleaned.upper().split(".")[0] in reserved:
        cleaned = "_" + cleaned
    return (cleaned or "untitled")[:max_len]


def key_label(key: str, gettext_fn: Callable[[str], str]) -> str:
    k = parse_key(key)
    return gettext_fn(MAJOR_KEY if k.mode == "major" else MINOR_KEY).format(tonic=k.tonic)


def transposed_key(key: str, semitones: int) -> str:
    return str(transpose_key(parse_key(key), semitones))


def semitones_between(key: str, target: str) -> int:
    """Smallest move from ``key`` to ``target``, in [-6, +5] semitones."""
    return interval_to(parse_key(key), parse_key(target))


def keys_like(key: str) -> list[str]:
    """The 12 keys with the same mode as ``key``, starting from C."""
    mode = parse_key(key).mode
    return [k for k in KEY_CHOICES if k.endswith(mode)]


def inspect(path: Path) -> AudioInfo:
    """Duration, audio tracks, and embedded title of a file, without decoding it."""
    return probe(path)


def export_score(score: Score, fmt: str, target: Path, pdf_language: str | None = None) -> Path:
    """Write ``score`` as ``"midi"`` or ``"musicxml"`` outside a pipeline run."""
    from notirua.core import export

    if fmt == "midi":
        return export.write_midi(score, target)
    tr = translator(pdf_language)
    return export.write_musicxml(score, target, {s: tr.gettext(INSTRUMENT_NAMES[s]) for s in STEMS})


class Pipeline:
    def __init__(
        self,
        engines: Engines | None = None,
        cache_root: Path | None = None,
        stage_weights: dict[str, float] | None = None,
        cache_limit_bytes: int = 5 * 1024**3,
    ) -> None:
        self.engines = engines or default_engines()
        self.cache_root = cache_root or (paths.cache_dir() / "jobs")
        self.weights = {**DEFAULT_STAGE_WEIGHTS, **(stage_weights or {})}
        self.cache_limit_bytes = cache_limit_bytes
        self._separator: Separator | None = None
        self._pitched: PitchedTranscriber | None = None
        self._drums: DrumTranscriber | None = None
        self._engraver: Engraver | None = None

    # Engines are created on first use and kept for later jobs.
    def separator(self) -> Separator:
        if self._separator is None:
            self._separator = self.engines.separator()
        return self._separator

    def pitched(self) -> PitchedTranscriber:
        if self._pitched is None:
            self._pitched = self.engines.pitched()
        return self._pitched

    def drums(self) -> DrumTranscriber:
        if self._drums is None:
            self._drums = self.engines.drums()
        return self._drums

    def engraver(self) -> Engraver:
        if self._engraver is None:
            self._engraver = self.engines.engraver()
        return self._engraver

    def run(
        self,
        input_path: Path,
        out_dir: Path,
        options: JobOptions | None = None,
        progress: ProgressCallback | None = None,
        cancel: CancelToken | None = None,
    ) -> JobResult:
        opts = options or JobOptions()
        cancel = cancel or CancelToken()
        started = time.monotonic()
        stages = [StageSpec(n, self.weights.get(n, 1.0), STAGE_MESSAGES[n]) for n in STAGE_MESSAGES]
        reporter = ProgressReporter("pipeline", stages, progress)
        current = "decode"
        with reporter:
            try:
                return self._run(input_path, out_dir, opts, reporter, cancel, started)
            except Cancelled:
                raise
            except NotiruaError:
                current = next((s for s, st in reporter.states.items() if st == "running"), current)
                reporter.fail(current)
                raise
            except Exception:
                current = next((s for s, st in reporter.states.items() if st == "running"), current)
                reporter.fail(current)
                log.exception("pipeline failed in %s", current)
                raise

    def _run(
        self,
        input_path: Path,
        out_dir: Path,
        opts: JobOptions,
        rep: ProgressReporter,
        cancel: CancelToken,
        started: float,
    ) -> JobResult:
        cache = cache_mod.StageCache(
            self.cache_root, cache_mod.file_hash(input_path), self.cache_limit_bytes
        )
        warnings: list[str] = []

        # 1. decode -------------------------------------------------------
        rep.start("decode")
        info = probe(input_path)
        title = (opts.title or info.title or input_path.stem).strip() or input_path.stem
        decode_key = cache_mod.options_hash("decode", opts.stream_index, opts.start_s, opts.end_s)
        cached_mix = cache.load_audio("decode", decode_key, ["mix"])
        if cached_mix is not None:
            mix = cached_mix["mix"]
            rep.done("decode", STAGE_CACHED)
        else:
            mix = decode(
                input_path,
                stream_index=opts.stream_index,
                start_s=opts.start_s,
                end_s=opts.end_s,
                progress=rep.sub("decode"),
                cancel=cancel,
            )
            cache.save_audio("decode", decode_key, {"mix": mix})
            rep.done("decode")
        cancel.raise_if_cancelled()

        # 2. separate -----------------------------------------------------
        rep.start("separate")
        sep_key = cache_mod.options_hash("separate", decode_key, "htdemucs_6s")
        stems_audio = cache.load_audio("separate", sep_key, list(STEMS))
        if stems_audio is not None:
            rep.done("separate", STAGE_CACHED)
        else:
            separator = self.separator()
            raw = separator.separate(mix, progress=rep.sub("separate"), cancel=cancel)
            stems_audio = {s: raw[s] for s in STEMS if s in raw}
            cache.save_audio("separate", sep_key, stems_audio)
            rep.done("separate")
        cancel.raise_if_cancelled()

        skipped: dict[str, str] = {}
        wanted = [s for s in STEMS if opts.stems is None or s in opts.stems]
        for s in STEMS:
            if s not in wanted:
                skipped[s] = SKIP_NOT_SELECTED
        active = []
        for s in wanted:
            audio = stems_audio.get(s)
            if audio is None or is_silent(audio):
                skipped[s] = SKIP_SILENT
            else:
                active.append(s)

        # 3. transcribe ---------------------------------------------------
        rep.start("transcribe")
        tr_key = cache_mod.options_hash(
            "transcribe", sep_key, PostprocessSettings(), DrumSettings(), sorted(active), "gate1"
        )
        events = cache.load_notes("transcribe", tr_key) or {}
        todo = [s for s in active if s not in events]
        for i, stem in enumerate(todo):
            cancel.raise_if_cancelled()
            base = i / max(1, len(todo))
            rep.update(
                "transcribe",
                base,
                TRANSCRIBE_STEM,
                instrument=INSTRUMENT_NAMES[stem],
                index=i + 1,
                count=len(todo),
            )

            def sub(f: float, base: float = base) -> None:
                rep.update("transcribe", base + f / max(1, len(todo)))

            audio = noise_gate(stems_audio[stem])
            if stem == "drums":
                events[stem] = self.drums().transcribe(
                    audio, SAMPLE_RATE, progress=sub, cancel=cancel
                )
            else:
                events[stem] = self.pitched().transcribe(
                    audio, SAMPLE_RATE, stem, progress=sub, cancel=cancel
                )
            cache.save_notes("transcribe", tr_key, events)
        rep.done("transcribe", STAGE_CACHED if not todo and active else None)

        # 4. analyze ------------------------------------------------------
        rep.start("analyze")
        an_key = cache_mod.options_hash(
            "analyze", tr_key, opts.time_signature, opts.tempo_bpm, opts.key, opts.downbeat_shift
        )
        cached_an = cache.load_json("analyze", an_key)
        if cached_an is not None:
            analysis = Analysis(
                **{**cached_an, "time_signature": tuple(cached_an["time_signature"])}
            )
            rep.done("analyze", STAGE_CACHED)
        else:
            pitched_notes = [
                e for s in active if s in PITCHED_STEMS and s != "bass" for e in events.get(s, [])
            ]
            if not pitched_notes:
                pitched_notes = [e for s in active if s in PITCHED_STEMS for e in events.get(s, [])]
            analysis = analyze(
                mix,
                SAMPLE_RATE,
                pitched_notes,
                time_signature=opts.time_signature,
                tempo_override=opts.tempo_bpm,
                key_override=opts.key,
                downbeat_shift=opts.downbeat_shift,
                drums=stems_audio.get("drums") if "drums" in active else None,
            )
            cache.save_json("analyze", an_key, analysis.__dict__)
            rep.done("analyze")
        cancel.raise_if_cancelled()

        # 5. quantize -----------------------------------------------------
        rep.start("quantize")
        quantized: dict[str, list[ScoreNote]] = {
            s: quantize(events.get(s, []), analysis.beat_times, analysis.downbeat_index)
            for s in active
        }
        measure = Fraction(analysis.time_signature[0] * 4, analysis.time_signature[1])
        offset = common_start(list(quantized.values()), measure)
        quantized = {s: shift(n, offset) for s, n in quantized.items()}
        rep.done("quantize")

        # 6. transpose + arrange ------------------------------------------
        rep.start("arrange")
        semitones = opts.transpose
        if opts.target_key:
            semitones = interval_to(parse_key(analysis.key), parse_key(opts.target_key))
        key = str(transpose_key(parse_key(analysis.key), semitones)) if semitones else analysis.key
        arrange_opts = ArrangeOptions(
            guitar_tuning=opts.guitar_tuning,
            bass_tuning=opts.bass_tuning,
            tab_weights=TabWeights.from_dict(opts.tab_weights),
        )
        parts: list[Part] = []
        for s in active:
            notes = quantized[s] if s == "drums" else transpose_notes(quantized[s], semitones)
            arranged = arrange_part(s, notes, arrange_opts)
            for p in arranged:
                warnings.extend(p.warnings)
            parts.extend(arranged)
        score = Score(title, analysis.tempo_bpm, analysis.time_signature, key, parts)
        rep.done("arrange")
        cancel.raise_if_cancelled()

        # 7. engrave ------------------------------------------------------
        rep.start("engrave")
        out_dir.mkdir(parents=True, exist_ok=True)
        tr = translator(opts.pdf_language)
        names = {s: tr.gettext(INSTRUMENT_NAMES[s]) for s in STEMS}
        info_line = tr.gettext(INFO_LINE).format(
            bpm=round(score.tempo_bpm), key=key_label(score.key, tr.gettext)
        )
        eopts = EngraveOptions(
            paper=opts.paper, tab_mode=opts.tab_mode, instrument_names=names, info_line=info_line
        )
        jobs: list[tuple[str | None, Path]] = []
        base_name = safe_filename(title)
        if opts.per_stem_pdfs:
            jobs.extend(
                (s, out_dir / f"{base_name} - {safe_filename(names[s])}.pdf") for s in active
            )
        # A combined PDF of a single instrument would duplicate the per-instrument file.
        if opts.combined_pdf and (len(active) > 1 or not opts.per_stem_pdfs):
            jobs.append((None, out_dir / f"{base_name}.pdf"))
        pdfs: dict[str, Path] = {}
        combined: Path | None = None
        engraver = self.engraver() if jobs and active else None
        for i, (job_stem, target) in enumerate(jobs):
            cancel.raise_if_cancelled()
            label = names[job_stem] if job_stem else title
            rep.update(
                "engrave",
                i / len(jobs),
                ENGRAVE_STEM,
                instrument=label,
                index=i + 1,
                count=len(jobs),
            )
            assert engraver is not None
            if job_stem is None:
                ly = render_ly(score, active, eopts, combined=True)
            else:
                ly = render_ly(score, [job_stem], eopts)
            engraver.engrave(ly, target, cancel=cancel)
            if job_stem is None:
                combined = target
            else:
                pdfs[job_stem] = target
        rep.done("engrave")

        # 8. export -------------------------------------------------------
        rep.start("export")
        others: list[Path] = []
        if opts.export_midi or opts.export_musicxml:
            from notirua.core import export

            if opts.export_midi:
                others.append(export.write_midi(score, out_dir / f"{base_name}.mid"))
            if opts.export_musicxml:
                others.append(
                    export.write_musicxml(score, out_dir / f"{base_name}.musicxml", names)
                )
        rep.done("export")
        cache.enforce_limit()

        return JobResult(
            title=title,
            score=score,
            pdfs=pdfs,
            combined_pdf=combined,
            other_files=others,
            skipped=skipped,
            warnings=sorted(set(warnings)),
            elapsed_s=time.monotonic() - started,
        )

    def export_stem_audio(self, input_path: Path, stem: str, target: Path) -> Path:
        """Write one separated stem as WAV from the cache (FR-2)."""
        from notirua.core.decode import write_wav

        cache = cache_mod.StageCache(self.cache_root, cache_mod.file_hash(input_path))
        for item in sorted(
            cache.dir.glob(f"separate-*-{stem}.npy"), key=lambda p: p.stat().st_mtime
        ):
            audio: AudioArray = np.load(item).astype(np.float32)
            write_wav(target, audio)
            return target
        raise FileNotFoundError(stem)
