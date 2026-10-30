"""Acquire the code-owned declaration corpus through verified byte evidence."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Callable, NamedTuple, NoReturn, SupportsIndex, TypeGuard

from ._authority import IdentityAuthorityStore, identity_value_state
from .acquisition_contract import (
    AcquisitionLock,
    FacetConstituentLock,
    InternalSourceLock,
    validated_packaged_lock,
)
from .byte_carriers import (
    AuthoritativeByteCarrier,
    RetainedDirectory,
    TrustedDirectory,
    VerifiedByteCarrier,
)
from .exceptions import AcquisitionContractError
from .facets import FacetRegistry, load_facet_registry_bytes
from .models import JsonValue, freeze_json
from .source import load_yaml_bytes


class _PackagedState(NamedTuple):
    facet_evidence: VerifiedByteCarrier
    declaration_evidence: tuple[VerifiedByteCarrier, ...]
    facet_lock: FacetConstituentLock
    facet_lock_state: object
    facet_registry: FacetRegistry
    facet_registry_state: object
    facet_document: Mapping[str, JsonValue]
    declaration_documents: tuple[JsonValue, ...]
    facet_content_revision: str
    facet_acquisition_revision: str
    content_revision: str
    acquisition_revision: str


class _PackagedFacetRead(NamedTuple):
    """Retain the parsed packaged facet base before final verification."""

    authoritative: AuthoritativeByteCarrier
    registry: FacetRegistry
    document: Mapping[str, JsonValue]


class _PackagedDeclarationReads(NamedTuple):
    """Retain ordered packaged declarations before final verification."""

    authoritative: tuple[AuthoritativeByteCarrier, ...]
    documents: tuple[JsonValue, ...]


_PACKAGED_AUTHORITIES: IdentityAuthorityStore[object] = IdentityAuthorityStore()


def _issued_state(
    value: object,
    authority: IdentityAuthorityStore[object] = _PACKAGED_AUTHORITIES,
    state_type: type[_PackagedState] = _PackagedState,
) -> _PackagedState:
    state = authority.state(value)
    if not isinstance(state, state_type):
        raise AcquisitionContractError(
            "$.internal-source",
            "packaged source is not issued here",
        )
    return state


def _issued_packaged_facet_state(
    value: object,
) -> tuple[VerifiedByteCarrier, FacetConstituentLock, FacetRegistry]:
    """Return the exact verified packaged facet constituent and its lock."""
    state = _issued_state(value)
    evidence = state.facet_evidence
    lock = state.facet_lock
    registry = state.facet_registry
    if identity_value_state(lock) != state.facet_lock_state:
        _fail("$.facet-registry.base", "packaged facet lock state changed")
    if identity_value_state(registry) != state.facet_registry_state:
        _fail("$.facet-registry.base", "packaged facet registry state changed")
    authoritative = evidence.authoritative
    if authoritative.path != lock.path or authoritative.sha256 != lock.sha256:
        _fail("$.facet-registry.base", "packaged facet evidence differs from lock")
    if registry.id != lock.id or registry.owner != lock.owner:
        _fail("$.facet-registry.base", "packaged facet registry differs from lock")
    if (
        lock.content_revision != state.facet_content_revision
        or lock.acquisition_revision != state.facet_acquisition_revision
    ):
        _fail("$.facet-registry.base", "packaged facet revisions changed")
    return evidence, lock, registry


class PackagedInternalSource:
    """Expose one issued, verified view of Eutaxis-owned source resources."""

    __slots__ = ("__weakref__",)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "PackagedInternalSource instances must be issued by acquisition"
        )

    @property
    def facet_evidence(
        self,
        _state: Callable[[object], _PackagedState] = _issued_state,
    ) -> VerifiedByteCarrier:
        """Return the matching observations of the packaged facet base."""
        return _state(self).facet_evidence

    @property
    def declaration_evidence(
        self,
        _state: Callable[[object], _PackagedState] = _issued_state,
    ) -> tuple[VerifiedByteCarrier, ...]:
        """Return matching observations in the code-owned declaration order."""
        return _state(self).declaration_evidence

    @property
    def facet_registry(
        self,
        _state: Callable[[object], _PackagedState] = _issued_state,
    ) -> FacetRegistry:
        """Return the exact parsed packaged facet registry."""
        return _state(self).facet_registry

    @property
    def facet_document(
        self,
        _state: Callable[[object], _PackagedState] = _issued_state,
    ) -> Mapping[str, JsonValue]:
        """Return the frozen parsed facet-base document."""
        return _state(self).facet_document

    @property
    def declaration_documents(
        self,
        _state: Callable[[object], _PackagedState] = _issued_state,
    ) -> tuple[JsonValue, ...]:
        """Return frozen parsed declarations in code-owned order."""
        return _state(self).declaration_documents

    @property
    def facet_content_revision(
        self,
        _state: Callable[[object], _PackagedState] = _issued_state,
    ) -> str:
        """Return the locked transport-independent facet revision."""
        return _state(self).facet_content_revision

    @property
    def facet_acquisition_revision(
        self,
        _state: Callable[[object], _PackagedState] = _issued_state,
    ) -> str:
        """Return the locked packaged-facet acquisition revision."""
        return _state(self).facet_acquisition_revision

    @property
    def content_revision(
        self,
        _state: Callable[[object], _PackagedState] = _issued_state,
    ) -> str:
        """Return the locked internal-source content revision."""
        return _state(self).content_revision

    @property
    def acquisition_revision(
        self,
        _state: Callable[[object], _PackagedState] = _issued_state,
    ) -> str:
        """Return the locked internal-source acquisition revision."""
        return _state(self).acquisition_revision

    def __copy__(self) -> NoReturn:
        raise TypeError("PackagedInternalSource instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("PackagedInternalSource instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("PackagedInternalSource instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("PackagedInternalSource instances cannot be serialized")


def _require_digest(actual: str, expected: str, location: str) -> None:
    if actual != expected:
        _fail(location, "retained resource digest differs from the lock")


def _fail(location: str, message: str) -> NoReturn:
    raise AcquisitionContractError(location, message)


def _is_json_mapping(
    value: JsonValue,
    mapping_type: type[Mapping[object, object]] = Mapping,
) -> TypeGuard[Mapping[str, JsonValue]]:
    return isinstance(value, mapping_type)


class _PackagedDependencies(NamedTuple):
    validate_lock: Callable[
        [AcquisitionLock],
        tuple[FacetConstituentLock, InternalSourceLock],
    ]
    nofollow: int | None
    root_flags: int | None
    open_root: Callable[..., int]
    close_fd: Callable[[int], None]
    trusted_from_fd: Callable[..., TrustedDirectory]
    load_facet_registry: Callable[..., FacetRegistry]
    load_yaml: Callable[..., tuple[object, object, str]]
    freeze: Callable[[object], JsonValue]
    is_json_mapping: Callable[[JsonValue], TypeGuard[Mapping[str, JsonValue]]]
    path: Callable[[str], Path]
    require_digest: Callable[[str, str, str], None]
    fail: Callable[[str, str], NoReturn]
    result_type: type[PackagedInternalSource]
    state_type: type[_PackagedState]
    authority: IdentityAuthorityStore[object]


def _root_open_flags() -> int | None:
    """Return safe directory-open flags when the platform supplies them."""
    required = ("O_DIRECTORY", "O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK")
    supports_dir_fd: set[object] = getattr(os, "supports_dir_fd", set())
    if (
        any(not hasattr(os, name) for name in required)
        or os.open not in supports_dir_fd
    ):
        return None
    return os.O_RDONLY | getattr(os, "O_DIRECTORY") | getattr(os, "O_CLOEXEC")


_SYSTEM_DEPENDENCIES = _PackagedDependencies(
    validate_lock=validated_packaged_lock,
    nofollow=getattr(os, "O_NOFOLLOW", None),
    root_flags=_root_open_flags(),
    open_root=os.open,
    close_fd=os.close,
    trusted_from_fd=TrustedDirectory.from_fd,
    load_facet_registry=load_facet_registry_bytes,
    load_yaml=load_yaml_bytes,
    freeze=freeze_json,
    is_json_mapping=_is_json_mapping,
    path=Path,
    require_digest=_require_digest,
    fail=_fail,
    result_type=PackagedInternalSource,
    state_type=_PackagedState,
    authority=_PACKAGED_AUTHORITIES,
)


class _PackagedAcquisitionSession:
    """Let one outer transaction order packaged facet and declaration phases."""

    def __init__(
        self,
        base_lock: FacetConstituentLock,
        source_lock: InternalSourceLock,
        facet_root: RetainedDirectory,
        declaration_root: RetainedDirectory,
        dependencies: _PackagedDependencies,
    ) -> None:
        self._base_lock = base_lock
        self._source_lock = source_lock
        self._facet_root = facet_root
        self._declaration_root = declaration_root
        self._dependencies = dependencies
        self._facet_read: _PackagedFacetRead | None = None
        self._declaration_reads: _PackagedDeclarationReads | None = None
        self._finished = False

    def read_facet(self) -> _PackagedFacetRead:
        """Read and parse the packaged facet base exactly once."""
        if self._finished or self._facet_read is not None:
            self._dependencies.fail(
                "$.facet-registry.base",
                "packaged facet phase has already run",
            )
        self._facet_read = _read_packaged_facet(
            self._base_lock,
            self._facet_root,
            self._dependencies,
        )
        return self._facet_read

    def read_declarations(self) -> _PackagedDeclarationReads:
        """Read and parse packaged declarations after the facet phase."""
        if self._facet_read is None:
            self._dependencies.fail(
                "$.internal-source",
                "packaged facet phase must run before declarations",
            )
        if self._finished or self._declaration_reads is not None:
            self._dependencies.fail(
                "$.internal-source",
                "packaged declaration phase has already run",
            )
        self._declaration_reads = _read_packaged_declarations(
            self._source_lock,
            self._declaration_root,
            self._dependencies,
        )
        return self._declaration_reads

    def verify_and_issue(self) -> PackagedInternalSource:
        """Verify every retained read and issue one packaged source."""
        if self._facet_read is None or self._declaration_reads is None:
            self._dependencies.fail(
                "$.internal-source",
                "packaged reads are incomplete",
            )
        if self._finished:
            self._dependencies.fail(
                "$.internal-source",
                "packaged acquisition session has already finished",
            )
        self._finished = True
        return _verify_and_issue_packaged_source(
            self._base_lock,
            self._source_lock,
            self._facet_root,
            self._declaration_root,
            self._facet_read,
            self._declaration_reads,
            self._dependencies,
        )


def _trusted_directory_from_path(
    root_path: Path,
    dependencies: _PackagedDependencies,
) -> TrustedDirectory:
    """Retain one trusted directory from a no-follow descriptor open."""
    nofollow = dependencies.nofollow
    root_flags = dependencies.root_flags
    if nofollow is None or root_flags is None:
        dependencies.fail(
            "$.internal-source",
            "platform lacks required descriptor support",
        )
    try:
        root_fd = dependencies.open_root(
            root_path,
            root_flags | nofollow,
        )
    except OSError as exc:
        dependencies.fail("$.internal-source", str(exc))
    try:
        trusted = dependencies.trusted_from_fd(root_fd, label=str(root_path))
    except BaseException:
        try:
            dependencies.close_fd(root_fd)
        except OSError as exc:
            dependencies.fail("$.internal-source", str(exc))
        raise
    try:
        dependencies.close_fd(root_fd)
    except BaseException as bootstrap_error:
        try:
            trusted.close()
        except BaseException as cleanup_error:
            try:
                trusted.close()
            except BaseException as retry_error:
                cleanup_error.__cause__ = bootstrap_error
                raise retry_error from cleanup_error
            raise cleanup_error from bootstrap_error
        if isinstance(bootstrap_error, OSError):
            dependencies.fail("$.internal-source", str(bootstrap_error))
        raise
    return trusted


def _acquire_from_retained_roots(
    base_lock: FacetConstituentLock,
    source_lock: InternalSourceLock,
    facet_root: RetainedDirectory,
    declaration_root: RetainedDirectory,
    dependencies: _PackagedDependencies,
) -> PackagedInternalSource:
    """Acquire one source through already-retained resource roots."""
    session = _PackagedAcquisitionSession(
        base_lock,
        source_lock,
        facet_root,
        declaration_root,
        dependencies,
    )
    session.read_facet()
    session.read_declarations()
    return session.verify_and_issue()


def _read_packaged_facet(
    base_lock: FacetConstituentLock,
    facet_root: RetainedDirectory,
    dependencies: _PackagedDependencies,
) -> _PackagedFacetRead:
    """Read, authenticate, and parse the packaged facet base."""
    facet_authoritative = facet_root.read_authoritative(base_lock.path)
    dependencies.require_digest(
        facet_authoritative.sha256,
        base_lock.sha256,
        "$.facet-registry.base.sha256",
    )
    facet_registry = dependencies.load_facet_registry(
        facet_authoritative.data,
        path=dependencies.path(base_lock.path),
    )
    if facet_registry.id != "eutaxis/context-facets":
        dependencies.fail(
            "$.facet-registry.base.id",
            "packaged facet id differs",
        )
    if facet_registry.owner != "eutaxis":
        dependencies.fail(
            "$.facet-registry.base.owner",
            "packaged facet owner differs",
        )
    facet_document_value, _locations, _digest = dependencies.load_yaml(
        facet_authoritative.data,
        path=dependencies.path(base_lock.path),
    )
    frozen_facet_document = dependencies.freeze(facet_document_value)
    if not dependencies.is_json_mapping(frozen_facet_document):
        dependencies.fail(
            "$.facet-registry.base",
            "packaged facet document is not a mapping",
        )
    return _PackagedFacetRead(
        authoritative=facet_authoritative,
        registry=facet_registry,
        document=frozen_facet_document,
    )


def _read_packaged_declarations(
    source_lock: InternalSourceLock,
    declaration_root: RetainedDirectory,
    dependencies: _PackagedDependencies,
) -> _PackagedDeclarationReads:
    """Read, authenticate, and parse packaged declarations in lock order."""
    declaration_authoritative = tuple(
        declaration_root.read_authoritative(locked_file.path)
        for locked_file in source_lock.files
    )
    declaration_documents: list[JsonValue] = []
    for index, (carrier, locked_file) in enumerate(
        zip(
            declaration_authoritative,
            source_lock.files,
            strict=True,
        )
    ):
        dependencies.require_digest(
            carrier.sha256,
            locked_file.sha256,
            f"$.internal-source.files[{index}].sha256",
        )
        document, _locations, _digest = dependencies.load_yaml(
            carrier.data,
            path=dependencies.path(locked_file.path),
        )
        declaration_documents.append(dependencies.freeze(document))
    return _PackagedDeclarationReads(
        authoritative=declaration_authoritative,
        documents=tuple(declaration_documents),
    )


def _verify_and_issue_packaged_source(
    base_lock: FacetConstituentLock,
    source_lock: InternalSourceLock,
    facet_root: RetainedDirectory,
    declaration_root: RetainedDirectory,
    facet_read: _PackagedFacetRead,
    declaration_reads: _PackagedDeclarationReads,
    dependencies: _PackagedDependencies,
) -> PackagedInternalSource:
    """Verify phased packaged reads and issue their immutable source."""
    facet_verified = facet_root.verify(facet_read.authoritative)
    declaration_verified = tuple(
        declaration_root.verify(carrier) for carrier in declaration_reads.authoritative
    )
    result = object.__new__(dependencies.result_type)
    state = dependencies.state_type(
        facet_evidence=facet_verified,
        declaration_evidence=declaration_verified,
        facet_lock=base_lock,
        facet_lock_state=identity_value_state(base_lock),
        facet_registry=facet_read.registry,
        facet_registry_state=identity_value_state(facet_read.registry),
        facet_document=facet_read.document,
        declaration_documents=declaration_reads.documents,
        facet_content_revision=base_lock.content_revision,
        facet_acquisition_revision=base_lock.acquisition_revision,
        content_revision=source_lock.content_revision,
        acquisition_revision=source_lock.acquisition_revision,
    )
    try:
        dependencies.authority.issue(result, state)
        return result
    except BaseException:
        dependencies.authority.retire(result)
        raise


def _acquire_packaged_internal_source_with_dependencies(
    lock: AcquisitionLock,
    root_path: Path,
    dependencies: _PackagedDependencies,
) -> PackagedInternalSource:
    """Acquire locked resources through an explicit root and dependency set."""
    base_lock, source_lock = dependencies.validate_lock(lock)
    trusted = _trusted_directory_from_path(root_path, dependencies)
    with trusted:
        with (
            trusted.retain_directory(".") as facet_root,
            trusted.retain_directory("declarations/v1") as declaration_root,
        ):
            return _acquire_from_retained_roots(
                base_lock,
                source_lock,
                facet_root,
                declaration_root,
                dependencies,
            )


def _acquire_packaged_internal_source_from_root(
    lock: AcquisitionLock,
    root_path: Path,
    dependencies: _PackagedDependencies = _SYSTEM_DEPENDENCIES,
) -> PackagedInternalSource:
    """Acquire locked resources below one explicit root for boundary tests."""
    return _acquire_packaged_internal_source_with_dependencies(
        lock,
        root_path,
        dependencies,
    )


def _build_packaged_source_acquirer(
    distribution: TrustedDirectory,
    retained_implementation: Callable[
        [
            FacetConstituentLock,
            InternalSourceLock,
            RetainedDirectory,
            RetainedDirectory,
            _PackagedDependencies,
        ],
        PackagedInternalSource,
    ],
    dependencies: _PackagedDependencies,
) -> Callable[[AcquisitionLock], PackagedInternalSource]:
    """Bind the public acquirer to its distribution and dependencies."""

    def acquire(lock: AcquisitionLock) -> PackagedInternalSource:
        """Acquire every code-owned resource named by the packaged lock."""
        base_lock, source_lock = dependencies.validate_lock(lock)
        with (
            distribution.retain_directory("data") as facet_root,
            distribution.retain_directory("data/declarations/v1") as declaration_root,
        ):
            return retained_implementation(
                base_lock,
                source_lock,
                facet_root,
                declaration_root,
                dependencies,
            )

    return acquire


def _build_running_distribution_acquirer(
    module_file: str,
    dependencies: _PackagedDependencies,
) -> Callable[[AcquisitionLock], PackagedInternalSource]:
    """Retain the running distribution or return a closed platform boundary."""
    if dependencies.nofollow is None or dependencies.root_flags is None:

        def unsupported(_lock: AcquisitionLock) -> NoReturn:
            dependencies.fail(
                "$.internal-source",
                "platform lacks required descriptor support",
            )

        return unsupported
    distribution = _trusted_directory_from_path(
        dependencies.path(module_file).resolve().parent.parent,
        dependencies,
    )
    return _build_packaged_source_acquirer(
        distribution,
        _acquire_from_retained_roots,
        dependencies,
    )


acquire_packaged_internal_source = _build_running_distribution_acquirer(
    __file__,
    _SYSTEM_DEPENDENCIES,
)
