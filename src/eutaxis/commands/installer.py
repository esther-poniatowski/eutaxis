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
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .adapters import AgentAdapter
from .exceptions import OwnershipError
from .models import ArtifactFile, CommandSource, InstallRecord, RenderedArtifact
from .registry import Registry, utcnow_iso
from .rendering import (
    ENTRYPOINT_FILENAME,
    OWNED_FRONTMATTER_KEY,
    SIDECAR_FILENAME,
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
    rendered = render_command(
        source, adapter, project_root=project_root, home=home
    )
    target_dir = adapter.artifact_dir(
        source.name, scope, home=home, project_root=project_root
    )
    for artifact_file in rendered.files:
        _owned_path(target_dir, artifact_file.relative_path)

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
                source=source,
                adapter=adapter,
                scope=scope,
                target_dir=target_dir,
                content_hash=rendered.content_hash,
            )
            return InstallOutcome(
                name=source.name,
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
        source=source,
        adapter=adapter,
        scope=scope,
        target_dir=target_dir,
        content_hash=rendered.content_hash,
    )

    return InstallOutcome(
        name=source.name,
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
    """Remove one installed artifact and drop its registry row."""
    target_dir = adapter.artifact_dir(
        name, scope, home=home, project_root=project_root
    )

    if target_dir.is_symlink():
        raise OwnershipError(
            f"Refusing to uninstall through symbolic-link target: {target_dir}."
        )
    if not target_dir.exists():
        registry.remove(
            name=name, adapter=adapter.name, scope=scope, path=target_dir
        )
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
    registry.remove(
        name=name, adapter=adapter.name, scope=scope, path=target_dir
    )
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
    rendered = render_command(
        source, adapter, project_root=project_root, home=home
    )
    target_dir = adapter.artifact_dir(
        source.name, scope, home=home, project_root=project_root
    )

    diff_chunks: list[str] = []
    rendered_files = {
        f.relative_path: f.content
        for f in rendered.files
        if f.relative_path != SIDECAR_FILENAME
    }
    paths = sorted(rendered_files)
    for rel in paths:
        on_disk_path = target_dir / rel
        existing = on_disk_path.read_text(encoding="utf-8") if on_disk_path.is_file() else ""
        chunk = "".join(
            difflib.unified_diff(
                existing.splitlines(keepends=True),
                rendered_files[rel].splitlines(keepends=True),
                fromfile=str(on_disk_path),
                tofile=f"{on_disk_path} (rendered)",
            )
        )
        if chunk:
            diff_chunks.append(chunk)
    for rel in _stale_owned_paths(target_dir, rendered):
        stale_path = target_dir / rel
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


def _stale_owned_paths(target_dir: Path, rendered: RenderedArtifact) -> list[str]:
    """Return owned paths on disk that the rendered artifact no longer holds."""
    if not (target_dir / SIDECAR_FILENAME).is_file():
        return []
    existing = _read_existing(target_dir)
    rendered_paths = {f.relative_path for f in rendered.files}
    return sorted(
        rel
        for rel in existing.owned_paths
        if rel not in rendered_paths and (target_dir / rel).is_file()
    )


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
        return _ExistingArtifact(
            eutaxis_owned=False, owned_paths=(), content_hash=None
        )
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
            return stripped[len(prefix):].strip().strip("'\"") or None
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
            f"Ownership sidecar at {source} contains unsafe path "
            f"{relative_path!r}."
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
    source: CommandSource,
    adapter: AgentAdapter,
    scope: str,
    target_dir: Path,
    content_hash: str,
) -> None:
    """Ensure the registry describes the artifact currently on disk."""
    current = registry.find(
        name=source.name,
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
            name=source.name,
            adapter=adapter.name,
            scope=scope,
            path=target_dir,
            content_hash=content_hash,
            installed_at=utcnow_iso(),
        )
    )
