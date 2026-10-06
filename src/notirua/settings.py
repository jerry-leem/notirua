"""User settings persisted as JSON in the config folder (FR-8 "remember", FR-10 consent)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from notirua import paths

log = logging.getLogger(__name__)

SETTINGS_FILE = "settings.json"

# Relative stage durations measured in M0 on an M4 Pro (CPU + CoreML), 4 min song.
DEFAULT_STAGE_WEIGHTS: dict[str, float] = {
    "decode": 1.0,
    "separate": 60.0,
    "transcribe": 12.0,
    "analyze": 3.0,
    "quantize": 1.0,
    "arrange": 1.0,
    "engrave": 10.0,
    "export": 1.0,
}


@dataclass
class ConsentRecord:
    manifest_version: int
    components: dict[str, str]  # component id -> version
    accepted_at: str  # ISO 8601 UTC


@dataclass
class Settings:
    language: str | None = None
    pdf_language: str | None = None
    paper: str | None = None  # "a4" | "letter"; None = from locale
    guitar_tuning: str = "standard"
    bass_tuning: str = "standard"
    output_dir: str | None = None
    window_geometry: str | None = None
    recent_files: list[str] = field(default_factory=list)
    components_dir: str | None = None
    cache_limit_gb: float = 5.0
    consent: ConsentRecord | None = None
    stage_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_STAGE_WEIGHTS))
    tab_weights: dict[str, float] = field(default_factory=dict)
    transcription: dict[str, float] = field(default_factory=dict)

    @property
    def components_path(self) -> Path:
        return Path(self.components_dir) if self.components_dir else paths.default_components_dir()


def default_paper() -> str:
    """Letter in North America and the Philippines, A4 elsewhere (from the OS locale)."""
    import locale

    try:
        region = (locale.getlocale()[0] or "").split("_")[-1].upper()
    except ValueError:
        region = ""
    return "letter" if region in {"US", "CA", "MX", "PH"} else "a4"


def settings_path() -> Path:
    return paths.config_dir() / SETTINGS_FILE


def load() -> Settings:
    path = settings_path()
    if not path.is_file():
        return Settings()
    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("settings file unreadable, using defaults: %s", exc)
        return Settings()
    known = {f.name for f in fields(Settings)}
    values = {k: v for k, v in raw.items() if k in known}
    consent = values.pop("consent", None)
    settings = Settings(**values)
    if isinstance(consent, dict):
        try:
            settings.consent = ConsentRecord(**consent)
        except TypeError:
            settings.consent = None
    weights = dict(DEFAULT_STAGE_WEIGHTS)
    weights.update(settings.stage_weights or {})
    settings.stage_weights = weights
    return settings


def save(settings: Settings) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(settings)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
