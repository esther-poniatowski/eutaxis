"""Issue composite facet registries with process-local constituent authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import NamedTuple, NoReturn, SupportsIndex

from ._authority import IdentityAuthorityStore, identity_value_state
from .acquisition_contract import (
    AcquisitionLock,
    FacetConstituentLock,
    composite_facet_content_revision,
)
from .exceptions import AcquisitionContractError
from .facets import (
    ContextFacet,
    FacetRegistry,
    _validate_context,
)
from .models import JsonValue
from .packaged_source import (
    PackagedInternalSource,
    acquire_packaged_internal_source,
    _issued_packaged_facet_state,
)
from ._external_evidence import (
    _ExternalAcquisitionEvidence,
    _issued_external_facet_state,
    _provisional_external_facet_state,
)

COMPOSITE_FACET_REGISTRY_ID = "composite/context-facets-v1"


@dataclass(frozen=True, init=False)
class CompositeFacetRegistry:
    """Retain one issued ordered union of exact facet registries."""

    schema_version: int
    id: str
    constituents: tuple[FacetRegistry, ...]
    facets: Mapping[str, ContextFacet]
    facet_authorities: Mapping[str, FacetRegistry]
    content_revision: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("CompositeFacetRegistry instances must be issued")

    def require_authority(self) -> None:
        """Require this exact composite and all retained state to remain issued."""
        if not _is_issued_composite_facet_registry(self):
            raise AcquisitionContractError(
                "$.facet-registry",
                "composite facet registry is not issued here",
            )

    def authority_for(self, facet_id: str) -> FacetRegistry:
        """Return the exact constituent that introduced one known facet."""
        self.require_authority()
        return self.facet_authorities[facet_id]

    def validate_context(
        self, context: Mapping[str, object]
    ) -> Mapping[str, JsonValue]:
        """Validate and freeze one context through the issued composite."""
        return _validate_context(self, context)

    def __copy__(self) -> NoReturn:
        raise TypeError("CompositeFacetRegistry instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("CompositeFacetRegistry instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("CompositeFacetRegistry instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("CompositeFacetRegistry instances cannot be serialized")


class _FacetCompositeProvenance:
    """Authenticate the one source that chooses composite constituents."""

    __slots__ = ("__weakref__",)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("facet composite provenance must be issued")

    def __copy__(self) -> NoReturn:
        raise TypeError("facet composite provenance cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("facet composite provenance cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("facet composite provenance cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("facet composite provenance cannot be serialized")


class _ProvisionalCompositeFacetView:
    """Expose a provisional composite only to byte-owned declaration parsing."""

    __slots__ = ("_composite",)

    def __init__(self, composite: CompositeFacetRegistry) -> None:
        self._composite = composite

    @property
    def schema_version(self) -> int:
        return self._composite.schema_version

    @property
    def id(self) -> str:
        return self._composite.id

    @property
    def facets(self) -> Mapping[str, ContextFacet]:
        return self._composite.facets

    def require_authority(self) -> None:
        if not _has_composite_authority(self._composite, allow_provisional=True):
            _fail("$.facet-registry", "provisional composite is not issued here")

    def authority_for(self, facet_id: str) -> FacetRegistry:
        self.require_authority()
        return self._composite.facet_authorities[facet_id]

    def validate_context(
        self, context: Mapping[str, object]
    ) -> Mapping[str, JsonValue]:
        return _validate_context(self, context)


class _PackagedProvenanceState(NamedTuple):
    """Bind packaged provenance to its exact source, lock, and registry."""

    packaged: PackagedInternalSource
    lock: FacetConstituentLock
    registry: FacetRegistry


class _ExternalProvenanceState(NamedTuple):
    """Bind external provenance to one complete correlated evidence record."""

    evidence: _ExternalAcquisitionEvidence


class _CompositeAuthorityState(NamedTuple):
    """Bind a composite snapshot to the provenance that selected it."""

    snapshot: tuple[object, ...]
    provenance: _FacetCompositeProvenance


_FACET_PROVENANCE_AUTHORITIES: IdentityAuthorityStore[object] = IdentityAuthorityStore()
_COMPOSITE_AUTHORITIES: IdentityAuthorityStore[object] = IdentityAuthorityStore()


def _capture_composite_authority(
    value: CompositeFacetRegistry,
) -> tuple[object, ...]:
    """Capture exact composite values and nested carrier identities."""
    return (identity_value_state(value),)


def _is_issued_composite_facet_registry(value: object) -> bool:
    """Return whether ``value`` retains its complete issuance snapshot."""
    return _has_composite_authority(value, allow_provisional=False)


def _has_composite_authority(value: object, *, allow_provisional: bool) -> bool:
    """Check final authority, or internal provisional authority when requested."""
    if type(value) is not CompositeFacetRegistry:
        return False
    try:
        state = _COMPOSITE_AUTHORITIES.state(value)
        if type(state) is not _CompositeAuthorityState:
            return False
        if state.snapshot != _capture_composite_authority(value):
            return False
        constituents, _locks, content_revision = _issued_provenance_state(
            state.provenance,
            allow_provisional=allow_provisional,
        )
        return (
            len(value.constituents) == len(constituents)
            and all(
                current is issued
                for current, issued in zip(
                    value.constituents,
                    constituents,
                    strict=True,
                )
            )
            and value.content_revision == content_revision
        )
    except Exception:
        return False


def acquire_packaged_composite_facet_registry(
    lock: AcquisitionLock,
) -> CompositeFacetRegistry:
    """Acquire and issue the composite for the code-owned packaged facet base."""
    return _issue_composite_facet_registry(acquire_packaged_internal_source(lock))


def _issue_composite_facet_registry(
    packaged: PackagedInternalSource,
) -> CompositeFacetRegistry:
    """Issue the packaged composite used before external acquisition lands."""
    provenance = _issue_packaged_provenance(packaged)
    return _issue_composite_from_provenance(provenance)


def _issue_packaged_provenance(
    packaged: PackagedInternalSource,
) -> _FacetCompositeProvenance:
    """Issue the only provenance route admitted before external acquisition."""
    if type(packaged) is not PackagedInternalSource:
        _fail("$.facet-registry.base", "packaged source has the wrong exact type")

    _evidence, base_lock, base = _issued_packaged_facet_state(packaged)
    _require_constituent(base, base_lock, "$.facet-registry.base")
    if base.id != "eutaxis/context-facets" or base.owner != "eutaxis":
        _fail(
            "$.facet-registry.base",
            "base registry identity is not canonical",
        )
    result = object.__new__(_FacetCompositeProvenance)
    state = _PackagedProvenanceState(
        packaged=packaged,
        lock=base_lock,
        registry=base,
    )
    try:
        _FACET_PROVENANCE_AUTHORITIES.issue(result, state)
        return result
    except BaseException:
        _FACET_PROVENANCE_AUTHORITIES.retire(result)
        raise


def _issue_external_composite(
    evidence: _ExternalAcquisitionEvidence,
) -> CompositeFacetRegistry:
    """Issue a composite only from one complete external acquisition record."""
    provenance = _issue_external_provenance(evidence)
    return _issue_composite_from_provenance(provenance)


def _issue_external_provenance(
    evidence: _ExternalAcquisitionEvidence,
) -> _FacetCompositeProvenance:
    """Bind external composite selection to exact issued source evidence."""
    if type(evidence) is not _ExternalAcquisitionEvidence:
        _fail("$.facet-registry", "external acquisition evidence has wrong type")
    _provisional_external_facet_state(evidence)
    result = object.__new__(_FacetCompositeProvenance)
    state = _ExternalProvenanceState(evidence)
    try:
        _FACET_PROVENANCE_AUTHORITIES.issue(result, state)
        return result
    except BaseException:
        _FACET_PROVENANCE_AUTHORITIES.retire(result)
        raise


def _issued_provenance_state(
    provenance: object,
    *,
    allow_provisional: bool = False,
) -> tuple[
    tuple[FacetRegistry, ...],
    tuple[FacetConstituentLock, ...],
    str,
]:
    """Return constituents selected by one exact issued provenance record."""
    if type(provenance) is not _FacetCompositeProvenance:
        _fail("$.facet-registry", "facet composite provenance is not issued here")
    state = _FACET_PROVENANCE_AUTHORITIES.state(provenance)
    if type(state) is _ExternalProvenanceState:
        if allow_provisional:
            return _provisional_external_facet_state(state.evidence)
        return _issued_external_facet_state(state.evidence)
    if type(state) is not _PackagedProvenanceState:
        _fail("$.facet-registry", "facet composite provenance is not issued here")
    _evidence, current_lock, current_registry = _issued_packaged_facet_state(
        state.packaged
    )
    if current_lock is not state.lock or current_registry is not state.registry:
        _fail("$.facet-registry.base", "packaged facet provenance changed")
    _require_constituent(state.registry, state.lock, "$.facet-registry.base")
    constituents = (state.registry,)
    locks = (state.lock,)
    content_revision = composite_facet_content_revision(
        state.lock.content_revision,
        (),
    )
    return constituents, locks, content_revision


def _issue_composite_from_provenance(
    provenance: _FacetCompositeProvenance,
) -> CompositeFacetRegistry:
    """Publish a composite and retire its provenance if publication fails."""
    try:
        return _assemble_composite_from_provenance(provenance)
    except BaseException:
        _FACET_PROVENANCE_AUTHORITIES.retire(provenance)
        raise


def _assemble_composite_from_provenance(
    provenance: _FacetCompositeProvenance,
) -> CompositeFacetRegistry:
    """Assemble and issue the exact constituents selected by provenance."""
    constituents, locks, content_revision = _issued_provenance_state(
        provenance,
        allow_provisional=True,
    )
    merged: dict[str, ContextFacet] = {}
    authorities: dict[str, FacetRegistry] = {}
    for constituent_index, (registry, lock) in enumerate(
        zip(constituents, locks, strict=True)
    ):
        location = (
            "$.facet-registry.base"
            if constituent_index == 0
            else f"$.facet-registry.extensions[{constituent_index - 1}]"
        )
        _require_constituent(registry, lock, location)
        for facet_id, facet in registry.facets.items():
            if facet_id in merged:
                _fail(location, f"duplicate facet id {facet_id!r}")
            merged[facet_id] = facet
            authorities[facet_id] = registry

    result = object.__new__(CompositeFacetRegistry)
    object.__setattr__(result, "schema_version", 1)
    object.__setattr__(result, "id", COMPOSITE_FACET_REGISTRY_ID)
    object.__setattr__(result, "constituents", constituents)
    object.__setattr__(result, "facets", MappingProxyType(merged))
    object.__setattr__(result, "facet_authorities", MappingProxyType(authorities))
    object.__setattr__(result, "content_revision", content_revision)
    state = _CompositeAuthorityState(
        snapshot=_capture_composite_authority(result),
        provenance=provenance,
    )
    try:
        _COMPOSITE_AUTHORITIES.issue(result, state)
        return result
    except BaseException:
        _COMPOSITE_AUTHORITIES.retire(result)
        raise


def _retire_composite_tree(value: object) -> None:
    """Retire a provisional composite and its provenance in dependency order."""
    if type(value) is not CompositeFacetRegistry:
        return
    state = _COMPOSITE_AUTHORITIES.retire(value)
    if type(state) is _CompositeAuthorityState:
        _FACET_PROVENANCE_AUTHORITIES.retire(state.provenance)


def _provisional_composite_view(
    composite: CompositeFacetRegistry,
) -> _ProvisionalCompositeFacetView:
    """Return a parsing-only view after checking provisional authority."""
    if not _has_composite_authority(composite, allow_provisional=True):
        _fail("$.facet-registry", "provisional composite is not issued here")
    return _ProvisionalCompositeFacetView(composite)


def _require_constituent(
    registry: FacetRegistry,
    lock: FacetConstituentLock,
    location: str,
) -> None:
    """Match one exact parsed registry with its validated lock identity."""
    if registry.schema_version != 1:
        _fail(location + ".schema-version", "constituent schema version is not 1")
    if registry.id != lock.id:
        _fail(location + ".id", "constituent identifier differs from the lock")
    if registry.owner != lock.owner:
        _fail(location + ".owner", "constituent owner differs from the lock")
    if lock.namespace != lock.owner:
        _fail(location + ".namespace", "constituent namespace differs from owner")
    for facet_id, facet in registry.facets.items():
        if type(facet_id) is not str or type(facet) is not ContextFacet:
            _fail(location + ".facets", "constituent facets have the wrong type")
        if facet.id != facet_id:
            _fail(location + ".facets", "constituent facet key differs from its id")


def _fail(location: str, message: str) -> NoReturn:
    raise AcquisitionContractError(location, message)
