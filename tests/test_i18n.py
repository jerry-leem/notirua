"""i18n checks (SPEC 6.7, 9.4)."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest
from babel.messages.pofile import read_po

from notirua import i18n

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "locales"
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def test_fallback_chain() -> None:
    assert i18n.fallback_chain("pt_BR.UTF-8") == ["pt_BR", "pt"]
    assert i18n.fallback_chain("ko-KR") == ["ko_KR", "ko"]


def test_resolve_order_user_then_os_then_english() -> None:
    assert i18n.resolve_language("ko", "en_US") == "ko"
    assert i18n.resolve_language(None, "ko_KR.UTF-8") == "ko"
    assert i18n.resolve_language("xx", "yy_ZZ") == "en"


def test_switching_language_changes_strings() -> None:
    assert i18n.set_language("ko_KR") == "ko"
    assert i18n._("Piano") == "피아노"
    i18n.set_language("en")
    assert i18n._("Piano") == "Piano"


def test_new_language_needs_only_a_po_file(tmp_path: Path) -> None:
    """Dropping a .po (no .mo, no code) adds a working language (FR-9)."""
    import shutil

    shutil.copytree(LOCALES, tmp_path / "locales")
    ja = tmp_path / "locales" / "ja" / "LC_MESSAGES"
    ja.mkdir(parents=True)
    (ja / "notirua.po").write_text(
        'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
        'msgid "Piano"\nmsgstr "ピアノ"\n',
        encoding="utf-8",
    )
    i18n.set_locales_dir(tmp_path / "locales")
    assert "ja" in i18n.available_languages()
    assert i18n.set_language("ja_JP") == "ja"
    assert i18n._("Piano") == "ピアノ"
    assert i18n._("Guitar") == "Guitar"  # untranslated falls back to English


def _catalogs() -> list[Path]:
    return sorted(LOCALES.glob("*/LC_MESSAGES/notirua.po"))


@pytest.mark.parametrize("po", _catalogs(), ids=lambda p: p.parts[-3])
def test_placeholders_match_source(po: Path) -> None:
    with po.open("rb") as fp:
        catalog = read_po(fp)
    for m in catalog:
        if not m.id or not m.string:
            continue
        ids = m.id if isinstance(m.id, tuple) else (m.id,)
        strings = m.string if isinstance(m.string, tuple) else (m.string,)
        expected = set(PLACEHOLDER.findall(ids[0]))
        for s in strings:
            if s:
                assert set(PLACEHOLDER.findall(s)) == expected, m.id


@pytest.mark.parametrize("po", _catalogs(), ids=lambda p: p.parts[-3])
def test_catalog_compiles(po: Path, tmp_path: Path) -> None:
    from babel.messages.mofile import write_mo

    with po.open("rb") as fp:
        catalog = read_po(fp)
    with (tmp_path / "x.mo").open("wb") as fp:
        write_mo(fp, catalog)


def test_korean_is_complete() -> None:
    with (LOCALES / "ko" / "LC_MESSAGES" / "notirua.po").open("rb") as fp:
        catalog = read_po(fp)
    missing = [m.id for m in catalog if m.id and (not m.string or m.fuzzy)]
    assert not missing


def test_template_is_up_to_date(tmp_path: Path) -> None:
    out = tmp_path / "fresh.pot"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "babel.messages.frontend",
            "-q",
            "extract",
            "-F",
            "babel.cfg",
            "-k",
            "_",
            "-k",
            "N_",
            "-k",
            "ngettext:1,2",
            "-k",
            "pgettext:1c,2",
            "--no-location",
            "--sort-output",
            "-o",
            str(out),
            ".",
        ],
        cwd=ROOT,
        check=True,
    )

    def ids(path: Path) -> set[object]:
        with path.open("rb") as fp:
            return {m.id for m in read_po(fp) if m.id}

    assert ids(out) == ids(LOCALES / "notirua.pot"), "run the pybabel extract command in AGENTS.md"


USER_FACING_CALLS = {"print", "add_argument", "add_parser", "ArgumentParser", "input"}
USER_FACING_KWARGS = {"help", "description", "metavar"}


def _literal_strings(node: ast.AST) -> list[ast.Constant]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node]
    if isinstance(node, ast.JoinedStr):
        return [v for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)]
    if isinstance(node, ast.BinOp):
        return _literal_strings(node.left) + _literal_strings(node.right)
    return []


def test_no_unwrapped_user_strings_in_interfaces() -> None:
    """User-visible text in the CLI/GUI must go through gettext (SPEC 9.4)."""
    offenders = []
    files = [
        ROOT / "src" / "notirua" / "cli.py",
        *sorted((ROOT / "src" / "notirua" / "gui").rglob("*.py")),
    ]
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in USER_FACING_CALLS:
                continue
            candidates = list(node.args) if name in ("print", "input") else []
            candidates += [k.value for k in node.keywords if k.arg in USER_FACING_KWARGS]
            for arg in candidates:
                for const in _literal_strings(arg):
                    text = const.value.strip()
                    if re.search(r"[A-Za-z]{3,}", text) and not text.startswith("-"):
                        offenders.append(f"{path.name}:{const.lineno}: {text!r}")
    assert not offenders, offenders


def test_ui_wording_avoids_jargon() -> None:
    """Screen text must not use the banned terms in docs/ui/wording.md (SPEC 9.5)."""
    wording = (ROOT / "docs" / "ui" / "wording.md").read_text(encoding="utf-8")
    banned = re.findall(r"^- `([^`]+)`", wording, flags=re.M)
    assert banned
    with (LOCALES / "notirua.pot").open("rb") as fp:
        template = read_po(fp)
    exempt = re.compile(r"MIDI|MusicXML|LilyPond|--\w+|five_string|drop_d|half_down|notirua \w+")
    hits = []
    for m in template:
        texts = m.id if isinstance(m.id, tuple) else (m.id,)
        for text in texts:
            cleaned = exempt.sub("", text or "")
            for term in banned:
                if re.search(rf"\b{re.escape(term)}\b", cleaned, flags=re.I):
                    hits.append((term, text))
    assert not hits, hits
