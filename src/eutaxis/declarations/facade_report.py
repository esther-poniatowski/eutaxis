"""Project authenticated resolution into concise artifact-facade reports."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import hashlib
from typing import cast

from .external_composition import (
    ExternalCumulativeArtifact,
    plan_external_cumulative_composition,
    render_external_cumulative_markdown,
    render_external_cumulative_markdowns,
)
from .external_resolution import (
    ExternalResolutionResult,
    _issued_external_resolution_state,
    resolve_external_compilation_unit,
)
from .external_result import (
    ExternalAcquisitionResult,
    _authenticated_external_result_operation,
    open_external_declaration_acquisition_from_path,
)
from .models import (
    CompositionManifestDeclaration,
    CumulativeMarkdownProfile,
    JsonValue,
    freeze_json,
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


@dataclass(frozen=True)
class ExternalCumulativeSourceRequest:
    """Describe one cumulative source to snapshot at batch entry."""

    composition_manifest: str
    context: Mapping[str, JsonValue]


@dataclass(frozen=True)
class _FrozenExternalCumulativeSourceRequest:
    """Retain one validated request snapshot inside an acquisition operation."""

    composition_manifest: str
    context: Mapping[str, JsonValue]


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


def resolve_external_cumulative_source(
    acquisition: ExternalAcquisitionResult,
    composition_manifest: str,
    context: Mapping[str, JsonValue],
) -> ResolvedCumulativeSource:
    """Project one cumulative source from a caller-owned acquisition."""

    def resolve() -> ResolvedCumulativeSource:
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

    return _authenticated_external_result_operation(acquisition, resolve)


def resolve_external_cumulative_sources(
    acquisition: ExternalAcquisitionResult,
    requests: Iterable[ExternalCumulativeSourceRequest],
) -> tuple[ResolvedCumulativeSource, ...]:
    """Resolve ordered cumulative sources under one acquisition boundary."""
    return _authenticated_external_result_operation(
        acquisition,
        lambda: _resolve_external_cumulative_sources(acquisition, requests),
    )


def _resolve_external_cumulative_sources(
    acquisition: ExternalAcquisitionResult,
    requests: Iterable[ExternalCumulativeSourceRequest],
) -> tuple[ResolvedCumulativeSource, ...]:
    """Snapshot every request before resolving any member of the batch."""
    snapshots = tuple(_snapshot_cumulative_source_request(item) for item in requests)
    resolutions = tuple(
        resolve_external_compilation_unit(
            acquisition,
            item.composition_manifest,
            item.context,
        )
        for item in snapshots
    )
    plans = tuple(plan_external_cumulative_composition(item) for item in resolutions)
    artifacts = render_external_cumulative_markdowns(
        acquisition,
        plans,
        profile=CumulativeMarkdownProfile.AGENT_INSTRUCTIONS,
    )
    return tuple(
        _resolved_cumulative_source(resolution, artifact)
        for resolution, artifact in zip(resolutions, artifacts, strict=True)
    )


def _resolved_cumulative_source(
    result: ExternalResolutionResult,
    artifact: ExternalCumulativeArtifact,
) -> ResolvedCumulativeSource:
    """Project one detached cumulative-source report from issued objects."""
    content = bytes(artifact.content)
    return ResolvedCumulativeSource(
        selection=resolved_artifact_selection(result),
        source_revisions=build_external_query_packet(result).source_revisions,
        content=content,
        sha256="sha256:" + hashlib.sha256(content).hexdigest(),
        contributors=artifact.contributors,
    )


def _snapshot_cumulative_source_request(
    request: ExternalCumulativeSourceRequest,
) -> _FrozenExternalCumulativeSourceRequest:
    """Deep-freeze one exact batch request inside its authority bracket."""
    if type(request) is not ExternalCumulativeSourceRequest:
        raise TypeError("cumulative source request has an invalid type")
    if type(request.composition_manifest) is not str or not request.composition_manifest:
        raise ValueError("cumulative source request manifest must be a non-empty string")
    frozen_context = freeze_json(request.context)
    if not isinstance(frozen_context, Mapping):
        raise TypeError("cumulative source request context must be a mapping")
    return _FrozenExternalCumulativeSourceRequest(
        composition_manifest=request.composition_manifest,
        context=cast(Mapping[str, JsonValue], frozen_context),
    )


def resolve_external_cumulative_source_from_path(
    workspace: str,
    acquisition_manifest: str,
    acquisition_lock: str,
    composition_manifest: str,
    context: Mapping[str, JsonValue],
) -> ResolvedCumulativeSource:
    """Issue one immutable candidate plan from one bounded acquisition."""
    with open_external_declaration_acquisition_from_path(
        workspace,
        acquisition_manifest,
        acquisition_lock,
    ) as acquisition:
        return resolve_external_cumulative_source(
            acquisition,
            composition_manifest,
            context,
        )
