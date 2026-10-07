"""Consent-gated component installation (FR-10, SPEC 7.2).

No network request happens unless the caller passes a :class:`ConsentRecord`
that matches the current manifest. The GUI and ``notirua setup`` both create
that record only after the user explicitly agrees.
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
import tarfile
import tempfile
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from notirua import settings as settings_mod
from notirua.components.download import DownloadStatus, PauseToken, download, sha256_file
from notirua.components.manifest import (
    MANIFEST_VERSION,
    Component,
    ComponentFile,
    components_for_platform,
    current_platform,
    optional_components_for_platform,
)
from notirua.core.errors import (
    ChecksumMismatchError,
    ComponentMissingError,
    ConsentRequiredError,
    DiskSpaceError,
    DownloadError,
    PermissionDeniedError,
)
from notirua.core.progress import CancelToken, ProgressCallback, ProgressReporter, StageSpec
from notirua.i18n import N_
from notirua.settings import ConsentRecord, Settings

log = logging.getLogger(__name__)

STATE_FILE = "installed.json"
OFFLINE_BUNDLE_MANIFEST = "notirua-components.json"


@dataclass(frozen=True)
class ComponentStatus:
    component: Component
    installed: bool
    installed_version: str | None
    size_on_disk: int


@dataclass(frozen=True)
class SetupPlan:
    components: list[Component]
    download_bytes: int
    install_bytes: int
    free_bytes: int
    install_dir: Path

    @property
    def enough_space(self) -> bool:
        # Archives are extracted next to the download, so both must fit at once.
        return self.free_bytes >= self.download_bytes + self.install_bytes


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


class ComponentManager:
    def __init__(self, install_dir: Path, platform_key: str | None = None) -> None:
        self.install_dir = install_dir
        self.platform_key = platform_key or current_platform()
        self.components = components_for_platform(self.platform_key)

    # -- state -------------------------------------------------------------
    def _state_path(self) -> Path:
        return self.install_dir / STATE_FILE

    def _read_state(self) -> dict[str, str]:
        try:
            data = json.loads(self._state_path().read_text(encoding="utf-8"))
            return {str(k): str(v) for k, v in data.get("components", {}).items()}
        except (OSError, ValueError):
            return {}

    def _write_state(self, state: dict[str, str]) -> None:
        self.install_dir.mkdir(parents=True, exist_ok=True)
        payload = {"manifest_version": MANIFEST_VERSION, "components": state}
        self._state_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def component_dir(self, component: Component) -> Path:
        return self.install_dir / component.id

    def entry_path(self, component: Component) -> Path:
        exe = ".exe" if self.platform_key.startswith("windows") else ""
        return self.component_dir(component) / component.entry.format(exe=exe)

    def status(self) -> list[ComponentStatus]:
        state = self._read_state()
        result = []
        for c in self.components:
            version = state.get(c.id)
            ok = version == c.version and self.entry_path(c).exists()
            result.append(
                ComponentStatus(c, ok, version, _dir_size(self.component_dir(c)) if ok else 0)
            )
        return result

    def missing(self, required_only: bool = True) -> list[Component]:
        return [
            s.component
            for s in self.status()
            if not s.installed and (s.component.required or not required_only)
        ]

    def require(self, component_id: str) -> Path:
        """Path to an installed component's entry file, or raise ComponentMissingError."""
        for s in self.status():
            if s.component.id == component_id:
                if not s.installed:
                    raise ComponentMissingError(name=component_id)
                return self.entry_path(s.component)
        raise ComponentMissingError(name=component_id)

    # -- consent -----------------------------------------------------------
    def plan(self, components: Sequence[Component] | None = None) -> SetupPlan:
        todo = list(components) if components is not None else self.missing(required_only=False)
        download_bytes = sum(f.size for c in todo if (f := c.file_for(self.platform_key)))
        install_bytes = sum(c.installed_size for c in todo)
        probe = self.install_dir
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        free = shutil.disk_usage(probe).free
        return SetupPlan(todo, download_bytes, install_bytes, free, self.install_dir)

    @staticmethod
    def make_consent(components: Sequence[Component]) -> ConsentRecord:
        """Call only after the user pressed “Agree and install” (or ``--accept-licenses``)."""
        return ConsentRecord(
            manifest_version=MANIFEST_VERSION,
            components={c.id: c.version for c in components},
            accepted_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )

    @staticmethod
    def consent_is_current(record: ConsentRecord | None, components: Sequence[Component]) -> bool:
        if record is None or record.manifest_version != MANIFEST_VERSION:
            return False
        return all(record.components.get(c.id) == c.version for c in components)

    def needs_setup(self, settings: Settings) -> bool:
        return bool(self.missing()) or not self.consent_is_current(
            settings.consent, self.components
        )

    # -- install -----------------------------------------------------------
    def install(
        self,
        components: Sequence[Component],
        consent: ConsentRecord,
        *,
        progress: ProgressCallback | None = None,
        cancel: CancelToken | None = None,
        pause: PauseToken | None = None,
        downloads_dir: Path | None = None,
    ) -> None:
        if not self.consent_is_current(consent, components):
            raise ConsentRequiredError()
        plan = self.plan(components)
        if not plan.enough_space:
            raise DiskSpaceError(
                needed=human_size(plan.download_bytes + plan.install_bytes),
                available=human_size(plan.free_bytes),
            )
        stages = []
        for c in components:
            f = c.file_for(self.platform_key)
            size_mb = (f.size if f else 0) / 1e6
            stages.append(
                StageSpec(f"download:{c.id}", max(1.0, size_mb), N_("Downloading {name}"))
            )
            stages.append(
                StageSpec(f"install:{c.id}", max(1.0, size_mb / 20), N_("Installing {name}"))
            )
        cancel = cancel or CancelToken()
        dl_dir = downloads_dir or (self.install_dir / ".downloads")
        with ProgressReporter("setup", stages, progress) as reporter:
            for c in components:
                f = c.file_for(self.platform_key)
                if f is None:
                    continue
                stage = f"download:{c.id}"
                reporter.start(stage, name=c.name_id)

                def on_bytes(st: DownloadStatus, stage: str = stage, c: Component = c) -> None:
                    reporter.update(
                        stage,
                        st.received / max(1, st.total),
                        N_("Downloading {name}: {received} of {total}"),
                        name=c.name_id,
                        received=human_size(st.received),
                        total=human_size(st.total),
                        speed=human_size(st.bytes_per_s),
                    )

                try:
                    archive = _download_any(
                        f,
                        dl_dir / f.filename,
                        progress=on_bytes,
                        cancel=cancel,
                        pause=pause,
                    )
                except Exception:
                    reporter.fail(stage, name=c.name_id)
                    raise
                reporter.done(stage, name=c.name_id)
                istage = f"install:{c.id}"
                reporter.start(istage, name=c.name_id)
                try:
                    self._install_file(c, archive)
                except Exception:
                    reporter.fail(istage, name=c.name_id)
                    raise
                reporter.done(istage, name=c.name_id)
                archive.unlink(missing_ok=True)
        shutil.rmtree(dl_dir, ignore_errors=True)

    def _install_file(self, component: Component, path: Path) -> None:
        f = component.file_for(self.platform_key)
        assert f is not None
        target = self.component_dir(component)
        staging = Path(tempfile.mkdtemp(prefix=f".{component.id}-", dir=self.install_dir))
        try:
            if f.archive == "tar.gz":
                with tarfile.open(path, "r:gz") as tar:
                    tar.extractall(staging, filter="data")
            elif f.archive == "zip":
                with zipfile.ZipFile(path) as zf:
                    _safe_zip_extract(zf, staging)
            else:
                shutil.copy2(path, staging / f.filename)
            if target.exists():
                shutil.rmtree(target)
            staging.replace(target)
        except PermissionError as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise PermissionDeniedError(str(exc)) from exc
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        entry = self.entry_path(component)
        if not entry.exists():
            raise DownloadError(f"{component.id}: entry {entry} missing after install")
        if sys.platform != "win32" and f.archive:
            entry.chmod(entry.stat().st_mode | 0o111)
        state = self._read_state()
        state[component.id] = component.version
        self._write_state(state)
        log.info("installed %s %s into %s", component.id, component.version, target)

    def remove(self, component: Component) -> None:
        shutil.rmtree(self.component_dir(component), ignore_errors=True)
        state = self._read_state()
        state.pop(component.id, None)
        self._write_state(state)

    # -- offline bundle ----------------------------------------------------
    def install_from_bundle(
        self,
        bundle: Path,
        *,
        progress: ProgressCallback | None = None,
        cancel: CancelToken | None = None,
    ) -> list[Component]:
        """Install from a zip produced by :meth:`build_bundle` (no network)."""
        cancel = cancel or CancelToken()
        installed: list[Component] = []
        with (
            zipfile.ZipFile(bundle) as zf,
            tempfile.TemporaryDirectory(dir=self._tmp_root()) as tmp,
        ):
            names = set(zf.namelist())
            todo = [
                c
                for c in self.components
                if (f := c.file_for(self.platform_key)) and f.filename in names
            ]
            if not todo:
                raise DownloadError("bundle does not contain components for this platform")
            # Each file is copied out of the bundle and then installed, like a download.
            plan = self.plan(todo)
            if not plan.enough_space:
                raise DiskSpaceError(
                    needed=human_size(plan.download_bytes + plan.install_bytes),
                    available=human_size(plan.free_bytes),
                )
            stages = [StageSpec(f"install:{c.id}", 1.0, N_("Installing {name}")) for c in todo]
            with ProgressReporter("setup", stages, progress) as reporter:
                for c in todo:
                    cancel.raise_if_cancelled()
                    f = c.file_for(self.platform_key)
                    assert f is not None
                    stage = f"install:{c.id}"
                    reporter.start(stage, name=c.name_id)
                    out = Path(tmp) / f.filename
                    with zf.open(f.filename) as src, out.open("wb") as dst:
                        shutil.copyfileobj(src, dst, 1024 * 1024)
                    if sha256_file(out) != f.sha256:
                        reporter.fail(stage, name=c.name_id)
                        raise ChecksumMismatchError(f"{f.filename} in bundle")
                    self._install_file(c, out)
                    reporter.done(stage, name=c.name_id)
                    installed.append(c)
        return installed

    def _tmp_root(self) -> Path:
        self.install_dir.mkdir(parents=True, exist_ok=True)
        return self.install_dir

    @staticmethod
    def build_bundle(files: dict[str, Path], out: Path) -> Path:
        """Pack already-downloaded component files (by manifest filename) into a zip."""
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as zf:
            for name, path in files.items():
                zf.write(path, arcname=name)
            zf.writestr(
                OFFLINE_BUNDLE_MANIFEST,
                json.dumps({"manifest_version": MANIFEST_VERSION, "files": sorted(files)}),
            )
        return out


