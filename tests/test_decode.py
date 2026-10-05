from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from notirua.core.decode import SAMPLE_RATE, decode, probe
from notirua.core.errors import CorruptFileError, NoAudioTrackError, TooLongError
from tests import synth


@pytest.fixture(scope="module")
def audio() -> np.ndarray:
    return synth.to_stereo(synth.render_notes(synth.scale_notes(), total_s=5.0))


@pytest.mark.parametrize("kind", ["m4a", "alac.m4a", "mp4", "mp3", "flac", "opus", "aiff"])
def test_formats_decode_to_standard_layout(tmp_path: Path, audio: np.ndarray, kind: str) -> None:
    path = synth.encode(tmp_path / f"곡 이름 🎵.{kind}", audio, kind, title="봄날")
    info = probe(path)
    out = decode(path)
    assert out.dtype == np.float32
    assert out.shape[0] == 2
    assert abs(out.shape[1] / SAMPLE_RATE - 5.0) < 0.2
    if kind != "opus":
        assert info.title == "봄날"


def test_wav_with_unicode_path(tmp_path: Path, audio: np.ndarray) -> None:
    path = synth.write_wav(tmp_path / "日本語 フォルダ" / "Ёжик song.wav", audio)
    out = decode(path)
    assert np.allclose(out[:, :1000], audio[:, :1000], atol=1e-3)


def test_extension_is_ignored(tmp_path: Path, audio: np.ndarray) -> None:
    path = synth.encode(tmp_path / "really_flac.mp3", audio, "flac")
    assert probe(path).streams[0].codec == "flac"


def test_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "broken.m4a"
    path.write_bytes(b"\x00garbage" * 200)
    with pytest.raises(CorruptFileError):
        decode(path)


def test_video_without_audio(tmp_path: Path) -> None:
    import av

    path = tmp_path / "silent.mp4"
    with av.open(str(path), "w") as container:
        stream = container.add_stream("mpeg4", rate=10)
        stream.width, stream.height, stream.pix_fmt = 32, 32, "yuv420p"
        for _ in range(5):
            frame = av.VideoFrame.from_ndarray(np.zeros((32, 32, 3), np.uint8), format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    with pytest.raises(NoAudioTrackError):
        decode(path)


def test_length_limit_and_section(tmp_path: Path, audio: np.ndarray) -> None:
    path = synth.write_wav(tmp_path / "a.wav", audio)
    with pytest.raises(TooLongError):
        decode(path, max_duration_s=2.0)
    part = decode(path, start_s=1.0, end_s=2.5, max_duration_s=2.0)
    assert part.shape[1] == round(1.5 * SAMPLE_RATE)
    assert np.allclose(part[:, :500], audio[:, SAMPLE_RATE : SAMPLE_RATE + 500], atol=1e-3)
