"""Install, uninstall, and diff rendered command artifacts on the filesystem.

The artifact is an Agent Skill directory (multi-file). Ownership is
detected via two mechanisms in priority order:

1. ``.eutaxis-owned.json`` sidecar inside the artifact directory — the
   source of truth for the file list and per-file hashes.
2. ``x-eutaxis-owned`` key inside ``SKILL.md`` frontmatter — fallback if
   the sidecar is missing (e.g. a user deleted it).

A directory that exists but matches neither check is treated as
user-owned and refused unless ``force=True``.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections.abc import Callable, Collection
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from .adapters import AgentAdapter
from .exceptions import CommandRenderError, OwnershipError
from .models import ArtifactFile, CommandSource, InstallRecord, RenderedArtifact
from .registry import Registry, utcnow_iso
from .rendering import (
    ENTRYPOINT_FILENAME,
    OWNED_FRONTMATTER_KEY,
    SIDECAR_FILENAME,
    SIDECAR_SCHEMA,
    render_command,
)


@dataclass(frozen=True)
class InstallOutcome:
    """Result of one install or uninstall operation.

    ``path`` is the artifact **directory**.
    """

    name: str
    adapter: str
    scope: str
    path: Path
    action: str  # "created" | "updated" | "unchanged" | "removed" | "skipped"
    warnings: tuple[str, ...] = ()
    """Warnings of the render, such as a link whose target does not exist."""


def install_command(
    source: CommandSource,
    adapter: AgentAdapter,
    *,
    scope: str,
    project_root: Path,
    home: Path,
    registry: Registry,
    force: bool = False,
) -> InstallOutcome:
    """Render and write one skill artifact to its native location."""
    rendered = render_command(source, adapter, project_root=project_root, home=home)
    rendered = replace(rendered, scope=scope)
    return _install_artifact(
        rendered,
        adapter,
        scope=scope,
        project_root=project_root,
        home=home,
        registry=registry,
        force=force,
    )


def install_artifact(
    rendered: RenderedArtifact,
    adapter: AgentAdapter,
    *,
    scope: str,
    project_root: Path,
    home: Path,
    registry: Registry,
    force: bool = False,
) -> InstallOutcome:
    """Publish one rendered Skill under the deployment lock with rollback."""
    target_dir = adapter.artifact_dir(
        rendered.name, scope, home=home, project_root=project_root
    )
    # Local import avoids the module cycle: synchronization composes the legacy
    # command operations from this module, while this public direct-artifact API
    # owns its single-target transaction.
    from .synchronization import skill_write_transaction

    with skill_write_transaction((target_dir,), registry):
        return _install_artifact(
            rendered,
            adapter,
            scope=scope,
            project_root=project_root,
            home=home,
            registry=registry,
            force=force,
        )


def install_artifacts(
    artifacts: Collection[tuple[RenderedArtifact, AgentAdapter]],
    *,
    project_root: Path,
    home: Path,
    registry: Registry,
    finalize: Callable[[], None] | None = None,
    rollback_files: Collection[Path] = (),
    force: bool = False,
    externally_locked: bool = False,
) -> tuple[InstallOutcome, ...]:
    """Publish several rendered Skills as one failure-atomic write set.

    Parameters
    ----------
    artifacts
        Rendered artifact and matching adapter pairs. Each artifact supplies
        its installation scope.
    project_root
        Project root used to resolve project-scope targets.
    home
        User home used to resolve user-scope targets.
    registry
        Registry updated with the complete installed set.
    finalize
        Optional callback run after every artifact is installed but before the
        transaction commits.
    rollback_files
        State files changed by ``finalize`` and restored if any operation
        fails.
    force
        Whether an existing non-Eutaxis directory may be replaced.
    externally_locked
        Whether a transaction coordinator already holds the deployment and
        registry locks continuously, in canonical order. Ordinary callers
        must use the default.

    Returns
    -------
    tuple of InstallOutcome
        One outcome for each input artifact, in input order.

    Raises
    ------
    CommandRenderError
        If the batch is empty, repeats a target, or contains an invalid
        artifact.
    OwnershipError
        If distinct target paths resolve to the same or nested filesystem
        tree.
    """
    batch = tuple(artifacts)
    if not batch:
        raise CommandRenderError("At least one rendered artifact is required.")

    targets: list[Path] = []
    for rendered, adapter in batch:
        target = adapter.artifact_dir(
            rendered.name,
            rendered.scope,
            home=home,
            project_root=project_root,
        )
        if target in targets:
            raise CommandRenderError(
                f"Rendered artifact batch repeats target: {target}."
            )
        _validated_artifact_paths(rendered, adapter, rendered.scope, target)
        targets.append(target)

    outcomes: list[InstallOutcome] = []
    from .synchronization import skill_write_transaction

    with skill_write_transaction(
        targets,
        registry,
        file_paths=rollback_files,
        externally_locked=externally_locked,
    ):
        for rendered, adapter in batch:
            outcomes.append(
                _install_artifact(
                    rendered,
                    adapter,
                    scope=rendered.scope,
                    project_root=project_root,
                    home=home,
                    registry=registry,
                    force=force,
                )
            )
        if finalize is not None:
            finalize()
    return tuple(outcomes)


def _install_artifact(
    rendered: RenderedArtifact,
    adapter: AgentAdapter,
    *,
    scope: str,
    project_root: Path,
    home: Path,
    registry: Registry,
    force: bool = False,
) -> InstallOutcome:
    """Apply one rendered artifact inside its caller's write transaction."""
    target_dir = adapter.artifact_dir(
        rendered.name, scope, home=home, project_root=project_root
    )
    _validated_artifact_paths(rendered, adapter, scope, target_dir)

    if target_dir.is_symlink():
        raise OwnershipError(
            f"Refusing to install through symbolic-link target: {target_dir}."
        )
    if target_dir.exists():
        existing = _read_existing(target_dir)
        if existing.eutaxis_owned is False and not force:
            raise OwnershipError(
                f"Refusing to overwrite non-eutaxis directory: {target_dir}. "
                "Re-run with --force to overwrite, or back up the contents first."
            )
        if existing.matches(rendered, target_dir):
            _reconcile_registry(
                registry,
                name=rendered.name,
                adapter=adapter,
                scope=scope,
                target_dir=target_dir,
                content_hash=rendered.content_hash,
            )
            return InstallOutcome(
                name=rendered.name,
                adapter=adapter.name,
                scope=scope,
                path=target_dir,
                action="unchanged",
                warnings=rendered.warnings,
            )
        _remove_owned_files(target_dir, existing.owned_paths)
        action = "updated"
    else:
        action = "created"

    target_dir.mkdir(parents=True, exist_ok=True)
    for artifact_file in rendered.files:
        _write_artifact_file(target_dir, artifact_file)

    _reconcile_registry(
        registry,
        name=rendered.name,
        adapter=adapter,
        scope=scope,
        target_dir=target_dir,
        content_hash=rendered.content_hash,
    )

    return InstallOutcome(
        name=rendered.name,
        adapter=adapter.name,
        scope=scope,
        path=target_dir,
        action=action,
        warnings=rendered.warnings,
    )


