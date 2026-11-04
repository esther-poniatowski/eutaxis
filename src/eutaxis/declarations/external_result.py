"""Publish authenticated external declarations as one opaque capability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple, NoReturn, SupportsIndex, cast

from ._authority import IdentityAuthorityStore, identity_value_state
from ._external_evidence import (
    _EVIDENCE_AUTHORITIES,
    _FinalEvidenceState,
)
from .acquisition_contract import AcquisitionLock, AcquisitionManifest
from .byte_carriers import TrustedDirectory
from .composite_facets import CompositeFacetRegistry
from .exceptions import AcquisitionContractError
from .external_acquisition import (
    _ExternalAcquisitionStage,
    _ExternalAcquisitionStageState,
    _acquire_external_stage,
    _acquire_external_stage_from_path,
    _issued_external_stage_state,
    _retire_stage_tree,
)
from .external_registry import (
    _ExternalRegistryResult,
    _ExternalRegistryState,
    _issue_external_declaration_registry,
    _issued_external_registry_state,
    _retire_external_registry,
)
from .loader import LoadedDeclarationSource
from .registry import DeclarationRegistry


@dataclass(frozen=True)
class AcquisitionSourceCoordinate:
    """Identify one acquired declaration file without transport-specific paths."""

    namespace: str
    path: str
    sha256: str


class _ExternalAcquisitionResultState(NamedTuple):
    """Retain the exact private authority graph behind one public result."""

    stage: _ExternalAcquisitionStage
    stage_state: _ExternalAcquisitionStageState
    external_registry: _ExternalRegistryResult
    external_registry_state: _ExternalRegistryState
    evidence_state: _FinalEvidenceState
    source_coordinates: tuple[AcquisitionSourceCoordinate, ...]
    coordinate_state: object
    source_map: tuple[tuple[LoadedDeclarationSource, AcquisitionSourceCoordinate], ...]


class ExternalAcquisitionResult:
    """Retain one fully verified external declaration corpus.

    Instances are process-local capabilities. Eutaxis issues them only after
    byte, transport, declaration, and cross-record checks all succeed.
    """

    __slots__ = ("__weakref__",)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("external acquisition results must be issued")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("external acquisition results cannot be subclassed")

    @property
    def manifest(self) -> AcquisitionManifest:
        """Return the exact manifest admitted by this acquisition."""
        return _issued_external_result_state(self).evidence_state.manifest

    @property
    def lock(self) -> AcquisitionLock:
        """Return the exact canonical lock admitted by this acquisition."""
        return _issued_external_result_state(self).evidence_state.lock

    @property
    def facet_registry(self) -> CompositeFacetRegistry:
        """Return the issued composite facet registry used for parsing."""
        composite = _issued_external_result_state(self).stage_state.composite
        return cast(CompositeFacetRegistry, composite)

    @property
    def source_coordinates(self) -> tuple[AcquisitionSourceCoordinate, ...]:
        """Return portable declaration coordinates in acquisition order."""
        return _issued_external_result_state(self).source_coordinates

    def __copy__(self) -> NoReturn:
        raise TypeError("external acquisition results cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("external acquisition results cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("external acquisition results cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("external acquisition results cannot be serialized")


_RESULT_AUTHORITIES: IdentityAuthorityStore[object] = IdentityAuthorityStore()


def acquire_external_declarations(
    workspace: TrustedDirectory,
    manifest_path: str,
    lock_path: str,
) -> ExternalAcquisitionResult:
    """Acquire external declarations through a caller-owned workspace capability."""
    stage = _acquire_external_stage(workspace, manifest_path, lock_path)
    return _publish_external_result(stage)


def acquire_external_declarations_from_path(
    workspace_path: str,
    manifest_path: str,
    lock_path: str,
) -> ExternalAcquisitionResult:
    """Acquire external declarations through an exact workspace path."""
    stage = _acquire_external_stage_from_path(
        workspace_path,
        manifest_path,
        lock_path,
    )
    return _publish_external_result(stage)


def _publish_external_result(
    stage: _ExternalAcquisitionStage,
) -> ExternalAcquisitionResult:
    """Build the combined registry and transfer stage ownership to one result."""
    external_registry: _ExternalRegistryResult | None = None
    try:
        external_registry = _issue_external_declaration_registry(stage)
        return _issue_external_result(stage, external_registry)
    except BaseException:
        if external_registry is not None:
            _retire_external_registry(external_registry)
        _retire_stage_tree(stage)
        raise


def _issue_external_result(
    stage: _ExternalAcquisitionStage,
    external_registry: _ExternalRegistryResult,
) -> ExternalAcquisitionResult:
    """Issue a result only from one authenticated stage and its exact registry."""
    stage_state = _issued_external_stage_state(stage)
    registry_state = _issued_external_registry_state(external_registry)
    if (
        registry_state.stage is not stage
        or registry_state.stage_state is not stage_state
    ):
        _fail("$.registry", "external registry belongs to another stage")
    evidence_state = _EVIDENCE_AUTHORITIES.state(stage_state.evidence)
    if type(evidence_state) is not _FinalEvidenceState:
        _fail("$", "external acquisition evidence is not final")
    source_coordinates, source_map = _derive_source_coordinates(
        stage_state,
        evidence_state,
    )
    result = object.__new__(ExternalAcquisitionResult)
    state = _ExternalAcquisitionResultState(
        stage=stage,
        stage_state=stage_state,
        external_registry=external_registry,
        external_registry_state=registry_state,
        evidence_state=evidence_state,
        source_coordinates=source_coordinates,
        coordinate_state=identity_value_state(source_coordinates),
        source_map=source_map,
    )
    try:
        _RESULT_AUTHORITIES.issue(result, state)
        _issued_external_result_state(result)
        return result
    except BaseException:
        _RESULT_AUTHORITIES.retire(result)
        raise


def _issued_external_result_state(
    result: object,
) -> _ExternalAcquisitionResultState:
    """Authenticate a public result and every private aggregate it retains."""
    try:
        return _authenticate_external_result_state(result)
    except BaseException:
        _retire_external_result_tree(result)
        raise


def _authenticate_external_result_state(
    result: object,
) -> _ExternalAcquisitionResultState:
    """Return one complete result state after checking its authority graph."""
    if type(result) is not ExternalAcquisitionResult:
        _fail("$", "external acquisition result is not issued here")
    state = _RESULT_AUTHORITIES.state(result)
    if type(state) is not _ExternalAcquisitionResultState:
        _fail("$", "external acquisition result is not issued here")
    stage_state = _issued_external_stage_state(state.stage)
    if stage_state is not state.stage_state:
        _fail("$", "external acquisition stage state changed")
    evidence_state = _EVIDENCE_AUTHORITIES.state(stage_state.evidence)
    if evidence_state is not state.evidence_state:
        _fail("$", "external acquisition evidence state changed")
    registry_state = _issued_external_registry_state(state.external_registry)
    if registry_state is not state.external_registry_state:
        _fail("$.registry", "external registry authority state changed")
    if registry_state.stage is not state.stage:
        _fail("$.registry", "external registry belongs to another stage")
    _validate_registry_sources(registry_state.registry, stage_state.declarations)
    expected = _coordinate_inputs(stage_state, state.evidence_state)
    _validate_source_coordinates(state, expected)
    return state


def _derive_source_coordinates(
    stage_state: _ExternalAcquisitionStageState,
    evidence_state: _FinalEvidenceState,
) -> tuple[
    tuple[AcquisitionSourceCoordinate, ...],
    tuple[tuple[LoadedDeclarationSource, AcquisitionSourceCoordinate], ...],
]:
    """Derive portable coordinates only from retained declarations and locks."""
    inputs = _coordinate_inputs(stage_state, evidence_state)
    coordinates = tuple(
        AcquisitionSourceCoordinate(namespace, path, sha256)
        for _source, namespace, path, sha256 in inputs
    )
    source_map = tuple(
        (item[0], coordinate)
        for item, coordinate in zip(inputs, coordinates, strict=True)
    )
    return coordinates, source_map


def _coordinate_inputs(
    stage_state: _ExternalAcquisitionStageState,
    evidence_state: _FinalEvidenceState,
) -> tuple[tuple[LoadedDeclarationSource, str, str, str], ...]:
    """Correlate each parsed source with its authenticated logical coordinate."""
    declarations = stage_state.declarations
    packaged_files = evidence_state.lock.internal_source.files
    inputs: list[tuple[LoadedDeclarationSource, str, str, str]] = []
    offset = 0
    for source, locked_file in zip(
        declarations[: len(packaged_files)],
        packaged_files,
        strict=True,
    ):
        inputs.append((source, "eutaxis", locked_file.path, locked_file.sha256))
        offset += 1
    for external in evidence_state.sources:
        count = len(external.declarations)
        stage_sources = declarations[offset : offset + count]
        if len(stage_sources) != count or any(
            stage_source is not external_source
            for stage_source, external_source in zip(
                stage_sources,
                external.declarations,
                strict=True,
            )
        ):
            _fail(
                f"$.sources[{external.position}].files",
                "parsed declarations differ from final source evidence",
            )
        for source, locked_file in zip(
            external.declarations,
            external.lock.files,
            strict=True,
        ):
            inputs.append(
                (
                    source,
                    external.manifest.namespace,
                    locked_file.path,
                    locked_file.sha256,
                )
            )
        offset += count
    if offset != len(declarations):
        _fail("$.sources", "coordinate count differs from parsed declarations")
    return tuple(inputs)


def _validate_registry_sources(
    registry: DeclarationRegistry,
    declarations: tuple[LoadedDeclarationSource, ...],
) -> None:
    """Require registry paths and records to retain the exact acquired sources."""
    if len(registry.paths) != len(declarations) or any(
        path is not source.path
        for path, source in zip(registry.paths, declarations, strict=True)
    ):
        _fail("$.registry.paths", "registry paths differ from acquired sources")
    registered = tuple(registry.records.values()) + tuple(
        record
        for family in registry.families.values()
        for record in family.versions.values()
    )
    for record in registered:
        if not any(record.source is source for source in declarations):
            _fail("$.registry.records", "registry record has an unknown source")


def _validate_source_coordinates(
    state: _ExternalAcquisitionResultState,
    expected: tuple[tuple[LoadedDeclarationSource, str, str, str], ...],
) -> None:
    """Match every public coordinate with its exact private source and lock row."""
    if identity_value_state(state.source_coordinates) != state.coordinate_state:
        _fail("$.source-coordinates", "source coordinate state changed")
    if len(state.source_coordinates) != len(expected) or len(state.source_map) != len(
        expected
    ):
        _fail("$.source-coordinates", "source coordinate count changed")
    for index, (coordinate, mapped, item) in enumerate(
        zip(state.source_coordinates, state.source_map, expected, strict=True)
    ):
        source, namespace, path, sha256 = item
        mapped_source, mapped_coordinate = mapped
        if (
            type(coordinate) is not AcquisitionSourceCoordinate
            or mapped_source is not source
            or mapped_coordinate is not coordinate
            or coordinate.namespace != namespace
            or coordinate.path != path
            or coordinate.sha256 != sha256
        ):
            _fail(
                f"$.source-coordinates[{index}]",
                "source coordinate differs from acquired evidence",
            )


def _retire_external_result_tree(result: object) -> None:
    """Retire one public result and every private authority that it owns."""
    state = _RESULT_AUTHORITIES.retire(result)
    if type(state) is _ExternalAcquisitionResultState:
        _retire_external_registry(state.external_registry)
        _retire_stage_tree(state.stage)


def _fail(location: str, message: str) -> NoReturn:
    raise AcquisitionContractError(location, message)
