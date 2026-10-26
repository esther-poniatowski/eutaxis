"""Execute procedure lifecycles behind one exact-once evidence boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum, StrEnum
from _thread import LockType
from threading import Lock
from types import MappingProxyType
from typing import NoReturn, Protocol, SupportsIndex, TypeAlias, cast
from weakref import ReferenceType, WeakKeyDictionary, ref

from ._runner_support import exception_detail, validate_synchronous_runner
from .applicability import ApplicabilityTrace
from .attention import (
    AttentionObligationKey,
    AttentionPlan,
    CompletionRequirement,
    EvaluatorInput,
    OperationPredicateKey,
    ProcedureObligationSnapshot,
    ProcedurePredicateKey,
    _validate_assurance,
)
from .embedded_schema import validate_json_instance
from .enforcement import EnforcementClass, PredicatePhase
from .exceptions import (
    CheckerExecutionError,
    DetectorExecutionError,
    OperationExecutionError,
    ProcedureExecutionError,
)
from .execution import (
    KnownFailureAssurance,
    DetectorExecution,
    _capture_assurance_state,
    _is_issued_detector_execution,
    execute_checker,
    execute_detector,
)
from .fixtures import EvaluatorFixtureIndex
from .models import (
    EvaluatorDeclaration,
    JsonValue,
    VersionedReference,
    freeze_json,
    json_values_equal,
)
from .observations import (
    ObservationProviderRegistry,
    ProcedureBoundaryKind,
    ProcedureLifecycleObservationRequest,
    ProcedurePredicateObservation,
    _evaluate_requirement,
    _is_builder_issued_observation_registry,
    _requested_facets,
    _snapshot_observation,
)
from .operations import (
    OperationFailure,
    OperationResult,
    OperationRunnerBinding,
    OperationRunnerRegistry,
    OperationSuccess,
    execute_operation,
)
from .pre_action_evidence import (
    PreActionEvidence,
    PreActionEvidenceRecord,
    _PreActionEvidenceAuthoritySnapshot,
    _issued_pre_action_evidence_snapshot,
)
from .procedure_runs import PreparedProcedureAction, ProcedureRunPlan
from .procedure_runs import (
    PreparedAssistedLifecycleEvaluation,
    PreparedLifecycleEvaluation,
    PreparedManualLifecycleEvaluation,
    PreparedMechanicalLifecycleEvaluation,
)
from .results import CheckerResult, EvaluationState
from .runners import (
    CheckerRunnerBinding,
    CheckerRunnerRegistry,
    DetectorRunnerBinding,
    DetectorRunnerRegistry,
)
from .source import format_document_path

_SESSION_ISSUER = object()
_TRANSCRIPT_ISSUER = object()
_COORDINATE_ISSUER = object()
_REQUEST_ISSUER = object()
_CLAIM_LOCK = Lock()


class ProcedureExecutionSessionState(StrEnum):
    READY = "ready"
    RUNNING = "running"
    TERMINAL = "terminal"


class ProcedureGraphDisposition(StrEnum):
    SUCCESS_TERMINAL = "success-terminal"
    FAILURE_TERMINAL = "failure-terminal"
    NO_TERMINAL = "no-terminal"


class ProcedureAdjudicationDisposition(StrEnum):
    ACCEPTED = "accepted"
    TERMINAL_EVIDENCE_REJECTED = "terminal-evidence-rejected"
    AUTHORIZATION_ABORTED = "authorization-aborted"
    EVIDENCE_ABORTED = "evidence-aborted"
    EXECUTION_ABORTED = "execution-aborted"
    AUTHORITY_ABORTED = "authority-aborted"


class ProcedureFailureStage(StrEnum):
    OBSERVATION = "observation"
    MANUAL = "manual"
    EVALUATOR_INPUT = "evaluator-input"
    DETECTOR = "detector"
    RESIDUAL = "residual"
    CHECKER = "checker"
    AUTHORIZATION = "authorization"
    OPERATION_RUNNER = "operation-runner"
    OPERATION_RESULT = "operation-result"
    AUTHORITY = "authority"
    INTERRUPTION = "interruption"


class ProcedureRequirementApplicabilityState(StrEnum):
    APPLICABLE = "applicable"
    INAPPLICABLE = "inapplicable"
    UNCHECKED = "unchecked"


@dataclass(frozen=True, init=False)
class ProcedureBoundaryCoordinate:
    kind: ProcedureBoundaryKind
    occurrence: int
    action: str | None
    operation: VersionedReference | None
    terminal: str | None
    predecessor_action: str | None
    predecessor_operation: VersionedReference | None
    operation_result: OperationResult | None
    selected_transition: str | None
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("procedure boundary coordinates must be issued by execution")


@dataclass(frozen=True, init=False)
class ProcedureLifecycleManualJudgmentRequest:
    coordinate: ProcedureBoundaryCoordinate
    requirement: CompletionRequirement
    evaluator: EvaluatorDeclaration

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("manual lifecycle requests must be issued by execution")


@dataclass(frozen=True)
class ProcedureLifecycleManualJudgmentSubmission:
    request: ProcedureLifecycleManualJudgmentRequest
    input_revision: str
    evidence: Mapping[str, object]


class ProcedureLifecycleManualProvider(Protocol):
    def __call__(
        self, request: ProcedureLifecycleManualJudgmentRequest, /
    ) -> ProcedureLifecycleManualJudgmentSubmission: ...


@dataclass(frozen=True, init=False)
class ProcedureLifecycleEvaluatorInputRequest:
    coordinate: ProcedureBoundaryCoordinate
    requirement: CompletionRequirement

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "lifecycle evaluator input requests must be issued by execution"
        )


class ProcedureLifecycleEvaluatorInputProvider(Protocol):
    def __call__(
        self, request: ProcedureLifecycleEvaluatorInputRequest, /
    ) -> EvaluatorInput: ...


@dataclass(frozen=True, init=False)
class ProcedureLifecycleResidualJudgmentRequest:
    coordinate: ProcedureBoundaryCoordinate
    requirement: CompletionRequirement
    residual_question: str
    execution: DetectorExecution

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("residual lifecycle requests must be issued by execution")


@dataclass(frozen=True)
class ProcedureLifecycleResidualJudgmentSubmission:
    schema_version: int
    request: ProcedureLifecycleResidualJudgmentRequest
    state: EvaluationState
    rationale: str


class ProcedureLifecycleResidualProvider(Protocol):
    def __call__(
        self, request: ProcedureLifecycleResidualJudgmentRequest, /
    ) -> ProcedureLifecycleResidualJudgmentSubmission: ...


@dataclass(frozen=True)
class ProcedureManualLifecycleBinding:
    provider: ProcedureLifecycleManualProvider


@dataclass(frozen=True)
class ProcedureAssistedLifecycleBinding:
    input_provider: ProcedureLifecycleEvaluatorInputProvider
    residual_provider: ProcedureLifecycleResidualProvider


@dataclass(frozen=True)
class ProcedureMechanicalLifecycleBinding:
    input_provider: ProcedureLifecycleEvaluatorInputProvider


ProcedureLifecycleBinding: TypeAlias = (
    ProcedureManualLifecycleBinding
    | ProcedureAssistedLifecycleBinding
    | ProcedureMechanicalLifecycleBinding
)


@dataclass(frozen=True)
class ProcedureObservedBoundaryEvidence:
    requirement: CompletionRequirement
    state: EvaluationState
    trace: ApplicabilityTrace


@dataclass(frozen=True)
class ProcedureManualBoundaryEvidence:
    requirement: CompletionRequirement
    state: EvaluationState
    judgment: ProcedureLifecycleManualJudgmentSubmission


@dataclass(frozen=True)
class ProcedureAssistedBoundaryEvidence:
    requirement: CompletionRequirement
    state: EvaluationState
    execution: DetectorExecution | None
    judgment: ProcedureLifecycleResidualJudgmentSubmission | None
    diagnostic: str | None


@dataclass(frozen=True)
class ProcedureMechanicalBoundaryEvidence:
    requirement: CompletionRequirement
    state: EvaluationState
    result: CheckerResult | None
    diagnostic: str | None


ProcedureBoundaryRecord: TypeAlias = (
    ProcedureObservedBoundaryEvidence
    | ProcedureManualBoundaryEvidence
    | ProcedureAssistedBoundaryEvidence
    | ProcedureMechanicalBoundaryEvidence
)


@dataclass(frozen=True)
class ProcedureBoundaryEvidence:
    coordinate: ProcedureBoundaryCoordinate
    records: tuple[ProcedureBoundaryRecord, ...]
    complete: bool


@dataclass(frozen=True)
class ProcedureBoundaryAttempt:
    coordinate: ProcedureBoundaryCoordinate
    requirements: tuple[CompletionRequirement, ...]
    evidence: ProcedureBoundaryEvidence | None


@dataclass(frozen=True)
class ProcedureActionExecution:
    coordinate: ProcedureBoundaryCoordinate
    action: PreparedProcedureAction
    input_data: Mapping[str, JsonValue]
    result: OperationResult | None
    transition: str | None


@dataclass(frozen=True)
class ProcedureExecutionFailure:
    coordinate: ProcedureBoundaryCoordinate
    stage: ProcedureFailureStage
    diagnostic: str | None


@dataclass(frozen=True)
class ProcedureRequirementApplicability:
    requirement: CompletionRequirement
    state: ProcedureRequirementApplicabilityState


@dataclass(frozen=True)
class ProcedureLifecycleProviderAuthoritySnapshot:
    """Retain one validated execution-time provider map without rereading it."""

    mapping_origin: object | None
    keys: tuple[AttentionObligationKey, ...]
    bindings: tuple[ProcedureLifecycleBinding, ...]
    callbacks: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ProcedureExecutionAuthoritySnapshot:
    """Retain factory-time semantics separately from their live origin identities."""

    entry_evidence_origin: PreActionEvidence
    entry_evidence_state: tuple[object, ...]
    entry_evidence_records: tuple[PreActionEvidenceRecord, ...]
    entry_attention_plan_origin: AttentionPlan
    entry_observation_registry_origin: ObservationProviderRegistry
    entry_observation_provider_origin: object
    lifecycle_observation_registry_origin: ObservationProviderRegistry
    lifecycle_observation_provider_origin: object
    operation_registry_origin: OperationRunnerRegistry
    operation_registry: OperationRunnerRegistry
    lifecycle_evaluation_origins: tuple[PreparedLifecycleEvaluation, ...]
    lifecycle_evaluations: tuple[PreparedLifecycleEvaluation, ...]
    detector_registry_origin: DetectorRunnerRegistry | None
    detector_registry: DetectorRunnerRegistry | None
    checker_registry_origin: CheckerRunnerRegistry | None
    checker_registry: CheckerRunnerRegistry | None
    fixture_index_origin: EvaluatorFixtureIndex | None
    assurance_origin: KnownFailureAssurance | None
    lifecycle: tuple[CompletionRequirement, ...]
    actions: tuple[PreparedProcedureAction, ...]
    procedure_id: str
    entry_action: str
    success_terminals: tuple[str, ...]
    failure_terminals: tuple[str, ...]
    parameters: Mapping[str, JsonValue]


@dataclass(frozen=True, init=False, eq=False)
class ProcedureExecutionTranscript:
    authority: ProcedureExecutionAuthoritySnapshot
    provider_authority: ProcedureLifecycleProviderAuthoritySnapshot
    boundaries: tuple[ProcedureBoundaryAttempt, ...]
    actions: tuple[ProcedureActionExecution, ...]
    applicability: tuple[ProcedureRequirementApplicability, ...]
    graph_disposition: ProcedureGraphDisposition
    adjudication_disposition: ProcedureAdjudicationDisposition
    failure: ProcedureExecutionFailure | None
    successful: bool
    _token: object
    _state: tuple[object, ...]
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("procedure execution transcripts must be issued by execution")

    def __copy__(self) -> NoReturn:
        raise TypeError("procedure execution transcripts cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("procedure execution transcripts cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("procedure execution transcripts cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("procedure execution transcripts cannot be serialized")


@dataclass
class _SessionControl:
    token: object
    entry: PreActionEvidence
    registry: ObservationProviderRegistry
    provider: object
    operation_registry: OperationRunnerRegistry
    detector_registry: DetectorRunnerRegistry | None
    checker_registry: CheckerRunnerRegistry | None
    fixture_index: EvaluatorFixtureIndex | None
    assurance: KnownFailureAssurance | None
    authority: ProcedureExecutionAuthoritySnapshot
    lifecycle: tuple[CompletionRequirement, ...]
    lifecycle_evaluations: tuple[PreparedLifecycleEvaluation, ...]
    lifecycle_evaluation_origins: tuple[PreparedLifecycleEvaluation, ...]
    actions: tuple[PreparedProcedureAction, ...]
    procedure_id: str
    entry_action: str
    success_terminals: tuple[str, ...]
    failure_terminals: tuple[str, ...]
    parameters: Mapping[str, JsonValue]
    authority_state: tuple[object, ...]
    publication: tuple[
        ProcedureExecutionSessionState, ProcedureExecutionTranscript | None
    ]
    active: bool
    active_stage: ProcedureFailureStage
    provider_authority: ProcedureLifecycleProviderAuthoritySnapshot | None
    lock: LockType
    session: ReferenceType[ProcedureExecutionSession] | None


_RUN_CLAIMS: WeakKeyDictionary[object, object] = WeakKeyDictionary()
_SESSION_CONTROLS: WeakKeyDictionary[object, _SessionControl] = WeakKeyDictionary()
_TRANSCRIPT_STATES: WeakKeyDictionary[object, tuple[object, tuple[object, ...]]] = (
    WeakKeyDictionary()
)


class ProcedureExecutionSession:
    __slots__ = ("_token", "_issuer", "__weakref__")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("sessions must be issued by create_procedure_execution_session")

    def __copy__(self) -> NoReturn:
        raise TypeError("procedure execution sessions cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("procedure execution sessions cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("procedure execution sessions cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("procedure execution sessions cannot be serialized")

    @property
    def state(self) -> ProcedureExecutionSessionState:
        return _require_session(self).publication[0]

    @property
    def transcript(self) -> ProcedureExecutionTranscript | None:
        return _require_session(self).publication[1]

    def execute(
        self,
        *,
        evidence_bindings: (
            Mapping[AttentionObligationKey, ProcedureLifecycleBinding] | None
        ) = None,
    ) -> ProcedureExecutionTranscript:
        control = _require_session(self)
        claimed = False
        try:
            with control.lock:
                if (
                    control.publication[0] is not ProcedureExecutionSessionState.READY
                    or control.active
                ):
                    _fail(("session", "state"), "session is not ready")
                claimed = True
                control.active = True
            _require_control_authority(control)
            provider_authority = _prepare_provider_authority(control, evidence_bindings)
            _require_control_authority(control)
            _require_provider_authority(provider_authority)
            control.provider_authority = provider_authority
            with control.lock:
                control.publication = (ProcedureExecutionSessionState.RUNNING, None)
        except BaseException as exc:
            if claimed:
                with control.lock:
                    started = (
                        control.publication[0] is ProcedureExecutionSessionState.RUNNING
                    )
                    if not started:
                        control.active = False
                if started:
                    coordinate = _coordinate(
                        ProcedureBoundaryKind.ACTION, 0, control.actions[0], None
                    )
                    _publish(
                        control,
                        [],
                        [],
                        set(),
                        ProcedureGraphDisposition.NO_TERMINAL,
                        ProcedureAdjudicationDisposition.AUTHORITY_ABORTED,
                        ProcedureExecutionFailure(
                            coordinate,
                            ProcedureFailureStage.INTERRUPTION,
                            _safe_detail(exc),
                        ),
                    )
            raise
        boundaries: list[ProcedureBoundaryAttempt] = []
        actions: list[ProcedureActionExecution] = []
        selected: set[int] = set()
        current: ProcedureBoundaryCoordinate | None = None
        graph = ProcedureGraphDisposition.NO_TERMINAL
        try:
            action_by_id = {item.node.id: item for item in control.actions}
            next_id = control.entry_action
            occurrence = 0
            while next_id in action_by_id:
                action = action_by_id[next_id]
                current = _coordinate(
                    ProcedureBoundaryKind.ACTION, occurrence, action, None
                )
                control.active_stage = ProcedureFailureStage.OBSERVATION
                requirements = _action_requirements(control.lifecycle, action)
                selected.update(id(item) for item in requirements)
                boundaries.append(
                    ProcedureBoundaryAttempt(
                        current,
                        requirements,
                        ProcedureBoundaryEvidence(current, (), False),
                    )
                )
                attempt, failure = _evaluate_boundary(
                    control, current, requirements, boundaries
                )
                if failure is not None:
                    return _publish(
                        control,
                        boundaries,
                        actions,
                        selected,
                        graph,
                        _failure_disposition(failure),
                        failure,
                    )
                control.active_stage = ProcedureFailureStage.AUTHORITY
                _require_control_authority(control)
                control.active_stage = ProcedureFailureStage.AUTHORIZATION
                assert attempt.evidence is not None
                if not attempt.evidence.complete or any(
                    item.state is not EvaluationState.SATISFIED
                    for item in attempt.evidence.records
                ):
                    failure = ProcedureExecutionFailure(
                        current,
                        ProcedureFailureStage.AUTHORIZATION,
                        "action boundary is not satisfied",
                    )
                    return _publish(
                        control,
                        boundaries,
                        actions,
                        selected,
                        graph,
                        ProcedureAdjudicationDisposition.AUTHORIZATION_ABORTED,
                        failure,
                    )
                actions.append(
                    ProcedureActionExecution(
                        current,
                        action,
                        cast(Mapping[str, JsonValue], freeze_json(action.input_data)),
                        None,
                        None,
                    )
                )
                control.active_stage = ProcedureFailureStage.OPERATION_RUNNER
                try:
                    result = execute_operation(
                        control.operation_registry,
                        action.operation,
                        input_data=action.input_data,
                    )
                except OperationExecutionError as exc:
                    callback_failure = exc.location.startswith(("$.runner", "$.result"))
                    stage = ProcedureFailureStage.AUTHORITY
                    adjudication = ProcedureAdjudicationDisposition.AUTHORITY_ABORTED
                    if callback_failure:
                        stage = (
                            ProcedureFailureStage.OPERATION_RUNNER
                            if exc.location.startswith("$.runner")
                            else ProcedureFailureStage.OPERATION_RESULT
                        )
                        adjudication = (
                            ProcedureAdjudicationDisposition.EXECUTION_ABORTED
                        )
                    failure = ProcedureExecutionFailure(current, stage, exc.detail)
                    return _publish(
                        control,
                        boundaries,
                        actions,
                        selected,
                        graph,
                        adjudication,
                        failure,
                    )
                detached = _copy_result(result)
                control.active_stage = ProcedureFailureStage.AUTHORITY
                actions[-1] = ProcedureActionExecution(
                    current,
                    action,
                    cast(Mapping[str, JsonValue], freeze_json(action.input_data)),
                    detached,
                    None,
                )
                _require_control_authority(control)
                transition = (
                    action.node.on_success
                    if isinstance(detached, OperationSuccess)
                    else action.node.on_failure[detached.outcome]
                )
                actions[-1] = ProcedureActionExecution(
                    current,
                    action,
                    cast(Mapping[str, JsonValue], freeze_json(action.input_data)),
                    detached,
                    transition,
                )
                next_id = transition
                occurrence += 1

            success_ids = set(control.success_terminals)
            if next_id in success_ids:
                graph = ProcedureGraphDisposition.SUCCESS_TERMINAL
            elif next_id in set(control.failure_terminals):
                graph = ProcedureGraphDisposition.FAILURE_TERMINAL
            else:
                _fail(("transition",), "captured action selected an unknown terminal")
            predecessor = actions[-1].action
            final_action = actions[-1]
            current = _coordinate(
                ProcedureBoundaryKind.TERMINAL,
                occurrence,
                predecessor,
                next_id,
                final_action.result,
                final_action.transition,
            )
            requirements = _terminal_requirements(control.lifecycle, next_id, graph)
            control.active_stage = ProcedureFailureStage.OBSERVATION
            selected.update(id(item) for item in requirements)
            boundaries.append(
                ProcedureBoundaryAttempt(
                    current,
                    requirements,
                    ProcedureBoundaryEvidence(current, (), False),
                )
            )
            attempt, failure = _evaluate_boundary(
                control, current, requirements, boundaries
            )
            if failure is not None:
                return _publish(
                    control,
                    boundaries,
                    actions,
                    selected,
                    graph,
                    _failure_disposition(failure),
                    failure,
                )
            control.active_stage = ProcedureFailureStage.AUTHORITY
            _require_control_authority(control)
            control.active_stage = ProcedureFailureStage.AUTHORIZATION
            assert attempt.evidence is not None
            adjudication = (
                ProcedureAdjudicationDisposition.ACCEPTED
                if all(
                    item.state is EvaluationState.SATISFIED
                    for item in attempt.evidence.records
                )
                and attempt.evidence.complete
                else ProcedureAdjudicationDisposition.TERMINAL_EVIDENCE_REJECTED
            )
            return _publish(
                control, boundaries, actions, selected, graph, adjudication, None
            )
        except ProcedureExecutionError as exc:
            coordinate = current or _coordinate(
                ProcedureBoundaryKind.ACTION, 0, control.actions[0], None
            )
            failure = ProcedureExecutionFailure(
                coordinate, ProcedureFailureStage.AUTHORITY, exc.detail
            )
            return _publish(
                control,
                boundaries,
                actions,
                selected,
                graph,
                ProcedureAdjudicationDisposition.AUTHORITY_ABORTED,
                failure,
            )
        except BaseException as exc:
            if control.publication[0] is ProcedureExecutionSessionState.TERMINAL:
                raise
            coordinate = current or _coordinate(
                ProcedureBoundaryKind.ACTION, 0, control.actions[0], None
            )
            interrupted_stage = control.active_stage
            authority_failure = _guarded_authority_failure(control, coordinate)
            failure = authority_failure or ProcedureExecutionFailure(
                coordinate, interrupted_stage, _safe_detail(exc)
            )
            _publish(
                control,
                boundaries,
                actions,
                selected,
                graph,
                (
                    ProcedureAdjudicationDisposition.EXECUTION_ABORTED
                    if failure.stage
                    in {
                        ProcedureFailureStage.OPERATION_RUNNER,
                        ProcedureFailureStage.OPERATION_RESULT,
                    }
                    else (
                        ProcedureAdjudicationDisposition.AUTHORITY_ABORTED
                        if failure.stage is ProcedureFailureStage.AUTHORITY
                        else ProcedureAdjudicationDisposition.EVIDENCE_ABORTED
                    )
                ),
                failure,
            )
            raise


def create_procedure_execution_session(
    entry_evidence: PreActionEvidence, observation_registry: ObservationProviderRegistry
) -> ProcedureExecutionSession:
    entry_authority = _require_authority(entry_evidence, observation_registry)
    if entry_authority.cleared is not True:
        _fail(("entry-evidence", "cleared"), "procedure entry was not cleared")
    run = entry_authority.plan.run
    lifecycle = _lifecycle_requirements(run)
    lifecycle_origins = run.lifecycle_evaluations
    _validate_lifecycle_timing(lifecycle_origins)
    detached_evaluations = cast(
        tuple[PreparedLifecycleEvaluation, ...],
        tuple(_detach(item) for item in lifecycle_origins),
    )
    detached_by_origin = {
        id(origin.source_requirement): detached
        for origin, detached in zip(lifecycle_origins, detached_evaluations)
    }
    detached_lifecycle = tuple(
        (
            detached_by_origin[id(item)].requirement
            if id(item) in detached_by_origin
            else cast(CompletionRequirement, _detach(item))
        )
        for item in lifecycle
    )
    detached_actions = cast(
        tuple[PreparedProcedureAction, ...],
        tuple(_detach(item) for item in run.actions),
    )
    detached_operation_registry = _detach_operation_registry(
        run.operation_registry,
        bindings=cast(
            Mapping[VersionedReference, OperationRunnerBinding],
            run._operation_registry_state.bindings,
        ),
        contracts=run._operation_registry_state.contracts,
    )
    detached_detector_registry = _detach_detector_registry(run)
    detached_checker_registry = _detach_checker_registry(run)
    parameters = cast(Mapping[str, JsonValue], _detach(run.parameters))
    procedure_id = run.procedure.id
    entry_action = run.procedure.entry
    success_terminals = tuple(item.id for item in run.procedure.postconditions)
    failure_terminals = tuple(run.procedure.failures)
    authority_state = _factory_authority_state(
        entry_evidence, observation_registry, lifecycle, run.actions
    )
    authority = ProcedureExecutionAuthoritySnapshot(
        entry_evidence_origin=entry_evidence,
        entry_evidence_state=_entry_authority_state(entry_authority),
        entry_evidence_records=entry_authority.records,
        entry_attention_plan_origin=run.attention,
        entry_observation_registry_origin=entry_authority.observation.registry,
        entry_observation_provider_origin=entry_authority.observation.registry.provider,
        lifecycle_observation_registry_origin=observation_registry,
        lifecycle_observation_provider_origin=observation_registry.provider,
        operation_registry_origin=run.operation_registry,
        operation_registry=detached_operation_registry,
        lifecycle_evaluation_origins=lifecycle_origins,
        lifecycle_evaluations=detached_evaluations,
        detector_registry_origin=run.attention.detector_registry,
        detector_registry=detached_detector_registry,
        checker_registry_origin=run.attention.checker_registry,
        checker_registry=detached_checker_registry,
        fixture_index_origin=run.attention.fixture_index,
        assurance_origin=run.attention.assurance,
        lifecycle=detached_lifecycle,
        actions=detached_actions,
        procedure_id=procedure_id,
        entry_action=entry_action,
        success_terminals=success_terminals,
        failure_terminals=failure_terminals,
        parameters=parameters,
    )
    _require_authority(entry_evidence, observation_registry)
    if authority_state != _factory_authority_state(
        entry_evidence, observation_registry, lifecycle, run.actions
    ) or not _snapshot_matches_live(authority, run):
        _fail(("run",), "procedure authority changed during session preparation")
    with _CLAIM_LOCK:
        _require_authority(entry_evidence, observation_registry)
        if authority_state != _factory_authority_state(
            entry_evidence,
            observation_registry,
            _lifecycle_requirements(run),
            run.actions,
        ) or not _snapshot_matches_live(authority, run):
            _fail(("run",), "procedure authority changed before claim installation")
        if run in _RUN_CLAIMS:
            _fail(("run",), "procedure run already owns an execution session")
        token = object()
        session = object.__new__(ProcedureExecutionSession)
        object.__setattr__(session, "_token", token)
        object.__setattr__(session, "_issuer", _SESSION_ISSUER)
        control = _SessionControl(
            token=token,
            entry=entry_evidence,
            registry=observation_registry,
            provider=observation_registry.provider,
            operation_registry=detached_operation_registry,
            detector_registry=detached_detector_registry,
            checker_registry=detached_checker_registry,
            fixture_index=run.attention.fixture_index,
            assurance=run.attention.assurance,
            authority=authority,
            lifecycle=detached_lifecycle,
            lifecycle_evaluations=detached_evaluations,
            lifecycle_evaluation_origins=lifecycle_origins,
            actions=detached_actions,
            procedure_id=procedure_id,
            entry_action=entry_action,
            success_terminals=success_terminals,
            failure_terminals=failure_terminals,
            parameters=parameters,
            authority_state=authority_state,
            publication=(ProcedureExecutionSessionState.READY, None),
            active=False,
            active_stage=ProcedureFailureStage.AUTHORITY,
            provider_authority=None,
            lock=Lock(),
            session=None,
        )
        control.session = ref(session)
        _RUN_CLAIMS[run] = token
        _SESSION_CONTROLS[session] = control
    return session


def _require_session(session: object) -> _SessionControl:
    if (
        type(session) is not ProcedureExecutionSession
        or getattr(session, "_issuer", None) is not _SESSION_ISSUER
    ):
        _fail(("session",), "session was not issued")
    with _CLAIM_LOCK:
        control = _SESSION_CONTROLS.get(cast(ProcedureExecutionSession, session))
        if (
            control is None
            or _RUN_CLAIMS.get(control.entry.plan.run) is not control.token
        ):
            _fail(("session",), "session authority differs")
    if (
        control.session is None
        or control.session() is not session
        or getattr(session, "_token", None) is not control.token
    ):
        _fail(("session",), "session authority differs")
    return control


def _require_authority(
    entry: PreActionEvidence,
    registry: ObservationProviderRegistry,
    provider: object | None = None,
) -> _PreActionEvidenceAuthoritySnapshot:
    entry_authority = _issued_pre_action_evidence_snapshot(entry)
    if entry_authority is None:
        _fail(("entry-evidence",), "entry evidence is not authoritative")
    if not _is_builder_issued_observation_registry(registry):
        _fail(("observation-registry",), "registry was not issued")
    declarations = entry_authority.plan.run.attention.resolution.registry
    if (
        registry.declarations is not declarations
        or registry.facets is not declarations.facet_registry
    ):
        _fail(("observation-registry",), "registry authority differs from the run")
    if provider is not None and registry.provider is not provider:
        _fail(("observation-registry", "provider"), "provider authority changed")
    return entry_authority


def _require_control_authority(control: _SessionControl) -> None:
    """Require live execution authorities to match their factory-time snapshot."""
    _require_authority(control.entry, control.registry, control.provider)
    run = control.entry.plan.run
    authority = control.authority
    if (
        control.operation_registry is not authority.operation_registry
        or control.detector_registry is not authority.detector_registry
        or control.checker_registry is not authority.checker_registry
        or control.fixture_index is not authority.fixture_index_origin
        or control.assurance is not authority.assurance_origin
        or control.lifecycle is not authority.lifecycle
        or control.lifecycle_evaluations is not authority.lifecycle_evaluations
        or control.lifecycle_evaluation_origins
        is not authority.lifecycle_evaluation_origins
        or control.actions is not authority.actions
        or control.parameters is not authority.parameters
        or control.authority_state
        != _factory_authority_state(
            control.entry,
            control.registry,
            _lifecycle_requirements(run),
            run.actions,
        )
        or not _snapshot_matches_live(authority, run)
    ):
        _fail(("run",), "procedure authority changed after session issuance")


def _lifecycle_requirements(run: ProcedureRunPlan) -> tuple[CompletionRequirement, ...]:
    return tuple(
        item
        for item in run.requirements
        if isinstance(item.key, OperationPredicateKey)
        or (
            isinstance(item.key, ProcedurePredicateKey)
            and item.key.phase
            in {PredicatePhase.INVARIANT, PredicatePhase.POSTCONDITION}
        )
    )


def _action_requirements(
    lifecycle: tuple[CompletionRequirement, ...], action: PreparedProcedureAction
) -> tuple[CompletionRequirement, ...]:
    return tuple(
        item
        for item in lifecycle
        if (
            isinstance(item.key, ProcedurePredicateKey)
            and item.key.phase is PredicatePhase.INVARIANT
        )
        or (
            isinstance(item.key, OperationPredicateKey)
            and item.key.action == action.node.id
            and item.key.subject_operation == action.operation
        )
    )


def _terminal_requirements(
    lifecycle: tuple[CompletionRequirement, ...],
    terminal: str,
    graph: ProcedureGraphDisposition,
) -> tuple[CompletionRequirement, ...]:
    return tuple(
        item
        for item in lifecycle
        if isinstance(item.key, ProcedurePredicateKey)
        and (
            item.key.phase is PredicatePhase.INVARIANT
            or (
                graph is ProcedureGraphDisposition.SUCCESS_TERMINAL
                and item.key.phase is PredicatePhase.POSTCONDITION
                and item.key.predicate == terminal
            )
        )
    )


def _coordinate(
    kind: ProcedureBoundaryKind,
    occurrence: int,
    action: PreparedProcedureAction,
    terminal: str | None,
    result: OperationResult | None = None,
    transition: str | None = None,
) -> ProcedureBoundaryCoordinate:
    value = object.__new__(ProcedureBoundaryCoordinate)
    object.__setattr__(value, "kind", kind)
    object.__setattr__(value, "occurrence", occurrence)
    object.__setattr__(
        value,
        "action",
        action.node.id if kind is ProcedureBoundaryKind.ACTION else None,
    )
    object.__setattr__(
        value,
        "operation",
        (
            VersionedReference(action.operation.id, action.operation.version)
            if kind is ProcedureBoundaryKind.ACTION
            else None
        ),
    )
    object.__setattr__(value, "terminal", terminal)
    object.__setattr__(
        value,
        "predecessor_action",
        action.node.id if kind is ProcedureBoundaryKind.TERMINAL else None,
    )
    object.__setattr__(
        value,
        "predecessor_operation",
        (
            VersionedReference(action.operation.id, action.operation.version)
            if kind is ProcedureBoundaryKind.TERMINAL
            else None
        ),
    )
    object.__setattr__(
        value, "operation_result", _copy_result(result) if result else None
    )
    object.__setattr__(value, "selected_transition", transition)
    object.__setattr__(value, "_issuer", _COORDINATE_ISSUER)
    return value


def _prepare_provider_authority(
    control: _SessionControl,
    supplied: Mapping[AttentionObligationKey, ProcedureLifecycleBinding] | None,
) -> ProcedureLifecycleProviderAuthoritySnapshot:
    expected = tuple(
        item
        for item in control.lifecycle_evaluation_origins
        if type(item)
        in {
            PreparedManualLifecycleEvaluation,
            PreparedAssistedLifecycleEvaluation,
            PreparedMechanicalLifecycleEvaluation,
        }
    )
    if supplied is None:
        if expected:
            _fail(("evidence-bindings",), "required lifecycle bindings are absent")
        return ProcedureLifecycleProviderAuthoritySnapshot(None, (), (), ())
    if not isinstance(supplied, Mapping):
        _fail(("evidence-bindings",), "value must be a mapping")
    try:
        supplied_items = tuple(supplied.items())
    except Exception as exc:
        _fail(
            ("evidence-bindings",),
            f"mapping could not be read: {exception_detail(exc)}",
        )
    normalized: list[tuple[object, object]] = []
    for index, item in enumerate(supplied_items):
        try:
            supplied_key, supplied_binding = item
        except Exception as exc:
            _fail(
                ("evidence-bindings", index),
                f"item is not a key-value pair: {exception_detail(exc)}",
            )
        normalized.append((supplied_key, supplied_binding))
    pairs = tuple(normalized)
    if len(pairs) != len(expected):
        _fail(("evidence-bindings",), "mapping does not contain the exact keys")
    keys: list[AttentionObligationKey] = []
    bindings: list[ProcedureLifecycleBinding] = []
    callbacks: list[tuple[object, ...]] = []
    for index, specification in enumerate(expected):
        captured: tuple[object, ...]
        pair = next(
            (pair for pair in pairs if pair[0] is specification.source_key), None
        )
        if pair is None or any(pair[0] is key for key in keys):
            _fail(
                ("evidence-bindings", index, "key"),
                "key is not one exact required key",
            )
        key, binding = pair
        if type(specification) is PreparedManualLifecycleEvaluation:
            if type(binding) is not ProcedureManualLifecycleBinding:
                _fail(("evidence-bindings", index), "manual binding kind differs")
            typed_manual = cast(ProcedureManualLifecycleBinding, binding)
            manual_provider = typed_manual.provider
            captured = (manual_provider,)
            _validate_callback(manual_provider, ("evidence-bindings", index))
            _require_control_authority(control)
            if typed_manual.provider is not manual_provider:
                _fail(("evidence-bindings", index), "manual provider changed")
        elif type(specification) is PreparedAssistedLifecycleEvaluation:
            if type(binding) is not ProcedureAssistedLifecycleBinding:
                _fail(("evidence-bindings", index), "assisted binding kind differs")
            typed_assisted = cast(ProcedureAssistedLifecycleBinding, binding)
            input_provider = typed_assisted.input_provider
            residual_provider = typed_assisted.residual_provider
            captured = (input_provider, residual_provider)
            _validate_callback(
                input_provider,
                ("evidence-bindings", index, "input-provider"),
            )
            _require_control_authority(control)
            if (
                typed_assisted.input_provider is not input_provider
                or typed_assisted.residual_provider is not residual_provider
            ):
                _fail(("evidence-bindings", index), "assisted provider changed")
            _validate_callback(
                residual_provider,
                ("evidence-bindings", index, "residual-provider"),
            )
        else:
            if type(binding) is not ProcedureMechanicalLifecycleBinding:
                _fail(("evidence-bindings", index), "mechanical binding kind differs")
            typed_mechanical = cast(ProcedureMechanicalLifecycleBinding, binding)
            input_provider = typed_mechanical.input_provider
            captured = (input_provider,)
            _validate_callback(
                input_provider,
                ("evidence-bindings", index, "input-provider"),
            )
            _require_control_authority(control)
            if typed_mechanical.input_provider is not input_provider:
                _fail(("evidence-bindings", index), "mechanical provider changed")
        _require_control_authority(control)
        if type(binding) is ProcedureManualLifecycleBinding:
            if binding.provider is not captured[0]:
                _fail(("evidence-bindings", index), "manual provider changed")
        elif type(binding) is ProcedureAssistedLifecycleBinding:
            assisted_binding = cast(ProcedureAssistedLifecycleBinding, binding)
            assisted_callbacks = cast(tuple[object, object], captured)
            if (
                assisted_binding.input_provider is not assisted_callbacks[0]
                or assisted_binding.residual_provider is not assisted_callbacks[1]
            ):
                _fail(("evidence-bindings", index), "assisted provider changed")
        else:
            mechanical_binding = cast(ProcedureMechanicalLifecycleBinding, binding)
            if mechanical_binding.input_provider is not captured[0]:
                _fail(("evidence-bindings", index), "mechanical provider changed")
        keys.append(cast(AttentionObligationKey, key))
        bindings.append(cast(ProcedureLifecycleBinding, binding))
        callbacks.append(captured)
    authority = ProcedureLifecycleProviderAuthoritySnapshot(
        supplied, tuple(keys), tuple(bindings), tuple(callbacks)
    )
    _require_provider_authority(authority)
    return authority


def _validate_callback(callback: object, location: tuple[str | int, ...]) -> None:
    validate_synchronous_runner(
        callback,
        lambda message: ProcedureExecutionError(
            format_document_path(location), message
        ),
    )


def _require_provider_authority(
    authority: ProcedureLifecycleProviderAuthoritySnapshot,
) -> None:
    if not (
        type(authority.keys) is tuple
        and type(authority.bindings) is tuple
        and type(authority.callbacks) is tuple
        and len(authority.keys) == len(authority.bindings) == len(authority.callbacks)
    ):
        _fail(("evidence-bindings",), "provider snapshot is invalid")
    for index, (binding, callbacks) in enumerate(
        zip(authority.bindings, authority.callbacks)
    ):
        if type(binding) is ProcedureManualLifecycleBinding:
            if len(callbacks) != 1 or binding.provider is not callbacks[0]:
                _fail(("evidence-bindings", index), "manual provider changed")
        elif type(binding) is ProcedureAssistedLifecycleBinding:
            if (
                len(callbacks) != 2
                or binding.input_provider is not callbacks[0]
                or binding.residual_provider is not callbacks[1]
            ):
                _fail(("evidence-bindings", index), "assisted provider changed")
        elif type(binding) is ProcedureMechanicalLifecycleBinding:
            if len(callbacks) != 1 or binding.input_provider is not callbacks[0]:
                _fail(("evidence-bindings", index), "mechanical provider changed")
        else:
            _fail(("evidence-bindings", index), "binding carrier changed")


def _evaluate_boundary(
    control: _SessionControl,
    coordinate: ProcedureBoundaryCoordinate,
    requirements: tuple[CompletionRequirement, ...],
    boundaries: list[ProcedureBoundaryAttempt],
) -> tuple[ProcedureBoundaryAttempt, ProcedureExecutionFailure | None]:
    observed_requirements = tuple(
        item for item in requirements if item.evaluator is None
    )
    observations: tuple[ProcedurePredicateObservation, ...] = ()
    if observed_requirements:
        control.active_stage = ProcedureFailureStage.OBSERVATION
        observations, failure = _observe_requirements(
            control, coordinate, observed_requirements
        )
        if failure is not None:
            return boundaries[-1], failure
    records: list[ProcedureBoundaryRecord] = []
    for requirement in requirements:
        if requirement.evaluator is None:
            observation = next(
                item for item in observations if item.requirement is requirement
            )
            records.append(
                ProcedureObservedBoundaryEvidence(
                    requirement, _observation_state(observation), observation.trace
                )
            )
            _replace_boundary_prefix(boundaries, coordinate, requirements, records)
            continue
        specification = next(
            (
                item
                for item in control.lifecycle_evaluations
                if item.requirement is requirement
            ),
            None,
        )
        if specification is None:
            return boundaries[-1], ProcedureExecutionFailure(
                coordinate, ProcedureFailureStage.AUTHORITY, "specification is absent"
            )
        if type(specification) is PreparedManualLifecycleEvaluation:
            manual_record, failure = _evaluate_manual(
                control, coordinate, specification
            )
            record: ProcedureBoundaryRecord | None = manual_record
        elif type(specification) is PreparedAssistedLifecycleEvaluation:
            assisted_record, failure = _evaluate_assisted(
                control, coordinate, specification
            )
            record = assisted_record
        else:
            mechanical_record, failure = _evaluate_mechanical(
                control,
                coordinate,
                cast(PreparedMechanicalLifecycleEvaluation, specification),
            )
            record = mechanical_record
        if failure is not None:
            return boundaries[-1], failure
        assert record is not None
        records.append(record)
        _replace_boundary_prefix(boundaries, coordinate, requirements, records)
    attempt = ProcedureBoundaryAttempt(
        coordinate,
        requirements,
        ProcedureBoundaryEvidence(coordinate, tuple(records), True),
    )
    boundaries[-1] = attempt
    return attempt, None


def _observe_requirements(
    control: _SessionControl,
    coordinate: ProcedureBoundaryCoordinate,
    requirements: tuple[CompletionRequirement, ...],
) -> tuple[tuple[ProcedurePredicateObservation, ...], ProcedureExecutionFailure | None]:
    facets = _requested_facets(requirements)
    request = object.__new__(ProcedureLifecycleObservationRequest)
    for name, value in (
        ("procedure", control.procedure_id),
        ("kind", coordinate.kind),
        ("occurrence", coordinate.occurrence),
        ("action", coordinate.action),
        ("operation", coordinate.operation),
        ("terminal", coordinate.terminal),
        ("facets", facets),
        ("parameters", control.parameters),
    ):
        object.__setattr__(request, name, value)
    try:
        returned = control.provider(request)  # type: ignore[operator]
        context = _snapshot_observation(returned, facets, control.registry.facets)
    except Exception as exc:
        return (), ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.OBSERVATION, _safe_detail(exc)
        )
    try:
        previous_stage = control.active_stage
        control.active_stage = ProcedureFailureStage.AUTHORITY
        _require_control_authority(control)
    except ProcedureExecutionError as exc:
        return (), ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.AUTHORITY, exc.detail
        )
    control.active_stage = previous_stage
    records = tuple(_evaluate_requirement(item, context) for item in requirements)
    return records, None


def _replace_boundary_prefix(
    boundaries: list[ProcedureBoundaryAttempt],
    coordinate: ProcedureBoundaryCoordinate,
    requirements: tuple[CompletionRequirement, ...],
    records: list[ProcedureBoundaryRecord],
) -> None:
    boundaries[-1] = ProcedureBoundaryAttempt(
        coordinate,
        requirements,
        ProcedureBoundaryEvidence(coordinate, tuple(records), False),
    )


def _callbacks_for_specification(
    control: _SessionControl, specification: PreparedLifecycleEvaluation
) -> tuple[object, ...]:
    authority = control.provider_authority
    if authority is None:
        _fail(("evidence-bindings",), "provider authority is absent")
    index = next(
        (
            index
            for index, item in enumerate(control.lifecycle_evaluations)
            if item is specification
        ),
        None,
    )
    if index is None:
        _fail(("requirements",), "lifecycle specification is not retained")
    origin = control.lifecycle_evaluation_origins[index]
    provider_index = next(
        (
            provider_index
            for provider_index, key in enumerate(authority.keys)
            if key is origin.source_key
        ),
        None,
    )
    if provider_index is None:
        _fail(("evidence-bindings",), "provider binding is absent")
    return authority.callbacks[provider_index]


def _evaluate_manual(
    control: _SessionControl,
    coordinate: ProcedureBoundaryCoordinate,
    specification: PreparedManualLifecycleEvaluation,
) -> tuple[ProcedureManualBoundaryEvidence | None, ProcedureExecutionFailure | None]:
    control.active_stage = ProcedureFailureStage.MANUAL
    request = object.__new__(ProcedureLifecycleManualJudgmentRequest)
    for name, value in (
        ("coordinate", coordinate),
        ("requirement", specification.requirement),
        ("evaluator", specification.evaluator),
        ("_issuer", _REQUEST_ISSUER),
    ):
        object.__setattr__(request, name, value)
    provider = cast(
        ProcedureLifecycleManualProvider,
        _callbacks_for_specification(control, specification)[0],
    )
    try:
        returned = provider(request)
    except Exception as exc:
        return None, ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.MANUAL, _safe_detail(exc)
        )
    authority_failure = _post_callback_authority_failure(control, coordinate)
    if authority_failure is not None:
        return None, authority_failure
    try:
        judgment, state = _validate_manual_judgment(specification, request, returned)
    except _EvidenceValidationError as exc:
        authority_failure = _post_callback_authority_failure(control, coordinate)
        if authority_failure is not None:
            return None, authority_failure
        return None, ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.MANUAL, exc.detail
        )
    authority_failure = _post_callback_authority_failure(control, coordinate)
    if authority_failure is not None:
        return None, authority_failure
    return (
        ProcedureManualBoundaryEvidence(specification.requirement, state, judgment),
        None,
    )


def _evaluate_assisted(
    control: _SessionControl,
    coordinate: ProcedureBoundaryCoordinate,
    specification: PreparedAssistedLifecycleEvaluation,
) -> tuple[ProcedureAssistedBoundaryEvidence | None, ProcedureExecutionFailure | None]:
    callbacks = _callbacks_for_specification(control, specification)
    control.active_stage = ProcedureFailureStage.EVALUATOR_INPUT
    input_request = object.__new__(ProcedureLifecycleEvaluatorInputRequest)
    object.__setattr__(input_request, "coordinate", coordinate)
    object.__setattr__(input_request, "requirement", specification.requirement)
    object.__setattr__(input_request, "_issuer", _REQUEST_ISSUER)
    provider = cast(ProcedureLifecycleEvaluatorInputProvider, callbacks[0])
    try:
        returned_input = provider(input_request)
    except Exception as exc:
        freshness_failure = _mechanical_authority_failure(control, coordinate)
        if freshness_failure is not None:
            return None, freshness_failure
        return None, ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.EVALUATOR_INPUT, _safe_detail(exc)
        )
    except BaseException:
        _mechanical_authority_failure(control, coordinate)
        raise
    authority_failure = _post_callback_authority_failure(control, coordinate)
    if authority_failure is not None:
        return None, authority_failure
    try:
        evaluator_input = _validate_lifecycle_input(specification, returned_input)
    except _EvidenceValidationError as exc:
        authority_failure = _post_callback_authority_failure(control, coordinate)
        if authority_failure is not None:
            return None, authority_failure
        return None, ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.EVALUATOR_INPUT, exc.detail
        )
    except BaseException:
        _mechanical_authority_failure(control, coordinate)
        raise
    authority_failure = _post_callback_authority_failure(control, coordinate)
    if authority_failure is not None:
        return None, authority_failure
    registry = control.detector_registry
    if registry is None:
        return None, ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.AUTHORITY, "detector registry is absent"
        )
    control.active_stage = ProcedureFailureStage.DETECTOR
    try:
        execution = execute_detector(
            registry,
            specification.invocation.evaluator,
            input_revision=evaluator_input.input_revision,
            input_data=evaluator_input.input_data,
        )
    except DetectorExecutionError as exc:
        authority_failure = _post_callback_authority_failure(control, coordinate)
        if authority_failure is not None:
            return None, authority_failure
        if exc.document_path and exc.document_path[0] in {"runner", "result"}:
            return (
                ProcedureAssistedBoundaryEvidence(
                    specification.requirement,
                    EvaluationState.BLOCKED,
                    None,
                    None,
                    exc.detail,
                ),
                None,
            )
        return None, ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.AUTHORITY, exc.detail
        )
    authority_failure = _post_callback_authority_failure(control, coordinate)
    if authority_failure is not None:
        return None, authority_failure
    if not _is_issued_detector_execution(execution):
        return None, ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.AUTHORITY, "detector execution is invalid"
        )
    control.active_stage = ProcedureFailureStage.RESIDUAL
    residual_request = object.__new__(ProcedureLifecycleResidualJudgmentRequest)
    for name, value in (
        ("coordinate", coordinate),
        ("requirement", specification.requirement),
        ("residual_question", specification.residual_question),
        ("execution", execution),
        ("_issuer", _REQUEST_ISSUER),
    ):
        object.__setattr__(residual_request, name, value)
    residual_provider = cast(ProcedureLifecycleResidualProvider, callbacks[1])
    try:
        returned_judgment = residual_provider(residual_request)
    except Exception as exc:
        return None, ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.RESIDUAL, _safe_detail(exc)
        )
    authority_failure = _post_callback_authority_failure(control, coordinate)
    if authority_failure is not None:
        return None, authority_failure
    try:
        judgment = _validate_residual_judgment(residual_request, returned_judgment)
    except _EvidenceValidationError as exc:
        authority_failure = _post_callback_authority_failure(control, coordinate)
        if authority_failure is not None:
            return None, authority_failure
        return None, ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.RESIDUAL, exc.detail
        )
    authority_failure = _post_callback_authority_failure(control, coordinate)
    if authority_failure is not None:
        return None, authority_failure
    return (
        ProcedureAssistedBoundaryEvidence(
            specification.requirement,
            judgment.state,
            execution,
            judgment,
            None,
        ),
        None,
    )


def _evaluate_mechanical(
    control: _SessionControl,
    coordinate: ProcedureBoundaryCoordinate,
    specification: PreparedMechanicalLifecycleEvaluation,
) -> tuple[
    ProcedureMechanicalBoundaryEvidence | None, ProcedureExecutionFailure | None
]:
    freshness_failure = _mechanical_authority_failure(control, coordinate)
    if freshness_failure is not None:
        return None, freshness_failure
    control.active_stage = ProcedureFailureStage.EVALUATOR_INPUT
    input_request = object.__new__(ProcedureLifecycleEvaluatorInputRequest)
    object.__setattr__(input_request, "coordinate", coordinate)
    object.__setattr__(input_request, "requirement", specification.requirement)
    object.__setattr__(input_request, "_issuer", _REQUEST_ISSUER)
    provider = cast(
        ProcedureLifecycleEvaluatorInputProvider,
        _callbacks_for_specification(control, specification)[0],
    )
    try:
        returned_input = provider(input_request)
    except Exception as exc:
        freshness_failure = _mechanical_authority_failure(control, coordinate)
        if freshness_failure is not None:
            return None, freshness_failure
        return None, ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.EVALUATOR_INPUT, _safe_detail(exc)
        )
    except BaseException:
        _mechanical_authority_failure(control, coordinate)
        raise
    freshness_failure = _mechanical_authority_failure(control, coordinate)
    if freshness_failure is not None:
        return None, freshness_failure
    try:
        evaluator_input = _validate_lifecycle_input(specification, returned_input)
    except _EvidenceValidationError as exc:
        freshness_failure = _mechanical_authority_failure(control, coordinate)
        if freshness_failure is not None:
            return None, freshness_failure
        return None, ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.EVALUATOR_INPUT, exc.detail
        )
    freshness_failure = _mechanical_authority_failure(control, coordinate)
    if freshness_failure is not None:
        return None, freshness_failure
    registry = control.checker_registry
    if registry is None:
        return None, ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.AUTHORITY, "checker registry is absent"
        )
    control.active_stage = ProcedureFailureStage.CHECKER
    try:
        result = execute_checker(
            registry,
            specification.invocation.evaluator,
            input_revision=evaluator_input.input_revision,
            input_data=evaluator_input.input_data,
        )
    except CheckerExecutionError as exc:
        freshness_failure = _mechanical_authority_failure(control, coordinate)
        if freshness_failure is not None:
            return None, freshness_failure
        if exc.document_path and exc.document_path[0] in {"runner", "result"}:
            return (
                ProcedureMechanicalBoundaryEvidence(
                    specification.requirement,
                    EvaluationState.BLOCKED,
                    None,
                    exc.detail,
                ),
                None,
            )
        return None, ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.AUTHORITY, exc.detail
        )
    except BaseException:
        _mechanical_authority_failure(control, coordinate)
        raise
    freshness_failure = _mechanical_authority_failure(control, coordinate)
    if freshness_failure is not None:
        return None, freshness_failure
    retained = CheckerResult(
        VersionedReference(result.evaluator.id, result.evaluator.version),
        result.input_revision,
        result.state,
        cast(Mapping[str, JsonValue], freeze_json(result.evidence)),
    )
    return (
        ProcedureMechanicalBoundaryEvidence(
            specification.requirement, retained.state, retained, None
        ),
        None,
    )


def _mechanical_authority_failure(
    control: _SessionControl, coordinate: ProcedureBoundaryCoordinate
) -> ProcedureExecutionFailure | None:
    authority_failure = _post_callback_authority_failure(control, coordinate)
    if authority_failure is not None:
        return authority_failure
    previous_stage = control.active_stage
    control.active_stage = ProcedureFailureStage.AUTHORITY
    if control.fixture_index is None or control.assurance is None:
        return ProcedureExecutionFailure(
            coordinate,
            ProcedureFailureStage.AUTHORITY,
            "mechanical assurance authority is absent",
        )
    try:
        _validate_assurance(
            control.entry.plan.run.attention.requirements,
            control.fixture_index,
            control.assurance,
        )
    except Exception as exc:
        return ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.AUTHORITY, _safe_detail(exc)
        )
    authority_failure = _post_callback_authority_failure(control, coordinate)
    if authority_failure is not None:
        return authority_failure
    control.active_stage = previous_stage
    return None


@dataclass(frozen=True)
class _EvidenceValidationError(Exception):
    detail: str


def _validate_manual_judgment(
    specification: PreparedManualLifecycleEvaluation,
    request: ProcedureLifecycleManualJudgmentRequest,
    returned: object,
) -> tuple[ProcedureLifecycleManualJudgmentSubmission, EvaluationState]:
    if type(returned) is not ProcedureLifecycleManualJudgmentSubmission:
        raise _EvidenceValidationError("manual provider returned an invalid carrier")
    submission = cast(ProcedureLifecycleManualJudgmentSubmission, returned)
    if submission.request is not request:
        raise _EvidenceValidationError("manual judgment request differs")
    if (
        type(submission.input_revision) is not str
        or submission.input_revision not in specification.evaluator.input_revisions
    ):
        raise _EvidenceValidationError("manual judgment revision is not admitted")
    try:
        frozen = freeze_json(submission.evidence)
    except Exception as exc:
        raise _EvidenceValidationError(
            f"manual evidence is not finite JSON: {exception_detail(exc)}"
        ) from exc
    if type(frozen) is not MappingProxyType:
        raise _EvidenceValidationError("manual evidence must be an object")
    evidence = cast(Mapping[str, JsonValue], frozen)
    error = validate_json_instance(
        cast(Mapping[str, object], specification.evaluator.evidence_schema), evidence
    )
    if error is not None:
        raise _EvidenceValidationError(f"manual evidence is invalid: {error.message}")
    try:
        state = EvaluationState(cast(str, evidence.get("conclusion")))
    except (TypeError, ValueError) as exc:
        raise _EvidenceValidationError("manual conclusion is invalid") from exc
    return (
        ProcedureLifecycleManualJudgmentSubmission(
            request, submission.input_revision, evidence
        ),
        state,
    )


def _validate_lifecycle_input(
    specification: (
        PreparedAssistedLifecycleEvaluation | PreparedMechanicalLifecycleEvaluation
    ),
    returned: object,
) -> EvaluatorInput:
    if type(returned) is not EvaluatorInput:
        raise _EvidenceValidationError("input provider returned an invalid carrier")
    value = cast(EvaluatorInput, returned)
    invocation = specification.invocation
    if (
        type(value.input_revision) is not str
        or value.input_revision != invocation.input_revision
    ):
        raise _EvidenceValidationError("evaluator input revision differs")
    try:
        frozen = freeze_json(value.input_data)
    except Exception as exc:
        raise _EvidenceValidationError(
            f"evaluator input is not finite JSON: {exception_detail(exc)}"
        ) from exc
    if type(frozen) is not MappingProxyType:
        raise _EvidenceValidationError("evaluator input must be an object")
    input_data = cast(Mapping[str, JsonValue], frozen)
    error = validate_json_instance(
        cast(Mapping[str, object], specification.input_schema), input_data
    )
    if error is not None:
        raise _EvidenceValidationError(f"evaluator input is invalid: {error.message}")
    if not json_values_equal(input_data, invocation.input_data):
        raise _EvidenceValidationError("evaluator input differs from the plan")
    return EvaluatorInput(value.input_revision, input_data)


def _validate_residual_judgment(
    request: ProcedureLifecycleResidualJudgmentRequest, returned: object
) -> ProcedureLifecycleResidualJudgmentSubmission:
    if type(returned) is not ProcedureLifecycleResidualJudgmentSubmission:
        raise _EvidenceValidationError("residual provider returned an invalid carrier")
    judgment = cast(ProcedureLifecycleResidualJudgmentSubmission, returned)
    if judgment.request is not request:
        raise _EvidenceValidationError("residual judgment request differs")
    if type(judgment.schema_version) is not int or judgment.schema_version != 1:
        raise _EvidenceValidationError("residual schema version must be 1")
    if type(judgment.state) is not EvaluationState:
        raise _EvidenceValidationError("residual state is invalid")
    if type(judgment.rationale) is not str or not judgment.rationale.strip():
        raise _EvidenceValidationError("residual rationale must be non-empty")
    return ProcedureLifecycleResidualJudgmentSubmission(
        1, request, judgment.state, judgment.rationale
    )


def _post_callback_authority_failure(
    control: _SessionControl, coordinate: ProcedureBoundaryCoordinate
) -> ProcedureExecutionFailure | None:
    previous_stage = control.active_stage
    control.active_stage = ProcedureFailureStage.AUTHORITY
    try:
        _require_control_authority(control)
        if control.provider_authority is None:
            _fail(("evidence-bindings",), "provider authority is absent")
        _require_provider_authority(control.provider_authority)
    except ProcedureExecutionError as exc:
        return ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.AUTHORITY, exc.detail
        )
    control.active_stage = previous_stage
    return None


def _guarded_authority_failure(
    control: _SessionControl, coordinate: ProcedureBoundaryCoordinate
) -> ProcedureExecutionFailure | None:
    """Check authority while converting a failing check into a terminal diagnosis."""
    previous_stage = control.active_stage
    control.active_stage = ProcedureFailureStage.AUTHORITY
    try:
        _require_control_authority(control)
        if control.provider_authority is None:
            _fail(("evidence-bindings",), "provider authority is absent")
        _require_provider_authority(control.provider_authority)
    except BaseException as exc:
        return ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.AUTHORITY, _safe_detail(exc)
        )
    control.active_stage = previous_stage
    return None


def _observation_state(record: ProcedurePredicateObservation) -> EvaluationState:
    if record.truth.value == "true":
        return EvaluationState.SATISFIED
    if record.truth.value == "false":
        return EvaluationState.VIOLATED
    return EvaluationState.BLOCKED


def _failure_disposition(
    failure: ProcedureExecutionFailure,
) -> ProcedureAdjudicationDisposition:
    if failure.stage is ProcedureFailureStage.AUTHORITY:
        return ProcedureAdjudicationDisposition.AUTHORITY_ABORTED
    return ProcedureAdjudicationDisposition.EVIDENCE_ABORTED


def _copy_result(result: OperationResult) -> OperationResult:
    reference = VersionedReference(result.operation.id, result.operation.version)
    if isinstance(result, OperationFailure):
        return OperationFailure(reference, result.outcome)
    return OperationSuccess(
        reference,
        cast(Mapping[str, JsonValue], freeze_json(result.outputs)),
    )


def _detach_operation_registry(
    registry: OperationRunnerRegistry,
    *,
    bindings: Mapping[VersionedReference, OperationRunnerBinding] | None = None,
    contracts: Mapping[VersionedReference, object] | None = None,
) -> OperationRunnerRegistry:
    """Retain exact runners with detached invocation contracts."""
    snapshot = object.__new__(OperationRunnerRegistry)
    bindings = {
        VersionedReference(reference.id, reference.version): OperationRunnerBinding(
            VersionedReference(reference.id, reference.version), binding.runner
        )
        for reference, binding in (bindings or registry.bindings).items()
    }
    contracts = {
        VersionedReference(reference.id, reference.version): _detach(contract)
        for reference, contract in (contracts or registry.contracts).items()
    }
    object.__setattr__(snapshot, "declarations", registry.declarations)
    object.__setattr__(snapshot, "bindings", MappingProxyType(bindings))
    object.__setattr__(snapshot, "contracts", MappingProxyType(contracts))
    object.__setattr__(snapshot, "_issuer", getattr(registry, "_issuer"))
    return snapshot


def _validate_lifecycle_timing(
    specifications: tuple[PreparedLifecycleEvaluation, ...],
) -> None:
    """Require each evaluator to be available by its earliest realized boundary."""
    for index, item in enumerate(specifications):
        key = item.source_key
        admitted = {"pre-design", "pre-action"}
        if (
            type(key) is ProcedurePredicateKey
            and key.phase is PredicatePhase.POSTCONDITION
        ):
            admitted.add("post-action")
        if item.evaluator.timing not in admitted:
            _fail(
                ("requirements", index, "evaluator", "timing"),
                "evaluator timing is later than its lifecycle boundary",
            )


def _detach_detector_registry(run: ProcedureRunPlan) -> DetectorRunnerRegistry | None:
    """Detach captured detector runners and contracts for lifecycle execution."""
    if not any(
        type(item) is PreparedAssistedLifecycleEvaluation
        for item in run.lifecycle_evaluations
    ):
        return None
    state = run._detector_registry_state
    if state is None or run.attention.detector_registry is not state.registry:
        _fail(("detector-registry",), "detector registry authority is absent")
    bindings: dict[VersionedReference, DetectorRunnerBinding] = {}
    contracts: dict[VersionedReference, Mapping[str, object]] = {}
    records: dict[VersionedReference, object] = {}
    for record in state.records:
        reference = VersionedReference(cast(str, record[1]), cast(int, record[2]))
        operation = VersionedReference(cast(str, record[8]), cast(int, record[9]))
        bindings[reference] = DetectorRunnerBinding(
            reference, operation, cast(object, record[10])  # type: ignore[arg-type]
        )
        contracts[reference] = cast(
            Mapping[str, object], freeze_json(cast(Mapping[str, object], record[11]))
        )
        records[reference] = _detach(record[13])
    snapshot = object.__new__(DetectorRunnerRegistry)
    object.__setattr__(snapshot, "declarations", state.declarations)
    object.__setattr__(snapshot, "bindings", MappingProxyType(bindings))
    object.__setattr__(snapshot, "input_contracts", MappingProxyType(contracts))
    object.__setattr__(snapshot, "evaluator_records", MappingProxyType(records))
    object.__setattr__(snapshot, "_issuer", getattr(state.registry, "_issuer"))
    return snapshot


def _detach_checker_registry(run: ProcedureRunPlan) -> CheckerRunnerRegistry | None:
    """Detach captured checker runners and contracts for lifecycle execution."""
    if not any(
        type(item) is PreparedMechanicalLifecycleEvaluation
        for item in run.lifecycle_evaluations
    ):
        return None
    registry = run.attention.checker_registry
    fixtures = run.attention.fixture_index
    assurance = run.attention.assurance
    if registry is None or fixtures is None or assurance is None:
        _fail(("checker-registry",), "mechanical lifecycle authority is absent")
    bindings = {
        VersionedReference(reference.id, reference.version): CheckerRunnerBinding(
            VersionedReference(binding.evaluator.id, binding.evaluator.version),
            VersionedReference(binding.operation.id, binding.operation.version),
            binding.runner,
        )
        for reference, binding in registry.bindings.items()
    }
    contracts = {
        VersionedReference(reference.id, reference.version): cast(
            Mapping[str, object], freeze_json(contract)
        )
        for reference, contract in registry.input_contracts.items()
    }
    records = {
        VersionedReference(reference.id, reference.version): _detach(record)
        for reference, record in registry.evaluator_records.items()
    }
    snapshot = object.__new__(CheckerRunnerRegistry)
    object.__setattr__(snapshot, "declarations", registry.declarations)
    object.__setattr__(snapshot, "bindings", MappingProxyType(bindings))
    object.__setattr__(snapshot, "input_contracts", MappingProxyType(contracts))
    object.__setattr__(snapshot, "evaluator_records", MappingProxyType(records))
    object.__setattr__(snapshot, "_issuer", getattr(registry, "_issuer"))
    return snapshot


def _publish(
    control: _SessionControl,
    boundaries: list[ProcedureBoundaryAttempt],
    actions: list[ProcedureActionExecution],
    selected: set[int],
    graph: ProcedureGraphDisposition,
    adjudication: ProcedureAdjudicationDisposition,
    failure: ProcedureExecutionFailure | None,
) -> ProcedureExecutionTranscript:
    authority_interruption: BaseException | None = None
    if adjudication is not ProcedureAdjudicationDisposition.AUTHORITY_ABORTED:
        coordinate = (
            failure.coordinate
            if failure is not None
            else (
                boundaries[-1].coordinate
                if boundaries
                else _coordinate(
                    ProcedureBoundaryKind.ACTION, 0, control.actions[0], None
                )
            )
        )
        previous_stage = control.active_stage
        control.active_stage = ProcedureFailureStage.AUTHORITY
        try:
            _require_control_authority(control)
            if control.provider_authority is None:
                _fail(("evidence-bindings",), "provider authority is absent")
            _require_provider_authority(control.provider_authority)
        except ProcedureExecutionError as exc:
            adjudication = ProcedureAdjudicationDisposition.AUTHORITY_ABORTED
            failure = ProcedureExecutionFailure(
                coordinate, ProcedureFailureStage.AUTHORITY, exc.detail
            )
        except BaseException as exc:
            adjudication = ProcedureAdjudicationDisposition.AUTHORITY_ABORTED
            failure = ProcedureExecutionFailure(
                coordinate, ProcedureFailureStage.AUTHORITY, _safe_detail(exc)
            )
            authority_interruption = exc
        else:
            control.active_stage = previous_stage
    try:
        transcript = _publish_once(
            control, boundaries, actions, selected, graph, adjudication, failure
        )
    except BaseException:
        # Rebuild and complete publication after one interruption, then re-raise.
        _publish_once(
            control, boundaries, actions, selected, graph, adjudication, failure
        )
        raise
    if authority_interruption is not None:
        raise authority_interruption
    return transcript


def _publish_once(
    control: _SessionControl,
    boundaries: list[ProcedureBoundaryAttempt],
    actions: list[ProcedureActionExecution],
    selected: set[int],
    graph: ProcedureGraphDisposition,
    adjudication: ProcedureAdjudicationDisposition,
    failure: ProcedureExecutionFailure | None,
) -> ProcedureExecutionTranscript:
    """Prepare and commit one complete terminal publication."""
    lifecycle = control.lifecycle
    reached_terminal = graph is not ProcedureGraphDisposition.NO_TERMINAL
    applicability = tuple(
        ProcedureRequirementApplicability(
            item,
            (
                ProcedureRequirementApplicabilityState.APPLICABLE
                if id(item) in selected
                else (
                    ProcedureRequirementApplicabilityState.INAPPLICABLE
                    if reached_terminal
                    else ProcedureRequirementApplicabilityState.UNCHECKED
                )
            ),
        )
        for item in lifecycle
    )
    transcript = _prepare_transcript(
        control, boundaries, actions, applicability, graph, adjudication, failure
    )
    _commit_transcript(control, transcript)
    return transcript


def _prepare_transcript(
    control: _SessionControl,
    boundaries: list[ProcedureBoundaryAttempt],
    actions: list[ProcedureActionExecution],
    applicability: tuple[ProcedureRequirementApplicability, ...],
    graph: ProcedureGraphDisposition,
    adjudication: ProcedureAdjudicationDisposition,
    failure: ProcedureExecutionFailure | None,
) -> ProcedureExecutionTranscript:
    """Build one complete transcript before exposing any part of it."""
    if control.provider_authority is None:
        _fail(("evidence-bindings",), "provider authority is absent")
    transcript = object.__new__(ProcedureExecutionTranscript)
    transcript_token = object()
    for name, value in (
        ("authority", control.authority),
        ("provider_authority", control.provider_authority),
        ("boundaries", tuple(boundaries)),
        ("actions", tuple(actions)),
        ("applicability", applicability),
        ("graph_disposition", graph),
        ("adjudication_disposition", adjudication),
        ("failure", failure),
        (
            "successful",
            graph is ProcedureGraphDisposition.SUCCESS_TERMINAL
            and adjudication is ProcedureAdjudicationDisposition.ACCEPTED,
        ),
        ("_token", transcript_token),
        ("_issuer", _TRANSCRIPT_ISSUER),
    ):
        object.__setattr__(transcript, name, value)
    object.__setattr__(transcript, "_state", _capture_transcript_state(transcript))
    return transcript


def _commit_transcript(
    control: _SessionControl, transcript: ProcedureExecutionTranscript
) -> None:
    """Register and publish one prepared transcript with idempotent compensation."""
    registration = (transcript._token, transcript._state)
    try:
        with _CLAIM_LOCK:
            _TRANSCRIPT_STATES[transcript] = registration
        with control.lock:
            control.publication = (ProcedureExecutionSessionState.TERMINAL, transcript)
            control.active = False
    except BaseException:
        with _CLAIM_LOCK:
            _TRANSCRIPT_STATES[transcript] = registration
        with control.lock:
            control.publication = (ProcedureExecutionSessionState.TERMINAL, transcript)
            control.active = False
        raise


def _capture_transcript_state(
    transcript: ProcedureExecutionTranscript,
) -> tuple[object, ...]:
    """Capture every public transcript carrier and scalar without live-run reads."""
    return (
        _authority_transcript_state(transcript.authority),
        _provider_authority_transcript_state(transcript.provider_authority),
        _identity_semantic_state(transcript.boundaries),
        _identity_semantic_state(transcript.actions),
        _identity_semantic_state(transcript.applicability),
        _identity_semantic_state(transcript.failure),
        _semantic_state(transcript.graph_disposition),
        _semantic_state(transcript.adjudication_disposition),
        transcript.successful,
    )


def _provider_authority_transcript_state(
    authority: ProcedureLifecycleProviderAuthoritySnapshot,
) -> tuple[object, ...]:
    """Capture provider authority without traversing the caller's mapping again."""
    binding_state = tuple(
        (
            type(binding),
            id(binding),
            (
                (id(binding.provider),)
                if type(binding) is ProcedureManualLifecycleBinding
                else (
                    (
                        id(
                            cast(
                                ProcedureAssistedLifecycleBinding, binding
                            ).input_provider
                        ),
                        id(
                            cast(
                                ProcedureAssistedLifecycleBinding, binding
                            ).residual_provider
                        ),
                    )
                    if type(binding) is ProcedureAssistedLifecycleBinding
                    else (
                        id(
                            cast(
                                ProcedureMechanicalLifecycleBinding, binding
                            ).input_provider
                        ),
                    )
                )
            ),
        )
        for binding in authority.bindings
    )
    return (
        id(authority),
        id(authority.mapping_origin),
        tuple(id(key) for key in authority.keys),
        binding_state,
        tuple(tuple(id(callback) for callback in item) for item in authority.callbacks),
    )


