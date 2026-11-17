"""Plan and apply the complete config-registered Skill set."""

from __future__ import annotations

import ctypes
import fcntl
import hashlib
import json
import os
import shutil
import stat
import tempfile
import weakref
from collections.abc import Callable, Collection, Iterator, Mapping
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
from pathlib import Path

from .adapters import AgentAdapter
from .exceptions import CommandError, OwnershipError
from .installer import (
    _install_artifact,
    _uninstall_command,
    _write_artifact_file,
    diff_command,
    is_eutaxis_owned,
    verify_artifact,
)
from .models import CommandSource, RenderedArtifact
from .names import is_skill_name
from .registry import Registry

SYNC_MANIFEST_SCHEMA = "eutaxis:skill-sync-manifest@1"
RETAINED_SKILLS_DIRECTORY = "retained-skills"


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
class SkillTargetObservation:
    """Digest of one complete Skill target tree at planning time."""

    kind: str
    digest: str


@dataclass(frozen=True)
class SkillPublicationReceipt:
    """Exact published state and displaced tree for one changed Skill."""

    target: Path
    published_state: SkillTargetObservation
    retained_path: Path | None
    retained_state: SkillTargetObservation | None


@dataclass(frozen=True, eq=False)
class SkillSyncAction:
    """One planned change to an installed Skill."""

    action: str
    name: str
    adapter: AgentAdapter
    scope: str
    path: Path
    source: CommandSource | None = None
    artifact: RenderedArtifact | None = None
    target_observation: SkillTargetObservation | None = None
    warnings: tuple[str, ...] = ()


_ISSUED_SKILL_SYNC_ACTIONS: weakref.WeakSet[SkillSyncAction] = weakref.WeakSet()


@dataclass(frozen=True, init=False, eq=False)
class PreparedSkillSync:
    """Process-issued Skill actions and the digest binding their exact state."""

    actions: tuple[SkillSyncAction, ...]
    digest: str


_ISSUED_PREPARED_SKILL_SYNCS: weakref.WeakKeyDictionary[
    PreparedSkillSync, tuple[str, tuple[int, ...]]
] = weakref.WeakKeyDictionary()


def _issue_prepared_skill_sync(
    actions: tuple[SkillSyncAction, ...],
) -> PreparedSkillSync:
    """Issue one plan and retain its exact identity-bound authenticated state."""
    instance = object.__new__(PreparedSkillSync)
    digest = _skill_sync_digest(actions)
    object.__setattr__(instance, "actions", actions)
    object.__setattr__(instance, "digest", digest)
    _ISSUED_PREPARED_SKILL_SYNCS[instance] = (
        digest,
        tuple(id(action) for action in actions),
    )
    return instance


def prepare_skill_sync(
    sources: list[CommandSource],
    adapters: list[AgentAdapter],
    *,
    scope: str,
    project_root: Path,
    home: Path,
    managed_names_by_adapter: Mapping[str, Collection[str]] | None = None,
    protected_names_by_adapter: Mapping[str, Collection[str]] | None = None,
) -> PreparedSkillSync:
    """Prepare exact rendered actions without modifying installed Skills."""
    actions = plan_skill_sync(
        sources,
        adapters,
        scope=scope,
        project_root=project_root,
        home=home,
        managed_names_by_adapter=managed_names_by_adapter,
        protected_names_by_adapter=protected_names_by_adapter,
    )
    return _issue_prepared_skill_sync(actions)


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
            observation = _observe_skill_target(target)
            rendered, _, diff = diff_command(
                source,
                adapter,
                scope=scope,
                project_root=project_root,
                home=home,
            )
            if _observe_skill_target(target) != observation:
                raise CommandError(
                    f"Skill target changed during preparation: {target}."
                )
            if not target.exists() or not any(target.iterdir()):
                action = "create"
            elif diff:
                action = "update"
            else:
                action = "unchanged"
            planned = SkillSyncAction(
                action=action,
                name=source.name,
                adapter=adapter,
                scope=scope,
                path=target,
                source=source,
                artifact=rendered,
                target_observation=observation,
                warnings=rendered.warnings,
            )
            _ISSUED_SKILL_SYNC_ACTIONS.add(planned)
            actions.append(planned)

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
            planned = SkillSyncAction(
                action="remove",
                name=name,
                adapter=adapter,
                scope=scope,
                path=target,
                target_observation=_observe_skill_target(target),
            )
            _ISSUED_SKILL_SYNC_ACTIONS.add(planned)
            actions.append(planned)

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
    prepared = _issue_prepared_skill_sync(actions)
    return apply_prepared_skill_sync(
        prepared,
        selected=actions,
        project_root=project_root,
        home=home,
        registry=registry,
        finalize=finalize,
        rollback_files=rollback_files,
    )


