"""Derive enforcement requirements from external resolutions without registry access."""

from __future__ import annotations

from typing import NamedTuple, NoReturn

from ._authority import IdentityAuthorityStore
from .attention import (
    AttentionRequirements,
    DeliberativeAttentionRequirement,
    RunnableAttentionRequirement,
    _is_issued_requirements,
    derive_attention_requirements,
)
from .completion import CompletionRequirement
from .exceptions import AcquisitionContractError
from .external_resolution import (
    ExternalResolutionResult,
    _ExternalResolutionState,
    _issued_external_resolution_state,
)
from .runners import CheckerRunnerRegistry, DetectorRunnerRegistry


class _ExternalAttentionState(NamedTuple):
    """Bind one public requirement projection to its external resolution."""

    resolution: ExternalResolutionResult
    resolution_state: _ExternalResolutionState
    requirements: AttentionRequirements


class ExternalAttentionRequirements:
    """Expose canonical enforcement requirements without the private registry."""

    __slots__ = ("__weakref__", "_token")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("external attention requirements must be issued")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("external attention requirements cannot be subclassed")

    @property
    def completion(self) -> tuple[CompletionRequirement, ...]:
        """Return every canonical requirement in execution order."""
        return _issued_external_attention_state(self).requirements.completion

    @property
    def deliberative(self) -> tuple[DeliberativeAttentionRequirement, ...]:
        """Return requirements decided by unaided judgment."""
        return _issued_external_attention_state(self).requirements.deliberative

    @property
    def assisted(self) -> tuple[RunnableAttentionRequirement, ...]:
        """Return requirements supported by candidate detectors."""
        return _issued_external_attention_state(self).requirements.assisted

    @property
    def mechanical(self) -> tuple[RunnableAttentionRequirement, ...]:
        """Return requirements decided by authoritative checkers."""
        return _issued_external_attention_state(self).requirements.mechanical

    def __copy__(self) -> NoReturn:
        raise TypeError("external attention requirements cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("external attention requirements cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("external attention requirements cannot be serialized")

    def __reduce_ex__(self, _protocol: object) -> NoReturn:
        raise TypeError("external attention requirements cannot be serialized")


_EXTERNAL_ATTENTION_AUTHORITIES: IdentityAuthorityStore[object] = (
    IdentityAuthorityStore()
)


def derive_external_attention_requirements(
    resolution: ExternalResolutionResult,
    *,
    checker_registry: CheckerRunnerRegistry | None = None,
    detector_registry: DetectorRunnerRegistry | None = None,
) -> ExternalAttentionRequirements:
    """Derive canonical requirements through an authenticated external boundary."""
    resolution_state = _issued_external_resolution_state(resolution)
    requirements: AttentionRequirements | None = None
    try:
        requirements = derive_attention_requirements(
            resolution_state.resolution,
            checker_registry=checker_registry,
            detector_registry=detector_registry,
        )
    except BaseException as error:
        _raise_changed_resolution(resolution, resolution_state, error)
        raise
    try:
        _require_same_resolution(resolution, resolution_state)
        return _issue_external_attention_requirements(
            resolution,
            resolution_state,
            requirements,
        )
    except BaseException as error:
        _raise_changed_resolution(resolution, resolution_state, error)
        raise


def _issue_external_attention_requirements(
    resolution: ExternalResolutionResult,
    resolution_state: _ExternalResolutionState,
    requirements: AttentionRequirements,
) -> ExternalAttentionRequirements:
    """Issue one opaque projection after complete requirement derivation."""
    if not _is_issued_requirements(requirements):
        _fail("$", "attention requirements are not issued here")
    result = object.__new__(ExternalAttentionRequirements)
    state = _ExternalAttentionState(resolution, resolution_state, requirements)
    try:
        token = _EXTERNAL_ATTENTION_AUTHORITIES.issue(result, state)
        object.__setattr__(result, "_token", token)
        _issued_external_attention_state(result)
        return result
    except BaseException:
        _EXTERNAL_ATTENTION_AUTHORITIES.retire(result)
        raise


def _issued_external_attention_state(result: object) -> _ExternalAttentionState:
    """Authenticate one external requirement projection and its authorities."""
    try:
        return _authenticate_external_attention_state(result)
    except BaseException:
        _EXTERNAL_ATTENTION_AUTHORITIES.retire(result)
        raise


def _authenticate_external_attention_state(
    result: object,
) -> _ExternalAttentionState:
    if type(result) is not ExternalAttentionRequirements:
        _fail("$", "external attention requirements are not issued here")
    issued = _EXTERNAL_ATTENTION_AUTHORITIES.lookup(result)
    if issued is None or getattr(result, "_token", None) is not issued[0]:
        _fail("$", "external attention requirements are not issued here")
    state = issued[1]
    if type(state) is not _ExternalAttentionState:
        _fail("$", "external attention requirements are not issued here")
    _require_same_resolution(state.resolution, state.resolution_state)
    if not _is_issued_requirements(state.requirements):
        _fail("$", "external attention requirement state changed")
    return state


def _require_same_resolution(
    resolution: ExternalResolutionResult,
    expected: _ExternalResolutionState,
) -> None:
    if _issued_external_resolution_state(resolution) is not expected:
        _fail("$", "external resolution authority state changed")


def _raise_changed_resolution(
    resolution: ExternalResolutionResult,
    expected: _ExternalResolutionState,
    error: BaseException,
) -> None:
    try:
        _require_same_resolution(resolution, expected)
    except BaseException as authority_error:
        raise authority_error from error


def _fail(location: str, message: str) -> NoReturn:
    raise AcquisitionContractError(location, message)