def _operation_registry_state(registry: OperationRunnerRegistry) -> tuple[object, ...]:
    """Capture operation authority while treating executable runners as identities."""
    return (
        id(registry),
        id(registry._issuer),
        id(registry.declarations),
        id(registry.bindings),
        tuple(
            (
                id(reference),
                reference.id,
                reference.version,
                id(binding),
                id(binding.operation),
                binding.operation.id,
                binding.operation.version,
                id(binding.runner),
            )
            for reference, binding in registry.bindings.items()
        ),
        id(registry.contracts),
        _identity_semantic_state(registry.contracts),
    )


def _detector_registry_state(
    registry: DetectorRunnerRegistry | None,
) -> tuple[object, ...] | None:
    """Capture detector authority without traversing executable runner state."""
    if registry is None:
        return None
    return (
        id(registry),
        id(registry.declarations),
        id(registry.bindings),
        tuple(
            (
                id(reference),
                reference.id,
                reference.version,
                id(binding),
                id(binding.evaluator),
                binding.evaluator.id,
                binding.evaluator.version,
                id(binding.operation),
                binding.operation.id,
                binding.operation.version,
                id(binding.runner),
            )
            for reference, binding in registry.bindings.items()
        ),
        id(registry.input_contracts),
        _identity_semantic_state(registry.input_contracts),
        id(registry.evaluator_records),
        _identity_semantic_state(registry.evaluator_records),
    )


