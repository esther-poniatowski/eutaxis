"""Semantically validate generated locks without publishing acquisition results."""

from __future__ import annotations

from typing import NamedTuple, NoReturn, SupportsIndex

from ._authority import IdentityAuthorityStore
from .exceptions import AcquisitionContractError
from .external_acquisition import (
    _ExternalAcquisitionStage,
    _acquire_external_stage_from_candidate,
    _retire_stage_tree,
)
from .external_registry import (
    _ExternalRegistryResult,
    _issue_external_declaration_registry,
    _issued_external_registry_state,
    _retire_external_registry,
)
from .generation_candidate import (
    _GeneratedCandidate,
    _GeneratedCandidateState,
    _issued_generated_candidate_state,
    _retire_generated_candidate,
)


class _CandidateValidationReceiptState(NamedTuple):
    """Bind successful semantic validation to one exact live candidate."""

    candidate: _GeneratedCandidate
    candidate_state: _GeneratedCandidateState
    canonical_bytes: bytes


class _CandidateValidationReceipt:
    """Represent private, single-use proof of generated-candidate validation."""

    __slots__ = ("__weakref__",)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("candidate validation receipts must be issued")

    def __copy__(self) -> NoReturn:
        raise TypeError("candidate validation receipts cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("candidate validation receipts cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("candidate validation receipts cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("candidate validation receipts cannot be serialized")


_VALIDATION_RECEIPT_AUTHORITIES: IdentityAuthorityStore[object] = (
    IdentityAuthorityStore()
)


def _validate_generated_candidate(
    candidate: _GeneratedCandidate,
) -> _CandidateValidationReceipt:
    """Run complete locked acquisition and issue only a private receipt.

    Every failure retires the generated candidate. A successful validation
    retires its temporary acquisition graph before returning the receipt.
    """
    stage: _ExternalAcquisitionStage | None = None
    registry: _ExternalRegistryResult | None = None
    receipt: _CandidateValidationReceipt | None = None
    try:
        initial_state = _issued_generated_candidate_state(candidate)
        stage = _acquire_external_stage_from_candidate(candidate)
        registry = _issue_external_declaration_registry(stage)
        _issued_external_registry_state(registry)
        final_state = _issued_generated_candidate_state(candidate)
        if final_state is not initial_state:
            _fail("$", "generated candidate authority changed during validation")
        receipt = _issue_validation_receipt(candidate, final_state)
    except BaseException as primary_error:
        _retire_failed_validation(
            candidate,
            receipt=receipt,
            registry=registry,
            stage=stage,
            primary_error=primary_error,
        )
        raise
    if receipt is None:
        raise AssertionError("candidate validation receipt was not issued")

    try:
        _retire_validation_graph(registry, stage)
    except BaseException as primary_error:
        _retire_failed_validation(
            candidate,
            receipt=receipt,
            registry=registry,
            stage=stage,
            primary_error=primary_error,
        )
        raise
    return receipt


def _consume_validated_candidate(
    candidate: _GeneratedCandidate,
    receipt: _CandidateValidationReceipt,
) -> bytes:
    """Retire a validated candidate and receipt, then return its exact bytes."""
    state = _issued_validation_receipt_state(receipt)
    candidate_state = _issued_generated_candidate_state(candidate)
    if state.candidate is not candidate or state.candidate_state is not candidate_state:
        _fail("$", "validation receipt belongs to another candidate")
    canonical_bytes = candidate_state.canonical_bytes
    if canonical_bytes != state.canonical_bytes:
        _fail("$.lock", "validated candidate bytes changed")
    _VALIDATION_RECEIPT_AUTHORITIES.retire(receipt)
    _retire_generated_candidate(candidate)
    return canonical_bytes


def _issue_validation_receipt(
    candidate: _GeneratedCandidate,
    candidate_state: _GeneratedCandidateState,
) -> _CandidateValidationReceipt:
    """Issue one receipt from the exact candidate state that passed validation."""
    result = object.__new__(_CandidateValidationReceipt)
    state = _CandidateValidationReceiptState(
        candidate,
        candidate_state,
        candidate_state.canonical_bytes,
    )
    try:
        _VALIDATION_RECEIPT_AUTHORITIES.issue(result, state)
        _issued_validation_receipt_state(result)
        return result
    except BaseException:
        _VALIDATION_RECEIPT_AUTHORITIES.retire(result)
        raise


def _issued_validation_receipt_state(
    receipt: object,
) -> _CandidateValidationReceiptState:
    """Authenticate one receipt and its exact still-live candidate."""
    if type(receipt) is not _CandidateValidationReceipt:
        _fail("$", "candidate validation receipt is not issued here")
    state = _VALIDATION_RECEIPT_AUTHORITIES.state(receipt)
    if type(state) is not _CandidateValidationReceiptState:
        _fail("$", "candidate validation receipt is not issued here")
    candidate_state = _issued_generated_candidate_state(state.candidate)
    if (
        candidate_state is not state.candidate_state
        or candidate_state.canonical_bytes != state.canonical_bytes
    ):
        _fail("$", "validated candidate authority changed")
    return state


def _retire_validation_receipt(receipt: object) -> None:
    """Retire one private receipt without consuming its candidate."""
    _VALIDATION_RECEIPT_AUTHORITIES.retire(receipt)


def _retire_validation_graph(
    registry: _ExternalRegistryResult | None,
    stage: _ExternalAcquisitionStage | None,
) -> None:
    """Retire temporary semantic-acquisition authority in dependency order."""
    first_error: BaseException | None = None
    if registry is not None:
        try:
            _retire_external_registry(registry)
        except BaseException as exc:
            first_error = exc
    if stage is not None:
        try:
            _retire_stage_tree(stage)
        except BaseException as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise first_error


def _retire_failed_validation(
    candidate: _GeneratedCandidate,
    *,
    receipt: _CandidateValidationReceipt | None,
    registry: _ExternalRegistryResult | None,
    stage: _ExternalAcquisitionStage | None,
    primary_error: BaseException,
) -> None:
    """Retire all validation authority while preserving the primary failure."""
    cleanup_error: BaseException | None = None
    receipt_retirement_failed = False
    if receipt is not None:
        try:
            _retire_validation_receipt(receipt)
        except BaseException as exc:
            cleanup_error = exc
            receipt_retirement_failed = True
    try:
        _retire_validation_graph(registry, stage)
    except BaseException as exc:
        if cleanup_error is None:
            cleanup_error = exc
    try:
        _retire_generated_candidate(candidate)
    except BaseException as exc:
        if cleanup_error is None:
            cleanup_error = exc
    if receipt is not None and receipt_retirement_failed:
        try:
            _retire_validation_receipt(receipt)
        except BaseException as exc:
            if cleanup_error is None:
                cleanup_error = exc
    if cleanup_error is not None:
        _attach_cleanup_cause(primary_error, cleanup_error)


def _attach_cleanup_cause(
    primary_error: BaseException,
    cleanup_error: BaseException,
) -> None:
    """Attach cleanup failure without discarding an existing cause chain."""
    if cleanup_error is primary_error:
        return
    prior_cause = primary_error.__cause__
    cursor = cleanup_error
    seen: set[int] = set()
    contains_prior = False
    while True:
        if cursor is primary_error or id(cursor) in seen:
            return
        if cursor is prior_cause:
            contains_prior = True
        seen.add(id(cursor))
        if cursor.__cause__ is None:
            break
        cursor = cursor.__cause__
    if prior_cause is not None and not contains_prior:
        if cursor.__cause__ is None:
            cursor.__cause__ = prior_cause
    primary_error.__cause__ = cleanup_error


def _fail(location: str, message: str) -> NoReturn:
    raise AcquisitionContractError(location, message)
