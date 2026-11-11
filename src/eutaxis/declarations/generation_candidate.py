"""Assemble authenticated canonical lock candidates from private observations."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple, NoReturn, SupportsIndex

from ._authority import IdentityAuthorityStore, identity_value_state
from .acquisition_contract import (
    AcquisitionLock,
    AcquisitionManifest,
    ExternalSourceLock,
    FacetConstituentLock,
    FacetRegistryLock,
    InternalSourceLock,
    _parse_acquisition_manifest_bytes,
    acquisition_lock_json_bytes,
    composite_facet_content_revision,
    parse_acquisition_lock_bytes,
)
from .acquisition_paths import AcquisitionPathError, normalized_relative_path
from .byte_carriers import (
    TrustedDirectory,
    VerifiedByteCarrier,
    _issued_retained_context,
    _verified_carrier_context,
)
from .exceptions import AcquisitionContractError
from .generation_sources import (
    _WorkspaceGenerationObservation,
    _issued_workspace_generation_state,
    _observe_workspace_generation,
    _retire_workspace_generation_observation,
    _workspace_generation_components,
)
from .packaged_source import (
    _PackagedGenerationObservation,
    _issued_packaged_generation_state,
    _observe_running_packaged_generation,
    _packaged_generation_components,
    _retire_packaged_generation_observation,
)


class _GeneratedCandidateState(NamedTuple):
    """Bind canonical candidate bytes to their complete generation evidence."""

    workspace: TrustedDirectory
    workspace_root_path: str
    workspace_root_device: int
    workspace_root_inode: int
    manifest_path: str
    manifest_evidence: VerifiedByteCarrier
    manifest: AcquisitionManifest
    manifest_state: object
    packaged: _PackagedGenerationObservation
    external: _WorkspaceGenerationObservation
    lock: AcquisitionLock
    lock_state: object
    canonical_bytes: bytes
    parsed_lock: AcquisitionLock
    parsed_lock_state: object


class _GeneratedCandidate:
    """Represent one private single-use canonical lock candidate."""

    __slots__ = ("__weakref__",)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("generated candidates must be issued by generation")

    def __copy__(self) -> NoReturn:
        raise TypeError("generated candidates cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("generated candidates cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("generated candidates cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("generated candidates cannot be serialized")


_GENERATED_CANDIDATE_AUTHORITIES: IdentityAuthorityStore[object] = (
    IdentityAuthorityStore()
)


def _generate_workspace_candidate(
    workspace: TrustedDirectory,
    manifest_path: str,
) -> _GeneratedCandidate:
    """Generate one canonical candidate from a retained workspace manifest."""
    normalized_manifest_path = _normalized_manifest_path(manifest_path)
    packaged: _PackagedGenerationObservation | None = None
    external: _WorkspaceGenerationObservation | None = None
    try:
        with workspace.retain_directory(".") as workspace_root:
            workspace_root_path, workspace_root_identity = _issued_retained_context(
                workspace_root
            )
            manifest_authoritative = workspace_root.read_authoritative(
                normalized_manifest_path
            )
            manifest = _parse_acquisition_manifest_bytes(
                manifest_authoritative.data,
                path=Path(normalized_manifest_path),
            )
            packaged = _observe_running_packaged_generation()
            external = _observe_workspace_generation(workspace, manifest)
            lock = _candidate_lock(packaged, external)
            canonical_bytes = acquisition_lock_json_bytes(manifest, lock)
            parsed_lock = parse_acquisition_lock_bytes(canonical_bytes)
            if parsed_lock != lock:
                _fail("$.lock", "canonical candidate parses to another lock")
            manifest_evidence = workspace_root.verify(manifest_authoritative)

        result = object.__new__(_GeneratedCandidate)
        state = _GeneratedCandidateState(
            workspace,
            workspace_root_path,
            workspace_root_identity.device,
            workspace_root_identity.inode,
            normalized_manifest_path,
            manifest_evidence,
            manifest,
            identity_value_state(manifest),
            packaged,
            external,
            lock,
            identity_value_state(lock),
            canonical_bytes,
            parsed_lock,
            identity_value_state(parsed_lock),
        )
        try:
            _GENERATED_CANDIDATE_AUTHORITIES.issue(result, state)
            _issued_generated_candidate_state(result)
            return result
        except BaseException:
            _GENERATED_CANDIDATE_AUTHORITIES.retire(result)
            raise
    except BaseException as primary_error:
        try:
            _retire_nested_observations(packaged, external)
        except BaseException as cleanup_error:
            raise primary_error from cleanup_error
        raise


def _issued_generated_candidate_state(
    candidate: object,
) -> _GeneratedCandidateState:
    """Authenticate one live candidate and every relation used to build it."""
    if type(candidate) is not _GeneratedCandidate:
        _fail("$", "generated candidate is not issued here")
    state = _GENERATED_CANDIDATE_AUTHORITIES.state(candidate)
    if type(state) is not _GeneratedCandidateState:
        _fail("$", "generated candidate is not issued here")

    with state.workspace.retain_directory(".") as workspace_root:
        root_path, root_identity = _issued_retained_context(workspace_root)
    if (
        root_path != state.workspace_root_path
        or root_identity.device != state.workspace_root_device
        or root_identity.inode != state.workspace_root_inode
    ):
        _fail("$", "candidate workspace root identity changed")

    manifest_root, manifest_identity, manifest_snapshot = _verified_carrier_context(
        state.manifest_evidence
    )
    if (
        manifest_root != state.workspace_root_path
        or manifest_identity.device != state.workspace_root_device
        or manifest_identity.inode != state.workspace_root_inode
        or manifest_snapshot[0] != state.manifest_path
    ):
        _fail("$.manifest", "manifest evidence belongs to another workspace")
    parsed_manifest = _parse_acquisition_manifest_bytes(
        manifest_snapshot[1],
        path=Path(state.manifest_path),
    )
    if (
        identity_value_state(state.manifest) != state.manifest_state
        or parsed_manifest != state.manifest
    ):
        _fail("$.manifest", "manifest value differs from verified bytes")

    packaged_state = _issued_packaged_generation_state(state.packaged)
    external_state = _issued_workspace_generation_state(state.external)
    if (
        external_state.workspace is not state.workspace
        or external_state.manifest is not state.manifest
    ):
        _fail("$.sources", "external observation differs from candidate inputs")
    if packaged_state.facet_lock.namespace != "eutaxis":
        _fail("$.facet-registry.base", "packaged observation is not canonical")

    expected_lock = _candidate_lock(state.packaged, state.external)
    if (
        identity_value_state(state.lock) != state.lock_state
        or state.lock != expected_lock
    ):
        _fail("$.lock", "constructed candidate lock state changed")
    expected_bytes = acquisition_lock_json_bytes(state.manifest, expected_lock)
    if (
        type(state.canonical_bytes) is not bytes
        or state.canonical_bytes != expected_bytes
    ):
        _fail("$.lock", "canonical candidate bytes changed")
    reparsed_lock = parse_acquisition_lock_bytes(state.canonical_bytes)
    if (
        identity_value_state(state.parsed_lock) != state.parsed_lock_state
        or state.parsed_lock != reparsed_lock
        or state.parsed_lock != state.lock
    ):
        _fail("$.lock", "parsed candidate lock differs from canonical bytes")
    return state


def _generated_candidate_payload(
    candidate: object,
) -> tuple[bytes, AcquisitionManifest, AcquisitionLock]:
    """Return exact candidate values only after complete authentication."""
    state = _issued_generated_candidate_state(candidate)
    return state.canonical_bytes, state.manifest, state.parsed_lock


def _retire_generated_candidate(candidate: object) -> None:
    """Retire one candidate and both observations that it exclusively owns."""
    state = _GENERATED_CANDIDATE_AUTHORITIES.retire(candidate)
    if type(state) is not _GeneratedCandidateState:
        _fail("$", "generated candidate is not issued here")
    _retire_nested_observations(state.packaged, state.external)


def _candidate_lock(
    packaged: _PackagedGenerationObservation,
    external: _WorkspaceGenerationObservation,
) -> AcquisitionLock:
    """Construct the complete lock represented by two authenticated observers."""
    base, internal = _packaged_generation_components(packaged)
    sources, extensions = _workspace_generation_components(external)
    return _lock_from_components(base, internal, sources, extensions)


def _lock_from_components(
    base: FacetConstituentLock,
    internal: InternalSourceLock,
    sources: tuple[ExternalSourceLock, ...],
    extensions: tuple[FacetConstituentLock, ...],
) -> AcquisitionLock:
    """Construct one detached lock from already-authenticated components."""
    composite_revision = composite_facet_content_revision(
        base.content_revision,
        tuple(extension.content_revision for extension in extensions),
    )
    return AcquisitionLock(
        FacetRegistryLock(base, composite_revision, extensions),
        internal,
        1,
        sources,
    )


def _retire_nested_observations(
    packaged: _PackagedGenerationObservation | None,
    external: _WorkspaceGenerationObservation | None,
) -> None:
    """Retire both owned observations while preserving the first cleanup failure."""
    first_error: BaseException | None = None
    if external is not None:
        try:
            _retire_workspace_generation_observation(external)
        except BaseException as exc:
            first_error = exc
    if packaged is not None:
        try:
            _retire_packaged_generation_observation(packaged)
        except BaseException as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise first_error


def _normalized_manifest_path(value: object) -> str:
    """Validate one caller-supplied workspace-relative manifest path."""
    try:
        return normalized_relative_path(value, allow_dot=False)
    except AcquisitionPathError as exc:
        raise AcquisitionContractError("$.manifest-path", str(exc)) from exc


def _fail(location: str, message: str) -> NoReturn:
    raise AcquisitionContractError(location, message)