def _checker_registry_state(
    registry: CheckerRunnerRegistry | None,
) -> tuple[object, ...] | None:
    """Capture checker authority without traversing executable runner state."""
    if registry is None:
        return None
    return (
        id(registry),
        id(registry._issuer),
        id(registry.declarations),
        id(registry.bindings),
        tuple(
            (
                id(reference),
                reference.id,
                reference.version,
                id(binding),
                id(binding.evaluator),
                binding.evaluator.id,
                binding.evaluator.version,
                id(binding.operation),
                binding.operation.id,
                binding.operation.version,
                id(binding.runner),
            )
            for reference, binding in registry.bindings.items()
        ),
        id(registry.input_contracts),
        _identity_semantic_state(registry.input_contracts),
        id(registry.evaluator_records),
        _identity_semantic_state(registry.evaluator_records),
    )


def _operation_runner_correlations(
    registry: OperationRunnerRegistry,
) -> tuple[object, ...]:
    return tuple(
        (
            reference.id,
            reference.version,
            binding.operation.id,
            binding.operation.version,
            id(binding.runner),
        )
        for reference, binding in registry.bindings.items()
    )


def _detector_runner_correlations(
    registry: DetectorRunnerRegistry,
) -> tuple[object, ...]:
    return tuple(
        (
            reference.id,
            reference.version,
            binding.evaluator.id,
            binding.evaluator.version,
            binding.operation.id,
            binding.operation.version,
            id(binding.runner),
        )
        for reference, binding in registry.bindings.items()
    )


