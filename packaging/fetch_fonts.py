"""Download the pinned Noto Sans CJK fonts bundled with the Linux build (DECISIONS D8).

Usage: uv run python packaging/fetch_fonts.py [--out packaging/fonts]

Linux distributions do not always ship CJK fonts, and LilyPond silently drops
glyphs it cannot find. The Korean regional OTFs cover Hangul, kana, and all CJK
ideographs. Files are pinned by URL, size, and SHA-256 and are not committed;
the license travels in ``licenses/noto-cjk/LICENSE`` (OFL-1.1).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from notirua.components.download import download

_BASE = "https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/OTF/Korean/"


@dataclass(frozen=True)
class FontFile:
    name: str
    size: int
    sha256: str

    @property
    def url(self) -> str:
        return _BASE + self.name


FONTS = (
    FontFile(
        "NotoSansCJKkr-Regular.otf",
        16_433_112,
        "6bcb2a0703aa137e874fc2dffa85f6c21ba9a67fa329e81b8c801663af7e992a",
    ),
    FontFile(
        "NotoSansCJKkr-Bold.otf",
        16_997_996,
        "26d0c6748500a0444844280b308f5b62c7ae92ac6c6ac88148e502dd211eb52a",
    ),
)
DEFAULT_OUT = Path(__file__).resolve().parent / "fonts"


def fetch(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for font in FONTS:
        target = out / font.name
        if not target.is_file() or target.stat().st_size != font.size:
            download(font.url, target, expected_size=font.size, sha256=font.sha256)
        paths.append(target)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    for path in fetch(args.out):
        print(path)


if __name__ == "__main__":
    main()
