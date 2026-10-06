"""End-to-end tests with the real models and LilyPond (SPEC 9.3). Run with ``-m slow``."""

from __future__ import annotations

import re
from fractions import Fraction
from pathlib import Path

import pytest

from notirua.core.model import Score
from notirua.core.pipeline import JobOptions, Pipeline, default_engines
from notirua.settings import Settings
from tests import synth
from tests.conftest import real_components_dir

pytestmark = pytest.mark.slow

COMPONENTS = real_components_dir()
needs_components = pytest.mark.skipif(COMPONENTS is None, reason="run `notirua setup` first")


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> Pipeline:
    assert COMPONENTS is not None
    engines = default_engines(Settings(components_dir=str(COMPONENTS)))
    return Pipeline(engines, cache_root=tmp_path_factory.mktemp("cache"))


def _pdf_text(path: Path) -> tuple[int, list[str]]:
    """Page count and text per page from two extractors joined together.

    pypdf mis-maps glyphs of some fallback fonts (macOS kana); the PDFium in
    Qt 6.9 skips some runs (the footer). Each finds what the other misses.
    """
    from pypdf import PdfReader
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    doc = QPdfDocument()
    assert doc.load(str(path)) == QPdfDocument.Error.None_
    pdfium = [doc.getAllText(i).text() for i in range(doc.pageCount())]
    doc.close()
    pages = PdfReader(str(path)).pages
    assert len(pages) == len(pdfium)
    return len(pdfium), [
        f"{a}\n{b.extract_text() or ''}" for a, b in zip(pdfium, pages, strict=True)
    ]


# Fonts LilyPond brings itself; anything else in a PDF is a system fallback font.
LILYPOND_FONTS = re.compile(r"Emmentaler|C059|DejaVu|Nimbus|TeXGyre|URW")


def _fallback_fonts(pdf: Path) -> set[str]:
    found = re.findall(rb"/BaseFont\s*/(?:[A-Z]{6}\+)?([\w-]+)", pdf.read_bytes())
    return {n.decode() for n in found if not LILYPOND_FONTS.search(n.decode())}


def _assert_drawn(pdf: Path, extracted_ok: bool, text: str) -> None:
    """Non-Latin title text was drawn, not dropped.

    Some fallback fonts (Noto CJK on Linux) are embedded without a usable
    character map, so extraction returns other characters although the page
    renders correctly. When no font has the glyphs, LilyPond drops the text
    silently and embeds no fallback font, so require one in that case.
    """
    if not extracted_ok:
        assert _fallback_fonts(pdf), f"title glyphs missing: {text!r}"


def _matches(score: Score, expected: list[tuple[Fraction, int]]) -> tuple[float, float]:
    """Return (pitch accuracy, worst onset error in beats) across pitched parts."""
    notes = [n for p in score.parts if p.stem != "drums" for n in p.notes]

    def score_offset(base: Fraction) -> tuple[int, Fraction]:
        hits, worst = 0, Fraction(0)
        for onset, pitch in expected:
            cands = [n for n in notes if n.pitch == pitch]
            if not cands:
                continue
            err = min(abs(n.onset - base - onset) for n in cands)
            if err <= Fraction(1, 4):
                hits += 1
                worst = max(worst, err)
        return hits, worst

    # The score may start with a pickup; try every alignment of the first note.
    bases = {n.onset - expected[0][0] for n in notes if n.pitch == expected[0][1]}
    best = max((score_offset(b) for b in bases), key=lambda r: (r[0], -r[1]), default=(0, 0))
    return best[0] / len(expected), float(best[1])


@needs_components
def test_c_major_scale_e2e(pipeline: Pipeline, tmp_path: Path) -> None:
    pitches = [60, 62, 64, 65, 67, 69, 71, 72, 72, 71, 69, 67, 65, 64, 62, 60]
    notes = synth.scale_notes(120, pitches, lead_in_beats=4)
    audio = synth.to_stereo(synth.render_notes(notes, total_s=12.0))
    src = synth.write_wav(tmp_path / "한글 경로 with space" / "C major scale.wav", audio)
    result = pipeline.run(src, tmp_path / "출력 out", JobOptions(title="다장조 음계 Scale"))

    expected = [(Fraction(i), p) for i, p in enumerate(pitches)]
    accuracy, worst = _matches(result.score, expected)
    assert accuracy >= 0.9, accuracy
    assert worst <= 0.25
    assert 110 <= result.score.tempo_bpm <= 130
    assert result.score.key in ("C major", "A minor")

    pdfs = [*result.pdfs.values(), *([result.combined_pdf] if result.combined_pdf else [])]
    assert pdfs
    for pdf in pdfs:
        assert pdf.is_file()
        n_pages, texts = _pdf_text(pdf)
        assert n_pages >= 1
        # Text extraction may reorder runs of different scripts, so check word by word.
        assert "Scale" in texts[0]
        _assert_drawn(pdf, all(w in texts[0] for w in ["다장조", "음계"]), texts[0][:40])
        for i, text in enumerate(texts, start=1):
            assert re.search(rf"{i}\s*/\s*{n_pages}", text), text[-80:]


@needs_components
@pytest.mark.parametrize("title", ["봄날의 기타", "春の歌 テスト", "春天的歌", "Песня Ёжика"])
def test_titles_in_many_scripts_render(pipeline: Pipeline, tmp_path: Path, title: str) -> None:
    audio = synth.to_stereo(synth.render_notes(synth.scale_notes(120), total_s=6.0))
    src = synth.write_wav(tmp_path / "s.wav", audio)
    result = pipeline.run(src, tmp_path / "o", JobOptions(title=title, combined_pdf=False))
    pdf = next(iter(result.pdfs.values()))
    _n, texts = _pdf_text(pdf)
    wanted = title.replace(" ", "")
    first_line = texts[0].splitlines()[0].replace(" ", "")
    # Runs of different scripts may come back reordered; every glyph must be there.
    _assert_drawn(pdf, sorted(first_line) == sorted(wanted), first_line)


@needs_components
def test_snapshot_renders_with_lilypond(tmp_path: Path) -> None:
    from notirua.components.manager import ComponentManager
    from notirua.core.engrave.render import LilyPondEngraver

    assert COMPONENTS is not None
    engraver = LilyPondEngraver(ComponentManager(COMPONENTS).require("lilypond"))
    source = (Path(__file__).parent / "snapshots" / "demo_score.ly").read_text(encoding="utf-8")
    out = engraver.engrave(source, tmp_path / "스냅샷.pdf")
    assert out.stat().st_size > 1000


@needs_components
def test_injection_title_does_not_execute(tmp_path: Path) -> None:
    from notirua.components.manager import ComponentManager
    from notirua.core.engrave.lilypond import EngraveOptions, render_ly
    from notirua.core.engrave.render import LilyPondEngraver
    from notirua.core.model import Part, ScoreNote

    assert COMPONENTS is not None
    marker = tmp_path / "pwned"
    evil = f'"}} #(system "touch {marker}") \\header {{ title = "'
    score = Score(
        evil, 120, (4, 4), "C major", [Part("vocals", [ScoreNote(Fraction(0), Fraction(1), 60)])]
    )
    engraver = LilyPondEngraver(ComponentManager(COMPONENTS).require("lilypond"))
    engraver.engrave(render_ly(score, ["vocals"], EngraveOptions()), tmp_path / "x.pdf")
    assert not marker.exists()