def _checker_runner_correlations(
    registry: CheckerRunnerRegistry,
) -> tuple[object, ...]:
    return tuple(
        (
            reference.id,
            reference.version,
            binding.evaluator.id,
            binding.evaluator.version,
            binding.operation.id,
            binding.operation.version,
            id(binding.runner),
        )
        for reference, binding in registry.bindings.items()
    )


def _is_issued_procedure_execution_transcript(transcript: object) -> bool:
    """Return whether an issued transcript still matches its publication snapshot."""
    if (
        type(transcript) is not ProcedureExecutionTranscript
        or getattr(transcript, "_issuer", None) is not _TRANSCRIPT_ISSUER
        or type(getattr(transcript, "_state", None)) is not tuple
    ):
        return False
    try:
        with _CLAIM_LOCK:
            issued = _TRANSCRIPT_STATES.get(
                cast(ProcedureExecutionTranscript, transcript)
            )
        if (
            issued is None
            or getattr(transcript, "_token", None) is not issued[0]
            or transcript._state != issued[1]
        ):
            return False
        current = _capture_transcript_state(transcript)
        retained = transcript._state
        if current != retained:
            return False
        expected_success = (
            transcript.graph_disposition is ProcedureGraphDisposition.SUCCESS_TERMINAL
            and transcript.adjudication_disposition
            is ProcedureAdjudicationDisposition.ACCEPTED
        )
        return transcript.successful is expected_success
    except Exception:
        return False


