"""Per-agent adapter registry for skill-style artifacts.

Each adapter describes how one render input compiles into an Agent Skill
directory native to the target agent: the on-disk location, the
``SKILL.md`` frontmatter convention, and the sibling files (e.g.
``agents/openai.yaml`` for Codex). The source layer stays
adapter-neutral; adding a new agent is one ``register_adapter`` call
plus one adapter class.
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Protocol, runtime_checkable

from ..exceptions import CommandError
from ..models import ArtifactFile, SkillRenderInput


@runtime_checkable
class AgentAdapter(Protocol):
    """Adapter contract.

    Attributes
    ----------
    name : str
        Adapter identifier (``"claude"``, ``"codex"``, ...).
    """

    @property
    def name(self) -> str:
        """Adapter identifier used in configuration and output paths."""
        ...

    def supports_scope(self, scope: str) -> bool:
        """Whether ``scope`` (``"user"`` or ``"project"``) is supported."""

    def artifact_dir(
        self, command_name: str, scope: str, *, home: Path, project_root: Path
    ) -> Path:
        """Return the on-disk directory of an installed skill artifact."""

    def skills_root(self, scope: str, *, home: Path, project_root: Path) -> Path:
        """Return the directory containing installed Skill artifacts."""

    def skill_frontmatter(
        self, source: SkillRenderInput, *, rendered_body: str
    ) -> dict[str, object]:
        """Return the adapter-specific ``SKILL.md`` frontmatter as a dict.

        The renderer adds the universal ``x-eutaxis-owned`` hash after
        the adapter is consulted, so adapters must not set that key.
        """

    def sibling_files(self, source: SkillRenderInput) -> Iterable[ArtifactFile]:
        """Return sibling artifact files (other than ``SKILL.md``).

        Passthrough files in ``source`` are already rendered by its source
        converter before being added to the artifact.
        """

    def relative_artifact_link(
        self,
        *,
        from_artifact: str,
        from_file: str,
        to_artifact: str,
        to_file: str,
    ) -> str:
        """Return an installed relative link between two artifact files."""


def sibling_artifact_link(
    *,
    from_artifact: str,
    from_file: str,
    to_artifact: str,
    to_file: str,
) -> str:
    """Return a relative link for adapters with sibling artifact roots."""
    source = PurePosixPath(from_artifact) / PurePosixPath(from_file).parent
    target = PurePosixPath(to_artifact) / PurePosixPath(to_file)
    return posixpath.relpath(str(target), start=str(source))


_REGISTRY: dict[str, AgentAdapter] = {}


def register_adapter(adapter: AgentAdapter) -> None:
    """Register an adapter under ``adapter.name``.

    Re-registering the same name replaces the existing adapter.
    """
    if not adapter.name:
        raise CommandError("Adapter must declare a non-empty name")
    _REGISTRY[adapter.name] = adapter


def get_adapter(name: str) -> AgentAdapter:
    """Return the adapter registered under ``name``."""
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise CommandError(
            f"Unknown agent adapter: {name!r}. " f"Registered: {sorted(_REGISTRY)}"
        ) from exc


def all_adapters() -> list[AgentAdapter]:
    """Return all registered adapters sorted by name."""
    return [_REGISTRY[name] for name in sorted(_REGISTRY)]


def _bootstrap() -> None:
    from .claude import ClaudeCodeAdapter
    from .codex import CodexAdapter

    register_adapter(ClaudeCodeAdapter())
    register_adapter(CodexAdapter())


_bootstrap()
