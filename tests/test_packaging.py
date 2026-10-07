"""Packaging helpers that run without building a bundle (M6)."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))

import check_bundle  # noqa: E402
import icons  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n"


def test_icns_holds_every_png_size() -> None:
    data = icons.icns()
    assert data[:4] == b"icns"
    assert struct.unpack(">I", data[4:8])[0] == len(data)
    kinds = []
    pos = 8
    while pos < len(data):
        kind, length = data[pos : pos + 4], struct.unpack(">I", data[pos + 4 : pos + 8])[0]
        assert data[pos + 8 : pos + 16] == PNG
        kinds.append(kind)
        pos += length
    assert pos == len(data)
    assert kinds == [kind for kind, _size in icons.ICNS_TYPES]


def test_ico_entries_point_at_pngs() -> None:
    data = icons.ico()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind, count) == (0, 1, len(icons.ICO_SIZES))
    for i, size in enumerate(icons.ICO_SIZES):
        w, h, _c, _r, _p, _b, length, offset = struct.unpack(
            "<BBBBHHII", data[6 + 16 * i : 22 + 16 * i]
        )
        assert w == h == (0 if size >= 256 else size)
        assert data[offset : offset + 8] == PNG
        assert offset + length <= len(data)


def test_gpl_ffmpeg_strings_are_recognized() -> None:
    gpl = b"... FFmpeg configuration: --enable-gpl --enable-libx264 ... GPL version 2 or later"
    assert check_bundle.GPL_FFMPEG.search(gpl)
    assert not check_bundle.GPL_FFMPEG.search(b"--disable-everything LGPL version 2.1 or later")


def test_ffmpeg_libraries_are_recognized() -> None:
    for name in ("libavcodec.62.dylib", "libavutil-60.so.60", "avformat-62.dll"):
        assert check_bundle.is_ffmpeg(Path(name))
    assert not check_bundle.is_ffmpeg(Path("libavcodec.txt"))
    assert not check_bundle.is_ffmpeg(Path("QtCore.dll"))


def test_unused_qt_modules_are_recognized_on_every_platform() -> None:
    for name in ("QtQuick", "libQt6Quick.so.6", "Qt6Qml.dll", "libQt6VirtualKeyboard.so.6"):
        assert check_bundle.FORBIDDEN_QT.search(name), name
    for name in ("QtPdf", "libQt6PdfWidgets.so.6", "Qt6Widgets.dll", "libQt6XcbQpa.so.6"):
        assert not check_bundle.FORBIDDEN_QT.search(name), name


def test_installer_clears_the_old_program_folder() -> None:
    """Installing over an older version must not leave its files (notirua-<old>.dist-info
    would make the app report the old version)."""
    iss = (ROOT / "packaging" / "windows" / "notirua.iss").read_text(encoding="utf-8")
    assert "[InstallDelete]" in iss
    assert 'Name: "{app}\\_internal"' in iss
    assert "Type: filesandordirs" in iss


def test_find_av_wheel_accepts_a_universal2_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CI's python.org Python makes ``universal2`` wheels; an arm64 one still wins."""
    import build_app

    folder = tmp_path / "dist" / "lgpl-av"
    folder.mkdir(parents=True)
    monkeypatch.setattr(build_app, "ROOT", tmp_path)
    monkeypatch.setattr(build_app.sys, "platform", "darwin")
    monkeypatch.setattr(build_app.platform, "machine", lambda: "arm64")
    with pytest.raises(SystemExit):
        build_app.find_av_wheel()
    universal = folder / "av-18.1.0-cp311-abi3-macosx_14_0_universal2.whl"
    universal.write_bytes(b"x")
    assert build_app.find_av_wheel() == universal
    arm = folder / "av-18.1.0-cp311-abi3-macosx_14_0_arm64.whl"
    arm.write_bytes(b"x")
    assert build_app.find_av_wheel() == arm
