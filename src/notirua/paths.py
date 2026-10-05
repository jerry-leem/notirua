"""Per-user folders (platformdirs). Every folder can be redirected for tests."""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import PlatformDirs

APP_NAME = "notirua"

_dirs = PlatformDirs(APP_NAME, appauthor=False, roaming=False)


def _override(var: str, default: str) -> Path:
    value = os.environ.get(var)
    path = Path(value) if value else Path(default)
    return path


def data_dir() -> Path:
    return _override("NOTIRUA_DATA_DIR", _dirs.user_data_dir)


def config_dir() -> Path:
    return _override("NOTIRUA_CONFIG_DIR", _dirs.user_config_dir)


def cache_dir() -> Path:
    return _override("NOTIRUA_CACHE_DIR", _dirs.user_cache_dir)


def log_dir() -> Path:
    return _override("NOTIRUA_LOG_DIR", _dirs.user_log_dir)


def default_components_dir() -> Path:
    return data_dir() / "components"
