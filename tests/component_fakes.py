"""Local HTTP server and fake components for download and setup tests (no internet)."""

from __future__ import annotations

import gzip
import hashlib
import http.server
import io
import socket
import tarfile
import threading
from collections.abc import Iterator
from dataclasses import replace
from typing import ClassVar

from notirua.components import manifest

PAYLOAD = b"notirua-model-bytes" * 5000


class Handler(http.server.BaseHTTPRequestHandler):
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


def serve() -> Iterator[str]:
    Handler.files = {}
    Handler.fail_after = None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def tar_with(entry: str, content: bytes) -> bytes:
    """A .tar.gz with fixed timestamps, so every call yields the same bytes and checksum."""
    buf = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz,
        tarfile.open(fileobj=gz, mode="w") as tar,
    ):
        info = tarfile.TarInfo(entry)
        info.size = len(content)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def fake_components(base: str) -> tuple[manifest.Component, manifest.Component, dict[str, bytes]]:
    archive = tar_with("tool-1.0/bin/tool", b"#!/bin/sh\necho tool\n")
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