def apply_prepared_skill_sync(
    prepared: PreparedSkillSync,
    *,
    selected: Collection[SkillSyncAction],
    project_root: Path,
    home: Path,
    registry: Registry,
    finalize: Callable[[], None] | None = None,
    rollback_files: Collection[Path] = (),
    externally_locked: bool = False,
    before_commit: Callable[[tuple[SkillPublicationReceipt, ...]], None] | None = None,
) -> tuple[SkillSyncAction, ...]:
    """Apply exactly the selected prepared actions after rejecting drift.

    The function acquires the deployment lock before comparing every planned
    target with its planning-time observation. It writes the artifacts retained
    in ``prepared`` and never renders a source during publication.

    ``externally_locked`` is reserved for a transaction coordinator that holds
    the deployment and registry locks continuously, in that order.

    A successful update or removal retains the displaced prior directory so an
    edit through an old open file cannot be deleted after verification. The
    corresponding outcome reports its recovery path in ``warnings``; the caller
    may remove that directory after reconciling concurrent-editor state.
    """
    _validate_prepared_plan(prepared)
    selected_actions = tuple(selected)
    _validate_selected_actions(prepared.actions, selected_actions)
    _validate_action_targets(
        prepared.actions,
        project_root=project_root,
        home=home,
    )
    outcomes: list[SkillSyncAction] = []
    mutation_lock = nullcontext() if externally_locked else registry.mutation_locked()
    with mutation_lock:
        for action in prepared.actions:
            observation = action.target_observation
            if observation is None:  # pragma: no cover - dataclass invariant
                raise RuntimeError(f"Prepared action lacks observation: {action.name}")
            if _observe_skill_target(action.path) != observation:
                raise CommandError(
                    f"Skill target changed after preparation: {action.path}."
                )
        with skill_write_transaction(
            (action.path for action in selected_actions),
            registry,
            file_paths=rollback_files,
            externally_locked=True,
            guarded_rollback=True,
        ) as journal:
            for action in prepared.actions:
                if _observe_skill_target(action.path) != action.target_observation:
                    raise CommandError(
                        f"Skill target changed during publication: {action.path}."
                    )
            for action in selected_actions:
                assert action.target_observation is not None
                if _observe_skill_target(action.path) != action.target_observation:
                    raise CommandError(
                        f"Skill target changed during publication: {action.path}."
                    )
                if action.action in {"create", "update"}:
                    assert action.artifact is not None
                    journal.publish(
                        action.path,
                        action.artifact,
                        action.target_observation,
                    )
                    installed = _install_artifact(
                        action.artifact,
                        action.adapter,
                        scope=action.scope,
                        project_root=project_root,
                        home=home,
                        registry=registry,
                    )
                    outcome = replace(
                        installed,
                        action="created" if action.action == "create" else "updated",
                    )
                elif action.action == "remove":
                    journal.remove(action.path, action.target_observation)
                    removed = _uninstall_command(
                        name=action.name,
                        adapter=action.adapter,
                        scope=action.scope,
                        project_root=project_root,
                        home=home,
                        registry=registry,
                    )
                    outcome = replace(removed, action="removed")
                else:
                    assert action.artifact is not None
                    outcome = _install_artifact(
                        action.artifact,
                        action.adapter,
                        scope=action.scope,
                        project_root=project_root,
                        home=home,
                        registry=registry,
                    )
                completed = SkillSyncAction(
                    action=outcome.action,
                    name=outcome.name,
                    adapter=action.adapter,
                    scope=outcome.scope,
                    path=outcome.path,
                    source=action.source,
                    artifact=action.artifact,
                    target_observation=action.target_observation,
                    warnings=outcome.warnings,
                )
                _ISSUED_SKILL_SYNC_ACTIONS.add(completed)
                outcomes.append(completed)
            _verify_selected_post_state(
                selected_actions,
                project_root=project_root,
                home=home,
                registry=registry,
            )
            if finalize is not None:
                finalize()
                _verify_selected_post_state(
                    selected_actions,
                    project_root=project_root,
                    home=home,
                    registry=registry,
                )
            journal.verify_for_commit()
            journal.prepare_commit()
            receipts = journal.publication_receipts()
            if before_commit is not None:
                before_commit(receipts)
                _verify_selected_post_state(
                    selected_actions,
                    project_root=project_root,
                    home=home,
                    registry=registry,
                )
                journal.verify_for_commit()
    retained = journal.retained_backups()
    if retained:
        outcomes = [
            (
                replace(
                    outcome,
                    warnings=outcome.warnings
                    + (f"Prior Skill retained for recovery: {retained[outcome.path]}",),
                )
                if outcome.path in retained
                else outcome
            )
            for outcome in outcomes
        ]
    return tuple(outcomes)


