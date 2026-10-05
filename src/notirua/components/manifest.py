"""Pinned manifest of downloadable components (SPEC 7.2).

Nothing here follows "latest": every file is pinned by URL, size, and SHA-256.
Bump ``MANIFEST_VERSION`` whenever the list or a version changes so users are
asked for consent again (FR-10).
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from urllib.parse import urlparse

from notirua.i18n import N_

MANIFEST_VERSION = 1


@dataclass(frozen=True)
class ComponentFile:
    url: str
    sha256: str
    size: int
    archive: str | None  # "tar.gz" | "zip" | None (single file)
    filename: str

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc


@dataclass(frozen=True)
class Component:
    id: str
    name_id: str  # gettext ids
    purpose_id: str
    version: str
    required: bool
    license_id: str  # SPDX
    license_url: str
    installed_size: int
    files: dict[str, ComponentFile]  # platform key -> file
    entry: str  # relative path checked to decide "installed", may contain {platform}

    def file_for(self, platform_key: str | None = None) -> ComponentFile | None:
        key = platform_key or current_platform()
        return self.files.get(key) or self.files.get("any")


def current_platform() -> str:
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
    if sys.platform == "darwin":
        return f"darwin-{arch}"
    if sys.platform == "win32":
        return "windows-x86_64"
    return f"linux-{arch}"


_LILYPOND_BASE = "https://gitlab.com/lilypond/lilypond/-/releases/v2.26.0/downloads/"
_DEMUCS_REV = "49df9b6989cf2150840ea65b0bef77a2e471b678"

SEPARATION_MODEL = Component(
    id="htdemucs_6s",
    name_id=N_("Instrument separation model"),
    purpose_id=N_("Splits a song into vocals, drums, bass, guitar, piano, and other sounds."),
    version="htdemucs_6s-onnx@49df9b6",
    required=True,
    license_id="MIT",
    license_url="https://huggingface.co/StemSplitio/htdemucs-6s-onnx",
    installed_size=258_159_781,
    files={
        "any": ComponentFile(
            url=f"https://huggingface.co/StemSplitio/htdemucs-6s-onnx/resolve/{_DEMUCS_REV}/htdemucs_6s.onnx",
            sha256="48f8e84945579f8ab340e083339e9221e03785dbe733a52c388200b6d3ca779a",
            size=258_159_781,
            archive=None,
            filename="htdemucs_6s.onnx",
        )
    },
    entry="htdemucs_6s.onnx",
)

LILYPOND = Component(
    id="lilypond",
    name_id=N_("Score engraver (LilyPond)"),
    purpose_id=N_("Draws the finished sheet music and saves it as PDF."),
    version="2.26.0",
    required=True,
    license_id="GPL-3.0-or-later",
    license_url="https://lilypond.org/gpl.html",
    installed_size=135_000_000,
    files={
        "darwin-arm64": ComponentFile(
            url=_LILYPOND_BASE + "lilypond-2.26.0-darwin-arm64.tar.gz",
            sha256="18ffc454fef3753c26a015d95a3c232f89b22f052b897c046e0198740a1221be",
            size=40_823_655,
            archive="tar.gz",
            filename="lilypond-2.26.0-darwin-arm64.tar.gz",
        ),
        "darwin-x86_64": ComponentFile(
            url=_LILYPOND_BASE + "lilypond-2.26.0-darwin-x86_64.tar.gz",
            sha256="6dcbca34b13ad6d4ba3606a0b48edd02688284fcd52e9c00141242df1996a148",
            size=41_539_857,
            archive="tar.gz",
            filename="lilypond-2.26.0-darwin-x86_64.tar.gz",
        ),
        "linux-x86_64": ComponentFile(
            url=_LILYPOND_BASE + "lilypond-2.26.0-linux-x86_64.tar.gz",
            sha256="cd8a097a9f52cb2b9f4e7914774786f203f4fc61fcd299afcbb63c23fa5c6b24",
            size=42_590_078,
            archive="tar.gz",
            filename="lilypond-2.26.0-linux-x86_64.tar.gz",
        ),
        "windows-x86_64": ComponentFile(
            url=_LILYPOND_BASE + "lilypond-2.26.0-mingw-x86_64.zip",
            sha256="14ddddc233b469ef60d4ffc1c7f35520f15ac6b58e38cab458c60bdcc3af650c",
            size=45_581_453,
            archive="zip",
            filename="lilypond-2.26.0-mingw-x86_64.zip",
        ),
    },
    entry="lilypond-2.26.0/bin/lilypond{exe}",
)

COMPONENTS: tuple[Component, ...] = (SEPARATION_MODEL, LILYPOND)


def components_for_platform(platform_key: str | None = None) -> list[Component]:
    key = platform_key or current_platform()
    return [c for c in COMPONENTS if c.file_for(key) is not None]


def by_id(component_id: str) -> Component:
    for c in COMPONENTS:
        if c.id == component_id:
            return c
    raise KeyError(component_id)
