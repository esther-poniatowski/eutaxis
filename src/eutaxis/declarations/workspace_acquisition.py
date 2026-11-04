"""Acquire workspace and vendored declarations into one private issued stage."""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from typing import NamedTuple, NoReturn, SupportsIndex

from ._authority import IdentityAuthorityStore, identity_value_state
from .acquisition_contract import (
    AcquisitionLock,
    AcquisitionManifest,
    parse_acquisition_lock_bytes,
    parse_acquisition_manifest,
    validate_acquisition_contract,
)
from .acquisition_paths import AcquisitionPathError, normalized_relative_path
from .byte_carriers import (
    AuthoritativeByteCarrier,
    RetainedDirectory,
    TrustedDirectory,
    _issued_retained_context,
    _trusted_directory_from_workspace_path,
)
from .exceptions import AcquisitionContractError, DeclarationSchemaError
from .facets import FacetRegistryView, load_facet_registry_bytes
from .composite_facets import (
    _issue_workspace_vendored_composite,
    _provisional_composite_view,
    _retire_composite_tree,
)
from .loader import LoadedDeclarationSource, load_declaration_source_bytes
from .packaged_source import (
    _PackagedAcquisitionSession,
    _open_running_packaged_session,
)
from .source import load_yaml_bytes
from ._workspace_evidence import (
    _EVIDENCE_AUTHORITIES,
    _FacetExtensionRead,
    _FinalEvidenceState,
    _OpenExternalSource,
    _WorkspaceVendoredEvidence,
    _finalize_evidence,
    _issue_provisional_evidence,
    _issued_workspace_vendored_facet_state,
    _require_non_git_contract,
    _retire_workspace_vendored_evidence,
    _validate_final_declaration_evidence,
)


class _WorkspaceVendoredStageState(NamedTuple):
    """Bind final evidence, facets, and parsed declarations."""

    evidence: _WorkspaceVendoredEvidence
    composite: FacetRegistryView
    declarations: tuple[LoadedDeclarationSource, ...]
    declaration_state: object