def _safe_detail(exc: BaseException) -> str | None:
    try:
        return (
            exception_detail(exc) if isinstance(exc, Exception) else type(exc).__name__
        )
    except BaseException:
        return type(exc).__name__


def _detach(value: object) -> object:
    """Detach one trusted dataclass graph into immutable value carriers."""
    if (
        isinstance(value, Enum)
        or value is None
        or type(value)
        in {
            str,
            int,
            float,
            bool,
        }
    ):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType(
            {_detach(key): _detach(item) for key, item in value.items()}
        )
    if type(value) in {tuple, list}:
        sequence = cast(tuple[object, ...] | list[object], value)
        return tuple(_detach(item) for item in sequence)
    if is_dataclass(value):
        return type(value)(  # type: ignore[misc]
            **{
                field.name: _detach(getattr(value, field.name))
                for field in fields(value)
            }
        )
    return value


def _semantic_state(value: object) -> object:
    """Return an alias-free semantic snapshot suitable for later comparison."""
    if isinstance(value, Enum):
        return (type(value), value.value)
    if value is None or type(value) in {str, int, float, bool}:
        return value
    if isinstance(value, Mapping):
        return tuple(
            (_semantic_state(key), _semantic_state(item)) for key, item in value.items()
        )
    if type(value) is tuple:
        return tuple(_semantic_state(item) for item in value)
    if is_dataclass(value):
        return (
            type(value),
            tuple(
                (field.name, _semantic_state(getattr(value, field.name)))
                for field in fields(value)
            ),
        )
    return ("identity", type(value), id(value))


