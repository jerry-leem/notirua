from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from notirua import i18n


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep every test away from the real user folders."""
    for var in ("DATA", "CONFIG", "CACHE", "LOG"):
        monkeypatch.setenv(f"NOTIRUA_{var}_DIR", str(tmp_path / f"user-{var.lower()}"))
    i18n.set_language("en")
    yield
    i18n.set_locales_dir(None)
    i18n.set_language("en")


def real_components_dir() -> Path | None:
    """Components installed by `notirua setup` on this machine, for slow tests."""
    import os

    from platformdirs import PlatformDirs

    env = os.environ.get("NOTIRUA_TEST_COMPONENTS_DIR")
    path = (
        Path(env)
        if env
        else Path(PlatformDirs("notirua", appauthor=False).user_data_dir) / "components"
    )
    return path if (path / "installed.json").is_file() else None


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-snapshots", action="store_true", help="Rewrite tests/snapshots files."
    )
