"""Mixing chosen instruments into one audio file (0.4.0): sums, clipping, names,
encoding round trips, the pipeline call, and `notirua mix`."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pytest

from notirua import cli
from notirua.core import mix
from notirua.core.decode import SAMPLE_RATE, decode
from notirua.core.model import STEMS
from notirua.core.pipeline import INSTRUMENT_NAMES, Engines, JobOptions, Pipeline
from notirua.core.progress import CancelToken, ProgressEvent
from notirua.i18n import translator
from tests import synth
from tests.test_pipeline import Counter, FakeDrums, FakeEngraver, FakeSeparator, FakeTranscriber


def tone(freq: float, amp: float, seconds: float = 1.0) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    wave = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([wave, wave])


def stems_of(amp: float = 0.1) -> dict[str, np.ndarray]:
    return {s: tone(110.0 * (i + 1), amp) for i, s in enumerate(STEMS)}


# -- mix_stems -------------------------------------------------------------------
def test_mix_is_the_sum_of_the_chosen_instruments() -> None:
    stems = stems_of()
    out = mix.mix_stems(stems, {"bass", "piano"})
    assert out.shape == (2, SAMPLE_RATE)
    assert out.dtype == np.float32
    np.testing.assert_allclose(out, stems["bass"] + stems["piano"], atol=1e-6)


def test_all_instruments_give_back_the_whole_song() -> None:
    stems = stems_of()
    total = sum(stems.values())
    np.testing.assert_allclose(mix.mix_stems(stems, STEMS), total, atol=1e-6)


def test_loud_mix_is_turned_down_to_minus_1_dbfs() -> None:
    stems = stems_of(amp=0.5)
    out = mix.mix_stems(stems, STEMS)
    peak = float(np.max(np.abs(out)))
    assert peak == pytest.approx(mix.PEAK_LIMIT, rel=1e-5)
    assert 20 * np.log10(peak) == pytest.approx(-1.0, abs=1e-4)
    # The balance between instruments stays the same.
    unscaled = sum(stems.values())
    ratio = out / np.where(unscaled == 0, 1, unscaled)
    assert np.allclose(ratio[np.abs(unscaled) > 0.1], ratio[np.abs(unscaled) > 0.1].flat[0])


def test_quiet_mix_is_not_made_louder() -> None:
    stems = stems_of(amp=0.05)
    np.testing.assert_allclose(mix.mix_stems(stems, {"drums"}), stems["drums"])


def test_empty_or_unknown_choice_is_an_error() -> None:
    with pytest.raises(ValueError):
        mix.mix_stems(stems_of(), set())
    with pytest.raises(ValueError):
        mix.mix_stems(stems_of(), {"kazoo"})
    with pytest.raises(ValueError):
        mix.mix_stems({"bass": tone(55, 0.1)}, {"piano"})


def test_shorter_tracks_are_padded() -> None:
    stems = {"bass": tone(55, 0.1, 1.0), "piano": tone(440, 0.1, 0.5)}
    assert mix.mix_stems(stems, {"bass", "piano"}).shape == (2, SAMPLE_RATE)


# -- file names ------------------------------------------------------------------
@pytest.mark.parametrize(
    ("include", "available", "en", "ko"),
    [
        (set(STEMS) - {"vocals"}, STEMS, "Song - backing track", "Song - MR"),
        (set(STEMS), STEMS, "Song - all instruments", "Song - 모든 악기"),
        (
            set(STEMS) - {"vocals", "guitar"},
            STEMS,
            "Song - without Vocals, Guitar",
            "Song - 보컬, 기타 제외",
        ),
        ({"guitar", "bass"}, STEMS, "Song - Bass, Guitar", "Song - 베이스, 기타"),
        ({"drums"}, STEMS, "Song - Drums", "Song - 드럼"),
        # Silent instruments do not count as left out.
        ({"drums", "bass", "piano"}, ["drums", "bass", "piano", "vocals"], "Song - backing track",
         "Song - MR"),
    ],
)  # fmt: skip
def test_file_names_say_what_the_mix_holds(
    include: set[str], available: list[str], en: str, ko: str
) -> None:
    for lang, expected in (("en", en), ("ko", ko)):
        gettext = translator(lang).gettext
        assert mix.mix_name("Song", include, available, gettext, INSTRUMENT_NAMES) == expected


# -- encoding ----------------------------------------------------------------------
@pytest.mark.parametrize("fmt", ["wav", "m4a", "mp3"])
def test_encoding_round_trip(tmp_path: Path, fmt: str) -> None:
    if fmt not in mix.available_formats():
        pytest.skip(f"{fmt} encoder not in this FFmpeg")
    audio = tone(440.0, 0.3, seconds=2.0)
    seen: list[float] = []
    path = mix.write_audio(tmp_path / f"out{mix.FORMATS[fmt][0]}", audio, fmt, seen.append)
    assert path.is_file() and seen[-1] == 1.0
    assert not list(tmp_path.glob(".*.part"))
    back = decode(path)
    assert back.shape[0] == 2
    # Encoders add a little padding; the length stays within 0.1 s.
    assert abs(back.shape[1] - audio.shape[1]) < SAMPLE_RATE * 0.1
    level = float(np.sqrt(np.mean(back**2)))
    assert level == pytest.approx(0.3 / np.sqrt(2), rel=0.1)


def test_mp3_is_320_kbps(tmp_path: Path) -> None:
    if "mp3" not in mix.available_formats():
        pytest.skip("mp3 encoder not in this FFmpeg")
    import av

    path = mix.write_audio(tmp_path / "out.mp3", tone(440, 0.3, 3.0), "mp3")
    with av.open(str(path)) as f:
        stream = f.streams.audio[0]
        assert stream.codec_context.name.startswith("mp3")
        assert stream.sample_rate == SAMPLE_RATE and stream.channels == 2
        assert stream.bit_rate == 320_000


def test_cancel_stops_encoding_and_leaves_no_file(tmp_path: Path) -> None:
    token = CancelToken()
    token.cancel()
    from notirua.core.errors import Cancelled

    with pytest.raises(Cancelled):
        mix.write_audio(tmp_path / "out.m4a", tone(440, 0.3), "m4a", cancel=token)
    assert list(tmp_path.iterdir()) == []


def test_list_pattern() -> None:
    gettext = translator("en").gettext
    assert mix.join_names([], gettext) == ""
    assert mix.join_names(["A"], gettext) == "A"
    assert mix.join_names(["A", "B", "C"], gettext) == "A, B, C"


# -- pipeline ----------------------------------------------------------------------
@pytest.fixture
def song(tmp_path: Path) -> Path:
    audio = synth.to_stereo(synth.render_notes(synth.scale_notes(120), total_s=4.0))
    return synth.write_wav(tmp_path / "song.wav", audio)


def fake_pipeline(tmp_path: Path, counter: Counter) -> Pipeline:
    engines = Engines(
        separator=lambda: FakeSeparator(counter),
        pitched=lambda: FakeTranscriber(counter),
        drums=FakeDrums,
        engraver=lambda: FakeEngraver(counter),
    )
    return Pipeline(engines, cache_root=tmp_path / "cache")


def test_export_mix_separates_once_and_never_transcribes(tmp_path: Path, song: Path) -> None:
    counter = Counter()
    pipeline = fake_pipeline(tmp_path, counter)
    events: list[ProgressEvent] = []
    result = pipeline.export_mix(song, {"piano"}, tmp_path / "a.wav", "wav", progress=events.append)
    assert result.path.is_file()
    assert counter.separate == 1 and counter.transcribe == 0
    assert result.title == "song"
    # The fake separator gives sound only to piano and guitar.
    assert set(result.silent) == set(STEMS) - {"piano", "guitar"}
    assert events[-1].overall_fraction == pytest.approx(1.0)
    fractions = [e.overall_fraction for e in events]
    assert fractions == sorted(fractions)

    original = decode(song)
    piano = decode(result.path)
    assert piano.shape == original.shape
    assert np.allclose(piano, original, atol=2e-3)  # piano carries the whole fake song

    pipeline.export_mix(song, {"vocals", "drums"}, tmp_path / "b.wav", "wav")
    assert counter.separate == 1  # the second mix reuses the separated instruments
    assert np.max(np.abs(decode(tmp_path / "b.wav"))) < 1e-3


def test_export_mix_after_a_job_reuses_its_range(tmp_path: Path, song: Path) -> None:
    counter = Counter()
    pipeline = fake_pipeline(tmp_path, counter)
    options = JobOptions(start_s=1.0, end_s=3.0)
    pipeline.run(song, tmp_path / "out", options)
    assert counter.separate == 1
    result = pipeline.export_mix(song, {"piano"}, tmp_path / "part.wav", "wav", options)
    assert counter.separate == 1
    assert decode(result.path).shape[1] == pytest.approx(2 * SAMPLE_RATE, abs=2)


# -- command line ------------------------------------------------------------------
class EveryInstrument(FakeSeparator):
    """Every instrument gets a sixth of the song."""

    def separate(self, audio: np.ndarray, *args: object, **kwargs: object) -> dict[str, np.ndarray]:
        self.counter.separate += 1
        return {s: audio / len(STEMS) for s in STEMS}


@pytest.fixture
def cli_ready(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Counter:
    counter = Counter()
    monkeypatch.setattr(argparse, "_", argparse._)  # type: ignore[attr-defined]
    monkeypatch.setattr(argparse, "ngettext", argparse.ngettext)  # type: ignore[attr-defined]

    class NoMissing:
        def missing(self) -> list[object]:
            return []

    monkeypatch.setattr(
        "notirua.components.manager.manager_from_settings", lambda _user=None: NoMissing()
    )
    real = Pipeline.__init__

    def init(self: Pipeline, *args: object, **kwargs: object) -> None:
        real(
            self,
            Engines(
                separator=lambda: EveryInstrument(counter),
                pitched=lambda: FakeTranscriber(counter),
                drums=FakeDrums,
                engraver=lambda: FakeEngraver(counter),
            ),
            cache_root=tmp_path / "cache",
        )

    monkeypatch.setattr(Pipeline, "__init__", init)
    return counter


def test_cli_mix_default_leaves_out_the_vocals(
    cli_ready: Counter, song: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    code = cli.main(
        ["--lang", "en", "mix", str(song), "--out", str(out), "--format", "wav", "--title", "봄날"]
    )
    assert code == cli.EXIT_OK, capsys.readouterr().err
    assert [p.name for p in out.iterdir()] == ["봄날 - backing track.wav"]
    assert cli_ready.transcribe == 0


def test_cli_mix_names_the_kept_instruments(
    cli_ready: Counter, song: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(
        ["--lang", "ko", "mix", str(song), "--out", str(tmp_path), "--stems", "piano,guitar"]
    )
    assert code == cli.EXIT_OK, capsys.readouterr().err
    names = [p.name for p in tmp_path.glob("*.mp3")] if "mp3" in mix.available_formats() else []
    if names:
        assert names == ["song - 기타, 피아노.mp3"]
    assert cli_ready.separate == 1


def test_cli_mix_usage_errors(
    cli_ready: Counter, song: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = ["--out", str(tmp_path / "x")]
    assert cli.main(["--lang", "en", "mix", str(song), *out, "--stems", "kazoo"]) == cli.EXIT_USAGE
    assert "Unknown instrument: kazoo" in capsys.readouterr().err
    assert (
        cli.main(["--lang", "en", "mix", str(song), *out, "--without", ",".join(STEMS)])
        == cli.EXIT_USAGE
    )
    assert "Choose at least one instrument." in capsys.readouterr().err
    assert cli.main(["--lang", "en", "mix", str(song), *out, "--stems", ","]) == cli.EXIT_USAGE
    with pytest.raises(SystemExit) as exc:
        cli.main(["--lang", "en", "mix", str(song), *out, "--stems", "bass", "--without", "vocals"])
    assert exc.value.code == cli.EXIT_USAGE
    assert not (tmp_path / "x").exists()