def uninstall_command(
    *,
    name: str,
    adapter: AgentAdapter,
    scope: str,
    project_root: Path,
    home: Path,
    registry: Registry,
    force: bool = False,
) -> InstallOutcome:
    """Remove one artifact under the deployment lock with rollback."""
    target_dir = adapter.artifact_dir(name, scope, home=home, project_root=project_root)
    from .synchronization import skill_write_transaction

    with skill_write_transaction((target_dir,), registry):
        return _uninstall_command(
            name=name,
            adapter=adapter,
            scope=scope,
            project_root=project_root,
            home=home,
            registry=registry,
            force=force,
        )


def _uninstall_command(
    *,
    name: str,
    adapter: AgentAdapter,
    scope: str,
    project_root: Path,
    home: Path,
    registry: Registry,
    force: bool = False,
) -> InstallOutcome:
    """Remove one artifact inside its caller's write transaction."""
    target_dir = adapter.artifact_dir(name, scope, home=home, project_root=project_root)

    if target_dir.is_symlink():
        raise OwnershipError(
            f"Refusing to uninstall through symbolic-link target: {target_dir}."
        )
    if not target_dir.exists():
        registry.remove(name=name, adapter=adapter.name, scope=scope, path=target_dir)
        return InstallOutcome(
            name=name,
            adapter=adapter.name,
            scope=scope,
            path=target_dir,
            action="skipped",
        )

    existing = _read_existing(target_dir)
    if existing.eutaxis_owned is False and not force:
        raise OwnershipError(
            f"Refusing to delete non-eutaxis directory: {target_dir}. "
            "Re-run with --force to delete."
        )

    _remove_owned_files(target_dir, existing.owned_paths)
    _remove_dir_if_empty(target_dir)
    registry.remove(name=name, adapter=adapter.name, scope=scope, path=target_dir)
    return InstallOutcome(
        name=name,
        adapter=adapter.name,
        scope=scope,
        path=target_dir,
        action="removed",
    )