def _verify_selected_post_state(
    actions: tuple[SkillSyncAction, ...],
    *,
    project_root: Path,
    home: Path,
    registry: Registry,
) -> None:
    """Verify artifact and registry postconditions before transaction commit."""
    for action in actions:
        if action.action == "remove":
            if is_eutaxis_owned(action.path):
                raise OwnershipError(
                    f"Removed Skill remains Eutaxis-owned: {action.path}."
                )
            if (
                registry.find(
                    name=action.name,
                    adapter=action.adapter.name,
                    scope=action.scope,
                    path=action.path,
                )
                is not None
            ):
                raise OwnershipError(
                    f"Removed Skill remains in the registry: {action.path}."
                )
        else:
            assert action.artifact is not None
            verify_artifact(
                action.artifact,
                action.adapter,
                scope=action.scope,
                project_root=project_root,
                home=home,
            )
            record = registry.find(
                name=action.name,
                adapter=action.adapter.name,
                scope=action.scope,
                path=action.path,
            )
            if (
                record is None
                or record.path != action.path
                or record.content_hash != action.artifact.content_hash
            ):
                raise OwnershipError(
                    f"Installed Skill registry row differs from the artifact: "
                    f"{action.path}."
                )


def _validate_selected_actions(
    actions: tuple[SkillSyncAction, ...],
    selected: tuple[SkillSyncAction, ...],
) -> None:
    """Require a duplicate-free subset of the exact prepared action objects."""
    action_ids = {id(action) for action in actions}
    selected_ids = [id(action) for action in selected]
    if len(selected_ids) != len(set(selected_ids)):
        raise CommandError("Selected Skill synchronization actions repeat a target.")
    if any(action_id not in action_ids for action_id in selected_ids):
        raise CommandError(
            "Selected Skill synchronization action does not belong to the plan."
        )


