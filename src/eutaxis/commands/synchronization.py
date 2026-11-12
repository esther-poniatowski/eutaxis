"""Plan and apply the complete config-registered Skill set."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable, Collection, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .adapters import AgentAdapter
from .exceptions import CommandError, OwnershipError
from .installer import (
    _uninstall_command,
    diff_command,
    install_command,
    is_eutaxis_owned,
)
from .models import CommandSource
from .names import is_skill_name
from .registry import Registry

SYNC_MANIFEST_SCHEMA = "eutaxis:skill-sync-manifest@1"


class SkillSyncManifest:
    """Skill names recorded for one configuration, adapter, and scope."""

    def __init__(self, state_dir: Path, config_path: Path) -> None:
        self.config_path = config_path.expanduser().resolve()
        digest = hashlib.sha256(str(self.config_path).encode("utf-8")).hexdigest()
        self.path = state_dir / "sync-manifests" / f"{digest}.json"

    def managed_names(
        self, *, adapter: str, scope: str, project_root: Path
    ) -> frozenset[str]:
        """Return names recorded for one adapter and scope."""
        payload = self._load()
        deployments = payload["deployments"]
        assert isinstance(deployments, dict)  # validated by _load
        return frozenset(
            deployments.get(_deployment_key(adapter, scope, project_root), ())
        )

    def names_managed_by_other_configs(
        self,
        *,
        adapter: str,
        scope: str,
        project_root: Path,
    ) -> frozenset[str]:
        """Return names claimed by every other configuration manifest."""
        names: set[str] = set()
        if not self.path.parent.is_dir():
            return frozenset()
        for path in self.path.parent.glob("*.json"):
            if path == self.path:
                continue
            payload = self._read_payload(path)
            deployments = payload["deployments"]
            assert isinstance(deployments, dict)  # _read_payload validates this type
            key = _deployment_key(adapter, scope, project_root)
            names.update(deployments.get(key, ()))
        return frozenset(names)

    def update(
        self,
        *,
        scope: str,
        project_root: Path,
        names_by_adapter: Mapping[str, Collection[str]],
    ) -> None:
        """Atomically record the successful result for selected adapters."""
        payload = self._load()
        deployments = payload["deployments"]
        assert isinstance(deployments, dict)  # _load validates this type
        for adapter, names in names_by_adapter.items():
            key = _deployment_key(adapter, scope, project_root)
            deployments[key] = sorted(set(names))

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, self.path)

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Serialize plans and writes across configuration manifests."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.parent / "sync-manifests.lock"
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _load(self) -> dict[str, object]:
        if not self.path.is_file():
            return {
                "_schema": SYNC_MANIFEST_SCHEMA,
                "config": str(self.config_path),
                "deployments": {},
            }
        payload = self._read_payload(self.path)
        if payload.get("config") != str(self.config_path):
            raise CommandError(
                f"Skill sync manifest at {self.path} belongs to another config."
            )
        return payload

    @staticmethod
    def _read_payload(path: Path) -> dict[str, object]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(
                f"Skill sync manifest at {path} is corrupted: {exc}."
            ) from exc
        if not isinstance(payload, dict):
            raise CommandError(f"Skill sync manifest at {path} must be a JSON object.")
        if payload.get("_schema") != SYNC_MANIFEST_SCHEMA:
            raise CommandError(
                f"Skill sync manifest at {path} must declare "
                f"_schema: {SYNC_MANIFEST_SCHEMA}."
            )
        deployments = payload.get("deployments")
        if not isinstance(deployments, dict) or any(
            not isinstance(key, str)
            or not isinstance(names, list)
            or any(not is_skill_name(name) for name in names)
            for key, names in deployments.items()
        ):
            raise CommandError(
                f"Skill sync manifest at {path} has invalid deployments."
            )
        return payload


def _deployment_key(adapter: str, scope: str, project_root: Path) -> str:
    """Return the manifest key for one deployment target."""
    if scope == "project":
        root = project_root.expanduser().resolve()
        return f"project:{root}:{adapter}"
    return f"{scope}:{adapter}"


@dataclass(frozen=True)
class SkillSyncAction:
    """One planned change to an installed Skill."""

    action: str
    name: str
    adapter: AgentAdapter
    scope: str
    path: Path
    source: CommandSource | None = None
    warnings: tuple[str, ...] = ()


def plan_skill_sync(
    sources: list[CommandSource],
    adapters: list[AgentAdapter],
    *,
    scope: str,
    project_root: Path,
    home: Path,
    managed_names_by_adapter: Mapping[str, Collection[str]] | None = None,
    protected_names_by_adapter: Mapping[str, Collection[str]] | None = None,
) -> tuple[SkillSyncAction, ...]:
    """Plan installs and removals without modifying installed Skills.

    Render every configured source while building the plan. Any populated
    target without an Eutaxis ownership marker blocks the complete plan. The
    plan considers only names recorded by this configuration. A retired
    name enters the plan only while its directory carries an Eutaxis marker.
    Skills managed by other configurations cannot enter the removal set.
    """
    actions: list[SkillSyncAction] = []
    managed_names_by_adapter = managed_names_by_adapter or {}
    protected_names_by_adapter = protected_names_by_adapter or {}
    expected_by_adapter: dict[str, set[str]] = {
        adapter.name: set() for adapter in adapters
    }

    for adapter in adapters:
        if not adapter.supports_scope(scope):
            raise CommandError(
                f"Adapter {adapter.name!r} does not support scope {scope!r}."
            )
        for source in sources:
            if not source.targets.admits(adapter.name):
                continue
            expected_by_adapter[adapter.name].add(source.name)
            target = adapter.artifact_dir(
                source.name,
                scope=scope,
                home=home,
                project_root=project_root,
            )
            if target.is_symlink():
                raise OwnershipError(
                    f"Refusing to synchronize through symbolic-link target: {target}."
                )
            if target.exists() and not target.is_dir():
                raise OwnershipError(
                    f"Refusing to synchronize over non-directory target: {target}."
                )
            if (
                target.is_dir()
                and any(target.iterdir())
                and not is_eutaxis_owned(target)
            ):
                raise OwnershipError(
                    f"Refusing to synchronize over non-eutaxis directory: {target}. "
                    "Back up or remove the directory before synchronizing."
                )
            rendered, _, diff = diff_command(
                source,
                adapter,
                scope=scope,
                project_root=project_root,
                home=home,
            )
            if not target.exists() or not any(target.iterdir()):
                action = "create"
            elif diff:
                action = "update"
            else:
                action = "unchanged"
            actions.append(
                SkillSyncAction(
                    action=action,
                    name=source.name,
                    adapter=adapter,
                    scope=scope,
                    path=target,
                    source=source,
                    warnings=rendered.warnings,
                )
            )

    for adapter in adapters:
        retired = (
            set(managed_names_by_adapter.get(adapter.name, ()))
            - expected_by_adapter[adapter.name]
            - set(protected_names_by_adapter.get(adapter.name, ()))
        )
        for name in sorted(retired):
            target = adapter.artifact_dir(
                name,
                scope,
                home=home,
                project_root=project_root,
            )
            if not target.exists() and not target.is_symlink():
                continue
            if target.is_symlink() or not is_eutaxis_owned(target):
                raise OwnershipError(
                    f"Refusing to remove previously managed non-eutaxis "
                    f"target: {target}."
                )
            actions.append(
                SkillSyncAction(
                    action="remove",
                    name=name,
                    adapter=adapter,
                    scope=scope,
                    path=target,
                )
            )

    return tuple(actions)


def apply_skill_sync(
    actions: tuple[SkillSyncAction, ...],
    *,
    project_root: Path,
    home: Path,
    registry: Registry,
    finalize: Callable[[], None] | None = None,
    rollback_files: Collection[Path] = (),
) -> tuple[SkillSyncAction, ...]:
    """Apply one failure-atomic Skill plan and return the resulting states."""
    outcomes: list[SkillSyncAction] = []
    with skill_write_transaction(
        (action.path for action in actions),
        registry,
        file_paths=rollback_files,
    ):
        for action in actions:
            if action.action == "remove":
                outcome = _uninstall_command(
                    name=action.name,
                    adapter=action.adapter,
                    scope=action.scope,
                    project_root=project_root,
                    home=home,
                    registry=registry,
                )
            else:
                if action.source is None:  # pragma: no cover - dataclass invariant
                    raise RuntimeError(f"Install action lacks source: {action.name}")
                outcome = install_command(
                    action.source,
                    action.adapter,
                    scope=action.scope,
                    project_root=project_root,
                    home=home,
                    registry=registry,
                )
            outcomes.append(
                SkillSyncAction(
                    action=outcome.action,
                    name=outcome.name,
                    adapter=action.adapter,
                    scope=outcome.scope,
                    path=outcome.path,
                    source=action.source,
                    warnings=outcome.warnings,
                )
            )
        if finalize is not None:
            finalize()
    return tuple(outcomes)


@contextmanager
def skill_write_transaction(
    paths: Iterator[Path] | Collection[Path],
    registry: Registry,
    *,
    file_paths: Collection[Path] = (),
) -> Iterator[None]:
    """Restore every target when one write in a managed set fails."""
    unique_paths = tuple(dict.fromkeys(Path(path) for path in paths))
    unique_files = tuple(dict.fromkeys(Path(path) for path in file_paths))
    with registry.deployment_locked():
        _reject_aliased_or_overlapping_targets(unique_paths)
        with tempfile.TemporaryDirectory(prefix="eutaxis-skill-transaction-") as raw:
            scratch = Path(raw)
            snapshots: list[tuple[Path, Path | None]] = []
            for index, path in enumerate(unique_paths):
                if path.is_symlink():
                    raise OwnershipError(
                        f"Refusing to transact through symbolic-link target: {path}."
                    )
                backup: Path | None = None
                if path.exists():
                    if not path.is_dir():
                        raise OwnershipError(
                            f"Refusing to transact over non-directory target: {path}."
                        )
                    backup = scratch / f"directory-{index}"
                    shutil.copytree(path, backup, symlinks=True)
                snapshots.append((path, backup))
            file_snapshots: list[tuple[Path, bytes | None, int | None]] = []
            for path in unique_files:
                if path.is_symlink() or (path.exists() and not path.is_file()):
                    raise OwnershipError(
                        f"Refusing to transact over non-file state target: {path}."
                    )
                file_snapshots.append(
                    (
                        path,
                        path.read_bytes() if path.is_file() else None,
                        path.stat().st_mode if path.is_file() else None,
                    )
                )
            try:
                with registry.transaction():
                    yield
            except BaseException as primary:
                cleanup_failures: list[str] = []
                for path, backup in reversed(snapshots):
                    try:
                        _restore_directory_snapshot(path, backup)
                    except BaseException as cleanup:
                        cleanup_failures.append(
                            f"directory {path}: {type(cleanup).__name__}: {cleanup}"
                        )
                for path, content, mode in file_snapshots:
                    try:
                        _restore_file_snapshot(path, content, mode)
                    except BaseException as cleanup:
                        cleanup_failures.append(
                            f"file {path}: {type(cleanup).__name__}: {cleanup}"
                        )
                if cleanup_failures:
                    primary.add_note(
                        "Rollback cleanup also failed:\n- "
                        + "\n- ".join(cleanup_failures)
                    )
                raise


def _reject_aliased_or_overlapping_targets(paths: tuple[Path, ...]) -> None:
    """Reject write targets that resolve to the same or nested filesystem tree."""
    canonical: list[tuple[Path, Path]] = []
    for path in paths:
        try:
            resolved = path.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise OwnershipError(
                f"Cannot resolve Skill transaction target: {path}."
            ) from exc
        for prior_path, prior_resolved in canonical:
            if (
                resolved == prior_resolved
                or resolved in prior_resolved.parents
                or prior_resolved in resolved.parents
            ):
                raise OwnershipError(
                    "Refusing aliased or overlapping Skill transaction targets: "
                    f"{prior_path} and {path}."
                )
        canonical.append((path, resolved))


def _restore_directory_snapshot(path: Path, backup: Path | None) -> None:
    """Restore one directory target without affecting later restorations."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    if backup is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(backup, path, symlinks=True)


def _restore_file_snapshot(path: Path, content: bytes | None, mode: int | None) -> None:
    """Restore one state file without affecting later restorations."""
    if content is None:
        if path.is_file() or path.is_symlink():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if mode is not None:
        os.chmod(path, mode)