def diff_command(
    source: CommandSource,
    adapter: AgentAdapter,
    *,
    scope: str,
    project_root: Path,
    home: Path,
) -> tuple[RenderedArtifact, Path, str]:
    """Return rendered artifact, directory, and a unified diff vs disk.

    The diff is computed over the ``SKILL.md`` entrypoint plus all
    rendered sibling files (sorted by path). Missing files on disk are
    treated as empty. A file that the ownership sidecar on disk lists but
    the render no longer produces, such as the file of a deleted rule, is
    reported as a removal.
    """
    rendered = render_command(source, adapter, project_root=project_root, home=home)
    rendered = replace(rendered, scope=scope)
    return diff_artifact(
        rendered,
        adapter,
        scope=scope,
        project_root=project_root,
        home=home,
    )


def diff_artifact(
    rendered: RenderedArtifact,
    adapter: AgentAdapter,
    *,
    scope: str,
    project_root: Path,
    home: Path,
) -> tuple[RenderedArtifact, Path, str]:
    """Return one rendered artifact, its directory, and its diff from disk."""
    target_dir = adapter.artifact_dir(
        rendered.name, scope, home=home, project_root=project_root
    )
    validated_paths = _validated_artifact_paths(rendered, adapter, scope, target_dir)

    diff_chunks: list[str] = []
    rendered_files = {
        artifact.relative_path: (artifact.content, path)
        for artifact, path in validated_paths
        if artifact.relative_path != SIDECAR_FILENAME
    }
    paths = sorted(rendered_files)
    for rel in paths:
        rendered_content, on_disk_path = rendered_files[rel]
        existing = (
            on_disk_path.read_text(encoding="utf-8") if on_disk_path.is_file() else ""
        )
        chunk = "".join(
            difflib.unified_diff(
                existing.splitlines(keepends=True),
                rendered_content.splitlines(keepends=True),
                fromfile=str(on_disk_path),
                tofile=f"{on_disk_path} (rendered)",
            )
        )
        if chunk:
            diff_chunks.append(chunk)
    for rel, stale_path in _stale_owned_paths(target_dir, rendered):
        diff_chunks.append(
            "".join(
                difflib.unified_diff(
                    stale_path.read_text(encoding="utf-8").splitlines(keepends=True),
                    [],
                    fromfile=str(stale_path),
                    tofile=f"{stale_path} (removed)",
                )
            )
        )
    return rendered, target_dir, "".join(diff_chunks)


def verify_artifact(
    rendered: RenderedArtifact,
    adapter: AgentAdapter,
    *,
    scope: str,
    project_root: Path,
    home: Path,
) -> Path:
    """Require the installed artifact to equal the complete rendered tree.

    Unlike :func:`diff_artifact`, this verification includes the ownership
    sidecar and rejects extra entries, symbolic links, and mismatched file or
    directory kinds. It returns the verified artifact directory.
    """
    target_dir = adapter.artifact_dir(
        rendered.name, scope, home=home, project_root=project_root
    )
    validated = _validated_artifact_paths(rendered, adapter, scope, target_dir)
    expected_files = {
        artifact.relative_path: artifact.content.encode("utf-8", errors="strict")
        for artifact, _path in validated
    }
    expected_directories = {
        parent.as_posix()
        for relative_path in expected_files
        for parent in Path(relative_path).parents
        if parent != Path(".")
    }
    if not target_dir.is_dir() or target_dir.is_symlink():
        raise OwnershipError(
            f"Installed artifact is not a regular directory: {target_dir}."
        )
    observed_files: dict[str, bytes] = {}
    observed_directories: set[str] = set()
    for path in target_dir.rglob("*"):
        relative = path.relative_to(target_dir).as_posix()
        if path.is_symlink():
            raise OwnershipError(
                f"Installed artifact contains a symbolic link: {path}."
            )
        if path.is_file():
            observed_files[relative] = path.read_bytes()
        elif path.is_dir():
            observed_directories.add(relative)
        else:
            raise OwnershipError(
                f"Installed artifact contains an unsupported entry: {path}."
            )
    if observed_files != expected_files or observed_directories != expected_directories:
        raise OwnershipError(
            f"Installed artifact tree differs from the rendered artifact: {target_dir}."
        )
    return target_dir


