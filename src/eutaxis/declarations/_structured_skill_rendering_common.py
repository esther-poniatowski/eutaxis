"""Share final host-artifact checks across structured Skill renderers."""

from __future__ import annotations

from ..commands.models import RenderedArtifact
from ..commands.rendering import ENTRYPOINT_FILENAME
from .exceptions import CompositionError


def host_scope(scope: str) -> str:
    """Translate declaration scope into the established adapter vocabulary."""
    if scope == "personal":
        return "user"
    if scope == "project":
        return scope
    raise CompositionError("$.manifest.scope", f"unsupported Skill scope {scope!r}")


def check_budgets(
    artifact: RenderedArtifact,
    *,
    entrypoint_max_bytes: int,
    artifact_max_bytes: int,
) -> None:
    """Enforce both limits on the final host-specific artifact bytes."""
    entrypoint = next(
        file for file in artifact.files if file.relative_path == ENTRYPOINT_FILENAME
    )
    entrypoint_bytes = len(entrypoint.content.encode("utf-8", errors="strict"))
    if entrypoint_bytes > entrypoint_max_bytes:
        raise CompositionError(
            "$.budgets.entrypoint-max-bytes",
            f"SKILL.md uses {entrypoint_bytes} bytes, limit is {entrypoint_max_bytes}",
        )
    artifact_bytes = sum(
        len(file.content.encode("utf-8", errors="strict")) for file in artifact.files
    )
    if artifact_bytes > artifact_max_bytes:
        raise CompositionError(
            "$.budgets.artifact-max-bytes",
            f"complete artifact uses {artifact_bytes} bytes, limit is {artifact_max_bytes}",
        )


def require_positive_budget(value: object, field: str) -> None:
    """Require one exact positive integer budget."""
    if type(value) is not int or value <= 0:
        raise CompositionError(
            f"$.budgets.{field}",
            "budget must be an exact positive integer",
        )
