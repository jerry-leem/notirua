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
    mirrors: tuple[str, ...] = ()  # tried in order when ``url`` fails; same bytes

    @property
    def urls(self) -> tuple[str, ...]:
        return (self.url, *self.mirrors)

    @property
    def domain(self) -> str:
        """Every host a download may contact, for the consent screen."""
        return ", ".join(dict.fromkeys(urlparse(u).netloc for u in self.urls))


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
# Unchanged copy on the project's own GitHub release (DECISIONS D17).
_MODEL_MIRROR = (
    "https://github.com/jerry-leem/notirua/releases/download/"
    "model-htdemucs_6s-49df9b6/htdemucs_6s.onnx"
)

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
            mirrors=(_MODEL_MIRROR,),
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

# Deno runs the scripts that solve YouTube's player challenge (yt-dlp needs a JavaScript
# runtime for that). It is optional: only people who paste YouTube links need it, so it is
# not part of the first-run setup and is asked for (with consent) the first time it is used.
_DENO_VERSION = "2.9.7"
_DENO_BASE = f"https://github.com/denoland/deno/releases/download/v{_DENO_VERSION}/"

JS_RUNTIME = Component(
    id="deno",
    name_id=N_("Helper program (Deno)"),
    purpose_id=N_("Lets Notirua read YouTube links. Only needed for saving audio from YouTube."),
    version=_DENO_VERSION,
    required=False,
    license_id="MIT",
    license_url="https://github.com/denoland/deno/blob/main/LICENSE.md",
    installed_size=97_830_000,
    files={
        "darwin-arm64": ComponentFile(
            url=_DENO_BASE + "deno-aarch64-apple-darwin.zip",
            sha256="5cd46d6268f6f78f5d88bdc7159d20bd44cdaa4b3303474839f87ec6fe7ae25c",
            size=38_469_316,
            archive="zip",
            filename=f"deno-{_DENO_VERSION}-aarch64-apple-darwin.zip",
        ),
        "darwin-x86_64": ComponentFile(
            url=_DENO_BASE + "deno-x86_64-apple-darwin.zip",
            sha256="95daaff11c116a52ad54785e7914c8e9c9cdcaba793c5ed929c74ca2d8e6259a",
            size=42_295_422,
            archive="zip",
            filename=f"deno-{_DENO_VERSION}-x86_64-apple-darwin.zip",
        ),
        "linux-x86_64": ComponentFile(
            url=_DENO_BASE + "deno-x86_64-unknown-linux-gnu.zip",
            sha256="c6527f24f4b16031d3ae4fa9f658d5f11534c8d84ce7dc8502420280919c3490",
            size=41_596_794,
            archive="zip",
            filename=f"deno-{_DENO_VERSION}-x86_64-unknown-linux-gnu.zip",
        ),
        "windows-x86_64": ComponentFile(
            url=_DENO_BASE + "deno-x86_64-pc-windows-msvc.zip",
            sha256="a0c3101b4158d1dfb7d6a78a7bf0f3de80c96bb423c152beec8beb22786f2238",
            size=42_630_221,
            archive="zip",
            filename=f"deno-{_DENO_VERSION}-x86_64-pc-windows-msvc.zip",
        ),
    },
    entry="deno{exe}",
)

OPTIONAL_COMPONENTS: tuple[Component, ...] = (JS_RUNTIME,)


def components_for_platform(platform_key: str | None = None) -> list[Component]:
    key = platform_key or current_platform()
    return [c for c in COMPONENTS if c.file_for(key) is not None]


def optional_components_for_platform(platform_key: str | None = None) -> list[Component]:
    key = platform_key or current_platform()
    return [c for c in OPTIONAL_COMPONENTS if c.file_for(key) is not None]


def by_id(component_id: str) -> Component:
    for c in (*COMPONENTS, *OPTIONAL_COMPONENTS):
        if c.id == component_id:
            return c
    raise KeyError(component_id)
