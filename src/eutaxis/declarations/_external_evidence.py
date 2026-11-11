"""Authenticate private external acquisition evidence."""

from __future__ import annotations

from typing import NamedTuple, NoReturn, SupportsIndex

from ._authority import IdentityAuthorityStore, identity_value_state
from .acquisition_contract import (
    AcquisitionKind,
    AcquisitionLock,
    AcquisitionManifest,
    ExternalSourceLock,
    ExternalSourceManifest,
    FacetConstituentLock,
    FacetExtensionManifest,
    validate_acquisition_contract,
)
from .byte_carriers import (
    AuthoritativeByteCarrier,
    DirectoryIdentity,
    RetainedDirectory,
    VerifiedByteCarrier,
    _authoritative_carrier_context,
    _issued_retained_context,
    _verified_carrier_context,
)
from .exceptions import AcquisitionContractError
from .facets import FacetRegistry
from .loader import LoadedDeclarationSource
from .git_transport import _GitTransportEvidence, _issued_git_transport_state
from .packaged_source import (
    PackagedInternalSource,
    _PackagedFacetRead,
    _issued_packaged_facet_state,
)


class _OpenExternalSource(NamedTuple):
    """Retain one paired source contract and its open root."""

    position: int
    manifest: ExternalSourceManifest
    lock: ExternalSourceLock
    root: RetainedDirectory
    root_path: str
    root_identity: DirectoryIdentity


class _FacetExtensionRead(NamedTuple):
    """Retain one ordered extension parsed from authoritative bytes."""

    position: int
    source_index: int
    manifest: FacetExtensionManifest
    lock: FacetConstituentLock
    authoritative: AuthoritativeByteCarrier
    registry: FacetRegistry
    registry_state: object


class _FinalExternalSource(NamedTuple):
    """Retain verified declarations for one external source."""

    position: int
    manifest: ExternalSourceManifest
    lock: ExternalSourceLock
    root_path: str
    root_identity: DirectoryIdentity
    evidence: tuple[VerifiedByteCarrier, ...]
    declarations: tuple[LoadedDeclarationSource, ...]
    git_evidence: _GitTransportEvidence | None


class _FinalFacetExtension(NamedTuple):
    """Retain one verified extension and its parsed registry."""

    position: int
    source_index: int
    manifest: FacetExtensionManifest
    lock: FacetConstituentLock
    evidence: VerifiedByteCarrier
    registry: FacetRegistry
    registry_state: object


class _ProvisionalEvidenceState(NamedTuple):
    """Bind the complete contract and every facet read before declarations."""

    manifest_authoritative: AuthoritativeByteCarrier
    lock_authoritative: AuthoritativeByteCarrier | None
    generated_candidate: object | None
    manifest: AcquisitionManifest
    manifest_state: object
    lock: AcquisitionLock
    lock_state: object
    workspace_root_path: str
    workspace_root_identity: DirectoryIdentity
    packaged_facet: _PackagedFacetRead
    packaged_facet_state: object
    sources: tuple[_OpenExternalSource, ...]
    extensions: tuple[_FacetExtensionRead, ...]


class _FinalEvidenceState(NamedTuple):
    """Bind the complete verified non-Git source set."""

    manifest_evidence: VerifiedByteCarrier
    lock_evidence: VerifiedByteCarrier | None
    generated_candidate: object | None
    manifest: AcquisitionManifest
    manifest_state: object
    lock: AcquisitionLock
    lock_state: object
    workspace_root_path: str
    workspace_root_identity: DirectoryIdentity
    packaged: PackagedInternalSource
    sources: tuple[_FinalExternalSource, ...]
    extensions: tuple[_FinalFacetExtension, ...]


