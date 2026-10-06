"""Per-stage result cache keyed by input hash + stage options (SPEC 5.4)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import numpy as np

from notirua.core.decode import AudioArray
from notirua.core.model import NoteEvent

log = logging.getLogger(__name__)

CACHE_VERSION = 1


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for block in iter(lambda: fp.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()[:32]


def options_hash(*parts: Any) -> str:
    def default(o: Any) -> Any:
        if is_dataclass(o) and not isinstance(o, type):
            return asdict(o)
        if isinstance(o, Path):
            return str(o)
        return repr(o)

    blob = json.dumps([CACHE_VERSION, *parts], sort_keys=True, default=default)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


class StageCache:
    def __init__(self, root: Path, input_hash: str, limit_bytes: int = 5 * 1024**3) -> None:
        self.root = root
        self.dir = root / input_hash
        self.limit_bytes = limit_bytes

    def _path(self, stage: str, key: str, suffix: str) -> Path:
        return self.dir / f"{stage}-{key}{suffix}"

    def _touch(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        os.utime(self.dir)

    # -- audio -------------------------------------------------------------
    def has_audio(self, stage: str, key: str, names: Sequence[str]) -> bool:
        return all(self._path(stage, f"{key}-{n}", ".npy").is_file() for n in names)

    def load_audio(
        self, stage: str, key: str, names: Sequence[str]
    ) -> dict[str, AudioArray] | None:
        paths = {n: self._path(stage, f"{key}-{n}", ".npy") for n in names}
        if not all(p.is_file() for p in paths.values()):
            return None
        try:
            result = {n: np.load(p).astype(np.float32) for n, p in paths.items()}
        except (OSError, ValueError) as exc:
            log.warning("cache read failed for %s: %s", stage, exc)
            return None
        self._touch()
        return result

    def save_audio(self, stage: str, key: str, arrays: dict[str, AudioArray]) -> None:
        self._touch()
        for name, arr in arrays.items():
            target = self._path(stage, f"{key}-{name}", ".npy")
            tmp = target.with_suffix(".tmp.npy")
            np.save(tmp, arr.astype(np.float16))
            tmp.replace(target)

    # -- JSON --------------------------------------------------------------
    def load_json(self, stage: str, key: str) -> Any | None:
        path = self._path(stage, key, ".json")
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        self._touch()
        return data

    def save_json(self, stage: str, key: str, data: Any) -> None:
        self._touch()
        target = self._path(stage, key, ".json")
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(target)

    def load_notes(self, stage: str, key: str) -> dict[str, list[NoteEvent]] | None:
        data = self.load_json(stage, key)
        if data is None:
            return None
        return {stem: [NoteEvent(*row) for row in rows] for stem, rows in data.items()}

    def save_notes(self, stage: str, key: str, notes: dict[str, list[NoteEvent]]) -> None:
        self.save_json(
            stage,
            key,
            {
                stem: [[e.start_s, e.end_s, e.pitch, e.velocity] for e in ev]
                for stem, ev in notes.items()
            },
        )

    # -- housekeeping ------------------------------------------------------
    def enforce_limit(self) -> None:
        enforce_limit(self.root, self.limit_bytes, keep=self.dir)


def dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.exists() else 0


def enforce_limit(root: Path, limit_bytes: int, keep: Path | None = None) -> int:
    """Delete least-recently-used job folders until the cache fits. Returns bytes freed."""
    if not root.is_dir():
        return 0
    jobs = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
    sizes = {p: dir_size(p) for p in jobs}
    total = sum(sizes.values())
    freed = 0
    for job in jobs:
        if total <= limit_bytes:
            break
        if keep is not None and job == keep:
            continue
        shutil.rmtree(job, ignore_errors=True)
        total -= sizes[job]
        freed += sizes[job]
    return freed


def clear(root: Path) -> int:
    size = dir_size(root)
    shutil.rmtree(root, ignore_errors=True)
    return size


def free_bytes(path: Path) -> int:
    """Free space on the disk that holds ``path`` (or its nearest existing parent)."""
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free


def cache_size(root: Path) -> int:
    return dir_size(root)


def now() -> float:
    return time.time()
