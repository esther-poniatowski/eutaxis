"""Observe manifest-declared non-Git resources for lock generation."""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from typing import NamedTuple, NoReturn, SupportsIndex

from ._authority import IdentityAuthorityStore, identity_value_state
from .acquisition_contract import (
    AcquisitionKind,
    AcquisitionManifest,
    ExternalSourceLock,
    ExternalSourceManifest,
    FacetConstituentLock,
    FacetExtensionManifest,
    LockedFile,
    _external_source_acquisition_revision,
    _facet_extension_acquisition_revision,
    _require_manifest_state,
    facet_content_revision,
    source_content_revision,
)
from .byte_carriers import (
    AuthoritativeByteCarrier,
    DirectoryIdentity,
    RetainedDirectory,
    TrustedDirectory,
    VerifiedByteCarrier,
    _issued_retained_context,
    _verified_carrier_context,
)
from .exceptions import AcquisitionContractError
from .facets import FacetRegistry, load_facet_registry_bytes


class _ObservedGenerationSource(NamedTuple):
    """Bind one manifest source to its lock, root, and verified bytes."""

    position: int
    manifest: ExternalSourceManifest
    lock: ExternalSourceLock
    lock_state: object
    root_path: str
    root_device: int
    root_inode: int
    evidence: tuple[VerifiedByteCarrier, ...]


class _ObservedGenerationExtension(NamedTuple):
    """Bind one manifest extension to its lock and verified registry bytes."""

    position: int
    source_position: int
    manifest: FacetExtensionManifest
    lock: FacetConstituentLock
    lock_state: object
    evidence: VerifiedByteCarrier
    registry: FacetRegistry
    registry_state: object


class _WorkspaceGenerationState(NamedTuple):
    """Retain one complete non-Git generation observation."""

    workspace: TrustedDirectory
    workspace_root_path: str
    workspace_root_device: int
    workspace_root_inode: int
    manifest: AcquisitionManifest
    manifest_state: object
    sources: tuple[_ObservedGenerationSource, ...]
    extensions: tuple[_ObservedGenerationExtension, ...]