class _ExternalAcquisitionEvidence:
    """Authenticate one complete external acquisition contract across phases."""

    __slots__ = ("__weakref__",)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("external acquisition evidence must be issued")

    def __copy__(self) -> NoReturn:
        raise TypeError("external acquisition evidence cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("external acquisition evidence cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("external acquisition evidence cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("external acquisition evidence cannot be serialized")


_EVIDENCE_AUTHORITIES: IdentityAuthorityStore[object] = IdentityAuthorityStore()


def _issue_provisional_evidence(
    manifest_authoritative: AuthoritativeByteCarrier,
    lock_authoritative: AuthoritativeByteCarrier | None,
    manifest: AcquisitionManifest,
    lock: AcquisitionLock,
    workspace_root_path: str,
    workspace_root_identity: DirectoryIdentity,
    packaged_facet: _PackagedFacetRead,
    sources: tuple[_OpenExternalSource, ...],
    extensions: tuple[_FacetExtensionRead, ...],
    *,
    generated_candidate: object | None = None,
) -> _ExternalAcquisitionEvidence:
    """Issue the complete correlated source record used by the composite."""
    result = object.__new__(_ExternalAcquisitionEvidence)
    state = _ProvisionalEvidenceState(
        manifest_authoritative,
        lock_authoritative,
        generated_candidate,
        manifest,
        identity_value_state(manifest),
        lock,
        identity_value_state(lock),
        workspace_root_path,
        workspace_root_identity,
        packaged_facet,
        identity_value_state(packaged_facet.registry),
        sources,
        extensions,
    )
    try:
        _EVIDENCE_AUTHORITIES.issue(result, state)
        _provisional_external_facet_state(result)
        return result
    except BaseException:
        _EVIDENCE_AUTHORITIES.retire(result)
        raise


def _finalize_evidence(
    evidence: _ExternalAcquisitionEvidence,
    manifest_evidence: VerifiedByteCarrier,
    lock_evidence: VerifiedByteCarrier | None,
    packaged: PackagedInternalSource,
    sources: tuple[_OpenExternalSource, ...],
    extensions: tuple[_FacetExtensionRead, ...],
    extension_evidence: tuple[VerifiedByteCarrier, ...],
    declaration_evidence: tuple[tuple[VerifiedByteCarrier, ...], ...],
    external_declarations: tuple[LoadedDeclarationSource, ...],
    git_evidence: tuple[_GitTransportEvidence | None, ...],
) -> None:
    """Replace provisional state with complete verified source evidence."""
    provisional = _EVIDENCE_AUTHORITIES.state(evidence)
    if type(provisional) is not _ProvisionalEvidenceState:
        _fail("$", "external acquisition evidence is not provisional")
    declaration_offset = 0
    final_sources: list[_FinalExternalSource] = []
    for source, verified, git_proof in zip(
        sources, declaration_evidence, git_evidence, strict=True
    ):
        count = len(verified)
        loaded = external_declarations[declaration_offset : declaration_offset + count]
        declaration_offset += count
        final_sources.append(
            _FinalExternalSource(
                source.position,
                source.manifest,
                source.lock,
                source.root_path,
                source.root_identity,
                verified,
                loaded,
                git_proof,
            )
        )
    final_extensions = tuple(
        _FinalFacetExtension(
            item.position,
            item.source_index,
            item.manifest,
            item.lock,
            verified,
            item.registry,
            item.registry_state,
        )
        for item, verified in zip(extensions, extension_evidence, strict=True)
    )
    final = _FinalEvidenceState(
        manifest_evidence,
        lock_evidence,
        provisional.generated_candidate,
        provisional.manifest,
        provisional.manifest_state,
        provisional.lock,
        provisional.lock_state,
        provisional.workspace_root_path,
        provisional.workspace_root_identity,
        packaged,
        tuple(final_sources),
        final_extensions,
    )
    _EVIDENCE_AUTHORITIES.issue(evidence, final)
    _issued_external_facet_state(evidence)


def _retire_external_evidence(evidence: object) -> None:
    """Retire one provisional or final evidence authority."""
    _EVIDENCE_AUTHORITIES.retire(evidence)


def _issued_external_facet_state(
    evidence: object,
) -> tuple[
    tuple[FacetRegistry, ...],
    tuple[FacetConstituentLock, ...],
    str,
]:
    """Authenticate finalized evidence and return its facet constituents."""
    if type(evidence) is not _ExternalAcquisitionEvidence:
        _fail("$.facet-registry", "external acquisition evidence is not issued here")
    if type(_EVIDENCE_AUTHORITIES.state(evidence)) is not _FinalEvidenceState:
        _fail("$.facet-registry", "external acquisition evidence is not final")
    return _provisional_external_facet_state(evidence)


def _provisional_external_facet_state(
    evidence: object,
) -> tuple[
    tuple[FacetRegistry, ...],
    tuple[FacetConstituentLock, ...],
    str,
]:
    """Authenticate correlated facet state during or after acquisition."""
    if type(evidence) is not _ExternalAcquisitionEvidence:
        _fail("$.facet-registry", "external acquisition evidence is not issued here")
    state = _EVIDENCE_AUTHORITIES.state(evidence)
    if type(state) is _ProvisionalEvidenceState:
        _validate_contract_state(
            state.manifest,
            state.manifest_state,
            state.lock,
            state.lock_state,
        )
        _validate_provisional_correlations(state)
        manifest_root, manifest_identity, _manifest = _authoritative_carrier_context(
            state.manifest_authoritative
        )
        if (
            manifest_root != state.workspace_root_path
            or manifest_identity != state.workspace_root_identity
        ):
            _fail("$", "manifest belongs to another workspace root")
        _validate_provisional_lock_evidence(state)
        base_registry = state.packaged_facet.registry
        base_lock = state.lock.facet_registry.base
        if identity_value_state(base_registry) != state.packaged_facet_state:
            _fail("$.facet-registry.base", "packaged facet registry changed")
        for source in state.sources:
            root_path, root_identity = _issued_retained_context(source.root)
            if root_path != source.root_path or root_identity != source.root_identity:
                _fail(f"$.sources[{source.position}]", "source root state changed")
        return _provisional_facet_values(state, base_registry, base_lock)
    if type(state) is _FinalEvidenceState:
        _validate_contract_state(
            state.manifest,
            state.manifest_state,
            state.lock,
            state.lock_state,
        )
        _validate_final_correlations(state)
        manifest_root, manifest_identity, _manifest = _verified_carrier_context(
            state.manifest_evidence
        )
        if (
            manifest_root != state.workspace_root_path
            or manifest_identity != state.workspace_root_identity
        ):
            _fail("$", "manifest belongs to another workspace root")
        _validate_final_lock_evidence(state)
        _base_evidence, base_lock, base_registry = _issued_packaged_facet_state(
            state.packaged
        )
        return _final_facet_values(state, base_registry, base_lock)
    _fail("$.facet-registry", "external acquisition evidence is not issued here")


def _validate_provisional_lock_evidence(state: _ProvisionalEvidenceState) -> None:
    """Authenticate exactly one persisted or generated lock source."""
    if state.generated_candidate is None:
        if state.lock_authoritative is None:
            _fail("$.lock", "persisted lock evidence is missing")
        lock_root, lock_identity, _lock = _authoritative_carrier_context(
            state.lock_authoritative
        )
        if (
            lock_root != state.workspace_root_path
            or lock_identity != state.workspace_root_identity
        ):
            _fail("$.lock", "lock belongs to another workspace root")
        return
    if state.lock_authoritative is not None:
        _fail("$.lock", "generated acquisition also retained a persisted lock")
    _validate_generated_candidate_contract(state)


def _validate_final_lock_evidence(state: _FinalEvidenceState) -> None:
    """Reauthenticate the selected lock source after declaration validation."""
    if state.generated_candidate is None:
        if state.lock_evidence is None:
            _fail("$.lock", "persisted lock verification is missing")
        lock_root, lock_identity, _lock = _verified_carrier_context(state.lock_evidence)
        if (
            lock_root != state.workspace_root_path
            or lock_identity != state.workspace_root_identity
        ):
            _fail("$.lock", "lock belongs to another workspace root")
        return
    if state.lock_evidence is not None:
        _fail("$.lock", "generated acquisition also retained persisted verification")
    _validate_generated_candidate_contract(state)


def _validate_generated_candidate_contract(
    state: _ProvisionalEvidenceState | _FinalEvidenceState,
) -> None:
    """Bind generated bytes and values to the exact acquired contract."""
    from .generation_candidate import _issued_generated_candidate_state

    candidate = state.generated_candidate
    candidate_state = _issued_generated_candidate_state(candidate)
    if (
        candidate_state.workspace_root_path != state.workspace_root_path
        or candidate_state.workspace_root_device != state.workspace_root_identity.device
        or candidate_state.workspace_root_inode != state.workspace_root_identity.inode
        or candidate_state.manifest != state.manifest
        or candidate_state.parsed_lock != state.lock
    ):
        _fail("$.lock", "generated candidate differs from acquired contract")


def _validate_provisional_correlations(state: _ProvisionalEvidenceState) -> None:
    """Match every provisional carrier owner with the global contract."""
    if len(state.sources) != len(state.manifest.sources):
        _fail("$.sources", "source state count differs from manifest")
    if len(state.extensions) != len(state.manifest.facet_extensions):
        _fail("$.facet-extensions", "extension state count differs from manifest")
    for position, source in enumerate(state.sources):
        if (
            source.position != position
            or source.manifest is not state.manifest.sources[position]
            or source.lock is not state.lock.sources[position]
        ):
            _fail(f"$.sources[{position}]", "source state differs from contract")
    for position, extension in enumerate(state.extensions):
        owner = state.sources[extension.source_index]
        if (
            extension.position != position
            or extension.manifest is not state.manifest.facet_extensions[position]
            or extension.lock is not state.lock.facet_registry.extensions[position]
            or owner.manifest.namespace != extension.manifest.namespace
        ):
            _fail(
                f"$.facet-extensions[{position}]",
                "extension state differs from contract",
            )


def _validate_final_correlations(state: _FinalEvidenceState) -> None:
    """Match every final carrier owner with the global contract."""
    if len(state.sources) != len(state.manifest.sources):
        _fail("$.sources", "source state count differs from manifest")
    if len(state.extensions) != len(state.manifest.facet_extensions):
        _fail("$.facet-extensions", "extension state count differs from manifest")
    for position, source in enumerate(state.sources):
        if (
            source.position != position
            or source.manifest is not state.manifest.sources[position]
            or source.lock is not state.lock.sources[position]
        ):
            _fail(f"$.sources[{position}]", "source state differs from contract")
        if source.manifest.kind is AcquisitionKind.GIT_SUBMODULE:
            if source.git_evidence is None:
                _fail(f"$.sources[{position}].git", "Git proof is missing")
            git_state = _issued_git_transport_state(source.git_evidence)
            if (
                git_state.acquisition_manifest is not state.manifest
                or git_state.acquisition_lock is not state.lock
                or git_state.source_position != position
            ):
                _fail(f"$.sources[{position}].git", "Git proof differs from contract")
        elif source.git_evidence is not None:
            _fail(f"$.sources[{position}].git", "non-Git source has Git proof")
    for position, extension in enumerate(state.extensions):
        owner = state.sources[extension.source_index]
        if (
            extension.position != position
            or extension.manifest is not state.manifest.facet_extensions[position]
            or extension.lock is not state.lock.facet_registry.extensions[position]
            or owner.manifest.namespace != extension.manifest.namespace
        ):
            _fail(
                f"$.facet-extensions[{position}]",
                "extension state differs from contract",
            )


def _provisional_facet_values(
    state: _ProvisionalEvidenceState,
    base_registry: FacetRegistry,
    base_lock: FacetConstituentLock,
) -> tuple[
    tuple[FacetRegistry, ...],
    tuple[FacetConstituentLock, ...],
    str,
]:
    """Authenticate authoritative extension reads before final verification."""
    registries: list[FacetRegistry] = [base_registry]
    locks: list[FacetConstituentLock] = [base_lock]
    for item in state.extensions:
        if identity_value_state(item.registry) != item.registry_state:
            _fail(
                f"$.facet-registry.extensions[{item.position}]",
                "facet registry state changed",
            )
        root_path, root_identity, carrier = _authoritative_carrier_context(
            item.authoritative
        )
        source = state.sources[item.source_index]
        if root_path != source.root_path or root_identity != source.root_identity:
            _fail(
                f"$.facet-registry.extensions[{item.position}]",
                "facet carrier belongs to another source root",
            )
        if carrier[0] != item.lock.path or carrier[2] != item.lock.sha256:
            _fail(
                f"$.facet-registry.extensions[{item.position}]",
                "facet carrier differs from the lock",
            )
        registries.append(item.registry)
        locks.append(item.lock)
    return tuple(registries), tuple(locks), state.lock.facet_registry.content_revision


def _final_facet_values(
    state: _FinalEvidenceState,
    base_registry: FacetRegistry,
    base_lock: FacetConstituentLock,
) -> tuple[
    tuple[FacetRegistry, ...],
    tuple[FacetConstituentLock, ...],
    str,
]:
    """Authenticate verified extension reads after final source validation."""
    registries: list[FacetRegistry] = [base_registry]
    locks: list[FacetConstituentLock] = [base_lock]
    for item in state.extensions:
        if identity_value_state(item.registry) != item.registry_state:
            _fail(
                f"$.facet-registry.extensions[{item.position}]",
                "facet registry state changed",
            )
        root_path, root_identity, carrier = _verified_carrier_context(item.evidence)
        source = state.sources[item.source_index]
        if root_path != source.root_path or root_identity != source.root_identity:
            _fail(
                f"$.facet-registry.extensions[{item.position}]",
                "facet carrier belongs to another source root",
            )
        if carrier[0] != item.lock.path or carrier[2] != item.lock.sha256:
            _fail(
                f"$.facet-registry.extensions[{item.position}]",
                "facet carrier differs from the lock",
            )
        registries.append(item.registry)
        locks.append(item.lock)
    return tuple(registries), tuple(locks), state.lock.facet_registry.content_revision


def _validate_contract_state(
    manifest: AcquisitionManifest,
    manifest_state: object,
    lock: AcquisitionLock,
    lock_state: object,
) -> None:
    """Revalidate detached contract values and their identity snapshots."""
    if identity_value_state(manifest) != manifest_state:
        _fail("$.manifest", "manifest state changed")
    if identity_value_state(lock) != lock_state:
        _fail("$.lock", "lock state changed")
    validate_acquisition_contract(manifest, lock)


def _validate_final_declaration_evidence(
    evidence: _ExternalAcquisitionEvidence,
) -> None:
    """Authenticate every declaration carrier retained by final evidence."""
    state = _EVIDENCE_AUTHORITIES.state(evidence)
    if type(state) is not _FinalEvidenceState:
        _fail("$", "external acquisition evidence is not final")
    if (
        state.packaged.content_revision != state.lock.internal_source.content_revision
        or state.packaged.acquisition_revision
        != state.lock.internal_source.acquisition_revision
    ):
        _fail("$.internal-source", "packaged source revisions differ from lock")
    for index, (carrier, locked_file) in enumerate(
        zip(
            state.packaged.declaration_evidence,
            state.lock.internal_source.files,
            strict=True,
        )
    ):
        _root, _identity, snapshot = _verified_carrier_context(carrier)
        if snapshot[0] != locked_file.path or snapshot[2] != locked_file.sha256:
            _fail(
                f"$.internal-source.files[{index}]",
                "packaged declaration evidence differs from lock",
            )
    for source in state.sources:
        if len(source.evidence) != len(source.lock.files):
            _fail(f"$.sources[{source.position}].files", "evidence count differs")
        if len(source.declarations) != len(source.lock.files):
            _fail(f"$.sources[{source.position}].files", "declaration count differs")
        for file_index, (carrier, locked_file, declaration) in enumerate(
            zip(
                source.evidence,
                source.lock.files,
                source.declarations,
                strict=True,
            )
        ):
            root_path, root_identity, snapshot = _verified_carrier_context(carrier)
            if root_path != source.root_path or root_identity != source.root_identity:
                _fail(
                    f"$.sources[{source.position}].files[{file_index}]",
                    "declaration carrier belongs to another source root",
                )
            if snapshot[0] != locked_file.path or snapshot[2] != locked_file.sha256:
                _fail(
                    f"$.sources[{source.position}].files[{file_index}]",
                    "declaration evidence differs from lock",
                )
            if declaration.sha256 != locked_file.sha256.removeprefix("sha256:"):
                _fail(
                    f"$.sources[{source.position}].files[{file_index}]",
                    "parsed declaration digest differs from lock",
                )


def _fail(location: str, message: str) -> NoReturn:
    raise AcquisitionContractError(location, message)