def is_eutaxis_owned(target_dir: Path) -> bool:
    """Return whether ``target_dir`` holds a skill artifact written by eutaxis.

    A directory is eutaxis-owned when its ownership sidecar parses, or when
    its ``SKILL.md`` frontmatter carries the ``x-eutaxis-owned`` marker. A
    missing or empty directory is not an artifact and yields ``False``.
    """
    if not target_dir.is_dir() or not any(target_dir.iterdir()):
        return False
    try:
        return _read_existing(target_dir).eutaxis_owned
    except OwnershipError:
        return False


def _stale_owned_paths(
    target_dir: Path, rendered: RenderedArtifact
) -> list[tuple[str, Path]]:
    """Return validated owned paths absent from the rendered artifact."""
    if not (target_dir / SIDECAR_FILENAME).is_file():
        return []
    existing = _read_existing(target_dir)
    rendered_paths = {f.relative_path for f in rendered.files}
    stale: list[tuple[str, Path]] = []
    for rel in existing.owned_paths:
        if rel in rendered_paths:
            continue
        path = _owned_path(target_dir, rel)
        _reject_symlink_route(target_dir, path)
        if path.is_file():
            stale.append((rel, path))
    return sorted(stale, key=lambda item: item[0])


@dataclass(frozen=True)
class _ExistingArtifact:
    """Snapshot of an existing artifact directory's ownership state."""

    eutaxis_owned: bool
    owned_paths: tuple[str, ...]
    content_hash: str | None

    def matches(self, rendered: RenderedArtifact, target_dir: Path) -> bool:
        """Whether the directory already holds exactly the rendered files.

        The recorded hash alone does not detect a file edited or deleted by
        hand, so every rendered file is also compared with its copy on disk,
        and the owned file set must equal the rendered file set.
        """
        if self.content_hash != rendered.content_hash:
            return False
        rendered_paths = {f.relative_path for f in rendered.files}
        if set(self.owned_paths) != rendered_paths:
            return False
        for artifact_file in rendered.files:
            path = target_dir / artifact_file.relative_path
            if not path.is_file():
                return False
            if path.read_text(encoding="utf-8") != artifact_file.content:
                return False
        return True


def _read_existing(target_dir: Path) -> _ExistingArtifact:
    sidecar_path = target_dir / SIDECAR_FILENAME
    if sidecar_path.is_file():
        try:
            payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise OwnershipError(
                f"Ownership sidecar at {sidecar_path} is corrupted: {exc}. "
                "Remove the directory manually or use --force."
            ) from exc
        if not isinstance(payload, dict):
            raise OwnershipError(
                f"Ownership sidecar at {sidecar_path} must contain a JSON object."
            )
        if payload.get("_schema") != SIDECAR_SCHEMA:
            raise OwnershipError(
                f"Ownership sidecar at {sidecar_path} must declare "
                f"_schema: {SIDECAR_SCHEMA}."
            )
        files = payload.get("files") or []
        if not isinstance(files, list):
            raise OwnershipError(
                f"Ownership sidecar at {sidecar_path} has a non-list files field."
            )
        owned_paths_list: list[str] = []
        for entry in files:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise OwnershipError(
                    f"Ownership sidecar at {sidecar_path} has an invalid file entry."
                )
            rel = entry["path"]
            _owned_path(target_dir, rel, sidecar_path=sidecar_path)
            owned_paths_list.append(rel)
        owned_paths = tuple(owned_paths_list)
        if SIDECAR_FILENAME not in owned_paths:
            owned_paths = owned_paths + (SIDECAR_FILENAME,)
        return _ExistingArtifact(
            eutaxis_owned=True,
            owned_paths=owned_paths,
            content_hash=payload.get("content_hash"),
        )

    skill_md_path = target_dir / ENTRYPOINT_FILENAME
    if skill_md_path.is_file():
        marker = _read_frontmatter_marker(skill_md_path)
        if marker is not None:
            return _ExistingArtifact(
                eutaxis_owned=True,
                owned_paths=(ENTRYPOINT_FILENAME,),
                content_hash=marker,
            )

    # Directory exists but neither marker is present.
    if any(target_dir.iterdir()):
        return _ExistingArtifact(eutaxis_owned=False, owned_paths=(), content_hash=None)
    return _ExistingArtifact(eutaxis_owned=True, owned_paths=(), content_hash=None)