def _identity_semantic_state(value: object) -> object:
    """Capture nested carrier identity and detached semantics for a transcript."""
    if isinstance(value, Enum):
        return (type(value), value.value)
    if isinstance(value, type):
        return ("type", value)
    if value is None or type(value) in {str, int, float, bool}:
        return value
    if isinstance(value, Mapping):
        return (
            "mapping",
            type(value),
            id(value),
            tuple(
                (
                    _identity_semantic_state(key),
                    _identity_semantic_state(item),
                )
                for key, item in value.items()
            ),
        )
    if type(value) is tuple:
        return (
            "tuple",
            id(value),
            tuple(_identity_semantic_state(item) for item in value),
        )
    if type(value) is DetectorExecution:
        execution = cast(DetectorExecution, value)
        return (
            "detector-execution",
            id(execution),
            _detector_registry_state(execution.registry),
            _identity_semantic_state(execution.evaluator),
            execution.input_revision,
            _identity_semantic_state(execution.input_data),
            _identity_semantic_state(execution.evidence),
            id(execution._issuer),
        )
    if is_dataclass(value):
        return (
            "dataclass",
            type(value),
            id(value),
            tuple(
                (field.name, _identity_semantic_state(getattr(value, field.name)))
                for field in fields(value)
            ),
        )
    return ("identity", type(value), id(value))


