"""Pack the PNGs drawn by make_icon.py into .icns (macOS) and .ico (Windows).

Both formats can hold PNG data as is, so no image library is needed.
Usage: python packaging/icons.py OUT_DIR
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ICONS = Path(__file__).resolve().parents[1] / "src" / "notirua" / "resources" / "icons"

# icns element types that store PNG data, by pixel size (Apple "icns" format).
ICNS_TYPES = (
    (b"icp4", 16),
    (b"icp5", 32),
    (b"icp6", 64),
    (b"ic07", 128),
    (b"ic08", 256),
    (b"ic09", 512),
    (b"ic10", 1024),
    (b"ic11", 32),  # 16@2x
    (b"ic12", 64),  # 32@2x
    (b"ic13", 256),  # 128@2x
    (b"ic14", 512),  # 256@2x
)
ICO_SIZES = (16, 32, 48, 64, 128, 256)


def _png(size: int) -> bytes:
    return (ICONS / f"notirua-{size}.png").read_bytes()


def icns() -> bytes:
    body = b"".join(
        kind + struct.pack(">I", 8 + len(data)) + data
        for kind, data in ((kind, _png(size)) for kind, size in ICNS_TYPES)
    )
    return b"icns" + struct.pack(">I", 8 + len(body)) + body


def ico() -> bytes:
    images = [_png(size) for size in ICO_SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = b""
    for size, data in zip(ICO_SIZES, images, strict=True):
        dim = 0 if size >= 256 else size  # 0 means 256
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return header + entries + b"".join(images)


def write(out: Path) -> tuple[Path, Path]:
    out.mkdir(parents=True, exist_ok=True)
    mac, win = out / "notirua.icns", out / "notirua.ico"
    mac.write_bytes(icns())
    win.write_bytes(ico())
    return mac, win


if __name__ == "__main__":
    for path in write(Path(sys.argv[1])):
        print(path)
