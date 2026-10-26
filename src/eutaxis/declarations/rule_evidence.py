"""Evaluate every effective rule criterion in one single-use transaction."""

from __future__ import annotations

from _thread import LockType
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock
from types import MappingProxyType
from typing import NoReturn, Protocol, SupportsIndex, TypeAlias, cast
from weakref import ReferenceType, WeakKeyDictionary, ref

from ._authority import IdentityAuthorityStore, identity_value_state
from ._runner_support import exception_detail, validate_synchronous_runner
from .attention import (
    AssistedAttentionEntry,
    AttentionPlan,
    CompletionRequirement,
    DeliberativeAttentionEntry,
    MechanicalAttentionEntry,
    RuleCriterionKey,
    _is_issued_attention_plan,
    _validate_assurance,
)
from .embedded_schema import validate_json_instance
from .enforcement import EnforcementClass
from .exceptions import (
    CheckerExecutionError,
    DetectorExecutionError,
    RuleEvidenceError,
)
from .execution import (
    DetectorExecution,
    _is_issued_detector_execution,
    execute_checker,
    execute_detector,
)
from .models import JsonValue, VersionedReference, freeze_json, json_values_equal
from .results import CheckerResult, EvaluationState
from .source import format_document_path

_EVIDENCE_ISSUER = object()
_REQUEST_ISSUER = object()
_SESSION_ISSUER = object()
_EVIDENCE_AUTHORITIES: IdentityAuthorityStore[RuleEvidence] = IdentityAuthorityStore()
_SESSION_AUTHORITIES: IdentityAuthorityStore[RuleEvidenceSession] = (
    IdentityAuthorityStore()
)


class RuleEvidenceSessionState(StrEnum):
    """Lifecycle states of one non-reentrant rule-evidence transaction."""

    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED_AFTER_EXECUTION = "failed-after-execution"


@dataclass(frozen=True)
class RuleManualJudgmentSubmission:
    """Supply one untrusted manual judgment for a rule criterion."""

    key: RuleCriterionKey
    evaluator: VersionedReference
    input_revision: str
    evidence: Mapping[str, object]


@dataclass(frozen=True, init=False)
class RuleResidualJudgmentRequest:
    """Expose one exact detector execution for residual judgment."""

    requirement: CompletionRequirement
    residual_question: str
    execution: DetectorExecution
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("RuleResidualJudgmentRequest instances must be issued")


@dataclass(frozen=True)
class RuleResidualJudgmentSubmission:
    """Supply the residual decision for one exact detector execution."""

    schema_version: int
    request: RuleResidualJudgmentRequest
    state: EvaluationState
    rationale: str


class RuleResidualJudgmentProvider(Protocol):
    """Judge the residual question after one successful detector execution."""

    def __call__(
        self, request: RuleResidualJudgmentRequest, /
    ) -> RuleResidualJudgmentSubmission: ...


@dataclass(frozen=True)
class RuleManualEvidence:
    requirement: CompletionRequirement
    state: EvaluationState
    submission: RuleManualJudgmentSubmission


@dataclass(frozen=True)
class RuleAssistedEvidence:
    requirement: CompletionRequirement
    state: EvaluationState
    execution: DetectorExecution | None
    judgment: RuleResidualJudgmentSubmission | None
    diagnostic: str | None


@dataclass(frozen=True)
class RuleMechanicalEvidence:
    requirement: CompletionRequirement
    state: EvaluationState
    result: CheckerResult | None
    diagnostic: str | None


RuleEvidenceRecord: TypeAlias = (
    RuleManualEvidence | RuleAssistedEvidence | RuleMechanicalEvidence
)