class _WorkspaceVendoredAcquisitionStage:
    """Retain verified non-Git acquisition state without semantic authority."""

    __slots__ = ("__weakref__",)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("workspace/vendored stages must be issued")

    def __copy__(self) -> NoReturn:
        raise TypeError("workspace/vendored stages cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("workspace/vendored stages cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("workspace/vendored stages cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("workspace/vendored stages cannot be serialized")


_STAGE_AUTHORITIES: IdentityAuthorityStore[object] = IdentityAuthorityStore()


def _acquire_workspace_vendored_stage_from_path(
    workspace_path: str,
    manifest_path: str,
    lock_path: str,
) -> _WorkspaceVendoredAcquisitionStage:
    """Acquire one restricted contract through an exact workspace path."""
    workspace = _trusted_directory_from_workspace_path(workspace_path)
    try:
        stage = _acquire_workspace_vendored_stage(
            workspace,
            manifest_path,
            lock_path,
        )
    except BaseException as primary_error:
        try:
            workspace.close()
        except BaseException as cleanup_error:
            cleanup_error.__cause__ = primary_error
            raise cleanup_error
        raise
    try:
        workspace.close()
    except BaseException:
        _retire_stage_tree(stage)
        raise
    return stage


def _acquire_workspace_vendored_stage(
    workspace: TrustedDirectory,
    manifest_path: str,
    lock_path: str,
) -> _WorkspaceVendoredAcquisitionStage:
    """Acquire one non-Git contract through a retained workspace capability."""
    manifest_path = _normalized_file_path(manifest_path, "$.manifest-path")
    lock_path = _normalized_file_path(lock_path, "$.lock-path")
    evidence: _WorkspaceVendoredEvidence | None = None
    composite: FacetRegistryView | None = None
    stage: _WorkspaceVendoredAcquisitionStage | None = None
    try:
        with ExitStack() as stack:
            workspace_root = stack.enter_context(workspace.retain_directory("."))
            manifest_authoritative = workspace_root.read_authoritative(manifest_path)
            lock_authoritative = workspace_root.read_authoritative(lock_path)
            manifest = _parse_manifest_bytes(
                manifest_authoritative.data,
                path=Path(manifest_path),
            )
            lock = parse_acquisition_lock_bytes(lock_authoritative.data)
            validate_acquisition_contract(manifest, lock)
            _require_non_git_contract(manifest)
            workspace_root_path, workspace_root_identity = _issued_retained_context(
                workspace_root
            )
            sources = _open_external_sources(workspace, manifest, lock, stack)
            with _open_running_packaged_session(lock) as packaged_session:
                packaged_facet = packaged_session.read_facet()
                extensions = _read_extensions(manifest, lock, sources)
                evidence = _issue_provisional_evidence(
                    manifest_authoritative,
                    lock_authoritative,
                    manifest,
                    lock,
                    workspace_root_path,
                    workspace_root_identity,
                    packaged_facet,
                    sources,
                    extensions,
                )
                composite = _issue_workspace_vendored_composite(evidence)
                parsing_facets = _provisional_composite_view(composite)
                packaged_reads = packaged_session.read_declarations()
                external_authoritative = _read_external_declarations(sources)
                packaged_session.parse_declarations()
                declarations = _parse_all_declarations(
                    packaged_reads.authoritative,
                    sources,
                    external_authoritative,
                    parsing_facets,
                )
                manifest_evidence = workspace_root.verify(manifest_authoritative)
                lock_evidence = workspace_root.verify(lock_authoritative)
                packaged = packaged_session.verify_and_issue()
                extension_evidence = tuple(
                    sources[item.source_index].root.verify(item.authoritative)
                    for item in extensions
                )
                declaration_evidence = tuple(
                    tuple(source.root.verify(carrier) for carrier in source_carriers)
                    for source, source_carriers in zip(
                        sources,
                        external_authoritative,
                        strict=True,
                    )
                )
                _finalize_evidence(
                    evidence,
                    manifest_evidence,
                    lock_evidence,
                    packaged,
                    sources,
                    extensions,
                    extension_evidence,
                    declaration_evidence,
                    declarations[len(packaged_reads.authoritative) :],
                )
                composite.require_authority()
                stage = _issue_stage(evidence, composite, declarations)
        if stage is None:
            raise AssertionError("workspace/vendored stage was not issued")
        return stage
    except BaseException:
        if stage is not None:
            _retire_stage_tree(stage)
        if composite is not None:
            _retire_composite_tree(composite)
        if evidence is not None:
            _retire_workspace_vendored_evidence(evidence)
        raise


def _retire_stage_tree(stage: object) -> None:
    """Retire a stage and both nested authority layers."""
    state = _STAGE_AUTHORITIES.retire(stage)
    if type(state) is not _WorkspaceVendoredStageState:
        return
    _retire_composite_tree(state.composite)
    _retire_workspace_vendored_evidence(state.evidence)


def _parse_manifest_bytes(source: bytes, *, path: Path) -> AcquisitionManifest:
    """Parse a manifest only from retained YAML bytes."""
    try:
        document, _locations, _digest = load_yaml_bytes(source, path=path)
    except DeclarationSchemaError as exc:
        raise AcquisitionContractError(
            "$.manifest" + exc.location.removeprefix("$"),
            str(exc),
        ) from exc
    return parse_acquisition_manifest(document)


def _normalized_file_path(value: object, location: str) -> str:
    """Validate one caller-supplied workspace-relative file path."""
    try:
        return normalized_relative_path(value, allow_dot=False)
    except AcquisitionPathError as exc:
        raise AcquisitionContractError(location, str(exc)) from exc


def _open_external_sources(
    workspace: TrustedDirectory,
    manifest: AcquisitionManifest,
    lock: AcquisitionLock,
    stack: ExitStack,
) -> tuple[_OpenExternalSource, ...]:
    """Establish every external root before any facet read."""
    opened: list[_OpenExternalSource] = []
    for index, (source_manifest, source_lock) in enumerate(
        zip(manifest.sources, lock.sources, strict=True)
    ):
        root = stack.enter_context(workspace.retain_directory(source_manifest.root))
        root_path, root_identity = _issued_retained_context(root)
        opened.append(
            _OpenExternalSource(
                index,
                source_manifest,
                source_lock,
                root,
                root_path,
                root_identity,
            )
        )
    return tuple(opened)


def _read_extensions(
    manifest: AcquisitionManifest,
    lock: AcquisitionLock,
    sources: tuple[_OpenExternalSource, ...],
) -> tuple[_FacetExtensionRead, ...]:
    """Read extensions in manifest order from their exact owning roots."""
    source_by_namespace = {source.manifest.namespace: source for source in sources}
    reads: list[_FacetExtensionRead] = []
    for index, (extension_manifest, extension_lock) in enumerate(
        zip(
            manifest.facet_extensions,
            lock.facet_registry.extensions,
            strict=True,
        )
    ):
        source = source_by_namespace[extension_manifest.namespace]
        carrier = source.root.read_authoritative(extension_manifest.path)
        _require_digest(
            carrier.sha256,
            extension_lock.sha256,
            f"$.facet-registry.extensions[{index}].sha256",
        )
        registry = load_facet_registry_bytes(
            carrier.data,
            path=Path(source.manifest.root) / extension_manifest.path,
        )
        if registry.id != extension_lock.id:
            _fail(f"$.facet-registry.extensions[{index}].id", "facet id differs")
        if registry.owner != extension_lock.owner:
            _fail(
                f"$.facet-registry.extensions[{index}].owner",
                "facet owner differs",
            )
        reads.append(
            _FacetExtensionRead(
                index,
                source.position,
                extension_manifest,
                extension_lock,
                carrier,
                registry,
                identity_value_state(registry),
            )
        )
    return tuple(reads)


def _read_external_declarations(
    sources: tuple[_OpenExternalSource, ...],
) -> tuple[tuple[AuthoritativeByteCarrier, ...], ...]:
    """Read external declarations in source and file order."""
    result: list[tuple[AuthoritativeByteCarrier, ...]] = []
    for source in sources:
        carriers: list[AuthoritativeByteCarrier] = []
        for file_index, locked_file in enumerate(source.lock.files):
            carrier = source.root.read_authoritative(locked_file.path)
            _require_digest(
                carrier.sha256,
                locked_file.sha256,
                f"$.sources[{source.position}].files[{file_index}].sha256",
            )
            carriers.append(carrier)
        result.append(tuple(carriers))
    return tuple(result)


def _parse_all_declarations(
    packaged: tuple[AuthoritativeByteCarrier, ...],
    sources: tuple[_OpenExternalSource, ...],
    external: tuple[tuple[AuthoritativeByteCarrier, ...], ...],
    composite: FacetRegistryView,
) -> tuple[LoadedDeclarationSource, ...]:
    """Parse every retained declaration against the exact issued composite."""
    loaded: list[LoadedDeclarationSource] = []
    for carrier in packaged:
        loaded.append(
            load_declaration_source_bytes(
                carrier.data,
                path=Path(carrier.path),
                facets=composite,
            )
        )
    for source, carriers in zip(sources, external, strict=True):
        for carrier in carriers:
            loaded.append(
                load_declaration_source_bytes(
                    carrier.data,
                    path=Path(source.manifest.root) / carrier.path,
                    facets=composite,
                )
            )
    return tuple(loaded)


def _issue_stage(
    evidence: _WorkspaceVendoredEvidence,
    composite: FacetRegistryView,
    declarations: tuple[LoadedDeclarationSource, ...],
) -> _WorkspaceVendoredAcquisitionStage:
    """Issue the private final stage after all evidence has verified."""
    if type(_EVIDENCE_AUTHORITIES.state(evidence)) is not _FinalEvidenceState:
        _fail("$", "workspace/vendored evidence is not final")
    result = object.__new__(_WorkspaceVendoredAcquisitionStage)
    state = _WorkspaceVendoredStageState(
        evidence,
        composite,
        declarations,
        identity_value_state(declarations),
    )
    try:
        _STAGE_AUTHORITIES.issue(result, state)
        _issued_workspace_vendored_stage_state(result)
        return result
    except BaseException:
        _STAGE_AUTHORITIES.retire(result)
        raise


def _issued_workspace_vendored_stage_state(
    stage: object,
) -> _WorkspaceVendoredStageState:
    """Authenticate a completed private stage and every retained aggregate."""
    if type(stage) is not _WorkspaceVendoredAcquisitionStage:
        _fail("$", "workspace/vendored stage is not issued here")
    state = _STAGE_AUTHORITIES.state(stage)
    if type(state) is not _WorkspaceVendoredStageState:
        _fail("$", "workspace/vendored stage is not issued here")
    _issued_workspace_vendored_facet_state(state.evidence)
    state.composite.require_authority()
    _validate_final_declaration_evidence(state.evidence)
    if identity_value_state(state.declarations) != state.declaration_state:
        _fail("$.declarations", "parsed declaration state changed")
    return state


def _require_digest(actual: str, expected: str, location: str) -> None:
    if actual != expected:
        _fail(location, "retained resource digest differs from the lock")


def _fail(location: str, message: str) -> NoReturn:
    raise AcquisitionContractError(location, message)