class _WorkspaceGenerationObservation:
    """Represent authenticated workspace or vendored lock-generation evidence."""

    __slots__ = ("__weakref__",)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("workspace generation observations must be issued")

    def __copy__(self) -> NoReturn:
        raise TypeError("workspace generation observations cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("workspace generation observations cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("workspace generation observations cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("workspace generation observations cannot be serialized")


_WORKSPACE_GENERATION_AUTHORITIES: IdentityAuthorityStore[object] = (
    IdentityAuthorityStore()
)


def _observe_workspace_generation(
    workspace: TrustedDirectory,
    manifest: AcquisitionManifest,
) -> _WorkspaceGenerationObservation:
    """Observe all manifest-declared workspace and vendored resources twice."""
    _require_manifest_state(manifest)
    manifest_state = identity_value_state(manifest)
    for position, source in enumerate(manifest.sources):
        if source.kind is AcquisitionKind.GIT_SUBMODULE:
            _fail(
                f"$.sources[{position}].kind",
                "Git-submodule generation requires the Git observer",
            )

    with ExitStack() as stack:
        workspace_root = stack.enter_context(workspace.retain_directory("."))
        workspace_root_path, workspace_root_identity = _issued_retained_context(
            workspace_root
        )
        roots = tuple(
            stack.enter_context(workspace.retain_directory(source.root))
            for source in manifest.sources
        )
        root_contexts = tuple(_issued_retained_context(root) for root in roots)

        source_by_namespace = {
            source.namespace: position
            for position, source in enumerate(manifest.sources)
        }
        extension_authoritative = tuple(
            roots[source_by_namespace[extension.namespace]].read_authoritative(
                extension.path
            )
            for extension in manifest.facet_extensions
        )
        declaration_authoritative = tuple(
            tuple(root.read_authoritative(path) for path in source.files)
            for source, root in zip(manifest.sources, roots, strict=True)
        )

        source_locks = tuple(
            _source_lock(source, carriers)
            for source, carriers in zip(
                manifest.sources,
                declaration_authoritative,
                strict=True,
            )
        )
        extension_registries = tuple(
            _extension_registry(extension, carrier)
            for extension, carrier in zip(
                manifest.facet_extensions,
                extension_authoritative,
                strict=True,
            )
        )
        extension_locks = tuple(
            _extension_lock(extension, carrier.sha256, registry)
            for extension, carrier, registry in zip(
                manifest.facet_extensions,
                extension_authoritative,
                extension_registries,
                strict=True,
            )
        )

        extension_evidence = tuple(
            roots[source_by_namespace[extension.namespace]].verify(carrier)
            for extension, carrier in zip(
                manifest.facet_extensions,
                extension_authoritative,
                strict=True,
            )
        )
        declaration_evidence = tuple(
            tuple(root.verify(carrier) for carrier in carriers)
            for root, carriers in zip(
                roots,
                declaration_authoritative,
                strict=True,
            )
        )

    observed_sources = tuple(
        _ObservedGenerationSource(
            position,
            source,
            lock,
            identity_value_state(lock),
            root_path,
            root_identity.device,
            root_identity.inode,
            evidence,
        )
        for position, (source, lock, (root_path, root_identity), evidence) in enumerate(
            zip(
                manifest.sources,
                source_locks,
                root_contexts,
                declaration_evidence,
                strict=True,
            )
        )
    )
    observed_extensions = tuple(
        _ObservedGenerationExtension(
            position,
            source_by_namespace[extension.namespace],
            extension,
            lock,
            identity_value_state(lock),
            evidence,
            registry,
            identity_value_state(registry),
        )
        for position, (extension, lock, evidence, registry) in enumerate(
            zip(
                manifest.facet_extensions,
                extension_locks,
                extension_evidence,
                extension_registries,
                strict=True,
            )
        )
    )
    result = object.__new__(_WorkspaceGenerationObservation)
    state = _WorkspaceGenerationState(
        workspace,
        workspace_root_path,
        workspace_root_identity.device,
        workspace_root_identity.inode,
        manifest,
        manifest_state,
        observed_sources,
        observed_extensions,
    )
    try:
        _WORKSPACE_GENERATION_AUTHORITIES.issue(result, state)
        _issued_workspace_generation_state(result)
        return result
    except BaseException:
        _WORKSPACE_GENERATION_AUTHORITIES.retire(result)
        raise


def _issued_workspace_generation_state(
    observation: object,
) -> _WorkspaceGenerationState:
    """Authenticate every value and carrier in one live observation."""
    if type(observation) is not _WorkspaceGenerationObservation:
        _fail("$", "workspace generation observation is not issued here")
    state = _WORKSPACE_GENERATION_AUTHORITIES.state(observation)
    if type(state) is not _WorkspaceGenerationState:
        _fail("$", "workspace generation observation is not issued here")
    if identity_value_state(state.manifest) != state.manifest_state:
        _fail("$.manifest", "manifest state changed")
    _require_manifest_state(state.manifest)

    with ExitStack() as stack:
        workspace_root = stack.enter_context(state.workspace.retain_directory("."))
        root_path, root_identity = _issued_retained_context(workspace_root)
        if (
            root_path != state.workspace_root_path
            or root_identity.device != state.workspace_root_device
            or root_identity.inode != state.workspace_root_inode
        ):
            _fail("$", "workspace root identity changed")

        current_roots = tuple(
            stack.enter_context(state.workspace.retain_directory(source.root))
            for source in state.manifest.sources
        )
        current_contexts = tuple(
            _issued_retained_context(root) for root in current_roots
        )

        if len(state.sources) != len(state.manifest.sources):
            _fail("$.sources", "observed source count differs from manifest")
        source_by_namespace: dict[str, _ObservedGenerationSource] = {}
        for position, (source, current_context) in enumerate(
            zip(state.sources, current_contexts, strict=True)
        ):
            if (
                source.position != position
                or source.manifest is not state.manifest.sources[position]
            ):
                _fail(
                    f"$.sources[{position}]",
                    "observed source differs from manifest",
                )
            current_path, current_identity = current_context
            if (
                current_path != source.root_path
                or current_identity.device != source.root_device
                or current_identity.inode != source.root_inode
            ):
                _fail(
                    f"$.sources[{position}]",
                    "observed source root differs from live workspace",
                )
            _authenticate_source(source)
            source_by_namespace[source.manifest.namespace] = source

        if len(state.extensions) != len(state.manifest.facet_extensions):
            _fail(
                "$.facet-registry.extensions",
                "observed extension count differs from manifest",
            )
        for position, extension in enumerate(state.extensions):
            owner = source_by_namespace.get(extension.manifest.namespace)
            if (
                extension.position != position
                or extension.manifest is not state.manifest.facet_extensions[position]
                or owner is None
                or extension.source_position != owner.position
            ):
                _fail(
                    f"$.facet-registry.extensions[{position}]",
                    "observed extension differs from manifest",
                )
            _authenticate_extension(extension, owner)
    return state


def _workspace_generation_components(
    observation: object,
) -> tuple[
    tuple[ExternalSourceLock, ...],
    tuple[FacetConstituentLock, ...],
]:
    """Return lock components from one live authenticated observation."""
    state = _issued_workspace_generation_state(observation)
    return (
        tuple(source.lock for source in state.sources),
        tuple(extension.lock for extension in state.extensions),
    )


def _retire_workspace_generation_observation(observation: object) -> None:
    """Retire one exact live observation and reject repeated retirement."""
    state = _WORKSPACE_GENERATION_AUTHORITIES.retire(observation)
    if type(state) is not _WorkspaceGenerationState:
        _fail("$", "workspace generation observation is not issued here")


def _source_lock(
    manifest: ExternalSourceManifest,
    carriers: tuple[AuthoritativeByteCarrier, ...],
) -> ExternalSourceLock:
    """Derive one non-Git source lock from ordered authoritative carriers."""
    files = tuple(
        LockedFile(path, carrier.sha256)
        for path, carrier in zip(manifest.files, carriers, strict=True)
    )
    return _source_lock_from_files(manifest, files)


def _source_lock_from_files(
    manifest: ExternalSourceManifest,
    files: tuple[LockedFile, ...],
) -> ExternalSourceLock:
    """Derive one non-Git source lock from detached ordered file values."""
    content = source_content_revision(manifest.namespace, files)
    return ExternalSourceLock(
        _external_source_acquisition_revision(manifest, content, None),
        content,
        files,
        manifest.kind,
        manifest.namespace,
        None,
    )


def _extension_registry(
    manifest: FacetExtensionManifest,
    carrier: AuthoritativeByteCarrier,
) -> FacetRegistry:
    """Parse and validate one extension registry from retained bytes."""
    registry = load_facet_registry_bytes(
        carrier.data,
        path=Path(manifest.root) / manifest.path,
    )
    if registry.id.split("/", 1)[0] != manifest.namespace:
        _fail("$.facet-registry.extensions", "facet id namespace differs")
    if registry.owner != manifest.namespace:
        _fail("$.facet-registry.extensions", "facet owner differs")
    return registry


def _extension_lock(
    manifest: FacetExtensionManifest,
    sha256: str,
    registry: FacetRegistry,
) -> FacetConstituentLock:
    """Derive one non-Git facet-extension lock from retained bytes."""
    content = facet_content_revision(
        registry.id,
        manifest.namespace,
        registry.owner,
        manifest.path,
        sha256,
    )
    return FacetConstituentLock(
        _facet_extension_acquisition_revision(manifest, content, None),
        content,
        registry.id,
        manifest.kind.value,
        manifest.namespace,
        registry.owner,
        manifest.path,
        sha256,
    )


def _authenticate_source(source: _ObservedGenerationSource) -> None:
    """Recheck one source lock against its complete verified carrier set."""
    if identity_value_state(source.lock) != source.lock_state:
        _fail(f"$.sources[{source.position}]", "observed source lock state changed")
    if source.root_path != source.manifest.root:
        _fail(f"$.sources[{source.position}].root", "observed source root differs")
    if not (
        len(source.manifest.files) == len(source.lock.files) == len(source.evidence)
    ):
        _fail(
            f"$.sources[{source.position}].files",
            "manifest, lock, and evidence counts differ",
        )
    observed_files: list[LockedFile] = []
    for file_index, (manifest_path, locked_file, evidence) in enumerate(
        zip(
            source.manifest.files,
            source.lock.files,
            source.evidence,
            strict=True,
        )
    ):
        root_path, root_identity, snapshot = _verified_carrier_context(evidence)
        if (
            root_path != source.root_path
            or root_identity.device != source.root_device
            or root_identity.inode != source.root_inode
        ):
            _fail(
                f"$.sources[{source.position}].files[{file_index}]",
                "declaration evidence belongs to another source root",
            )
        if manifest_path != locked_file.path:
            _fail(
                f"$.sources[{source.position}].files[{file_index}].path",
                "locked declaration path differs from manifest",
            )
        if snapshot[0] != manifest_path or snapshot[2] != locked_file.sha256:
            _fail(
                f"$.sources[{source.position}].files[{file_index}]",
                "declaration evidence differs from lock",
            )
        observed_files.append(LockedFile(snapshot[0], snapshot[2]))
    expected = _source_lock_from_files(source.manifest, tuple(observed_files))
    if expected != source.lock:
        _fail(f"$.sources[{source.position}]", "observed source lock is invalid")


def _authenticate_extension(
    extension: _ObservedGenerationExtension,
    owner: _ObservedGenerationSource,
) -> None:
    """Recheck one extension lock, registry, and verified carrier."""
    location = f"$.facet-registry.extensions[{extension.position}]"
    if identity_value_state(extension.lock) != extension.lock_state:
        _fail(location, "observed extension lock state changed")
    if identity_value_state(extension.registry) != extension.registry_state:
        _fail(location, "observed extension registry state changed")
    root_path, root_identity, snapshot = _verified_carrier_context(extension.evidence)
    if (
        root_path != owner.root_path
        or root_identity.device != owner.root_device
        or root_identity.inode != owner.root_inode
    ):
        _fail(location, "facet evidence belongs to another source root")
    if snapshot[0] != extension.lock.path or snapshot[2] != extension.lock.sha256:
        _fail(location, "facet evidence differs from lock")
    expected = _extension_lock(
        extension.manifest,
        snapshot[2],
        extension.registry,
    )
    if expected != extension.lock:
        _fail(location, "observed extension lock is invalid")


def _fail(location: str, message: str) -> NoReturn:
    raise AcquisitionContractError(location, message)