_FRONTMATTER_BLOCK = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def _read_frontmatter_marker(skill_md: Path) -> str | None:
    raw = skill_md.read_text(encoding="utf-8")
    match = _FRONTMATTER_BLOCK.match(raw)
    if match is None:
        return None
    for line in match.group(1).splitlines():
        stripped = line.strip()
        prefix = f"{OWNED_FRONTMATTER_KEY}:"
        if stripped.startswith(prefix):
            return stripped[len(prefix) :].strip().strip("'\"") or None
    return None


def _remove_owned_files(target_dir: Path, owned_paths: tuple[str, ...]) -> None:
    for rel in owned_paths:
        path = _owned_path(target_dir, rel)
        if path.is_file() or path.is_symlink():
            path.unlink()
    # Clean up any now-empty sub-directories left behind.
    _prune_empty_subdirs(target_dir)


def _prune_empty_subdirs(target_dir: Path) -> None:
    for child in sorted(target_dir.rglob("*"), key=lambda p: -len(p.parts)):
        if child.is_symlink():
            continue
        if child.is_dir() and not any(child.iterdir()):
            child.rmdir()


def _remove_dir_if_empty(target_dir: Path) -> None:
    if target_dir.is_dir() and not any(target_dir.iterdir()):
        target_dir.rmdir()


def _write_artifact_file(target_dir: Path, artifact: ArtifactFile) -> None:
    path = target_dir / artifact.relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact.content, encoding="utf-8")


def _owned_path(
    target_dir: Path,
    relative_path: str,
    *,
    sidecar_path: Path | None = None,
) -> Path:
    """Resolve one owned path without permitting escape from the artifact."""
    rel = PurePosixPath(relative_path)
    source = sidecar_path or target_dir / SIDECAR_FILENAME
    if (
        not relative_path
        or rel.is_absolute()
        or any(part in {"", ".", ".."} for part in rel.parts)
    ):
        raise OwnershipError(
            f"Ownership sidecar at {source} contains unsafe path " f"{relative_path!r}."
        )
    path = target_dir.joinpath(*rel.parts)
    root = target_dir.resolve()
    parent = path.parent.resolve(strict=False)
    if parent != root and root not in parent.parents:
        raise OwnershipError(
            f"Ownership sidecar at {source} contains path outside its "
            f"artifact directory: {relative_path!r}."
        )
    return path


def _reconcile_registry(
    registry: Registry,
    *,
    name: str,
    adapter: AgentAdapter,
    scope: str,
    target_dir: Path,
    content_hash: str,
) -> None:
    """Ensure the registry describes the artifact currently on disk."""
    current = registry.find(
        name=name,
        adapter=adapter.name,
        scope=scope,
        path=target_dir,
    )
    if (
        current is not None
        and current.path == target_dir
        and current.content_hash == content_hash
    ):
        return
    registry.upsert(
        InstallRecord(
            name=name,
            adapter=adapter.name,
            scope=scope,
            path=target_dir,
            content_hash=content_hash,
            installed_at=utcnow_iso(),
        )
    )


