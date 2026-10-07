"""The version is written once (pyproject.toml); every copy must agree with it."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))

import check_bundle  # noqa: E402
import versioning  # noqa: E402


def test_installed_metadata_matches_pyproject() -> None:
    import notirua

    assert notirua.__version__ == versioning.project_version(), "run `uv sync` after a bump"


def test_lock_file_matches_pyproject() -> None:
    assert versioning.lock_version() == versioning.project_version(), "run `uv lock` after a bump"


def test_readme_states_the_current_version() -> None:
    version = versioning.project_version()
    found = versioning.readme_versions(versioning.README.read_text(encoding="utf-8"))
    for pattern, versions in zip(versioning.README_PATTERNS, found, strict=True):
        assert versions, f"README no longer matches {pattern.pattern!r}"
        assert set(versions) == {version}, (
            f"README says {sorted(set(versions))} for {pattern.pattern!r}; "
            "run scripts/bump_version.py"
        )


def test_sync_readme_rewrites_only_current_version_sentences() -> None:
    text = "현재 버전은 **0.1.0**이며\n`Notirua 0.1.0`\n# notirua 0.1.0\n[0.1.0 file](x/v0.1.0/f)"
    out = versioning.sync_readme(text, "0.2.0")
    assert (
        out
        == "현재 버전은 **0.2.0**이며\n`Notirua 0.2.0`\n# notirua 0.2.0\n[0.1.0 file](x/v0.1.0/f)"
    )


def test_release_notes_have_no_placeholder_or_invisible_separator() -> None:
    notes = versioning.render_notes("9.9.9")
    assert "{{version}}" not in notes
    assert "⁣" not in notes
    assert "Notirua-9.9.9-windows-x64-setup.exe" in notes


def test_tag_check(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    version = versioning.project_version()
    monkeypatch.setattr(sys, "argv", ["versioning", "--tag", f"v{version}"])
    assert versioning.main() == 0
    monkeypatch.setattr(sys, "argv", ["versioning", "--tag", "v0.0.1"])
    assert versioning.main() == 1
    assert "does not match" in capsys.readouterr().err


def test_bundle_metadata_version_check(tmp_path: Path) -> None:
    (tmp_path / "notirua-0.4.0.dist-info").mkdir()
    assert check_bundle.metadata_problems(tmp_path, "0.4.1")
    assert not check_bundle.metadata_problems(tmp_path, "0.4.0")
    (tmp_path / "notirua-0.4.1.dist-info").mkdir()
    assert check_bundle.metadata_problems(tmp_path, "0.4.1"), "two copies must fail"
    assert check_bundle.metadata_problems(tmp_path / "none", "0.4.1")
