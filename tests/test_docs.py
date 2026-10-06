"""Documentation checks: Markdown that renders as intended on GitHub (CommonMark)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]


def _markdown_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [ROOT / name for name in listed]


def test_bold_and_italic_markers_render() -> None:
    """A ``**`` left in the rendered text means the emphasis did not apply.

    Typical cause in Korean: ``**설정…**을`` — a closing ``**`` after punctuation
    and directly before a letter is not a closing marker in CommonMark. Write
    ``**설정…** 메뉴를`` or move the punctuation outside instead.
    """
    md = MarkdownIt("commonmark").enable("table")
    broken = []
    for path in _markdown_files():
        for token in md.parse(path.read_text(encoding="utf-8")):
            if token.type != "inline" or token.map is None:
                continue
            for child in token.children or []:
                if child.type == "text" and ("**" in child.content or "__" in child.content):
                    line = token.map[0] + 1
                    broken.append(f"{path.relative_to(ROOT)}:{line}: {child.content.strip()[:50]}")
    assert not broken, "\n".join(broken)