def _validate_prepared_plan(prepared: PreparedSkillSync) -> None:
    """Reject an incomplete, inconsistent, or changed prepared plan."""
    issued = _ISSUED_PREPARED_SKILL_SYNCS.get(prepared)
    current_identity = tuple(id(action) for action in prepared.actions)
    if issued is None or issued[1] != current_identity:
        raise CommandError("Prepared Skill synchronization plan was not issued here.")
    if issued[0] != prepared.digest or prepared.digest != _skill_sync_digest(
        prepared.actions
    ):
        raise CommandError("Prepared Skill synchronization plan has changed.")
    for action in prepared.actions:
        if action not in _ISSUED_SKILL_SYNC_ACTIONS:
            raise CommandError(
                f"Prepared Skill action was not issued here: {action.name}."
            )
        if action.action not in {"create", "update", "unchanged", "remove"}:
            raise CommandError(
                f"Prepared Skill action has invalid operation: {action.action!r}."
            )
        if action.target_observation is None:
            raise CommandError(
                f"Prepared Skill action lacks a target observation: {action.name}."
            )
        if action.action == "remove":
            if action.artifact is not None:
                raise CommandError(
                    f"Prepared removal carries an artifact: {action.name}."
                )
            continue
        artifact = action.artifact
        if artifact is None:
            raise CommandError(
                f"Prepared Skill action lacks an artifact: {action.name}."
            )
        if (
            artifact.name != action.name
            or artifact.adapter != action.adapter.name
            or artifact.scope != action.scope
        ):
            raise CommandError(
                f"Prepared Skill artifact does not match its action: {action.name}."
            )


def _validate_action_targets(
    actions: tuple[SkillSyncAction, ...],
    *,
    project_root: Path,
    home: Path,
) -> None:
    """Require every retained path to match its adapter deployment target."""
    for action in actions:
        expected = action.adapter.artifact_dir(
            action.name,
            action.scope,
            project_root=project_root,
            home=home,
        )
        if action.path != expected:
            raise CommandError(
                "Prepared Skill target does not match the apply context: "
                f"{action.path} != {expected}."
            )


