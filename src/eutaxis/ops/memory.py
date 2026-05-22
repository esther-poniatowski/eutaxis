"""Delete per-project agent memory directories.

Two agents are supported:

- Claude Code stores per-project memory at
  ``~/.claude/projects/<encoded-project>/memory/``. The project slug
  is the absolute project path with ``/`` replaced by ``-`` and the
  leading slash mapped to a leading dash.
- Codex stores a single user-level memory directory at
  ``~/.codex/memories/``.

The wipe operation removes every regular file under the resolved
directory, leaves the directory structure in place, and refuses to
operate on any path that does not lie under the agent's allowed root.
A ``--backup`` mode copies the tree to a sibling
``memory.bak.YYYYMMDD-HHMMSS/`` before deletion. ``--dry-run`` reports
the paths that would be removed without touching the filesystem.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .exceptions import OutsideAllowedRootError

CLAUDE_PROJECTS_ROOT = Path(".claude") / "projects"
CODEX_MEMORIES_ROOT = Path(".codex") / "memories"

_SUPPORTED_AGENTS = frozenset({"claude", "codex", "all"})


@dataclass
class MemoryWipeResult:
    """Outcome of one wipe call."""

    removed: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    backup_paths: list[Path] = field(default_factory=list)
    dry_run: bool = False


def clean_memory(
    *,
    agent: str,
    project_root: Path | None = None,
    wipe_all: bool = False,
    backup: bool = False,
    dry_run: bool = False,
    home: Path | None = None,
) -> MemoryWipeResult:
    """Delete agent memory directories.

    Parameters
    ----------
    agent : str
        ``"claude"``, ``"codex"``, or ``"all"``.
    project_root : Path, optional
        Project root used to derive the Claude project slug. Defaults to
        the current working directory.
    wipe_all : bool
        When true *and* ``agent`` includes ``claude``, wipe every Claude
        project memory under ``~/.claude/projects/*/memory``. Ignored
        for Codex (its memory is already user-level).
    backup : bool
        Copy the resolved directory to a timestamped sibling before
        deletion.
    dry_run : bool
        Resolve and report paths without touching the filesystem.
    home : Path, optional
        Override ``$HOME``. Injected by tests; defaults to
        ``Path.home()``.

    Returns
    -------
    MemoryWipeResult
        Removed regular file paths, plus any backup directories created.

    Raises
    ------
    OpsError
        If ``agent`` is not a supported identifier.
    OutsideAllowedRootError
        If a resolved target escapes its allowed root.
    """
    if agent not in _SUPPORTED_AGENTS:
        from .exceptions import OpsError

        raise OpsError(
            f"Unknown agent {agent!r}; expected one of {sorted(_SUPPORTED_AGENTS)}"
        )

    home_path = (home or Path.home()).expanduser().resolve()
    project = (project_root or Path.cwd()).expanduser().resolve()
    result = MemoryWipeResult(dry_run=dry_run)

    if agent in {"claude", "all"}:
        for target in _claude_targets(home_path, project, wipe_all=wipe_all):
            _wipe_directory(target, home_path / CLAUDE_PROJECTS_ROOT, result, backup=backup, dry_run=dry_run)

    if agent in {"codex", "all"}:
        target = home_path / CODEX_MEMORIES_ROOT
        _wipe_directory(target, home_path / CODEX_MEMORIES_ROOT, result, backup=backup, dry_run=dry_run)

    return result


def encode_project_slug(project_root: Path) -> str:
    """Encode an absolute project path as a Claude project directory name.

    Replaces ``/`` with ``-`` and prepends a leading dash so that
    ``/Users/eresther/oikos`` becomes ``-Users-eresther-oikos``.
    """
    resolved = project_root.expanduser().resolve()
    parts = [part for part in resolved.parts if part not in ("", "/")]
    return "-" + "-".join(parts)


def _claude_targets(
    home: Path, project_root: Path, *, wipe_all: bool
) -> list[Path]:
    root = home / CLAUDE_PROJECTS_ROOT
    if wipe_all:
        if not root.is_dir():
            return []
        return [child / "memory" for child in sorted(root.iterdir()) if child.is_dir()]
    slug = encode_project_slug(project_root)
    return [root / slug / "memory"]


def _wipe_directory(
    target: Path,
    allowed_root: Path,
    result: MemoryWipeResult,
    *,
    backup: bool,
    dry_run: bool,
) -> None:
    if not _is_under(target, allowed_root):
        raise OutsideAllowedRootError(
            f"Resolved target {target} is outside allowed root {allowed_root}"
        )

    if not target.exists():
        result.skipped.append(target)
        return

    if backup and not dry_run and target.is_dir():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = target.with_name(f"{target.name}.bak.{stamp}")
        shutil.copytree(target, backup_path)
        result.backup_paths.append(backup_path)

    if target.is_file():
        if not dry_run:
            target.unlink()
        result.removed.append(target)
        return

    for path in sorted(target.rglob("*")):
        if path.is_file() or path.is_symlink():
            if not _is_under(path.resolve(strict=False), allowed_root):
                raise OutsideAllowedRootError(
                    f"Refusing to delete {path}: outside {allowed_root}"
                )
            if not dry_run:
                path.unlink()
            result.removed.append(path)


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True