def _authority_transcript_state(
    authority: ProcedureExecutionAuthoritySnapshot,
) -> tuple[object, ...]:
    """Capture snapshot carriers while treating explicitly named origins as identities."""
    return (
        id(authority),
        id(authority.entry_evidence_origin),
        _identity_semantic_state(authority.entry_evidence_state),
        _identity_semantic_state(authority.entry_evidence_records),
        id(authority.entry_attention_plan_origin),
        id(authority.entry_observation_registry_origin),
        id(authority.entry_observation_provider_origin),
        id(authority.lifecycle_observation_registry_origin),
        id(authority.lifecycle_observation_provider_origin),
        id(authority.operation_registry_origin),
        _operation_registry_state(authority.operation_registry),
        _identity_semantic_state(authority.lifecycle_evaluation_origins),
        _identity_semantic_state(authority.lifecycle_evaluations),
        id(authority.detector_registry_origin),
        _detector_registry_state(authority.detector_registry),
        id(authority.checker_registry_origin),
        _checker_registry_state(authority.checker_registry),
        id(authority.fixture_index_origin),
        id(authority.assurance_origin),
        (
            _capture_assurance_state(authority.assurance_origin)
            if authority.assurance_origin is not None
            else None
        ),
        _identity_semantic_state(authority.lifecycle),
        _identity_semantic_state(authority.actions),
        authority.procedure_id,
        authority.entry_action,
        _identity_semantic_state(authority.success_terminals),
        _identity_semantic_state(authority.failure_terminals),
        _identity_semantic_state(authority.parameters),
    )