def _skill_sync_digest(actions: tuple[SkillSyncAction, ...]) -> str:
    """Bind action order, exact artifacts, targets, and observed target states."""
    payload: list[dict[str, object]] = []
    for action in actions:
        artifact = action.artifact
        observation = action.target_observation
        payload.append(
            {
                "action": action.action,
                "name": action.name,
                "adapter": action.adapter.name,
                "scope": action.scope,
                "path": str(action.path),
                "artifact": (
                    None
                    if artifact is None
                    else {
                        "name": artifact.name,
                        "adapter": artifact.adapter,
                        "scope": artifact.scope,
                        "content_hash": artifact.content_hash,
                        "files": [
                            {
                                "path": item.relative_path,
                                "sha256": hashlib.sha256(
                                    item.content.encode("utf-8", errors="strict")
                                ).hexdigest(),
                            }
                            for item in artifact.files
                        ],
                    }
                ),
                "target": (
                    None
                    if observation is None
                    else {"kind": observation.kind, "digest": observation.digest}
                ),
            }
        )
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _observe_skill_target(path: Path) -> SkillTargetObservation:
    """Digest one tree through no-follow descriptors and stable identities."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        root_descriptor = os.open(path, flags)
    except FileNotFoundError:
        return _absent_target_observation()
    except OSError as exc:
        raise OwnershipError(
            f"Skill target is not a regular directory: {path}."
        ) from exc

    try:
        initial = os.fstat(root_descriptor)
        entries = [_observed_entry(".", "directory", initial)]
        _observe_directory_entries(
            root_descriptor,
            relative=Path(),
            display=path,
            entries=entries,
        )
        final = os.fstat(root_descriptor)
        _require_stable_stat(initial, final, path)
        try:
            current = os.stat(path, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise CommandError(
                f"Skill target changed during observation: {path}."
            ) from exc
        if not _same_identity(initial, current) or not stat.S_ISDIR(current.st_mode):
            raise CommandError(f"Skill target changed during observation: {path}.")
    finally:
        os.close(root_descriptor)

    encoded = json.dumps(
        entries, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return SkillTargetObservation(
        kind="directory", digest=hashlib.sha256(encoded).hexdigest()
    )


def _absent_target_observation() -> SkillTargetObservation:
    """Return the canonical observation for an absent Skill target."""
    payload = b'[{"kind":"absent"}]'
    return SkillTargetObservation(
        kind="absent", digest=hashlib.sha256(payload).hexdigest()
    )


def _observe_directory_entries(
    descriptor: int,
    *,
    relative: Path,
    display: Path,
    entries: list[dict[str, object]],
) -> None:
    """Append a directory closure without following a replaced path entry."""
    with os.scandir(descriptor) as iterator:
        children = sorted(iterator, key=lambda entry: entry.name)
    for child in children:
        child_relative = relative / child.name
        child_display = display / child.name
        listed = child.stat(follow_symlinks=False)
        if stat.S_ISLNK(listed.st_mode):
            raise OwnershipError(
                f"Refusing to observe symbolic link inside Skill target: {child_display}."
            )
        if stat.S_ISDIR(listed.st_mode):
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            kind = "directory"
        elif stat.S_ISREG(listed.st_mode):
            flags = os.O_RDONLY | os.O_NOFOLLOW
            kind = "file"
        else:
            raise OwnershipError(
                f"Unsupported entry inside Skill target: {child_display}."
            )
        try:
            child_descriptor = os.open(child.name, flags, dir_fd=descriptor)
        except OSError as exc:
            raise CommandError(
                f"Skill target changed during observation: {child_display}."
            ) from exc
        try:
            initial = os.fstat(child_descriptor)
            if not _same_identity(listed, initial):
                raise CommandError(
                    f"Skill target changed during observation: {child_display}."
                )
            entry = _observed_entry(child_relative.as_posix(), kind, initial)
            entries.append(entry)
            if kind == "directory":
                _observe_directory_entries(
                    child_descriptor,
                    relative=child_relative,
                    display=child_display,
                    entries=entries,
                )
            else:
                entry["sha256"] = _descriptor_digest(child_descriptor)
            final = os.fstat(child_descriptor)
            _require_stable_stat(initial, final, child_display)
        finally:
            os.close(child_descriptor)


def _observed_entry(
    path: str, kind: str, metadata: os.stat_result
) -> dict[str, object]:
    """Return the stable metadata represented in a target observation."""
    return {
        "path": path,
        "kind": kind,
        "mode": stat.S_IMODE(metadata.st_mode),
    }


def _descriptor_digest(descriptor: int) -> str:
    """Hash all bytes from an already validated regular-file descriptor."""
    digest = hashlib.sha256()
    while chunk := os.read(descriptor, 1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def _same_identity(first: os.stat_result, second: os.stat_result) -> bool:
    """Return whether two stat results identify the same filesystem object."""
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)


def _require_stable_stat(
    initial: os.stat_result,
    final: os.stat_result,
    path: Path,
) -> None:
    """Reject identity, kind, mode, size, or write-time changes during a read."""
    fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(initial, field) != getattr(final, field) for field in fields):
        raise CommandError(f"Skill target changed during observation: {path}.")


@dataclass(frozen=True)
class _AtomicPublication:
    """Filesystem state retained for one atomic target replacement."""

    backup: Path | None
    backup_state: SkillTargetObservation | None
    published_state: SkillTargetObservation


def _atomic_rename_noreplace(source: Path, target: Path) -> None:
    """Rename one directory only when the destination remains absent."""
    _atomic_rename(source, target, mac_flag=0x00000004, linux_flag=0x1)


def _atomic_exchange(first: Path, second: Path) -> None:
    """Exchange two directories without exposing an absent destination."""
    _atomic_rename(first, second, mac_flag=0x00000002, linux_flag=0x2)


def _atomic_rename(
    source: Path,
    target: Path,
    *,
    mac_flag: int,
    linux_flag: int,
) -> None:
    """Call the host's fail-closed atomic directory rename primitive."""
    library = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    target_bytes = os.fsencode(target)
    system = os.uname().sysname
    if system == "Darwin":
        operation = library.renamex_np
        operation.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        operation.restype = ctypes.c_int
        result = operation(source_bytes, target_bytes, mac_flag)
    elif system == "Linux" and hasattr(library, "renameat2"):
        operation = library.renameat2
        operation.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        operation.restype = ctypes.c_int
        result = operation(-100, source_bytes, -100, target_bytes, linux_flag)
    else:
        raise CommandError(
            "Atomic no-replace Skill publication is unavailable on this host."
        )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(target))