def _validated_artifact_paths(
    rendered: RenderedArtifact,
    adapter: AgentAdapter,
    scope: str,
    target_dir: Path,
) -> tuple[tuple[ArtifactFile, Path], ...]:
    """Validate one complete artifact before any file is read or changed."""
    if rendered.adapter != adapter.name:
        raise CommandRenderError(
            f"Rendered artifact {rendered.name!r} targets adapter "
            f"{rendered.adapter!r}, not {adapter.name!r}."
        )
    if rendered.scope != scope:
        raise CommandRenderError(
            f"Rendered artifact {rendered.name!r} targets scope "
            f"{rendered.scope!r}, not {scope!r}."
        )
    if target_dir.is_symlink():
        raise OwnershipError(f"Refusing to access symbolic-link target: {target_dir}.")

    validated: list[tuple[ArtifactFile, Path]] = []
    parts_by_path: dict[str, tuple[str, ...]] = {}
    for artifact_file in rendered.files:
        if not isinstance(artifact_file.content, str):
            raise CommandRenderError(
                f"Rendered artifact file {artifact_file.relative_path!r} "
                "must contain text."
            )
        path = _owned_path(target_dir, artifact_file.relative_path)
        candidate_parts = PurePosixPath(artifact_file.relative_path).parts
        for prior_path, prior_parts in parts_by_path.items():
            common = min(len(prior_parts), len(candidate_parts))
            if prior_parts[:common] == candidate_parts[:common]:
                raise CommandRenderError(
                    f"Rendered artifact paths {prior_path!r} and "
                    f"{artifact_file.relative_path!r} collide."
                )
        _reject_symlink_route(target_dir, path)
        parts_by_path[artifact_file.relative_path] = candidate_parts
        validated.append((artifact_file, path))

    files_by_path = {item.relative_path: item for item, _path in validated}
    missing = {
        ENTRYPOINT_FILENAME,
        SIDECAR_FILENAME,
    }.difference(files_by_path)
    if missing:
        raise CommandRenderError(
            f"Rendered artifact {rendered.name!r} is missing required file(s): "
            + ", ".join(sorted(missing))
            + "."
        )
    _validate_rendered_sidecar(rendered, files_by_path)
    return tuple(validated)


def _reject_symlink_route(target_dir: Path, path: Path) -> None:
    """Reject a final or intermediate symbolic link below one artifact root."""
    current = path
    while current != target_dir:
        if current.is_symlink():
            raise OwnershipError(
                f"Refusing to access artifact path through symbolic link: {current}."
            )
        current = current.parent


def _validate_rendered_sidecar(
    rendered: RenderedArtifact,
    files_by_path: dict[str, ArtifactFile],
) -> None:
    """Bind the ownership record to every file of the rendered artifact."""
    sidecar = files_by_path[SIDECAR_FILENAME]
    try:
        payload = json.loads(sidecar.content)
    except json.JSONDecodeError as exc:
        raise CommandRenderError(
            f"Rendered ownership sidecar is invalid JSON: {exc}."
        ) from exc
    if not isinstance(payload, dict):
        raise CommandRenderError("Rendered ownership sidecar must be an object.")
    expected_header = {
        "_schema": SIDECAR_SCHEMA,
        "name": rendered.name,
        "adapter": rendered.adapter,
        "content_hash": rendered.content_hash,
    }
    for key, expected_value in expected_header.items():
        if payload.get(key) != expected_value:
            raise CommandRenderError(
                f"Rendered ownership sidecar field {key!r} does not match "
                "the artifact."
            )

    entries = payload.get("files")
    if not isinstance(entries, list):
        raise CommandRenderError(
            "Rendered ownership sidecar field 'files' must be a list."
        )
    observed: dict[str, str] = {}
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("path"), str)
            or not isinstance(entry.get("sha256"), str)
        ):
            raise CommandRenderError(
                "Rendered ownership sidecar contains an invalid file entry."
            )
        entry_path = entry["path"]
        if entry_path in observed:
            raise CommandRenderError(
                f"Rendered ownership sidecar repeats path {entry_path!r}."
            )
        observed[entry_path] = entry["sha256"]

    expected_files = {
        path: hashlib.sha256(item.content.encode("utf-8")).hexdigest()
        for path, item in files_by_path.items()
        if path != SIDECAR_FILENAME
    }
    if observed != expected_files:
        raise CommandRenderError(
            "Rendered ownership sidecar file inventory does not match the artifact."
        )

    entrypoint = files_by_path[ENTRYPOINT_FILENAME].content
    frontmatter = _FRONTMATTER_BLOCK.match(entrypoint)
    marker: str | None = None
    if frontmatter is not None:
        prefix = f"{OWNED_FRONTMATTER_KEY}:"
        for line in frontmatter.group(1).splitlines():
            stripped = line.strip()
            if stripped.startswith(prefix):
                marker = stripped[len(prefix) :].strip().strip("'\"") or None
                break
    if marker != rendered.content_hash:
        raise CommandRenderError(
            "Rendered entrypoint ownership marker does not match the artifact."
        )
