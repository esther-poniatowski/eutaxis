"""Project authenticated resolution into concise artifact-facade reports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
from typing import cast

from .external_composition import (
    plan_external_cumulative_composition,
    render_external_cumulative_markdown,
)
from .external_resolution import (
    ExternalResolutionResult,
    _issued_external_resolution_state,
    resolve_external_compilation_unit,
)
from .external_result import (
    _retire_external_result_tree,
    acquire_external_declarations_from_path,
)
from .models import (
    CompositionManifestDeclaration,
    CumulativeMarkdownProfile,
    JsonValue,
)
from .query_packet import QuerySourceRevision, build_external_query_packet


@dataclass(frozen=True)
class ResolvedArtifactSelection:
    """Identify one resolved artifact and its ordered effective records."""

    manifest: str
    mechanism: str
    scope: str
    target: str
    records: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedCumulativeSource:
    """Bind certified inputs and selection to exact cumulative candidate bytes."""

    selection: ResolvedArtifactSelection
    source_revisions: tuple[QuerySourceRevision, ...]
    content: bytes
    sha256: str
    contributors: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        """Decode the certified candidate as strict UTF-8."""
        return self.content.decode("utf-8", errors="strict")


def resolved_artifact_selection(
    result: ExternalResolutionResult,
) -> ResolvedArtifactSelection:
    """Return the concise facade projection of an authenticated resolution."""
    state = _issued_external_resolution_state(result)
    declaration = state.resolution.manifest_record.declaration
    if not isinstance(declaration, CompositionManifestDeclaration):
        raise TypeError("resolved artifact selection requires a composition manifest")
    manifest = cast(CompositionManifestDeclaration, declaration)
    return ResolvedArtifactSelection(
        manifest=manifest.id,
        mechanism=manifest.mechanism.value,
        scope=manifest.scope,
        target=manifest.target,
        records=tuple(
            component.declaration for component in state.resolution.unit.components
        ),
    )


def resolve_external_cumulative_source_from_path(
    workspace: str,
    acquisition_manifest: str,
    acquisition_lock: str,
    composition_manifest: str,
    context: Mapping[str, JsonValue],
) -> ResolvedCumulativeSource:
    """Issue one immutable candidate plan before retiring source authority."""
    acquisition = acquire_external_declarations_from_path(
        workspace,
        acquisition_manifest,
        acquisition_lock,
    )
    try:
        result = resolve_external_compilation_unit(
            acquisition,
            composition_manifest,
            context,
        )
        plan = plan_external_cumulative_composition(result)
        artifact = render_external_cumulative_markdown(
            plan,
            profile=CumulativeMarkdownProfile.AGENT_INSTRUCTIONS,
        )
        source_revisions = build_external_query_packet(result).source_revisions
        content = bytes(artifact.content)
        return ResolvedCumulativeSource(
            selection=resolved_artifact_selection(result),
            source_revisions=source_revisions,
            content=content,
            sha256="sha256:" + hashlib.sha256(content).hexdigest(),
            contributors=artifact.contributors,
        )
    finally:
        _retire_external_result_tree(acquisition)
