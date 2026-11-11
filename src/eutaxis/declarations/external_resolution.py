"""Resolve authenticated external corpora without exposing their registries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple, NoReturn

from ._authority import IdentityAuthorityStore
from .exceptions import AcquisitionContractError
from .external_result import (
    ExternalAcquisitionResult,
    _ExternalAcquisitionResultState,
    _issued_external_result_state,
)
from .resolution import (
    ResolutionResult,
    ResolutionTrace,
    ResolvedCompilationUnit,
    _RESOLUTION_AUTHORITIES,
    _is_issued_resolution_result,
    resolve_compilation_unit,
)


class _ExternalResolutionState(NamedTuple):
    """Bind one opaque projection to its acquisition and internal resolution."""

    acquisition: ExternalAcquisitionResult
    acquisition_state: _ExternalAcquisitionResultState
    resolution: ResolutionResult


class ExternalResolutionResult:
    """Expose one resolved unit and trace without its private registry."""

    __slots__ = ("__weakref__", "_owner_token", "_token")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("external resolution results must be issued")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("external resolution results cannot be subclassed")

    @property
    def unit(self) -> ResolvedCompilationUnit:
        """Return the authenticated resolved compilation unit."""
        return _issued_external_resolution_state(self).resolution.unit

    @property
    def trace(self) -> ResolutionTrace:
        """Return the authenticated semantic-resolution trace."""
        return _issued_external_resolution_state(self).resolution.trace

    def __copy__(self) -> NoReturn:
        raise TypeError("external resolution results cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("external resolution results cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("external resolution results cannot be serialized")

    def __reduce_ex__(self, _protocol: object) -> NoReturn:
        raise TypeError("external resolution results cannot be serialized")


_EXTERNAL_RESOLUTION_AUTHORITIES: IdentityAuthorityStore[object] = (
    IdentityAuthorityStore()
)
_EXTERNAL_RESOLUTION_OWNERS: IdentityAuthorityStore[object] = IdentityAuthorityStore()


def resolve_external_compilation_unit(
    acquisition: ExternalAcquisitionResult,
    manifest_id: str,
    context: Mapping[str, object],
) -> ExternalResolutionResult:
    """Resolve one manifest while retaining its exact acquisition authority."""
    acquisition_state = _issued_external_result_state(acquisition)
    registry = acquisition_state.external_registry_state.registry
    resolution: ResolutionResult | None = None
    try:
        resolution = resolve_compilation_unit(registry, manifest_id, context)
    except BaseException as error:
        _raise_changed_acquisition(acquisition, acquisition_state, error)
        raise
    try:
        _require_same_acquisition(acquisition, acquisition_state)
        return _issue_external_resolution(
            acquisition,
            acquisition_state,
            resolution,
        )
    except BaseException as error:
        _RESOLUTION_AUTHORITIES.retire(resolution)
        _raise_changed_acquisition(acquisition, acquisition_state, error)
        raise


def _issue_external_resolution(
    acquisition: ExternalAcquisitionResult,
    acquisition_state: _ExternalAcquisitionResultState,
    resolution: ResolutionResult,
) -> ExternalResolutionResult:
    if not _is_issued_resolution_result(resolution):
        _fail("$", "internal resolution result is not issued here")
    if resolution.registry is not acquisition_state.external_registry_state.registry:
        _fail("$", "resolution registry differs from the acquired registry")
    result = object.__new__(ExternalResolutionResult)
    state = _ExternalResolutionState(
        acquisition,
        acquisition_state,
        resolution,
    )
    try:
        owner_token = _EXTERNAL_RESOLUTION_OWNERS.issue(result, (resolution,))
        object.__setattr__(result, "_owner_token", owner_token)
        token = _EXTERNAL_RESOLUTION_AUTHORITIES.issue(result, state)
        object.__setattr__(result, "_token", token)
        _issued_external_resolution_state(result)
        return result
    except BaseException:
        _retire_external_resolution(result)
        raise


def _issued_external_resolution_state(result: object) -> _ExternalResolutionState:
    """Authenticate an external resolution and every retained authority."""
    try:
        return _authenticate_external_resolution_state(result)
    except BaseException:
        _retire_external_resolution(result)
        raise


def _authenticate_external_resolution_state(
    result: object,
) -> _ExternalResolutionState:
    if type(result) is not ExternalResolutionResult:
        _fail("$", "external resolution result is not issued here")
    issued = _EXTERNAL_RESOLUTION_AUTHORITIES.lookup(result)
    if issued is None or getattr(result, "_token", None) is not issued[0]:
        _fail("$", "external resolution result is not issued here")
    state = issued[1]
    if type(state) is not _ExternalResolutionState:
        _fail("$", "external resolution result is not issued here")
    owner = _EXTERNAL_RESOLUTION_OWNERS.lookup(result)
    if (
        owner is None
        or getattr(result, "_owner_token", None) is not owner[0]
        or type(owner[1]) is not tuple
        or len(owner[1]) != 1
        or owner[1][0] is not state.resolution
    ):
        _fail("$", "external resolution result owner changed")
    _require_same_acquisition(state.acquisition, state.acquisition_state)
    if not _is_issued_resolution_result(state.resolution):
        _fail("$", "internal resolution authority changed")
    if (
        state.resolution.registry
        is not state.acquisition_state.external_registry_state.registry
    ):
        _fail("$", "resolution registry differs from the acquired registry")
    return state


def _retire_external_resolution(result: object) -> None:
    primary = _EXTERNAL_RESOLUTION_AUTHORITIES.lookup(result)
    owner = _EXTERNAL_RESOLUTION_OWNERS.lookup(result)
    primary_state = primary[1] if primary is not None else None
    owner_state = owner[1] if owner is not None else None
    primary_resolution = (
        primary_state.resolution
        if (
            primary is not None
            and getattr(result, "_token", None) is primary[0]
            and type(primary_state) is _ExternalResolutionState
        )
        else None
    )
    owner_resolution = (
        owner_state[0]
        if (
            owner is not None
            and getattr(result, "_owner_token", None) is owner[0]
            and type(owner_state) is tuple
            and len(owner_state) == 1
            and type(owner_state[0]) is ResolutionResult
        )
        else None
    )
    _EXTERNAL_RESOLUTION_AUTHORITIES.retire(result)
    _EXTERNAL_RESOLUTION_OWNERS.retire(result)
    if (
        primary_resolution is not None
        and owner_resolution is not None
        and primary_resolution is not owner_resolution
    ):
        return
    owned = primary_resolution or owner_resolution
    if owned is not None:
        _RESOLUTION_AUTHORITIES.retire(owned)


def _require_same_acquisition(
    acquisition: ExternalAcquisitionResult,
    expected: _ExternalAcquisitionResultState,
) -> None:
    if _issued_external_result_state(acquisition) is not expected:
        _fail("$", "external acquisition authority state changed")


def _raise_changed_acquisition(
    acquisition: ExternalAcquisitionResult,
    expected: _ExternalAcquisitionResultState,
    error: BaseException,
) -> None:
    try:
        _require_same_acquisition(acquisition, expected)
    except BaseException as authority_error:
        raise authority_error from error


def _fail(location: str, message: str) -> NoReturn:
    raise AcquisitionContractError(location, message)
