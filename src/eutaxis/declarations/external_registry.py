"""Build the combined registry from one authenticated external stage."""

from __future__ import annotations

from typing import NamedTuple, NoReturn, SupportsIndex

from ._authority import IdentityAuthorityStore, identity_value_state
from .exceptions import AcquisitionContractError
from .external_acquisition import (
    _ExternalAcquisitionStage,
    _ExternalAcquisitionStageState,
    _issued_external_stage_state,
)
from .registry import (
    DeclarationRegistry,
    _build_declaration_registry_from_sources,
)


class _ExternalRegistryState(NamedTuple):
    """Bind one code-built combined registry to its exact source stage."""

    stage: _ExternalAcquisitionStage
    stage_state: _ExternalAcquisitionStageState
    registry: DeclarationRegistry
    registry_state: object


class _ExternalRegistryResult:
    """Authenticate one combined registry without exposing it publicly."""

    __slots__ = ("__weakref__",)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("external registry results must be issued")

    def __copy__(self) -> NoReturn:
        raise TypeError("external registry results cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("external registry results cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("external registry results cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("external registry results cannot be serialized")


_EXTERNAL_REGISTRY_AUTHORITIES: IdentityAuthorityStore[object] = (
    IdentityAuthorityStore()
)


def _issue_external_declaration_registry(
    stage: _ExternalAcquisitionStage,
) -> _ExternalRegistryResult:
    """Build and issue the only combined registry admitted for one stage."""
    registry = _build_external_declaration_registry(stage)
    stage_state = _issued_external_stage_state(stage)
    result = object.__new__(_ExternalRegistryResult)
    state = _ExternalRegistryState(
        stage=stage,
        stage_state=stage_state,
        registry=registry,
        registry_state=identity_value_state(registry),
    )
    try:
        _EXTERNAL_REGISTRY_AUTHORITIES.issue(result, state)
        _issued_external_registry_state(result)
        return result
    except BaseException:
        _EXTERNAL_REGISTRY_AUTHORITIES.retire(result)
        raise


def _issued_external_registry_state(result: object) -> _ExternalRegistryState:
    """Authenticate a code-built registry and its unchanged source stage."""
    if type(result) is not _ExternalRegistryResult:
        _fail("$", "external registry result is not issued here")
    state = _EXTERNAL_REGISTRY_AUTHORITIES.state(result)
    if type(state) is not _ExternalRegistryState:
        _fail("$", "external registry result is not issued here")
    stage_state = _issued_external_stage_state(state.stage)
    if stage_state is not state.stage_state:
        _fail("$", "external registry stage state changed")
    if type(state.registry) is not DeclarationRegistry:
        _fail("$.registry", "combined declaration registry has the wrong type")
    if state.registry.facet_registry is not stage_state.composite:
        _fail("$.registry.facet-registry", "registry changed its facet authority")
    if identity_value_state(state.registry) != state.registry_state:
        _fail("$.registry", "combined declaration registry state changed")
    return state


def _retire_external_registry(result: object) -> None:
    """Retire one private combined-registry authority."""
    _EXTERNAL_REGISTRY_AUTHORITIES.retire(result)


def _build_external_declaration_registry(stage: object) -> DeclarationRegistry:
    """Build one registry from the exact sources and facets retained by a stage."""
    state = _issued_external_stage_state(stage)
    try:
        registry = _build_declaration_registry_from_sources(
            state.declarations,
            state.composite,
        )
    except BaseException as primary_error:
        try:
            _issued_external_stage_state(stage)
        except BaseException as authority_error:
            authority_error.__cause__ = primary_error
            raise authority_error
        raise
    final_state = _issued_external_stage_state(stage)
    if final_state is not state:
        raise AssertionError("external acquisition stage state changed")
    if registry.facet_registry is not state.composite:
        raise AssertionError("combined registry changed the retained facet registry")
    return registry


def _fail(location: str, message: str) -> NoReturn:
    raise AcquisitionContractError(location, message)
