"""The optional JavaScript runtime (Deno) for YouTube links."""

from __future__ import annotations

import hashlib
import io
import sys
import zipfile
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from notirua.components import manifest
from notirua.components.manager import ComponentManager, OptionalComponentManager
from notirua.core.errors import ComponentMissingError, ConsentRequiredError
from notirua.settings import Settings
from tests.component_fakes import Handler, serve


@pytest.fixture
def server() -> Iterator[str]:
    yield from serve()


def test_manifest_pins_deno_for_every_platform() -> None:
    deno = manifest.JS_RUNTIME
    assert deno.required is False
    assert deno.license_id == "MIT"
    for key in ("windows-x86_64", "darwin-arm64", "darwin-x86_64", "linux-x86_64"):
        f = deno.files[key]
        assert len(f.sha256) == 64 and f.size > 1_000_000
        assert f.url.startswith("https://github.com/denoland/deno/releases/download/v")
        assert f.url.endswith(".zip") and f.archive == "zip"
        assert manifest._DENO_VERSION in f.url
    assert manifest.by_id("deno") is deno


def test_deno_is_not_part_of_the_first_run_setup() -> None:
    assert manifest.JS_RUNTIME not in manifest.COMPONENTS
    assert [c.id for c in manifest.components_for_platform("windows-x86_64")] == [
        "htdemucs_6s",
        "lilypond",
    ]
    required = ComponentManager(Path("."), "windows-x86_64")
    assert [c.id for c in required.components] == ["htdemucs_6s", "lilypond"]
    optional = OptionalComponentManager(Path("."), "windows-x86_64")
    assert [c.id for c in optional.components] == ["deno"]


def test_required_consent_does_not_need_deno() -> None:
    manager = ComponentManager(Path("."), "windows-x86_64")
    record = manager.make_consent(manager.components)
    assert manager.consent_is_current(record, manager.components)
    assert "deno" not in record.components


def _fake_deno(base: str) -> tuple[manifest.Component, dict[str, bytes]]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("deno", b"#!/bin/sh\necho deno 2.9.7\n")
    archive = buf.getvalue()
    deno = replace(
        manifest.JS_RUNTIME,
        installed_size=1000,
        files={
            "any": manifest.ComponentFile(
                f"{base}/deno.zip",
                hashlib.sha256(archive).hexdigest(),
                len(archive),
                "zip",
                "deno.zip",
            )
        },
    )
    return deno, {"/deno.zip": archive}


def test_install_after_consent(tmp_path: Path, server: str) -> None:
    deno, files = _fake_deno(server)
    Handler.files.update(files)
    manager = OptionalComponentManager(tmp_path, "linux-x86_64")
    manager.components = [deno]
    assert [c.id for c in manager.missing(required_only=False)] == ["deno"]
    with pytest.raises(ComponentMissingError):
        manager.require("deno")
    with pytest.raises(ConsentRequiredError):  # no consent record: nothing is downloaded
        manager.install([deno], consent=None)  # type: ignore[arg-type]
    manager.install([deno], manager.make_consent([deno]))
    entry = manager.require("deno")
    assert entry == tmp_path / "deno" / "deno"
    assert entry.read_bytes().startswith(b"#!/bin/sh")
    if sys.platform != "win32":  # Windows has no execute bit
        assert entry.stat().st_mode & 0o111  # executable on Linux and macOS
    assert manager.missing(required_only=False) == []


def test_state_file_keeps_required_components(tmp_path: Path, server: str) -> None:
    """Installing Deno must not forget the model and LilyPond (they share one state file)."""
    deno, files = _fake_deno(server)
    Handler.files.update(files)
    required = ComponentManager(tmp_path, "linux-x86_64")
    required._write_state({"htdemucs_6s": "x", "lilypond": "y"})
    manager = OptionalComponentManager(tmp_path, "linux-x86_64")
    manager.components = [deno]
    manager.install([deno], manager.make_consent([deno]))
    assert required._read_state() == {"htdemucs_6s": "x", "lilypond": "y", "deno": deno.version}
    manager.remove(deno)
    assert required._read_state() == {"htdemucs_6s": "x", "lilypond": "y"}


def test_settings_unchanged_by_the_optional_component() -> None:
    assert not hasattr(Settings(), "optional_consent")