def _download_any(
    f: ComponentFile,
    dest: Path,
    *,
    progress: Callable[[DownloadStatus], None],
    cancel: CancelToken,
    pause: PauseToken | None,
) -> Path:
    """Download ``f`` from its URL, then from each mirror in turn.

    A partial file carries over between hosts because every host serves the
    same bytes (the SHA-256 decides).
    """
    last: DownloadError | None = None
    for url in f.urls:
        try:
            return download(
                url,
                dest,
                expected_size=f.size,
                sha256=f.sha256,
                progress=progress,
                cancel=cancel,
                pause=pause,
            )
        except DownloadError as exc:  # ChecksumMismatchError included
            log.warning("download from %s failed: %s", url, exc)
            last = exc
    assert last is not None
    raise last


def _safe_zip_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    root = dest.resolve()
    for member in zf.infolist():
        target = (dest / member.filename).resolve()
        if not target.is_relative_to(root):
            raise DownloadError(f"unsafe path in archive: {member.filename}")
    zf.extractall(dest)


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def manager_from_settings(settings: Settings | None = None) -> ComponentManager:
    s = settings or settings_mod.load()
    return ComponentManager(s.components_path)


class OptionalComponentManager(ComponentManager):
    """Manages the optional components (Deno for YouTube links).

    Same downloads, checks, and install folder as the required components, and the same
    state file (entries merge), but a separate list: the first-run setup, the consent
    record, and the offline bundle only ever cover the required ones.
    """

    def __init__(self, install_dir: Path, platform_key: str | None = None) -> None:
        super().__init__(install_dir, platform_key)
        self.components = optional_components_for_platform(self.platform_key)

    @staticmethod
    def make_consent(components: Sequence[Component]) -> ConsentRecord:
        """Call only after the user pressed the download button of the optional-component dialog."""
        return ComponentManager.make_consent(components)


def optional_manager_from_settings(settings: Settings | None = None) -> OptionalComponentManager:
    s = settings or settings_mod.load()
    return OptionalComponentManager(s.components_path)