def _unused_sibling(path: Path, role: str) -> Path:
    """Reserve and release one unique sibling name for an atomic rename."""
    return _unused_child(path.parent, path.name, role)


def _unused_child(parent: Path, name: str, role: str) -> Path:
    """Reserve and release one unique child name for an atomic rename."""
    sibling = Path(tempfile.mkdtemp(prefix=f".{name}.eutaxis-{role}-", dir=parent))
    sibling.rmdir()
    return sibling


def _same_filesystem(first: Path, second: Path) -> bool:
    """Return whether two existing paths support an atomic rename."""
    return os.stat(first).st_dev == os.lstat(second).st_dev


class _SkillWriteJournal:
    """Publish complete targets atomically and preserve rollback conflicts."""

    def __init__(self, paths: Collection[Path], recovery_root: Path) -> None:
        self._paths = frozenset(paths)
        self._recovery_root = recovery_root.expanduser().resolve()
        self._publications: dict[Path, _AtomicPublication] = {}
        self._prepared = False

    def publish(
        self,
        path: Path,
        artifact: RenderedArtifact,
        expected: SkillTargetObservation,
    ) -> None:
        """Stage a complete artifact and atomically replace its target."""
        self._require_unused(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(
            tempfile.mkdtemp(prefix=f".{path.name}.eutaxis-stage-", dir=path.parent)
        )
        recorded = False
        try:
            for artifact_file in artifact.files:
                _write_artifact_file(stage, artifact_file)
            if _observe_skill_target(path) != expected:
                raise CommandError(f"Skill target changed before replacement: {path}.")
            if expected.kind == "absent":
                os.chmod(stage, 0o755)
                published = _observe_skill_target(stage)
                _atomic_rename_noreplace(stage, path)
                self._publications[path] = _AtomicPublication(
                    backup=None,
                    backup_state=None,
                    published_state=published,
                )
            else:
                os.chmod(stage, stat.S_IMODE(os.lstat(path).st_mode))
                published = _observe_skill_target(stage)
                _atomic_exchange(stage, path)
                self._publications[path] = _AtomicPublication(
                    backup=stage,
                    backup_state=expected,
                    published_state=published,
                )
            recorded = True
            self._require_publication_matches(path)
        except BaseException:
            if not recorded and stage.is_dir():
                shutil.rmtree(stage)
            raise

    def remove(self, path: Path, expected: SkillTargetObservation) -> None:
        """Atomically displace one complete target before registry removal."""
        self._require_unused(path)
        if _observe_skill_target(path) != expected:
            raise CommandError(f"Skill target changed before removal: {path}.")
        backup = _unused_sibling(path, "previous")
        _atomic_rename_noreplace(path, backup)
        self._publications[path] = _AtomicPublication(
            backup=backup,
            backup_state=expected,
            published_state=_absent_target_observation(),
        )
        self._require_publication_matches(path)

    def verify_for_commit(self) -> None:
        """Reject edits to published or displaced targets before commit."""
        for path in self._publications:
            self._require_publication_matches(path)

    def prepare_commit(self) -> None:
        """Move every displaced tree outside Skill discovery roots."""
        if self._prepared:
            return
        for path in self._paths:
            skill_root = path.parent.resolve()
            if (
                self._recovery_root == skill_root
                or skill_root in self._recovery_root.parents
            ):
                raise CommandError(
                    "Retained Skill root must be outside every Skill discovery "
                    f"root: {self._recovery_root}."
                )
        self._recovery_root.mkdir(parents=True, exist_ok=True)
        for path, publication in tuple(self._publications.items()):
            backup = publication.backup
            if backup is None:
                continue
            if not _same_filesystem(self._recovery_root, backup):
                raise CommandError(
                    "Retained Skill root must share a filesystem with its Skill "
                    f"target: {path}."
                )
            retained = _unused_child(
                self._recovery_root,
                path.name,
                "previous",
            )
            _atomic_rename_noreplace(backup, retained)
            self._publications[path] = replace(publication, backup=retained)
            self._require_publication_matches(path)
        self._prepared = True

    def commit(self) -> None:
        """Retain prior targets outside every Skill discovery root."""
        self.prepare_commit()

    def retained_backups(self) -> Mapping[Path, Path]:
        """Return committed prior targets that require explicit later cleanup."""
        return {
            path: publication.backup
            for path, publication in self._publications.items()
            if publication.backup is not None
        }

    def publication_receipts(self) -> tuple[SkillPublicationReceipt, ...]:
        """Return typed poststates before the journal commits its publications."""
        return tuple(
            SkillPublicationReceipt(
                target=path,
                published_state=publication.published_state,
                retained_path=publication.backup,
                retained_state=publication.backup_state,
            )
            for path, publication in self._publications.items()
        )

    def rollback_decision(self, path: Path) -> tuple[bool, str | None]:
        """Restore an atomic replacement unless its published state changed."""
        publication = self._publications.get(path)
        if publication is None:
            return False, None
        try:
            current = _observe_skill_target(path)
        except BaseException as exc:
            return (
                False,
                f"target {path}: rollback could not verify current state "
                f"({type(exc).__name__}: {exc}); current content was preserved",
            )
        if current != publication.published_state:
            retained = (
                f"; prior target retained at {publication.backup}"
                if publication.backup is not None
                else ""
            )
            return (
                False,
                f"target {path}: content changed after the transaction write; "
                f"the conflicting content was preserved{retained}",
            )
        backup = publication.backup
        if backup is None:
            if path.is_dir():
                shutil.rmtree(path)
        elif current.kind == "absent":
            _atomic_rename_noreplace(backup, path)
        else:
            _atomic_exchange(path, backup)
            if backup.is_dir():
                shutil.rmtree(backup)
        return False, None

    def _require_publication_matches(self, path: Path) -> None:
        """Require both sides of one atomic publication to retain exact state."""
        publication = self._publications[path]
        if _observe_skill_target(path) != publication.published_state:
            raise CommandError(f"Published Skill target changed before commit: {path}.")
        backup = publication.backup
        if backup is not None and (
            _observe_skill_target(backup) != publication.backup_state
        ):
            raise CommandError(
                f"Displaced Skill target changed during publication: {path}."
            )

    def _require_unused(self, path: Path) -> None:
        """Require one covered target without an earlier publication."""
        if self._prepared:
            raise RuntimeError("Skill write journal was already prepared for commit")
        if path not in self._paths:
            raise RuntimeError(f"Write journal does not cover target: {path}")
        if path in self._publications:
            raise RuntimeError(f"Write journal target was already published: {path}")


@contextmanager
def skill_write_transaction(
    paths: Iterator[Path] | Collection[Path],
    registry: Registry,
    *,
    file_paths: Collection[Path] = (),
    externally_locked: bool = False,
    guarded_rollback: bool = False,
) -> Iterator[_SkillWriteJournal]:
    """Restore transaction-owned target states when a managed write fails.

    ``externally_locked`` is reserved for a transaction coordinator that
    already holds the deployment and registry locks continuously, in that
    order. Ordinary callers must use the default.

    ``guarded_rollback`` is reserved for callers that publish through the
    yielded journal. Such rollback preserves an untouched target and any
    target changed after the journal's atomic publication.
    """
    unique_paths = tuple(dict.fromkeys(Path(path) for path in paths))
    unique_files = tuple(dict.fromkeys(Path(path) for path in file_paths))
    journal = _SkillWriteJournal(
        unique_paths,
        registry.state_dir / RETAINED_SKILLS_DIRECTORY,
    )
    deployment_lock = (
        nullcontext() if externally_locked else registry.deployment_locked()
    )
    with deployment_lock:
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
                with registry.transaction(externally_locked=externally_locked):
                    yield journal
                journal.commit()
            except BaseException as primary:
                cleanup_failures: list[str] = []
                for path, backup in reversed(snapshots):
                    if guarded_rollback:
                        restore, conflict = journal.rollback_decision(path)
                        if conflict is not None:
                            cleanup_failures.append(conflict)
                        if not restore:
                            continue
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
