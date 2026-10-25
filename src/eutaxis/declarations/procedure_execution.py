"""Execute evaluator-less procedure lifecycles behind one exact-once boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum, StrEnum
from _thread import LockType
from threading import Lock
from types import MappingProxyType
from typing import NoReturn, SupportsIndex, cast
from weakref import ReferenceType, WeakKeyDictionary, ref

from ._runner_support import exception_detail
from .attention import (
    CompletionRequirement,
    OperationPredicateKey,
    ProcedureObligationSnapshot,
    ProcedurePredicateKey,
)
from .enforcement import PredicatePhase
from .exceptions import OperationExecutionError, ProcedureExecutionError
from .models import JsonValue, VersionedReference, freeze_json
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
from .pre_action_evidence import PreActionEvidence, _is_issued_pre_action_evidence
from .procedure_runs import PreparedProcedureAction, ProcedureRunPlan
from .results import EvaluationState
from .source import format_document_path

_SESSION_ISSUER = object()
_TRANSCRIPT_ISSUER = object()
_COORDINATE_ISSUER = object()
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


@dataclass(frozen=True)
class ProcedureBoundaryEvidence:
    coordinate: ProcedureBoundaryCoordinate
    records: tuple[ProcedurePredicateObservation, ...]


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
class ProcedureExecutionAuthoritySnapshot:
    """Retain factory-time semantics separately from their live origin identities."""

    entry_evidence_origin: PreActionEvidence
    entry_evidence_state: tuple[object, ...]
    entry_observation_registry_origin: ObservationProviderRegistry
    entry_observation_provider_origin: object
    lifecycle_observation_registry_origin: ObservationProviderRegistry
    lifecycle_observation_provider_origin: object
    operation_registry_origin: OperationRunnerRegistry
    operation_registry: OperationRunnerRegistry
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
    authority: ProcedureExecutionAuthoritySnapshot
    lifecycle: tuple[CompletionRequirement, ...]
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

    def execute(self) -> ProcedureExecutionTranscript:
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
            if any(item.evaluator is not None for item in control.lifecycle):
                _fail(
                    ("requirements",),
                    "evaluator-backed lifecycle requirements are not supported",
                )
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
        active_stage = ProcedureFailureStage.OBSERVATION
        try:
            action_by_id = {item.node.id: item for item in control.actions}
            next_id = control.entry_action
            occurrence = 0
            while next_id in action_by_id:
                action = action_by_id[next_id]
                current = _coordinate(
                    ProcedureBoundaryKind.ACTION, occurrence, action, None
                )
                active_stage = ProcedureFailureStage.OBSERVATION
                requirements = _action_requirements(control.lifecycle, action)
                selected.update(id(item) for item in requirements)
                boundaries.append(ProcedureBoundaryAttempt(current, requirements, None))
                attempt, failure = _observe(control, current, requirements)
                boundaries[-1] = attempt
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
                _require_control_authority(control)
                assert attempt.evidence is not None
                if any(
                    _state(item) is not EvaluationState.SATISFIED
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
                active_stage = ProcedureFailureStage.OPERATION_RUNNER
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
                active_stage = ProcedureFailureStage.AUTHORITY
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
            active_stage = ProcedureFailureStage.OBSERVATION
            selected.update(id(item) for item in requirements)
            boundaries.append(ProcedureBoundaryAttempt(current, requirements, None))
            attempt, failure = _observe(control, current, requirements)
            boundaries[-1] = attempt
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
            _require_control_authority(control)
            assert attempt.evidence is not None
            adjudication = (
                ProcedureAdjudicationDisposition.ACCEPTED
                if all(
                    _state(item) is EvaluationState.SATISFIED
                    for item in attempt.evidence.records
                )
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
            coordinate = current or _coordinate(
                ProcedureBoundaryKind.ACTION, 0, control.actions[0], None
            )
            failure = ProcedureExecutionFailure(
                coordinate, active_stage, _safe_detail(exc)
            )
            _publish(
                control,
                boundaries,
                actions,
                selected,
                graph,
                (
                    ProcedureAdjudicationDisposition.EXECUTION_ABORTED
                    if active_stage
                    in {
                        ProcedureFailureStage.OPERATION_RUNNER,
                        ProcedureFailureStage.OPERATION_RESULT,
                    }
                    else (
                        ProcedureAdjudicationDisposition.AUTHORITY_ABORTED
                        if active_stage is ProcedureFailureStage.AUTHORITY
                        else ProcedureAdjudicationDisposition.EVIDENCE_ABORTED
                    )
                ),
                failure,
            )
            raise


def create_procedure_execution_session(
    entry_evidence: PreActionEvidence, observation_registry: ObservationProviderRegistry
) -> ProcedureExecutionSession:
    _require_authority(entry_evidence, observation_registry)
    if entry_evidence.cleared is not True:
        _fail(("entry-evidence", "cleared"), "procedure entry was not cleared")
    lifecycle = _lifecycle_requirements(entry_evidence.plan.run)
    if any(item.evaluator is not None for item in lifecycle):
        _fail(
            ("requirements",),
            "evaluator-backed lifecycle requirements are not supported",
        )
    run = entry_evidence.plan.run
    detached_lifecycle = cast(
        tuple[CompletionRequirement, ...],
        tuple(_detach(item) for item in lifecycle),
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
        entry_evidence_state=_entry_evidence_state(entry_evidence),
        entry_observation_registry_origin=entry_evidence.observation.registry,
        entry_observation_provider_origin=entry_evidence.observation.registry.provider,
        lifecycle_observation_registry_origin=observation_registry,
        lifecycle_observation_provider_origin=observation_registry.provider,
        operation_registry_origin=run.operation_registry,
        operation_registry=detached_operation_registry,
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
            token,
            entry_evidence,
            observation_registry,
            observation_registry.provider,
            detached_operation_registry,
            authority,
            detached_lifecycle,
            detached_actions,
            procedure_id,
            entry_action,
            success_terminals,
            failure_terminals,
            parameters,
            authority_state,
            (ProcedureExecutionSessionState.READY, None),
            False,
            Lock(),
            None,
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
) -> None:
    if not _is_issued_pre_action_evidence(entry):
        _fail(("entry-evidence",), "entry evidence is not authoritative")
    if not _is_builder_issued_observation_registry(registry):
        _fail(("observation-registry",), "registry was not issued")
    declarations = entry.plan.run.attention.resolution.registry
    if (
        registry.declarations is not declarations
        or registry.facets is not declarations.facet_registry
    ):
        _fail(("observation-registry",), "registry authority differs from the run")
    if provider is not None and registry.provider is not provider:
        _fail(("observation-registry", "provider"), "provider authority changed")


def _require_control_authority(control: _SessionControl) -> None:
    """Require live execution authorities to match their factory-time snapshot."""
    _require_authority(control.entry, control.registry, control.provider)
    run = control.entry.plan.run
    if control.authority_state != _factory_authority_state(
        control.entry,
        control.registry,
        _lifecycle_requirements(run),
        run.actions,
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


def _observe(
    control: _SessionControl,
    coordinate: ProcedureBoundaryCoordinate,
    requirements: tuple[CompletionRequirement, ...],
) -> tuple[ProcedureBoundaryAttempt, ProcedureExecutionFailure | None]:
    if not requirements:
        return (
            ProcedureBoundaryAttempt(
                coordinate, requirements, ProcedureBoundaryEvidence(coordinate, ())
            ),
            None,
        )
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
        failure = ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.OBSERVATION, _safe_detail(exc)
        )
        return ProcedureBoundaryAttempt(coordinate, requirements, None), failure
    try:
        _require_control_authority(control)
    except ProcedureExecutionError as exc:
        failure = ProcedureExecutionFailure(
            coordinate, ProcedureFailureStage.AUTHORITY, exc.detail
        )
        return ProcedureBoundaryAttempt(coordinate, requirements, None), failure
    records = tuple(_evaluate_requirement(item, context) for item in requirements)
    return (
        ProcedureBoundaryAttempt(
            coordinate, requirements, ProcedureBoundaryEvidence(coordinate, records)
        ),
        None,
    )


def _state(record: ProcedurePredicateObservation) -> EvaluationState:
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


def _publish(
    control: _SessionControl,
    boundaries: list[ProcedureBoundaryAttempt],
    actions: list[ProcedureActionExecution],
    selected: set[int],
    graph: ProcedureGraphDisposition,
    adjudication: ProcedureAdjudicationDisposition,
    failure: ProcedureExecutionFailure | None,
) -> ProcedureExecutionTranscript:
    try:
        return _publish_once(
            control, boundaries, actions, selected, graph, adjudication, failure
        )
    except BaseException:
        # Rebuild and complete publication after one interruption, then re-raise.
        _publish_once(
            control, boundaries, actions, selected, graph, adjudication, failure
        )
        raise


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
    transcript = object.__new__(ProcedureExecutionTranscript)
    transcript_token = object()
    for name, value in (
        ("authority", control.authority),
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
        _identity_semantic_state(transcript.boundaries),
        _identity_semantic_state(transcript.actions),
        _identity_semantic_state(transcript.applicability),
        _identity_semantic_state(transcript.failure),
        _semantic_state(transcript.graph_disposition),
        _semantic_state(transcript.adjudication_disposition),
        transcript.successful,
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
        id(authority.entry_observation_registry_origin),
        id(authority.entry_observation_provider_origin),
        id(authority.lifecycle_observation_registry_origin),
        id(authority.lifecycle_observation_provider_origin),
        id(authority.operation_registry_origin),
        _identity_semantic_state(authority.operation_registry),
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
        _semantic_state(entry.records),
        _semantic_state(entry._record_state),
        _semantic_state(entry.observation.requirements),
        _semantic_state(entry.observation.observations),
        _semantic_state(entry.observation.phase),
        entry.observation.occurrence,
    )


def _snapshot_matches_live(
    authority: ProcedureExecutionAuthoritySnapshot, run: ProcedureRunPlan
) -> bool:
    """Correlate every detached execution carrier with the final live authority."""
    return (
        _semantic_state(authority.lifecycle)
        == _semantic_state(_lifecycle_requirements(run))
        and _semantic_state(authority.actions) == _semantic_state(run.actions)
        and _semantic_state(authority.parameters) == _semantic_state(run.parameters)
        and _semantic_state(authority.operation_registry.bindings)
        == _semantic_state(run.operation_registry.bindings)
        and _semantic_state(authority.operation_registry.contracts)
        == _semantic_state(run.operation_registry.contracts)
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
        _semantic_state(run.operation_registry.bindings),
        _semantic_state(run.operation_registry.contracts),
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
