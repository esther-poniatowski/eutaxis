"""Issue composite facet registries with process-local constituent authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import NoReturn, SupportsIndex

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


_COMPOSITE_AUTHORITIES: IdentityAuthorityStore[object] = IdentityAuthorityStore()


def _capture_composite_authority(
    value: CompositeFacetRegistry,
) -> tuple[object, ...]:
    """Capture exact composite values and nested carrier identities."""
    return (identity_value_state(value),)


def _is_issued_composite_facet_registry(value: object) -> bool:
    """Return whether ``value`` retains its complete issuance snapshot."""
    if type(value) is not CompositeFacetRegistry:
        return False
    try:
        issued = _COMPOSITE_AUTHORITIES.lookup(value)
        if issued is None or type(issued[1]) is not tuple or len(issued[1]) != 2:
            return False
        snapshot, packaged = issued[1]
        if snapshot != _capture_composite_authority(value):
            return False
        if type(packaged) is not PackagedInternalSource:
            return False
        _evidence, _lock, base = _issued_packaged_facet_state(packaged)
        return value.constituents == (base,) and value.constituents[0] is base
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
    if type(packaged) is not PackagedInternalSource:
        _fail("$.facet-registry.base", "packaged source has the wrong exact type")

    _evidence, base_lock, base = _issued_packaged_facet_state(packaged)
    _require_constituent(base, base_lock, "$.facet-registry.base")
    if base.id != "eutaxis/context-facets" or base.owner != "eutaxis":
        _fail(
            "$.facet-registry.base",
            "base registry identity is not canonical",
        )
    content_revision = composite_facet_content_revision(
        base_lock.content_revision,
        (),
    )
    constituents = (base,)
    merged: dict[str, ContextFacet] = {}
    authorities: dict[str, FacetRegistry] = {}
    for constituent_index, registry in enumerate(constituents):
        for facet_id, facet in registry.facets.items():
            if facet_id in merged:
                location = (
                    "$.facet-registry.base"
                    if constituent_index == 0
                    else f"$.facet-registry.extensions[{constituent_index - 1}]"
                )
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
    state = (_capture_composite_authority(result), packaged)
    try:
        _COMPOSITE_AUTHORITIES.issue(result, state)
        return result
    except BaseException:
        _COMPOSITE_AUTHORITIES.retire(result)
        raise


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