@dataclass(frozen=True, init=False, eq=False)
class RuleEvidence:
    """Retain canonical evidence for every effective rule criterion."""

    plan: AttentionPlan
    records: tuple[RuleEvidenceRecord, ...]
    _token: object
    _state: tuple[object, ...]
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("RuleEvidence instances must be issued by execution")

    def __copy__(self) -> NoReturn:
        raise TypeError("RuleEvidence instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("RuleEvidence instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("RuleEvidence instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("RuleEvidence instances cannot be serialized")


@dataclass(frozen=True)
class _InputSnapshot:
    manual_keys: tuple[RuleCriterionKey, ...]
    manual: tuple[tuple[EvaluationState, RuleManualJudgmentSubmission], ...]
    residual_keys: tuple[RuleCriterionKey, ...]
    providers: tuple[RuleResidualJudgmentProvider, ...]


@dataclass(frozen=True)
class _ManualSubmissionCapture:
    submission: RuleManualJudgmentSubmission
    key: RuleCriterionKey
    key_state: object
    evaluator: VersionedReference
    evaluator_state: object
    input_revision: str
    evidence: Mapping[str, object]
    evidence_state: object


@dataclass
class _SessionControl:
    token: object
    plan: AttentionPlan
    requirements: tuple[CompletionRequirement, ...]
    publication: tuple[RuleEvidenceSessionState, RuleEvidence | None]
    inputs: _InputSnapshot | None
    active: bool
    lock: LockType
    session: ReferenceType[RuleEvidenceSession] | None


_PLAN_CLAIMS: WeakKeyDictionary[AttentionPlan, object] = WeakKeyDictionary()
_SESSION_CONTROLS: WeakKeyDictionary[RuleEvidenceSession, _SessionControl] = (
    WeakKeyDictionary()
)
_CLAIM_LOCK = Lock()


class RuleEvidenceSession:
    """Execute every effective rule criterion at most once."""

    __slots__ = ("_token", "_issuer", "__weakref__")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("sessions must be issued by create_rule_evidence_session")

    @property
    def plan(self) -> AttentionPlan:
        return _require_session(self).plan

    @property
    def state(self) -> RuleEvidenceSessionState:
        return _require_session(self).publication[0]

    @property
    def evidence(self) -> RuleEvidence | None:
        return _require_session(self).publication[1]

    def __copy__(self) -> NoReturn:
        raise TypeError("RuleEvidenceSession instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("RuleEvidenceSession instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("RuleEvidenceSession instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("RuleEvidenceSession instances cannot be serialized")

    def execute(
        self,
        *,
        manual: Mapping[RuleCriterionKey, RuleManualJudgmentSubmission],
        residual_providers: Mapping[RuleCriterionKey, RuleResidualJudgmentProvider],
    ) -> RuleEvidence:
        """Evaluate the canonical rule-criterion sequence."""
        control = _require_session(self)
        _require_control_authority(control)
        claimed = False
        try:
            with control.lock:
                if (
                    control.publication[0] is not RuleEvidenceSessionState.READY
                    or control.active
                ):
                    _fail(("session", "state"), "session is not ready")
                claimed = True
                control.active = True
                control.publication = (RuleEvidenceSessionState.RUNNING, None)
            _SESSION_AUTHORITIES.issue(self, _capture_control_state(control))
            _require_control_authority(control)
            inputs = _prepare_inputs(control, manual, residual_providers)
            control.inputs = inputs
            session = control.session() if control.session is not None else None
            if session is None:
                _fail(("session",), "session authority differs")
            _SESSION_AUTHORITIES.issue(session, _capture_control_state(control))
            _require_session_authority(control)
            records = _execute_records(control)
            _require_session_authority(control)
            evidence = _issue_evidence(control.plan, records)
            with control.lock:
                control.publication = (RuleEvidenceSessionState.COMPLETED, evidence)
                control.active = False
            _SESSION_AUTHORITIES.issue(self, _capture_control_state(control))
            return evidence
        except Exception as exc:
            if not claimed:
                raise
            authority_error: RuleEvidenceError | None = None
            try:
                _require_control_authority(control)
            except RuleEvidenceError as authority:
                authority_error = authority
            with control.lock:
                control.publication = (
                    RuleEvidenceSessionState.FAILED_AFTER_EXECUTION,
                    None,
                )
                control.active = False
            _SESSION_AUTHORITIES.issue(self, _capture_control_state(control))
            if authority_error is not None:
                raise authority_error from exc
            if isinstance(exc, RuleEvidenceError):
                raise
            _fail(
                ("session", "execution"),
                f"execution raised {exception_detail(exc)}",
                exc,
            )
        except BaseException as exc:
            if not claimed:
                raise
            authority_error = None
            try:
                _require_control_authority(control)
            except RuleEvidenceError as authority:
                authority_error = authority
            with control.lock:
                control.publication = (
                    RuleEvidenceSessionState.FAILED_AFTER_EXECUTION,
                    None,
                )
                control.active = False
            _SESSION_AUTHORITIES.issue(self, _capture_control_state(control))
            if authority_error is not None:
                raise authority_error from exc
            raise


def create_rule_evidence_session(plan: AttentionPlan) -> RuleEvidenceSession:
    """Create one ready session from an exact issued attention plan."""
    _require_plan(plan)
    requirements = tuple(
        item
        for item in plan.requirements.completion
        if type(item.key) is RuleCriterionKey
    )
    _require_packet_correlations(plan, requirements)
    with _CLAIM_LOCK:
        if plan in _PLAN_CLAIMS:
            _fail(("plan",), "attention plan already owns a rule-evidence session")
        token = object()
        session = object.__new__(RuleEvidenceSession)
        object.__setattr__(session, "_token", token)
        object.__setattr__(session, "_issuer", _SESSION_ISSUER)
        control = _SessionControl(
            token,
            plan,
            requirements,
            (RuleEvidenceSessionState.READY, None),
            None,
            False,
            Lock(),
            ref(session),
        )
        _PLAN_CLAIMS[plan] = token
        _SESSION_CONTROLS[session] = control
        _SESSION_AUTHORITIES.issue(session, _capture_control_state(control))
    return session


def _require_session(session: object) -> _SessionControl:
    if (
        type(session) is not RuleEvidenceSession
        or getattr(session, "_issuer", None) is not _SESSION_ISSUER
    ):
        _fail(("session",), "session was not issued")
    with _CLAIM_LOCK:
        control = _SESSION_CONTROLS.get(cast(RuleEvidenceSession, session))
        if control is None or _PLAN_CLAIMS.get(control.plan) is not control.token:
            _fail(("session",), "session authority differs")
    if control.session is None or control.session() is not session:
        _fail(("session",), "session authority differs")
    if getattr(session, "_token", None) is not control.token:
        _fail(("session",), "session authority differs")
    return control


def _prepare_inputs(
    control: _SessionControl,
    manual: Mapping[RuleCriterionKey, RuleManualJudgmentSubmission],
    residual: Mapping[RuleCriterionKey, RuleResidualJudgmentProvider],
) -> _InputSnapshot:
    manual_keys = tuple(
        cast(RuleCriterionKey, item.key)
        for item in control.requirements
        if item.enforcement is EnforcementClass.DELIBERATIVE
    )
    residual_keys = tuple(
        cast(RuleCriterionKey, item.key)
        for item in control.requirements
        if item.enforcement is EnforcementClass.ASSISTED
    )
    supplied_manual = _snapshot_exact_mapping(manual, manual_keys, ("manual",))
    _require_control_authority(control)
    manual_captures = tuple(
        _capture_manual_submission(value, index)
        for index, value in enumerate(supplied_manual)
    )
    _require_manual_captures(manual_captures)
    manual_values_list: list[tuple[EvaluationState, RuleManualJudgmentSubmission]] = []
    for index, (key, capture) in enumerate(zip(manual_keys, manual_captures)):
        _require_manual_captures(manual_captures)
        manual_values_list.append(
            _canonical_manual(control.plan, key, capture.submission, index)
        )
        _require_manual_captures(manual_captures)
        _require_control_authority(control)
    manual_values = tuple(manual_values_list)
    _require_control_authority(control)
    residual_values = _snapshot_exact_mapping(
        residual, residual_keys, ("residual-providers",)
    )
    _require_control_authority(control)
    providers: list[RuleResidualJudgmentProvider] = []
    for index, value in enumerate(residual_values):
        provider = cast(RuleResidualJudgmentProvider, value)

        def invalid_provider(message: str, *, item: int = index) -> RuleEvidenceError:
            return RuleEvidenceError(
                format_document_path(("residual-providers", item)), message
            )

        validate_synchronous_runner(
            provider,
            invalid_provider,
        )
        providers.append(provider)
        _require_control_authority(control)
    return _InputSnapshot(
        manual_keys,
        manual_values,
        residual_keys,
        tuple(providers),
    )


def _snapshot_exact_mapping(
    supplied: Mapping[RuleCriterionKey, object],
    expected: tuple[RuleCriterionKey, ...],
    location: tuple[str | int, ...],
) -> tuple[object, ...]:
    if not isinstance(supplied, Mapping):
        _fail(location, "value must be a mapping")
    try:
        pairs = tuple(supplied.items())
    except Exception as exc:
        _fail(location, f"mapping could not be read: {exception_detail(exc)}", exc)
    if len(pairs) != len(expected):
        _fail(location, "mapping does not contain the exact required keys")
    result: list[object | None] = [None] * len(expected)
    occupied: set[int] = set()
    for index, pair in enumerate(pairs):
        try:
            key, value = pair
        except Exception as exc:
            _fail(location + (index,), "item is not a key-value pair", exc)
        position = next(
            (offset for offset, canonical in enumerate(expected) if key is canonical),
            None,
        )
        if (
            type(key) is not RuleCriterionKey
            or position is None
            or position in occupied
        ):
            _fail(location + (index, "key"), "key is not one exact required key")
        occupied.add(position)
        result[position] = value
    if len(occupied) != len(expected):
        _fail(location, "mapping does not contain the exact required keys")
    return tuple(cast(object, item) for item in result)


def _capture_manual_submission(value: object, index: int) -> _ManualSubmissionCapture:
    if type(value) is not RuleManualJudgmentSubmission:
        _fail(("manual", index), "submission carrier is invalid")
    submission = cast(RuleManualJudgmentSubmission, value)
    if (
        type(submission.evaluator) is not VersionedReference
        or type(submission.evaluator.id) is not str
        or type(submission.evaluator.version) is not int
    ):
        _fail(("manual", index, "evaluator"), "evaluator reference is invalid")
    return _ManualSubmissionCapture(
        submission,
        submission.key,
        identity_value_state(submission.key),
        submission.evaluator,
        identity_value_state(submission.evaluator),
        submission.input_revision,
        submission.evidence,
        identity_value_state(submission.evidence),
    )


def _require_manual_captures(
    captures: tuple[_ManualSubmissionCapture, ...],
) -> None:
    for index, capture in enumerate(captures):
        submission = capture.submission
        if (
            type(submission) is not RuleManualJudgmentSubmission
            or submission.key is not capture.key
            or identity_value_state(submission.key) != capture.key_state
            or submission.evaluator is not capture.evaluator
            or identity_value_state(submission.evaluator) != capture.evaluator_state
            or submission.input_revision is not capture.input_revision
            or submission.evidence is not capture.evidence
            or identity_value_state(submission.evidence) != capture.evidence_state
        ):
            _fail(("manual", index), "captured submission authority changed")


def _execute_records(control: _SessionControl) -> tuple[RuleEvidenceRecord, ...]:
    assert control.inputs is not None
    records: list[RuleEvidenceRecord] = []
    for requirement in control.requirements:
        _require_session_authority(control)
        if requirement.enforcement is EnforcementClass.DELIBERATIVE:
            records.append(_execute_manual(control, requirement))
        elif requirement.enforcement is EnforcementClass.ASSISTED:
            records.append(_execute_assisted(control, requirement))
        elif requirement.enforcement is EnforcementClass.MECHANICAL:
            records.append(_execute_mechanical(control, requirement))
        else:
            _fail(("records",), "rule criterion has no enforcement class")
    return tuple(records)


def _execute_manual(
    control: _SessionControl, requirement: CompletionRequirement
) -> RuleManualEvidence:
    assert control.inputs is not None
    key = cast(RuleCriterionKey, requirement.key)
    index = next(i for i, item in enumerate(control.inputs.manual_keys) if item is key)
    state, submission = control.inputs.manual[index]
    _require_session_authority(control)
    return RuleManualEvidence(requirement, state, submission)


def _canonical_manual(
    plan: AttentionPlan, key: RuleCriterionKey, value: object, index: int
) -> tuple[EvaluationState, RuleManualJudgmentSubmission]:
    submission = value
    if type(submission) is not RuleManualJudgmentSubmission:
        _fail(("manual", index), "submission carrier is invalid")
    requirement = next(item for item in plan.requirements.completion if item.key is key)
    evaluator = requirement.evaluator
    assert evaluator is not None
    reference = VersionedReference(evaluator.id, evaluator.version)
    if (
        submission.key is not key
        or submission.evaluator.id != reference.id
        or submission.evaluator.version != reference.version
    ):
        _fail(("manual", index), "submission correlation differs from the plan")
    if type(submission.input_revision) is not str or (
        submission.input_revision not in evaluator.input_revisions
    ):
        _fail(("manual", index, "input-revision"), "revision is not admitted")
    try:
        frozen = freeze_json(submission.evidence)
    except Exception as exc:
        _fail(("manual", index, "evidence"), "evidence is not finite JSON", exc)
    if type(frozen) is not MappingProxyType:
        _fail(("manual", index, "evidence"), "evidence must be a JSON object")
    evidence = cast(Mapping[str, JsonValue], frozen)
    error = validate_json_instance(
        cast(Mapping[str, object], evaluator.evidence_schema), evidence
    )
    if error is not None:
        _fail(("manual", index, "evidence", *error.absolute_path), error.message)
    try:
        state = EvaluationState(cast(str, evidence.get("conclusion")))
    except (TypeError, ValueError) as exc:
        _fail(("manual", index, "evidence", "conclusion"), "invalid conclusion", exc)
    canonical = RuleManualJudgmentSubmission(
        RuleCriterionKey(key.declaration, key.criterion),
        VersionedReference(reference.id, reference.version),
        submission.input_revision,
        evidence,
    )
    return state, canonical


def _execute_assisted(
    control: _SessionControl, requirement: CompletionRequirement
) -> RuleAssistedEvidence:
    assert control.inputs is not None
    key = cast(RuleCriterionKey, requirement.key)
    entry = _assisted_entry(control.plan, key)
    registry = control.plan.detector_registry
    if registry is None:
        _fail(("assisted",), "detector registry is absent")
    try:
        execution = execute_detector(
            registry,
            entry.invocation.evaluator,
            input_revision=entry.invocation.input_revision,
            input_data=entry.invocation.input_data,
        )
    except DetectorExecutionError as exc:
        _require_session_authority(control)
        if exc.document_path and exc.document_path[0] in {"runner", "result"}:
            return RuleAssistedEvidence(
                requirement, EvaluationState.BLOCKED, None, None, exc.detail
            )
        _fail(("assisted",), exc.detail, exc)
    except BaseException:
        _require_session_authority(control)
        raise
    _require_session_authority(control)
    execution_state = _capture_detector_execution(execution)
    request = object.__new__(RuleResidualJudgmentRequest)
    object.__setattr__(request, "requirement", requirement)
    object.__setattr__(request, "residual_question", entry.residual_question)
    object.__setattr__(request, "execution", execution)
    object.__setattr__(request, "_issuer", _REQUEST_ISSUER)
    request_state = _capture_request_state(request)
    index = next(
        i for i, item in enumerate(control.inputs.residual_keys) if item is key
    )
    provider = control.inputs.providers[index]
    try:
        returned = provider(request)
    except Exception as exc:
        _require_session_authority(control)
        _require_request_authority(request, request_state)
        _require_detector_execution(entry, registry, execution, execution_state)
        _fail(
            ("residual-providers", index),
            f"provider raised {exception_detail(exc)}",
            exc,
        )
    except BaseException:
        _require_session_authority(control)
        _require_request_authority(request, request_state)
        _require_detector_execution(entry, registry, execution, execution_state)
        raise
    _require_session_authority(control)
    _require_request_authority(request, request_state)
    _require_detector_execution(entry, registry, execution, execution_state)
    judgment = _validate_residual(request, returned)
    return RuleAssistedEvidence(requirement, judgment.state, execution, judgment, None)


def _execute_mechanical(
    control: _SessionControl, requirement: CompletionRequirement
) -> RuleMechanicalEvidence:
    key = cast(RuleCriterionKey, requirement.key)
    entry = _mechanical_entry(control.plan, key)
    registry = control.plan.checker_registry
    if registry is None:
        _fail(("mechanical",), "checker registry is absent")
    _require_mechanical_authority(control)
    try:
        result = execute_checker(
            registry,
            entry.invocation.evaluator,
            input_revision=entry.invocation.input_revision,
            input_data=entry.invocation.input_data,
        )
    except CheckerExecutionError as exc:
        _require_mechanical_authority(control)
        if exc.document_path and exc.document_path[0] in {"runner", "result"}:
            return RuleMechanicalEvidence(
                requirement, EvaluationState.BLOCKED, None, exc.detail
            )
        _fail(("mechanical",), exc.detail, exc)
    except BaseException:
        _require_mechanical_authority(control)
        raise
    _require_mechanical_authority(control)
    retained = CheckerResult(
        VersionedReference(result.evaluator.id, result.evaluator.version),
        result.input_revision,
        result.state,
        cast(Mapping[str, JsonValue], freeze_json(result.evidence)),
    )
    return RuleMechanicalEvidence(requirement, retained.state, retained, None)


def _validate_residual(
    request: RuleResidualJudgmentRequest, returned: object
) -> RuleResidualJudgmentSubmission:
    if type(returned) is not RuleResidualJudgmentSubmission:
        _fail(("residual-judgment",), "submission carrier is invalid")
    judgment = cast(RuleResidualJudgmentSubmission, returned)
    if (
        type(judgment.schema_version) is not int
        or judgment.schema_version != 1
        or judgment.request is not request
    ):
        _fail(("residual-judgment",), "submission correlation is invalid")
    if type(judgment.state) is not EvaluationState:
        _fail(("residual-judgment", "state"), "state is invalid")
    if type(judgment.rationale) is not str or not judgment.rationale.strip():
        _fail(("residual-judgment", "rationale"), "rationale must be non-empty")
    if not _is_issued_detector_execution(request.execution):
        _fail(("residual-judgment", "execution"), "execution is not issued")
    return RuleResidualJudgmentSubmission(
        1, request, judgment.state, judgment.rationale
    )


def _capture_request_state(request: RuleResidualJudgmentRequest) -> tuple[object, ...]:
    return (
        request.requirement,
        request.residual_question,
        request.execution,
        request._issuer,
    )


def _require_request_authority(
    request: RuleResidualJudgmentRequest, snapshot: tuple[object, ...]
) -> None:
    current = _capture_request_state(request)
    if any(current[index] is not snapshot[index] for index in (0, 2, 3)) or (
        current[1] != snapshot[1]
    ):
        _fail(("residual-judgment", "request"), "request authority changed")


def _capture_detector_execution(
    execution: DetectorExecution,
) -> tuple[object, ...]:
    return (
        execution.registry,
        execution.evaluator,
        execution.input_revision,
        execution.input_data,
        freeze_json(execution.input_data),
        execution.evidence,
        freeze_json(execution.evidence),
    )


def _require_detector_execution(
    entry: AssistedAttentionEntry,
    registry: object,
    execution: DetectorExecution,
    snapshot: tuple[object, ...],
) -> None:
    if not _is_issued_detector_execution(execution):
        _fail(("assisted", "execution"), "detector execution is not issued")
    current = _capture_detector_execution(execution)
    if any(current[index] is not snapshot[index] for index in (0, 1, 3, 5)):
        _fail(("assisted", "execution"), "detector execution carrier changed")
    if (
        current[2] != snapshot[2]
        or not json_values_equal(current[4], snapshot[4])
        or not json_values_equal(current[6], snapshot[6])
    ):
        _fail(("assisted", "execution"), "detector execution content changed")
    invocation = entry.invocation
    if (
        execution.registry is not registry
        or execution.evaluator is not invocation.evaluator
        or execution.input_revision != invocation.input_revision
        or not json_values_equal(execution.input_data, invocation.input_data)
    ):
        _fail(("assisted", "execution"), "detector execution correlation differs")


def _require_packet_correlations(
    plan: AttentionPlan, requirements: tuple[CompletionRequirement, ...]
) -> None:
    for requirement in requirements:
        key = cast(RuleCriterionKey, requirement.key)
        if requirement.enforcement is EnforcementClass.DELIBERATIVE:
            matches = tuple(
                item for item in plan.deliberative.entries if item.obligation.key is key
            )
            if len(matches) != 1 or matches[0].obligation is not requirement.obligation:
                _fail(("plan", "deliberative"), "packet correlation differs")
        elif requirement.enforcement is EnforcementClass.ASSISTED:
            _assisted_entry(plan, key)
        elif requirement.enforcement is EnforcementClass.MECHANICAL:
            _mechanical_entry(plan, key)
        else:
            _fail(("plan",), "rule criterion has no enforcement class")


def _assisted_entry(
    plan: AttentionPlan, key: RuleCriterionKey
) -> AssistedAttentionEntry:
    matches = tuple(
        item for item in plan.assisted.entries if item.obligation.key is key
    )
    if len(matches) != 1:
        _fail(("plan", "assisted"), "packet correlation differs")
    return matches[0]


def _mechanical_entry(
    plan: AttentionPlan, key: RuleCriterionKey
) -> MechanicalAttentionEntry:
    matches = tuple(item for item in plan.mechanical.entries if item.key is key)
    if len(matches) != 1:
        _fail(("plan", "mechanical"), "packet correlation differs")
    return matches[0]


def _capture_input_state(inputs: _InputSnapshot) -> tuple[object, ...]:
    return (
        id(inputs.manual_keys),
        tuple((id(key), key.declaration, key.criterion) for key in inputs.manual_keys),
        id(inputs.manual),
        tuple(identity_value_state(item) for item in inputs.manual),
        id(inputs.residual_keys),
        tuple(
            (id(key), key.declaration, key.criterion) for key in inputs.residual_keys
        ),
        id(inputs.providers),
        tuple(id(item) for item in inputs.providers),
    )


def _require_session_authority(control: _SessionControl) -> None:
    _require_control_authority(control)
    if control.inputs is None:
        _fail(("inputs",), "captured input authority changed")


def _require_control_authority(control: _SessionControl) -> None:
    _require_plan(control.plan)
    session = None if control.session is None else control.session()
    with _CLAIM_LOCK:
        if (
            session is None
            or _SESSION_CONTROLS.get(session) is not control
            or _PLAN_CLAIMS.get(control.plan) is not control.token
        ):
            _fail(("session",), "session authority differs")
    if getattr(session, "_token", None) is not control.token:
        _fail(("session",), "session authority differs")
    issued = _SESSION_AUTHORITIES.lookup(session)
    if issued is None or issued[1] != _capture_control_state(control):
        _fail(("session",), "session authority differs")


def _capture_control_state(control: _SessionControl) -> tuple[object, ...]:
    return (
        id(control.plan),
        id(control.requirements),
        tuple(identity_value_state(item) for item in control.requirements),
        (
            None
            if control.inputs is None
            else (id(control.inputs), _capture_input_state(control.inputs))
        ),
        id(control.token),
        control.publication[0],
        id(control.publication[1]),
        control.active,
    )


def _require_mechanical_authority(control: _SessionControl) -> None:
    _require_session_authority(control)
    plan = control.plan
    if plan.fixture_index is None or plan.assurance is None:
        _fail(("mechanical",), "checker assurance is absent")
    try:
        _validate_assurance(plan.requirements, plan.fixture_index, plan.assurance)
    except Exception as exc:
        _fail(("mechanical", "assurance"), exception_detail(exc), exc)


def _require_plan(plan: AttentionPlan) -> None:
    if not _is_issued_attention_plan(plan):
        _fail(("plan",), "attention plan is no longer authoritative")


def _issue_evidence(
    plan: AttentionPlan, records: tuple[RuleEvidenceRecord, ...]
) -> RuleEvidence:
    expected = tuple(
        item
        for item in plan.requirements.completion
        if type(item.key) is RuleCriterionKey
    )
    if len(records) != len(expected) or any(
        record.requirement is not requirement
        for record, requirement in zip(records, expected)
    ):
        _fail(("records",), "record sequence is incomplete or out of order")
    if any(not _record_is_canonical(plan, record) for record in records):
        _fail(("records",), "record correlation is not canonical")
    evidence = object.__new__(RuleEvidence)
    object.__setattr__(evidence, "plan", plan)
    object.__setattr__(evidence, "records", records)
    object.__setattr__(evidence, "_issuer", _EVIDENCE_ISSUER)
    state = _capture_evidence_state(evidence)
    token = _EVIDENCE_AUTHORITIES.issue(evidence, state)
    object.__setattr__(evidence, "_token", token)
    object.__setattr__(evidence, "_state", state)
    return evidence


def _is_issued_rule_evidence(evidence: object) -> bool:
    """Return whether rule evidence retains its complete issuance authority."""
    if (
        type(evidence) is not RuleEvidence
        or getattr(evidence, "_issuer", None) is not _EVIDENCE_ISSUER
        or type(getattr(evidence, "_state", None)) is not tuple
    ):
        return False
    try:
        if not _is_issued_attention_plan(evidence.plan):
            return False
        expected = tuple(
            item
            for item in evidence.plan.requirements.completion
            if type(item.key) is RuleCriterionKey
        )
        if len(evidence.records) != len(expected) or any(
            record.requirement is not requirement
            for record, requirement in zip(evidence.records, expected)
        ):
            return False
        if any(
            not _record_is_canonical(evidence.plan, record)
            for record in evidence.records
        ):
            return False
        issued = _EVIDENCE_AUTHORITIES.lookup(evidence)
        return (
            issued is not None
            and evidence._token is issued[0]
            and evidence._state == issued[1]
            and evidence._state == _capture_evidence_state(evidence)
        )
    except Exception:
        return False


def _record_is_canonical(plan: AttentionPlan, record: RuleEvidenceRecord) -> bool:
    if type(record) is RuleManualEvidence:
        evaluator = record.requirement.evaluator
        conclusion = record.submission.evidence.get("conclusion")
        return (
            evaluator is not None
            and type(record.submission) is RuleManualJudgmentSubmission
            and record.submission.key == record.requirement.key
            and record.submission.evaluator
            == VersionedReference(evaluator.id, evaluator.version)
            and type(conclusion) is str
            and record.state is EvaluationState(conclusion)
        )
    if type(record) is RuleAssistedEvidence:
        if record.execution is None:
            return (
                record.state is EvaluationState.BLOCKED
                and record.judgment is None
                and type(record.diagnostic) is str
                and bool(record.diagnostic)
            )
        key = cast(RuleCriterionKey, record.requirement.key)
        entry = _assisted_entry(plan, key)
        invocation = entry.invocation
        return (
            _is_issued_detector_execution(record.execution)
            and type(record.judgment) is RuleResidualJudgmentSubmission
            and record.judgment.request._issuer is _REQUEST_ISSUER
            and record.judgment.request.execution is record.execution
            and record.judgment.request.requirement is record.requirement
            and record.judgment.request.residual_question == entry.residual_question
            and record.execution.registry is plan.detector_registry
            and record.execution.evaluator is invocation.evaluator
            and record.execution.input_revision == invocation.input_revision
            and json_values_equal(record.execution.input_data, invocation.input_data)
            and record.state is record.judgment.state
            and record.diagnostic is None
        )
    if type(record) is RuleMechanicalEvidence:
        if record.result is None:
            return (
                record.state is EvaluationState.BLOCKED
                and type(record.diagnostic) is str
                and bool(record.diagnostic)
            )
        evaluator = record.requirement.evaluator
        key = cast(RuleCriterionKey, record.requirement.key)
        mechanical_entry = _mechanical_entry(plan, key)
        return (
            evaluator is not None
            and record.result.evaluator
            == VersionedReference(evaluator.id, evaluator.version)
            and record.result.evaluator == mechanical_entry.invocation.evaluator
            and record.result.input_revision
            == mechanical_entry.invocation.input_revision
            and record.state is record.result.state
            and record.diagnostic is None
        )
    return False


def _capture_evidence_state(evidence: RuleEvidence) -> tuple[object, ...]:
    return (
        id(evidence.plan),
        id(evidence.records),
        tuple(identity_value_state(record) for record in evidence.records),
        id(evidence._issuer),
    )


def _fail(
    path: tuple[str | int, ...], message: str, cause: BaseException | None = None
) -> NoReturn:
    error = RuleEvidenceError(format_document_path(path), message)
    if cause is None:
        raise error
    raise error from cause
