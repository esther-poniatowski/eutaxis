"""Evaluate every procedure precondition in one single-use transaction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from _thread import LockType
from threading import Lock
from types import MappingProxyType
from typing import NoReturn, Protocol, SupportsIndex, cast
from weakref import ReferenceType, WeakKeyDictionary, ref

from ._runner_support import exception_detail, validate_synchronous_runner
from .applicability import ApplicabilityTrace, TruthValue
from .attention import CompletionRequirement, ProcedurePredicateKey
from .embedded_schema import validate_json_instance
from .exceptions import (
    CheckerExecutionError,
    DetectorExecutionError,
    PreActionEvidenceError,
)
from .execution import (
    DetectorExecution,
    _is_issued_detector_execution,
    execute_checker,
    execute_detector,
)
from .models import JsonValue, VersionedReference, freeze_json, json_values_equal
from .observations import (
    ProcedurePreconditionObservation,
    _is_issued_procedure_precondition_observation,
)
from .procedure_evaluations import (
    AssistedPreconditionEvaluation,
    ManualPreconditionEvaluation,
    MechanicalPreconditionEvaluation,
    ProcedurePreconditionEvaluationPlan,
    _is_issued_procedure_precondition_evaluation_plan,
)
from .results import CheckerResult, EvaluationState
from .source import format_document_path

_EVIDENCE_ISSUER = object()
_REQUEST_ISSUER = object()
_SESSION_ISSUER = object()


class PreActionEvidenceSessionState(StrEnum):
    """Lifecycle states of one non-reentrant evidence transaction."""

    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED_AFTER_EXECUTION = "failed-after-execution"


@dataclass(frozen=True)
class ManualJudgmentSubmission:
    """Supply one untrusted manual precondition judgment."""

    key: ProcedurePredicateKey
    evaluator: VersionedReference
    input_revision: str
    evidence: Mapping[str, object]


@dataclass(frozen=True)
class ResidualJudgmentSubmission:
    """Supply the judgment remaining after one detector execution."""

    schema_version: int
    key: ProcedurePredicateKey
    evaluator: VersionedReference
    input_revision: str
    state: EvaluationState
    rationale: str


@dataclass(frozen=True, init=False)
class ResidualJudgmentRequest:
    """Expose one exact detector execution to a residual-judgment provider."""

    requirement: CompletionRequirement
    residual_question: str
    execution: DetectorExecution
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("ResidualJudgmentRequest instances must be issued by execution")


class ResidualJudgmentProvider(Protocol):
    """Judge the residual question after one successful detector execution."""

    def __call__(
        self, request: ResidualJudgmentRequest, /
    ) -> ResidualJudgmentSubmission:
        """Return one correlated residual judgment."""


@dataclass(frozen=True)
class ObservedPreconditionEvidence:
    requirement: CompletionRequirement
    state: EvaluationState
    trace: ApplicabilityTrace


@dataclass(frozen=True)
class ManualPreconditionEvidence:
    requirement: CompletionRequirement
    state: EvaluationState
    evidence: Mapping[str, JsonValue]


@dataclass(frozen=True)
class AssistedPreconditionEvidence:
    requirement: CompletionRequirement
    state: EvaluationState
    execution: DetectorExecution | None
    judgment: ResidualJudgmentSubmission | None
    diagnostic: str | None


@dataclass(frozen=True)
class MechanicalPreconditionEvidence:
    requirement: CompletionRequirement
    state: EvaluationState
    result: CheckerResult | None
    diagnostic: str | None


PreActionEvidenceRecord = (
    ObservedPreconditionEvidence
    | ManualPreconditionEvidence
    | AssistedPreconditionEvidence
    | MechanicalPreconditionEvidence
)


@dataclass(frozen=True, init=False, eq=False)
class PreActionEvidence:
    """Retain the complete canonical evidence for procedure entry."""

    plan: ProcedurePreconditionEvaluationPlan
    observation: ProcedurePreconditionObservation
    records: tuple[PreActionEvidenceRecord, ...]
    cleared: bool
    _record_state: tuple[object, ...]
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("PreActionEvidence instances must be issued by execution")

    def __copy__(self) -> NoReturn:
        raise TypeError("PreActionEvidence instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("PreActionEvidence instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("PreActionEvidence instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("PreActionEvidence instances cannot be serialized")


@dataclass
class _SessionControl:
    token: object
    plan: ProcedurePreconditionEvaluationPlan
    observation: ProcedurePreconditionObservation
    publication: tuple[PreActionEvidenceSessionState, PreActionEvidence | None]
    active: bool
    lock: LockType
    session: ReferenceType[PreActionEvidenceSession] | None


_RUN_CLAIMS: WeakKeyDictionary[object, object] = WeakKeyDictionary()
_SESSION_CONTROLS: WeakKeyDictionary[object, _SessionControl] = WeakKeyDictionary()
_CLAIM_LOCK = Lock()


class PreActionEvidenceSession:
    """Execute one precondition transaction at most once."""

    __slots__ = ("_token", "_issuer", "__weakref__")

    _token: object
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("sessions must be issued by create_pre_action_evidence_session")

    @property
    def plan(self) -> ProcedurePreconditionEvaluationPlan:
        return _require_session(self).plan

    @property
    def observation(self) -> ProcedurePreconditionObservation:
        return _require_session(self).observation

    @property
    def state(self) -> PreActionEvidenceSessionState:
        return _require_session(self).publication[0]

    @property
    def evidence(self) -> PreActionEvidence | None:
        return _require_session(self).publication[1]

    def __copy__(self) -> NoReturn:
        raise TypeError("PreActionEvidenceSession instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("PreActionEvidenceSession instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("PreActionEvidenceSession instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("PreActionEvidenceSession instances cannot be serialized")

    def execute(
        self,
        *,
        manual: Mapping[ProcedurePredicateKey, ManualJudgmentSubmission],
        residual_providers: Mapping[ProcedurePredicateKey, ResidualJudgmentProvider],
    ) -> PreActionEvidence:
        """Evaluate every canonical precondition and derive entry clearance."""
        control = _require_session(self)
        claimed = False
        entered_running = False
        try:
            with control.lock:
                state = control.publication[0]
                if state is not PreActionEvidenceSessionState.READY or control.active:
                    _fail(("session", "state"), f"session is {state.value!r}")
                claimed = True
                control.active = True
            _require_authority(control.plan, control.observation)
            manual_values = _prepare_manual_submissions(control.plan, manual)
            _require_authority(control.plan, control.observation)
            residual_values = _prepare_residual_providers(
                control.plan, residual_providers
            )
            _require_authority(control.plan, control.observation)
            with control.lock:
                control.publication = (PreActionEvidenceSessionState.RUNNING, None)
                entered_running = True
            records = _execute_records(
                control.plan,
                control.observation,
                manual_values,
                residual_values,
            )
            _require_authority(control.plan, control.observation)
            evidence = _issue_evidence(control.plan, control.observation, records)
            with control.lock:
                control.publication = (
                    PreActionEvidenceSessionState.COMPLETED,
                    evidence,
                )
                control.active = False
            return evidence
        except BaseException:
            if claimed:
                with control.lock:
                    if (
                        entered_running
                        or control.publication[0]
                        is PreActionEvidenceSessionState.RUNNING
                    ) and control.publication[
                        0
                    ] is not PreActionEvidenceSessionState.COMPLETED:
                        control.publication = (
                            PreActionEvidenceSessionState.FAILED_AFTER_EXECUTION,
                            None,
                        )
                    control.active = False
            raise


def create_pre_action_evidence_session(
    plan: ProcedurePreconditionEvaluationPlan,
    observation: ProcedurePreconditionObservation,
) -> PreActionEvidenceSession:
    """Create one ready session from exact issued precondition authorities."""
    _require_authority(plan, observation)
    with _CLAIM_LOCK:
        if plan.run in _RUN_CLAIMS:
            _fail(("run",), "procedure run already owns an evidence session")
        token = object()
        control = _SessionControl(
            token,
            plan,
            observation,
            (PreActionEvidenceSessionState.READY, None),
            False,
            Lock(),
            None,
        )
        session = object.__new__(PreActionEvidenceSession)
        object.__setattr__(session, "_token", token)
        object.__setattr__(session, "_issuer", _SESSION_ISSUER)
        control.session = ref(session)
        _RUN_CLAIMS[plan.run] = token
        _SESSION_CONTROLS[session] = control
    return session


def _require_session(session: object) -> _SessionControl:
    if (
        type(session) is not PreActionEvidenceSession
        or getattr(session, "_issuer", None) is not _SESSION_ISSUER
    ):
        _fail(("session",), "session was not issued")
    with _CLAIM_LOCK:
        control = _SESSION_CONTROLS.get(cast(PreActionEvidenceSession, session))
        if type(control) is not _SessionControl:
            _fail(("session",), "session control is invalid")
        typed = cast(_SessionControl, control)
        claim = _RUN_CLAIMS.get(typed.plan.run)
    if (
        typed.session is None
        or typed.session() is not session
        or getattr(session, "_token", None) is not typed.token
        or claim is not typed.token
    ):
        _fail(("session",), "session control authority differs")
    return typed


def _prepare_manual_submissions(
    plan: ProcedurePreconditionEvaluationPlan,
    supplied: Mapping[ProcedurePredicateKey, ManualJudgmentSubmission],
) -> Mapping[ProcedurePredicateKey, tuple[EvaluationState, Mapping[str, JsonValue]]]:
    expected = tuple(
        cast(ProcedurePredicateKey, item.requirement.key) for item in plan.manual
    )
    snapshot = _snapshot_exact_mapping(supplied, expected, ("manual",))
    prepared: dict[
        ProcedurePredicateKey, tuple[EvaluationState, Mapping[str, JsonValue]]
    ] = {}
    for index, record in enumerate(plan.manual):
        key = cast(ProcedurePredicateKey, record.requirement.key)
        submission = snapshot[key]
        if type(submission) is not ManualJudgmentSubmission:
            _fail(("manual", index), "submission carrier is invalid")
        evaluator = record.entry.evaluator
        reference = VersionedReference(evaluator.id, evaluator.version)
        if submission.key is not key or submission.evaluator != reference:
            _fail(("manual", index), "submission correlation differs from the plan")
        if submission.input_revision not in evaluator.input_revisions:
            _fail(("manual", index, "input-revision"), "revision is not admitted")
        try:
            frozen = freeze_json(submission.evidence)
        except Exception as exc:
            _fail(
                ("manual", index, "evidence"),
                f"evidence is not finite JSON: {exception_detail(exc)}",
                cause=exc,
            )
        if type(frozen) is not MappingProxyType:
            _fail(("manual", index, "evidence"), "evidence must be a JSON object")
        evidence = cast(Mapping[str, JsonValue], frozen)
        error = validate_json_instance(
            cast(Mapping[str, object], evaluator.evidence_schema), evidence
        )
        if error is not None:
            _fail(("manual", index, "evidence", *error.absolute_path), error.message)
        conclusion = evidence.get("conclusion")
        try:
            state = EvaluationState(cast(str, conclusion))
        except (TypeError, ValueError) as exc:
            _fail(
                ("manual", index, "evidence", "conclusion"),
                "conclusion is invalid",
                cause=exc,
            )
        prepared[key] = (state, evidence)
    return MappingProxyType(prepared)


def _prepare_residual_providers(
    plan: ProcedurePreconditionEvaluationPlan,
    supplied: Mapping[ProcedurePredicateKey, ResidualJudgmentProvider],
) -> Mapping[ProcedurePredicateKey, ResidualJudgmentProvider]:
    expected = tuple(
        cast(ProcedurePredicateKey, item.requirement.key) for item in plan.assisted
    )
    snapshot = _snapshot_exact_mapping(supplied, expected, ("residual-providers",))
    for index, provider in enumerate(snapshot.values()):

        def invalid_provider(
            message: str, *, item_index: int = index
        ) -> PreActionEvidenceError:
            return PreActionEvidenceError(
                format_document_path(("residual-providers", item_index)), message
            )

        validate_synchronous_runner(
            provider,
            invalid_provider,
        )
    return MappingProxyType(
        cast(dict[ProcedurePredicateKey, ResidualJudgmentProvider], snapshot)
    )


def _snapshot_exact_mapping(
    supplied: Mapping[ProcedurePredicateKey, object],
    expected: tuple[ProcedurePredicateKey, ...],
    location: tuple[str | int, ...],
) -> dict[ProcedurePredicateKey, object]:
    if not isinstance(supplied, Mapping):
        _fail(location, "value must be a mapping")
    try:
        pairs = tuple(supplied.items())
    except Exception as exc:
        _fail(
            location, f"mapping could not be read: {exception_detail(exc)}", cause=exc
        )
    if len(pairs) != len(expected):
        _fail(location, "mapping does not contain the exact required keys")
    result: dict[ProcedurePredicateKey, object] = {}
    for index, pair in enumerate(pairs):
        try:
            key, value = pair
        except Exception as exc:
            _fail(
                location + (index,),
                f"item is not a key-value pair: {exception_detail(exc)}",
                cause=exc,
            )
        canonical = next((item for item in expected if key is item), None)
        if type(key) is not ProcedurePredicateKey or canonical is None or key in result:
            _fail(location + (index, "key"), "key is not one exact required key")
        result[canonical] = value
    if any(not any(actual is key for actual in result) for key in expected):
        _fail(location, "mapping does not contain the exact required keys")
    return result


def _execute_records(
    plan: ProcedurePreconditionEvaluationPlan,
    observation: ProcedurePreconditionObservation,
    manual: Mapping[
        ProcedurePredicateKey, tuple[EvaluationState, Mapping[str, JsonValue]]
    ],
    residual_providers: Mapping[ProcedurePredicateKey, ResidualJudgmentProvider],
) -> tuple[PreActionEvidenceRecord, ...]:
    records: list[PreActionEvidenceRecord] = []
    for requirement in plan.run.pre_action_requirements:
        if requirement.evaluator is None:
            item = next(
                item
                for item in observation.observations
                if item.requirement is requirement
            )
            records.append(
                ObservedPreconditionEvidence(
                    requirement, _truth_state(item.truth), item.trace
                )
            )
            continue
        evaluation = next(
            item for item in plan.records if item.requirement is requirement
        )
        key = cast(ProcedurePredicateKey, requirement.key)
        if type(evaluation) is ManualPreconditionEvaluation:
            state, evidence = manual[key]
            records.append(ManualPreconditionEvidence(requirement, state, evidence))
        elif type(evaluation) is AssistedPreconditionEvaluation:
            records.append(
                _execute_assisted(
                    plan, observation, evaluation, residual_providers[key]
                )
            )
        elif type(evaluation) is MechanicalPreconditionEvaluation:
            records.append(_execute_mechanical(plan, observation, evaluation))
        else:
            _fail(("records", len(records)), "evaluation record is invalid")
    return tuple(records)


def _execute_assisted(
    plan: ProcedurePreconditionEvaluationPlan,
    observation: ProcedurePreconditionObservation,
    record: AssistedPreconditionEvaluation,
    provider: ResidualJudgmentProvider,
) -> AssistedPreconditionEvidence:
    registry = plan.run.attention.detector_registry
    if registry is None:
        _fail(("assisted",), "detector registry is absent")
    invocation = record.entry.invocation
    try:
        execution = execute_detector(
            registry,
            invocation.evaluator,
            input_revision=record.evaluator_input.input_revision,
            input_data=record.evaluator_input.input_data,
        )
    except DetectorExecutionError as exc:
        _require_authority(plan, observation)
        if _is_runner_or_result_error(exc.document_path):
            return AssistedPreconditionEvidence(
                record.requirement, EvaluationState.BLOCKED, None, None, exc.detail
            )
        raise PreActionEvidenceError(exc.location, exc.detail) from exc
    _require_authority(plan, observation)
    execution_state = _capture_detector_execution(execution)
    request = object.__new__(ResidualJudgmentRequest)
    object.__setattr__(request, "requirement", record.requirement)
    object.__setattr__(request, "residual_question", record.entry.residual_question)
    object.__setattr__(request, "execution", execution)
    object.__setattr__(request, "_issuer", _REQUEST_ISSUER)
    try:
        returned = provider(request)
    except Exception as exc:
        _fail(
            ("residual-providers",),
            f"provider raised {exception_detail(exc)}",
            cause=exc,
        )
    _require_authority(plan, observation)
    _require_detector_execution(execution, execution_state)
    judgment = _validate_residual_judgment(record, execution, returned)
    return AssistedPreconditionEvidence(
        record.requirement, judgment.state, execution, judgment, None
    )


def _execute_mechanical(
    plan: ProcedurePreconditionEvaluationPlan,
    observation: ProcedurePreconditionObservation,
    record: MechanicalPreconditionEvaluation,
) -> MechanicalPreconditionEvidence:
    registry = plan.run.attention.checker_registry
    if registry is None:
        _fail(("mechanical",), "checker registry is absent")
    invocation = record.entry.invocation
    try:
        result = execute_checker(
            registry,
            invocation.evaluator,
            input_revision=record.evaluator_input.input_revision,
            input_data=record.evaluator_input.input_data,
        )
    except CheckerExecutionError as exc:
        _require_authority(plan, observation)
        if _is_runner_or_result_error(exc.document_path):
            return MechanicalPreconditionEvidence(
                record.requirement, EvaluationState.BLOCKED, None, exc.detail
            )
        raise PreActionEvidenceError(exc.location, exc.detail) from exc
    _require_authority(plan, observation)
    retained = CheckerResult(
        VersionedReference(result.evaluator.id, result.evaluator.version),
        result.input_revision,
        result.state,
        cast(Mapping[str, JsonValue], freeze_json(result.evidence)),
    )
    return MechanicalPreconditionEvidence(
        record.requirement, retained.state, retained, None
    )


def _validate_residual_judgment(
    record: AssistedPreconditionEvaluation,
    execution: DetectorExecution,
    returned: object,
) -> ResidualJudgmentSubmission:
    if type(returned) is not ResidualJudgmentSubmission:
        _fail(("residual-judgment",), "provider must return ResidualJudgmentSubmission")
    judgment = cast(ResidualJudgmentSubmission, returned)
    invocation = record.entry.invocation
    if judgment.schema_version != 1:
        _fail(("residual-judgment", "schema-version"), "schema version must be 1")
    if (
        judgment.key is not record.requirement.key
        or judgment.evaluator != invocation.evaluator
    ):
        _fail(("residual-judgment",), "judgment correlation differs from the execution")
    if judgment.input_revision != execution.input_revision:
        _fail(
            ("residual-judgment", "input-revision"),
            "revision differs from the execution",
        )
    if type(judgment.state) is not EvaluationState:
        _fail(("residual-judgment", "state"), "state is invalid")
    if type(judgment.rationale) is not str or not judgment.rationale.strip():
        _fail(("residual-judgment", "rationale"), "rationale must be non-empty text")
    if not _is_issued_detector_execution(execution):
        _fail(("residual-judgment", "execution"), "detector execution is not issued")
    if not json_values_equal(execution.input_data, record.evaluator_input.input_data):
        _fail(
            ("residual-judgment", "execution", "input"),
            "execution input differs from the plan",
        )
    return ResidualJudgmentSubmission(
        1,
        cast(ProcedurePredicateKey, record.requirement.key),
        VersionedReference(judgment.evaluator.id, judgment.evaluator.version),
        judgment.input_revision,
        judgment.state,
        judgment.rationale,
    )


def _issue_evidence(
    plan: ProcedurePreconditionEvaluationPlan,
    observation: ProcedurePreconditionObservation,
    records: tuple[PreActionEvidenceRecord, ...],
) -> PreActionEvidence:
    if len(records) != len(plan.run.pre_action_requirements):
        _fail(("records",), "evidence tuple is incomplete")
    evidence = object.__new__(PreActionEvidence)
    object.__setattr__(evidence, "plan", plan)
    object.__setattr__(evidence, "observation", observation)
    object.__setattr__(evidence, "records", records)
    object.__setattr__(
        evidence,
        "cleared",
        all(item.state is EvaluationState.SATISFIED for item in records),
    )
    object.__setattr__(evidence, "_record_state", _capture_record_state(records))
    object.__setattr__(evidence, "_issuer", _EVIDENCE_ISSUER)
    return evidence


def _is_issued_pre_action_evidence(evidence: object) -> bool:
    """Return whether one aggregate retains its complete issued authority."""
    if (
        type(evidence) is not PreActionEvidence
        or getattr(evidence, "_issuer", None) is not _EVIDENCE_ISSUER
    ):
        return False
    try:
        if not _is_issued_procedure_precondition_evaluation_plan(evidence.plan):
            return False
        if not _is_issued_procedure_precondition_observation(evidence.observation):
            return False
        if evidence.observation.run is not evidence.plan.run:
            return False
        expected = evidence.plan.run.pre_action_requirements
        if type(evidence.records) is not tuple or len(evidence.records) != len(
            expected
        ):
            return False
        if any(
            record.requirement is not requirement
            for record, requirement in zip(evidence.records, expected)
        ):
            return False
        if any(
            not _record_matches_canonical(
                evidence.plan, evidence.observation, record, requirement
            )
            for record, requirement in zip(evidence.records, expected)
        ):
            return False
        if type(evidence._record_state) is not tuple or not _record_state_matches(
            evidence.records, evidence._record_state
        ):
            return False
        cleared = all(
            record.state is EvaluationState.SATISFIED for record in evidence.records
        )
        if type(evidence.cleared) is not bool or evidence.cleared is not cleared:
            return False
    except Exception:
        return False
    return True


def _record_matches_canonical(
    plan: ProcedurePreconditionEvaluationPlan,
    observation: ProcedurePreconditionObservation,
    record: PreActionEvidenceRecord,
    requirement: CompletionRequirement,
) -> bool:
    if requirement.evaluator is None:
        observed = next(
            item for item in observation.observations if item.requirement is requirement
        )
        return (
            type(record) is ObservedPreconditionEvidence
            and record.trace is observed.trace
            and record.state is _truth_state(observed.truth)
        )
    evaluation = next(item for item in plan.records if item.requirement is requirement)
    if type(evaluation) is ManualPreconditionEvaluation:
        if type(record) is not ManualPreconditionEvidence:
            return False
        conclusion = record.evidence.get("conclusion")
        return (
            type(record.evidence) is MappingProxyType
            and type(conclusion) is str
            and record.state is EvaluationState(conclusion)
        )
    if type(evaluation) is AssistedPreconditionEvaluation:
        if type(record) is not AssistedPreconditionEvidence:
            return False
        if record.execution is None:
            return (
                record.state is EvaluationState.BLOCKED
                and record.judgment is None
                and type(record.diagnostic) is str
                and bool(record.diagnostic)
            )
        execution = record.execution
        judgment = record.judgment
        invocation = evaluation.entry.invocation
        return (
            record.diagnostic is None
            and judgment is not None
            and _is_issued_detector_execution(execution)
            and execution.registry is plan.run.attention.detector_registry
            and execution.evaluator is invocation.evaluator
            and execution.input_revision == evaluation.evaluator_input.input_revision
            and json_values_equal(
                execution.input_data, evaluation.evaluator_input.input_data
            )
            and judgment.key is requirement.key
            and judgment.evaluator == execution.evaluator
            and judgment.input_revision == execution.input_revision
            and judgment.state is record.state
            and type(judgment.rationale) is str
            and bool(judgment.rationale.strip())
        )
    if type(evaluation) is MechanicalPreconditionEvaluation:
        if type(record) is not MechanicalPreconditionEvidence:
            return False
        if record.result is None:
            return (
                record.state is EvaluationState.BLOCKED
                and type(record.diagnostic) is str
                and bool(record.diagnostic)
            )
        result = record.result
        invocation = evaluation.entry.invocation
        return (
            record.diagnostic is None
            and result.evaluator == invocation.evaluator
            and result.input_revision == evaluation.evaluator_input.input_revision
            and result.state is record.state
            and type(result.evidence) is MappingProxyType
            and validate_json_instance(
                cast(Mapping[str, object], evaluation.entry.evidence_schema),
                result.evidence,
            )
            is None
        )
    return False


def _capture_record_state(
    records: tuple[PreActionEvidenceRecord, ...],
) -> tuple[object, ...]:
    state: list[object] = []
    for record in records:
        identities: list[object] = [record, record.requirement]
        values: list[object] = [record.state.value]
        if type(record) is ObservedPreconditionEvidence:
            identities.append(record.trace)
        elif type(record) is ManualPreconditionEvidence:
            identities.append(record.evidence)
            values.append(freeze_json(record.evidence))
        elif type(record) is AssistedPreconditionEvidence:
            identities.extend((record.execution, record.judgment))
            values.extend((record.diagnostic,))
            if record.execution is not None:
                identities.extend(
                    (
                        record.execution.registry,
                        record.execution.evaluator,
                        record.execution.input_data,
                        record.execution.evidence,
                        getattr(record.execution, "_issuer", None),
                    )
                )
                values.extend(
                    (
                        record.execution.evaluator.id,
                        record.execution.evaluator.version,
                        record.execution.input_revision,
                        freeze_json(record.execution.input_data),
                        freeze_json(record.execution.evidence),
                    )
                )
            if record.judgment is not None:
                identities.extend((record.judgment.key, record.judgment.evaluator))
                values.extend(
                    (
                        record.judgment.schema_version,
                        record.judgment.evaluator.id,
                        record.judgment.evaluator.version,
                        record.judgment.input_revision,
                        record.judgment.state.value,
                        record.judgment.rationale,
                    )
                )
        elif type(record) is MechanicalPreconditionEvidence:
            identities.append(record.result)
            values.append(record.diagnostic)
            if record.result is not None:
                identities.extend((record.result.evaluator, record.result.evidence))
                values.extend(
                    (
                        record.result.input_revision,
                        record.result.evaluator.id,
                        record.result.evaluator.version,
                        record.result.state.value,
                        freeze_json(record.result.evidence),
                    )
                )
        else:
            raise ValueError("invalid evidence record")
        state.append((tuple(identities), tuple(values)))
    return tuple(state)


def _record_state_matches(
    records: tuple[PreActionEvidenceRecord, ...], snapshot: tuple[object, ...]
) -> bool:
    current = _capture_record_state(records)
    if len(current) != len(snapshot):
        return False
    for actual, expected in zip(current, snapshot):
        actual_ids, actual_values = cast(
            tuple[tuple[object, ...], tuple[object, ...]], actual
        )
        expected_ids, expected_values = cast(
            tuple[tuple[object, ...], tuple[object, ...]], expected
        )
        if len(actual_ids) != len(expected_ids) or any(
            left is not right for left, right in zip(actual_ids, expected_ids)
        ):
            return False
        if len(actual_values) != len(expected_values) or any(
            not json_values_equal(left, right)
            for left, right in zip(actual_values, expected_values)
        ):
            return False
    return True


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
    execution: DetectorExecution, snapshot: tuple[object, ...]
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


def _require_authority(
    plan: ProcedurePreconditionEvaluationPlan,
    observation: ProcedurePreconditionObservation,
) -> None:
    _require_plan(plan)
    if not _is_issued_procedure_precondition_observation(observation):
        _fail(("observation",), "observation aggregate was not issued")
    if observation.run is not plan.run:
        _fail(("observation", "run"), "observation belongs to another run")


def _require_plan(plan: ProcedurePreconditionEvaluationPlan) -> None:
    if not _is_issued_procedure_precondition_evaluation_plan(plan):
        _fail(("plan",), "evaluation plan is no longer authoritative")


def _truth_state(value: TruthValue) -> EvaluationState:
    if value is TruthValue.TRUE:
        return EvaluationState.SATISFIED
    if value is TruthValue.FALSE:
        return EvaluationState.VIOLATED
    return EvaluationState.BLOCKED


def _is_runner_or_result_error(path: tuple[str | int, ...] | None) -> bool:
    return bool(path and path[0] in {"runner", "result"})


def _fail(
    parts: tuple[str | int, ...], message: str, *, cause: Exception | None = None
) -> NoReturn:
    error = PreActionEvidenceError(format_document_path(parts), message)
    if cause is not None:
        raise error from cause
    raise error
