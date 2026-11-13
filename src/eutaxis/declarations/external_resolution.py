"""Resolve authenticated external corpora without exposing their registries."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple, NoReturn

from ._authority import IdentityAuthorityStore, identity_value_state
from .exceptions import AcquisitionAuthorityError
from .external_result import (
    AcquisitionSourceCoordinate,
    ExternalAcquisitionResult,
    _ExternalAcquisitionResultState,
    _issued_external_result_state,
)
from .resolution import (
    ResolutionError,
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
    source_coordinates_by_path: tuple[tuple[Path, AcquisitionSourceCoordinate], ...]


class _ExternalResolutionFailureState(NamedTuple):
    """Bind one resolver failure to its exact acquisition authority."""

    acquisition: ExternalAcquisitionResult
    acquisition_state: _ExternalAcquisitionResultState
    error: ResolutionError
    error_snapshot: tuple[object, ...]
    source_coordinates_by_path: tuple[tuple[Path, AcquisitionSourceCoordinate], ...]


class ExternalResolutionError(ResolutionError):
    """Report one acquisition-bound external semantic-resolution failure."""

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("external resolution errors must be issued")

    def __reduce__(self) -> NoReturn:
        raise TypeError("external resolution errors cannot be serialized")

    def __reduce_ex__(self, _protocol: object) -> NoReturn:
        raise TypeError("external resolution errors cannot be serialized")


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
_EXTERNAL_FAILURE_AUTHORITIES: IdentityAuthorityStore[object] = IdentityAuthorityStore()


def resolve_external_compilation_unit(
    acquisition: ExternalAcquisitionResult,
    manifest_id: str,
    context: Mapping[str, object],
) -> ExternalResolutionResult:
    """Resolve one manifest while retaining its exact acquisition authority."""
    acquisition_state = _issued_external_result_state(acquisition)
    source_coordinates = _snapshot_acquisition_source_coordinates(acquisition_state)
    registry = acquisition_state.external_registry_state.registry
    resolution: ResolutionResult | None = None
    try:
        resolution = resolve_compilation_unit(registry, manifest_id, context)
    except ResolutionError as error:
        _raise_changed_acquisition(acquisition, acquisition_state, error)
        raise _issue_external_resolution_error(
            acquisition,
            acquisition_state,
            error,
            source_coordinates,
        ) from error
    except BaseException as error:
        _raise_changed_acquisition(acquisition, acquisition_state, error)
        raise
    try:
        _require_same_acquisition(acquisition, acquisition_state)
        return _issue_external_resolution(
            acquisition,
            acquisition_state,
            resolution,
            source_coordinates,
        )
    except BaseException as error:
        _RESOLUTION_AUTHORITIES.retire(resolution)
        _raise_changed_acquisition(acquisition, acquisition_state, error)
        raise


def _issue_external_resolution(
    acquisition: ExternalAcquisitionResult,
    acquisition_state: _ExternalAcquisitionResultState,
    resolution: ResolutionResult,
    source_coordinates: tuple[tuple[Path, AcquisitionSourceCoordinate], ...],
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
        source_coordinates,
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


def _issue_external_resolution_error(
    acquisition: ExternalAcquisitionResult,
    acquisition_state: _ExternalAcquisitionResultState,
    error: ResolutionError,
    source_coordinates: tuple[tuple[Path, AcquisitionSourceCoordinate], ...],
) -> ExternalResolutionError:
    """Issue one opaque failure bound to the attempted external resolution."""
    issued = Exception.__new__(ExternalResolutionError)
    Exception.__init__(issued, *error.args)
    for name in (
        "code",
        "detail",
        "source",
        "trace",
        "truth",
        "applicability",
    ):
        setattr(issued, name, getattr(error, name))
    state = _ExternalResolutionFailureState(
        acquisition,
        acquisition_state,
        error,
        _resolution_error_snapshot(error),
        source_coordinates,
    )
    _EXTERNAL_FAILURE_AUTHORITIES.issue(issued, state)
    _issued_external_resolution_error_state(issued)
    return issued


def _issued_external_resolution_error_state(
    error: object,
) -> _ExternalResolutionFailureState:
    """Authenticate one external failure and its retained resolver evidence."""
    if type(error) is not ExternalResolutionError:
        _fail("$", "external resolution error is not issued here")
    state = _EXTERNAL_FAILURE_AUTHORITIES.state(error)
    if type(state) is not _ExternalResolutionFailureState:
        _fail("$", "external resolution error is not issued here")
    _require_same_acquisition(state.acquisition, state.acquisition_state)
    original = state.error
    if _resolution_error_snapshot(original) != state.error_snapshot:
        _fail("$", "original resolution error state changed")
    for name in (
        "code",
        "detail",
        "source",
        "trace",
        "truth",
        "applicability",
    ):
        if getattr(error, name) is not getattr(original, name):
            _fail("$", f"external resolution error {name} changed")
    if error.args != original.args:
        _fail("$", "external resolution error message changed")
    by_path = dict(state.source_coordinates_by_path)
    if len(by_path) != len(state.source_coordinates_by_path):
        _fail("$.sources", "external resolution failure sources changed")
    for source in (
        *((event.source for event in original.trace.events) if original.trace else ()),
        *((original.source,) if original.source is not None else ()),
    ):
        if source.path not in by_path:
            _fail("$.trace", "resolution failure source binding changed")
    return state


def _resolution_error_snapshot(error: ResolutionError) -> tuple[object, ...]:
    """Capture the complete identity and value state of resolver failure evidence."""
    return (
        error.code,
        error.detail,
        id(error.source),
        identity_value_state(error.source),
        id(error.trace),
        identity_value_state(error.trace),
        error.truth,
        id(error.applicability),
        identity_value_state(error.applicability),
        error.args,
    )


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
    _validate_resolution_source_coordinates(state)
    return state


def _snapshot_acquisition_source_coordinates(
    acquisition: _ExternalAcquisitionResultState,
) -> tuple[tuple[Path, AcquisitionSourceCoordinate], ...]:
    """Bind current source paths before semantic resolution begins."""
    by_path: dict[Path, AcquisitionSourceCoordinate] = {}
    for loaded, coordinate in acquisition.source_map:
        path = loaded.path.resolve()
        prior = by_path.get(path)
        if prior is not None and prior != coordinate:
            _fail("$.sources", f"duplicate resolved source path {path}")
        by_path[path] = coordinate
    return tuple(sorted(by_path.items(), key=lambda item: str(item[0])))


def _validate_resolution_source_coordinates(state: _ExternalResolutionState) -> None:
    """Require every retained resolver path to keep one acquired coordinate."""
    coordinates = state.acquisition_state.source_coordinates
    by_path = dict(state.source_coordinates_by_path)
    if (
        len(by_path) != len(state.source_coordinates_by_path)
        or any(
            not any(coordinate is issued for issued in coordinates)
            for coordinate in by_path.values()
        )
        or any(
            event.source.path not in by_path for event in state.resolution.trace.events
        )
    ):
        _fail("$.trace", "resolution source-coordinate binding changed")


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
    raise AcquisitionAuthorityError(location, message)