def _entry_evidence_state(entry: PreActionEvidence) -> tuple[object, ...]:
    """Detach the factory-time state carried by one exact entry aggregate."""
    return (
        entry.cleared,
        id(entry.records),
        tuple(id(record) for record in entry.records),
        _entry_record_state(entry._record_state),
        _semantic_state(entry.observation.requirements),
        _semantic_state(entry.observation.observations),
        _semantic_state(entry.observation.phase),
        entry.observation.occurrence,
    )


def _entry_authority_state(
    authority: _PreActionEvidenceAuthoritySnapshot,
) -> tuple[object, ...]:
    """Detach entry state only from one issuer-owned aggregate snapshot."""
    record_state = cast(tuple[object, ...], authority.evidence_state[3])
    return (
        authority.cleared,
        id(authority.records),
        tuple(id(record) for record in authority.records),
        _entry_record_state(record_state),
        _semantic_state(authority.observation.requirements),
        _semantic_state(authority.observation.observations),
        _semantic_state(authority.observation.phase),
        authority.observation.occurrence,
    )


def _entry_record_state(snapshot: tuple[object, ...]) -> tuple[object, ...]:
    """Retain issued entry evidence without traversing executable authorities."""
    state: list[object] = []
    for item in snapshot:
        identities, values = cast(tuple[tuple[object, ...], tuple[object, ...]], item)
        state.append(
            (
                tuple(id(value) for value in identities),
                _semantic_state(values),
            )
        )
    return tuple(state)


def _snapshot_matches_live(
    authority: ProcedureExecutionAuthoritySnapshot, run: ProcedureRunPlan
) -> bool:
    """Correlate every detached execution carrier with the final live authority."""
    return (
        _semantic_state(authority.lifecycle)
        == _semantic_state(_lifecycle_requirements(run))
        and _semantic_state(authority.actions) == _semantic_state(run.actions)
        and _semantic_state(authority.parameters) == _semantic_state(run.parameters)
        and _operation_runner_correlations(authority.operation_registry)
        == _operation_runner_correlations(run.operation_registry)
        and authority.operation_registry.declarations
        is run.operation_registry.declarations
        and _semantic_state(authority.operation_registry.contracts)
        == _semantic_state(run.operation_registry.contracts)
        and authority.lifecycle_evaluation_origins is run.lifecycle_evaluations
        and _semantic_state(authority.lifecycle_evaluations)
        == _semantic_state(run.lifecycle_evaluations)
        and authority.detector_registry_origin is run.attention.detector_registry
        and (
            authority.detector_registry is None
            or (
                run.attention.detector_registry is not None
                and _detector_runner_correlations(authority.detector_registry)
                == _detector_runner_correlations(run.attention.detector_registry)
                and _semantic_state(authority.detector_registry.input_contracts)
                == _semantic_state(run.attention.detector_registry.input_contracts)
                and _semantic_state(authority.detector_registry.evaluator_records)
                == _semantic_state(run.attention.detector_registry.evaluator_records)
                and authority.detector_registry.declarations
                is run.attention.detector_registry.declarations
            )
        )
        and authority.checker_registry_origin is run.attention.checker_registry
        and authority.fixture_index_origin is run.attention.fixture_index
        and authority.assurance_origin is run.attention.assurance
        and (
            authority.checker_registry is None
            or (
                run.attention.checker_registry is not None
                and _checker_runner_correlations(authority.checker_registry)
                == _checker_runner_correlations(run.attention.checker_registry)
                and _semantic_state(authority.checker_registry.input_contracts)
                == _semantic_state(run.attention.checker_registry.input_contracts)
                and _semantic_state(authority.checker_registry.evaluator_records)
                == _semantic_state(run.attention.checker_registry.evaluator_records)
                and authority.checker_registry.declarations
                is run.attention.checker_registry.declarations
            )
        )
        and authority.procedure_id == run.procedure.id
        and authority.entry_action == run.procedure.entry
        and authority.success_terminals
        == tuple(item.id for item in run.procedure.postconditions)
        and authority.failure_terminals == tuple(run.procedure.failures)
    )


def _factory_authority_state(
    entry: PreActionEvidence,
    registry: ObservationProviderRegistry,
    lifecycle: tuple[CompletionRequirement, ...],
    actions: tuple[PreparedProcedureAction, ...],
) -> tuple[object, ...]:
    run = entry.plan.run
    return (
        entry,
        _entry_evidence_state(entry),
        entry.observation,
        entry.observation.registry,
        entry.observation.registry.provider,
        _semantic_state(entry.observation.observations),
        registry,
        registry.declarations,
        registry.facets,
        registry.provider,
        run.operation_registry,
        run.operation_registry.declarations,
        _operation_registry_state(run.operation_registry),
        _semantic_state(run.operation_registry.contracts),
        _identity_semantic_state(run.lifecycle_evaluations),
        id(run.attention.detector_registry),
        (
            _detector_registry_state(run.attention.detector_registry)
            if run.attention.detector_registry is not None
            else None
        ),
        (
            _identity_semantic_state(run.attention.detector_registry.input_contracts)
            if run.attention.detector_registry is not None
            else None
        ),
        id(run.attention.checker_registry),
        _checker_registry_state(run.attention.checker_registry),
        id(run.attention.fixture_index),
        id(run.attention.assurance),
        (
            _capture_assurance_state(run.attention.assurance)
            if run.attention.assurance is not None
            else None
        ),
        _semantic_state(lifecycle),
        _semantic_state(actions),
        run.procedure.id,
        run.procedure.entry,
        tuple(item.id for item in run.procedure.postconditions),
        tuple(run.procedure.failures),
        _semantic_state(run.parameters),
    )


def _fail(parts: tuple[str | int, ...], message: str) -> NoReturn:
    raise ProcedureExecutionError(format_document_path(parts), message)
