from __future__ import annotations

import hashlib
import http.server
import io
import socket
import tarfile
import threading
import zipfile
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import ClassVar

import pytest

from notirua import settings as settings_mod
from notirua.components import manager as manager_mod
from notirua.components import manifest
from notirua.components.download import download
from notirua.components.manager import ComponentManager
from notirua.core.errors import (
    ChecksumMismatchError,
    ConsentRequiredError,
    DiskSpaceError,
    DownloadError,
)

PAYLOAD = b"notirua-model-bytes" * 5000


class _Handler(http.server.BaseHTTPRequestHandler):
    files: ClassVar[dict[str, bytes]] = {}
    fail_after: ClassVar[int | None] = None

    def do_GET(self) -> None:
        data = self.files.get(self.path)
        if data is None:
            self.send_error(404)
            return
        start = 0
        rng = self.headers.get("Range")
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        else:
            self.send_response(200)
        body = data[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.fail_after is not None and not rng:
            self.wfile.write(body[: self.fail_after])
            self.wfile.flush()
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture
def server() -> Iterator[str]:
    _Handler.files = {}
    _Handler.fail_after = None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _tar_with(entry: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(entry)
        info.size = len(content)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def _fake_components(base: str) -> tuple[manifest.Component, manifest.Component, dict[str, bytes]]:
    archive = _tar_with("tool-1.0/bin/tool", b"#!/bin/sh\necho tool\n")
    files = {"/model.onnx": PAYLOAD, "/tool.tar.gz": archive}
    model = replace(
        manifest.SEPARATION_MODEL,
        id="model",
        installed_size=len(PAYLOAD),
        entry="model.onnx",
        files={
            "any": manifest.ComponentFile(
                f"{base}/model.onnx",
                hashlib.sha256(PAYLOAD).hexdigest(),
                len(PAYLOAD),
                None,
                "model.onnx",
            )
        },
    )
    tool = replace(
        manifest.LILYPOND,
        id="tool",
        installed_size=1000,
        entry="tool-1.0/bin/tool{exe}",
        files={
            "any": manifest.ComponentFile(
                f"{base}/tool.tar.gz",
                hashlib.sha256(archive).hexdigest(),
                len(archive),
                "tar.gz",
                "tool.tar.gz",
            )
        },
    )
    return model, tool, files


def _manager(tmp_path: Path, comps: list[manifest.Component]) -> ComponentManager:
    m = ComponentManager(tmp_path / "components", platform_key="linux-x86_64")
    m.components = comps
    return m


def test_no_network_before_consent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Planning, status, and refused installs never open a socket (SPEC 9.5)."""
    calls: list[object] = []

    def guard(*args: object, **kwargs: object) -> None:
        calls.append(args)
        raise AssertionError("network used before consent")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
    m = ComponentManager(tmp_path / "c")
    settings = settings_mod.load()
    assert m.needs_setup(settings)
    plan = m.plan()
    assert plan.download_bytes > 0
    m.status()
    stale = replace(m.make_consent(m.components), manifest_version=manifest.MANIFEST_VERSION - 1)
    with pytest.raises(ConsentRequiredError):
        m.install(m.components, stale)
    assert calls == []


def test_consent_is_required_again_after_manifest_change(monkeypatch: pytest.MonkeyPatch) -> None:
    comps = list(manifest.COMPONENTS)
    record = ComponentManager.make_consent(comps)
    assert ComponentManager.consent_is_current(record, comps)
    monkeypatch.setattr(manager_mod, "MANIFEST_VERSION", manifest.MANIFEST_VERSION + 1)
    assert not ComponentManager.consent_is_current(record, comps)
    bumped = [replace(comps[0], version="newer"), *comps[1:]]
    monkeypatch.setattr(manager_mod, "MANIFEST_VERSION", manifest.MANIFEST_VERSION)
    assert not ComponentManager.consent_is_current(record, bumped)


def test_consent_round_trips_through_settings() -> None:
    s = settings_mod.load()
    s.consent = ComponentManager.make_consent(list(manifest.COMPONENTS))
    settings_mod.save(s)
    again = settings_mod.load()
    assert again.consent == s.consent


def test_install_and_remove(tmp_path: Path, server: str) -> None:
    model, tool, files = _fake_components(server)
    _Handler.files = files
    m = _manager(tmp_path, [model, tool])
    events: list[object] = []
    m.install([model, tool], m.make_consent([model, tool]), progress=events.append)
    status = {s.component.id: s for s in m.status()}
    assert status["model"].installed and status["tool"].installed
    assert m.require("tool").name == "tool"
    assert not (m.install_dir / ".downloads").exists()
    m.remove(tool)
    assert not {s.component.id: s for s in m.status()}["tool"].installed


def test_resume_after_connection_drop(tmp_path: Path, server: str) -> None:
    model, _tool, files = _fake_components(server)
    _Handler.files = files
    _Handler.fail_after = 10_000
    f = model.files["any"]
    dest = tmp_path / "dl" / "model.onnx"
    with pytest.raises(DownloadError):
        download(f.url, dest, expected_size=f.size, sha256=f.sha256)
    part = dest.with_name("model.onnx.part")
    assert part.is_file() and 0 < part.stat().st_size < f.size
    _Handler.fail_after = None
    download(f.url, dest, expected_size=f.size, sha256=f.sha256)
    assert dest.read_bytes() == PAYLOAD


def test_checksum_mismatch_removes_file(tmp_path: Path, server: str) -> None:
    _Handler.files = {"/x": b"tampered" * 10}
    dest = tmp_path / "x"
    with pytest.raises(ChecksumMismatchError):
        download(f"{server}/x", dest, expected_size=80, sha256="0" * 64)
    assert not dest.exists() and not dest.with_name("x.part").exists()


def test_network_failure_is_reported(tmp_path: Path) -> None:
    with pytest.raises(DownloadError):
        download("http://127.0.0.1:9/none", tmp_path / "n", expected_size=1, sha256="0" * 64)


def test_disk_space_checked_before_download(
    tmp_path: Path, server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    model, tool, _files = _fake_components(server)
    m = _manager(tmp_path, [model, tool])

    class Usage:
        free = 10

    monkeypatch.setattr(manager_mod.shutil, "disk_usage", lambda _p: Usage())
    with pytest.raises(DiskSpaceError):
        m.install([model], m.make_consent([model]))


def test_offline_bundle_install(tmp_path: Path, server: str) -> None:
    model, tool, files = _fake_components(server)
    src = tmp_path / "src"
    src.mkdir()
    (src / "model.onnx").write_bytes(files["/model.onnx"])
    (src / "tool.tar.gz").write_bytes(files["/tool.tar.gz"])
    bundle = ComponentManager.build_bundle(
        {"model.onnx": src / "model.onnx", "tool.tar.gz": src / "tool.tar.gz"}, tmp_path / "b.zip"
    )
    m = _manager(tmp_path, [model, tool])
    installed = m.install_from_bundle(bundle)
    assert {c.id for c in installed} == {"model", "tool"}
    assert all(s.installed for s in m.status())


def test_bundle_with_bad_checksum_is_rejected(tmp_path: Path, server: str) -> None:
    model, _tool, _files = _fake_components(server)
    bundle = tmp_path / "bad.zip"
    with zipfile.ZipFile(bundle, "w") as zf:
        zf.writestr("model.onnx", b"wrong")
    m = _manager(tmp_path, [model])
    with pytest.raises(ChecksumMismatchError):
        m.install_from_bundle(bundle)


def test_manifest_is_pinned() -> None:
    for c in manifest.COMPONENTS:
        for f in c.files.values():
            assert len(f.sha256) == 64 and f.size > 0
            assert f.url.startswith("https://")
            assert "latest" not in f.url
