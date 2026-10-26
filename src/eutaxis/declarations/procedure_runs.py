"""Prepare immutable procedure inputs without executing actions or predicates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from types import MappingProxyType
from typing import NoReturn, SupportsIndex, TypeAlias, cast

from ._runner_support import exception_detail
from .attention import (
    AssistedAttentionEntry,
    AttentionObligationKey,
    AttentionPlan,
    CompletionRequirement,
    DeliberativeAttentionEntry,
    EvaluatorInvocation,
    MechanicalAttentionEntry,
    OperationObligationSnapshot,
    OperationPredicateKey,
    ProcedureObligationSnapshot,
    ProcedurePredicateKey,
    _is_issued_attention_plan,
)
from .embedded_schema import validate_json_instance
from .enforcement import EnforcementClass, PredicatePhase
from .exceptions import ProcedureRunPlanningError
from .models import (
    EvaluatorDeclaration,
    JsonValue,
    LiteralBinding,
    OperationDeclaration,
    ParameterBinding,
    Predicate,
    ProcedureDeclaration,
    ProcedureNode,
    VersionedReference,
    freeze_json,
    json_values_equal,
)
from .operations import (
    OperationRunnerBinding,
    OperationRunnerRegistry,
    _is_builder_issued_operation_registry,
)
from .runners import (
    DetectorRunnerBinding,
    DetectorRunnerRegistry,
    _is_builder_issued_detector_registry,
)
from .source import format_document_path

_PLAN_ISSUER = object()


@dataclass(frozen=True)
class _RequirementAuthorityState:
    """Retain the exact predicate contract present when preflight issues a run."""

    requirement: CompletionRequirement
    key: ProcedurePredicateKey | OperationPredicateKey
    key_state: tuple[object, ...]
    key_reference: VersionedReference | None
    obligation: ProcedureObligationSnapshot | OperationObligationSnapshot
    obligation_state: tuple[object, ...]
    obligation_maps: tuple[Mapping[str, JsonValue], ...]
    obligation_map_values: tuple[JsonValue, ...]
    obligation_sequences: tuple[tuple[str, ...], ...]
    obligation_sequence_values: tuple[tuple[str, ...], ...]
    obligation_action: ProcedureNode | None
    predicate: Predicate
    predicate_state: tuple[object, ...]
    expression: Mapping[str, JsonValue]
    expression_value: JsonValue
    evaluator_reference: VersionedReference | None
    evaluator_reference_state: tuple[object, ...] | None
    observes: tuple[str, ...]
    observes_value: tuple[str, ...]
    evaluator: EvaluatorDeclaration | None
    evaluator_state: tuple[object, ...] | None
    evaluator_declaration_state: _DeclarationAuthorityState | None
    evidence_schema: Mapping[str, JsonValue] | None
    evidence_schema_value: JsonValue | None
    enforcement: object


@dataclass(frozen=True)
class _ActionAuthorityState:
    """Retain one exact prepared action and its bound input."""

    action: PreparedProcedureAction
    node: ProcedureNode
    node_state: tuple[object, ...]
    bindings: Mapping[str, object]
    binding_state: tuple[tuple[object, ...], ...]
    failure_transitions: Mapping[str, str]
    failure_transition_value: JsonValue
    contract_state: _DeclarationAuthorityState
    operation: VersionedReference
    operation_state: tuple[object, ...]
    contract: OperationDeclaration
    input_data: Mapping[str, JsonValue]
    input_value: JsonValue


@dataclass(frozen=True)
class _PacketAuthorityState:
    """Retain one procedure-owned packet entry and invocation contract."""

    entry: object
    key: ProcedurePredicateKey | OperationPredicateKey
    obligation: ProcedureObligationSnapshot | OperationObligationSnapshot | None
    evaluator: EvaluatorDeclaration | None
    invocation: EvaluatorInvocation | None
    evaluator_reference: VersionedReference | None
    input_operation_reference: VersionedReference | None
    invocation_state: tuple[object, ...] | None
    input_data: Mapping[str, JsonValue] | None
    input_value: JsonValue | None
    evidence_schema: Mapping[str, JsonValue] | None
    evidence_value: JsonValue | None
    input_contract: OperationDeclaration | None
    input_contract_schema: Mapping[str, JsonValue] | None
    input_contract_value: JsonValue | None
    input_contract_state: _DeclarationAuthorityState | None
    entry_state: tuple[object, ...]


@dataclass(frozen=True)
class _DeclarationAuthorityState:
    """Retain complete semantics and carrier identities for one declaration."""

    declaration: ProcedureDeclaration | OperationDeclaration | EvaluatorDeclaration
    semantic_value: JsonValue
    identities: tuple[object, ...]
    scalar_state: tuple[object, ...]


@dataclass(frozen=True)
class _OperationRegistryAuthorityState:
    """Retain the exact executable operation authority of one run."""

    registry: OperationRunnerRegistry
    declarations: object
    bindings: Mapping[VersionedReference, object]
    contracts: Mapping[VersionedReference, OperationDeclaration]
    records: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class _DetectorRegistryAuthorityState:
    """Retain the live detector-registry origin used by one procedure run."""

    registry: DetectorRunnerRegistry
    declarations: object
    bindings: Mapping[VersionedReference, DetectorRunnerBinding]
    input_contracts: Mapping[VersionedReference, Mapping[str, object]]
    evaluator_records: Mapping[VersionedReference, object]
    records: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class PreparedProcedureEvaluationInput:
    """Retain detached canonical inputs for one precondition evaluation."""

    source_key: ProcedurePredicateKey
    procedure: str
    predicate: Predicate
    invocation_input: Mapping[str, JsonValue] | None
    input_schema: Mapping[str, JsonValue] | None


@dataclass(frozen=True)
class PreparedManualLifecycleEvaluation:
    """Retain detached manual authority for one later lifecycle requirement."""

    ordinal: int
    source_key: AttentionObligationKey
    source_requirement: CompletionRequirement
    source_entry: DeliberativeAttentionEntry
    requirement: CompletionRequirement
    evaluator: EvaluatorDeclaration
    enforcement: EnforcementClass


@dataclass(frozen=True)
class PreparedAssistedLifecycleEvaluation:
    """Retain detached detector authority for one later lifecycle requirement."""

    ordinal: int
    source_key: AttentionObligationKey
    source_requirement: CompletionRequirement
    source_entry: AssistedAttentionEntry
    requirement: CompletionRequirement
    evaluator: EvaluatorDeclaration
    enforcement: EnforcementClass
    invocation: EvaluatorInvocation
    input_schema: Mapping[str, JsonValue]
    residual_question: str


@dataclass(frozen=True)
class PreparedMechanicalLifecycleEvaluation:
    """Retain detached checker authority for one later lifecycle requirement."""

    ordinal: int
    source_key: AttentionObligationKey
    source_requirement: CompletionRequirement
    source_entry: MechanicalAttentionEntry
    requirement: CompletionRequirement
    evaluator: EvaluatorDeclaration
    enforcement: EnforcementClass
    invocation: EvaluatorInvocation
    input_schema: Mapping[str, JsonValue]
    evidence_schema: Mapping[str, JsonValue]


PreparedLifecycleEvaluation: TypeAlias = (
    PreparedManualLifecycleEvaluation
    | PreparedAssistedLifecycleEvaluation
    | PreparedMechanicalLifecycleEvaluation
)


@dataclass(frozen=True)
class _LifecycleEvaluationAuthorityState:
    """Bind one detached lifecycle specification to its exact live origins."""

    item: PreparedLifecycleEvaluation
    source_key: AttentionObligationKey
    source_requirement: CompletionRequirement
    source_entry: object
    detached_state: object


@dataclass(frozen=True)
class _EvaluationInputAuthorityState:
    """Retain authority over one detached evaluation-input carrier."""

    item: PreparedProcedureEvaluationInput
    source_key: ProcedurePredicateKey
    procedure: str
    predicate: Predicate
    predicate_state: tuple[object, ...]
    expression: Mapping[str, JsonValue]
    expression_value: JsonValue
    evaluator: VersionedReference | None
    evaluator_state: tuple[object, ...] | None
    observes: tuple[str, ...]
    observes_value: tuple[str, ...]
    invocation_input: Mapping[str, JsonValue] | None
    invocation_value: JsonValue | None
    input_schema: Mapping[str, JsonValue] | None
    schema_value: JsonValue | None


@dataclass(frozen=True)
class PreparedProcedureAction:
    """Retain one authored action with its exact immutable invocation input."""

    node: ProcedureNode
    operation: VersionedReference
    contract: OperationDeclaration
    input_data: Mapping[str, JsonValue]


@dataclass(frozen=True, init=False, eq=False)
class ProcedureRunPlan:
    """Process-local preflight authority for one effective procedure run."""

    attention: AttentionPlan
    operation_registry: OperationRunnerRegistry
    procedure: ProcedureDeclaration
    parameters: Mapping[str, JsonValue]
    requirements: tuple[CompletionRequirement, ...]
    executable_requirements: tuple[CompletionRequirement, ...]
    pre_action_requirements: tuple[CompletionRequirement, ...]
    evaluator_backed_pre_action_requirements: tuple[CompletionRequirement, ...]
    procedure_precondition_requirements: tuple[CompletionRequirement, ...]
    evaluator_backed_procedure_precondition_requirements: tuple[
        CompletionRequirement, ...
    ]
    actions: tuple[PreparedProcedureAction, ...]
    lifecycle_evaluations: tuple[PreparedLifecycleEvaluation, ...]
    _parameters_identity: Mapping[str, JsonValue]
    _parameters_value: JsonValue
    _actions_identity: tuple[PreparedProcedureAction, ...]
    _action_semantics: tuple[_ActionAuthorityState, ...]
    _procedure_semantics: _DeclarationAuthorityState
    _executable_identity: tuple[CompletionRequirement, ...]
    _pre_action_identity: tuple[CompletionRequirement, ...]
    _evaluator_backed_identity: tuple[CompletionRequirement, ...]
    _procedure_precondition_identity: tuple[CompletionRequirement, ...]
    _evaluator_backed_procedure_precondition_identity: tuple[CompletionRequirement, ...]
    _requirements_identity: tuple[CompletionRequirement, ...]
    _requirement_semantics: tuple[_RequirementAuthorityState, ...]
    _packet_semantics: tuple[_PacketAuthorityState, ...]
    _attention_identity: AttentionPlan
    _operation_registry_state: _OperationRegistryAuthorityState
    _detector_registry_state: _DetectorRegistryAuthorityState | None
    _evaluation_inputs: tuple[PreparedProcedureEvaluationInput, ...]
    _evaluation_input_state: tuple[_EvaluationInputAuthorityState, ...]
    _lifecycle_evaluations_identity: tuple[PreparedLifecycleEvaluation, ...]
    _lifecycle_evaluation_state: tuple[_LifecycleEvaluationAuthorityState, ...]
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("ProcedureRunPlan instances must be issued by preflight")

    def __copy__(self) -> NoReturn:
        raise TypeError("ProcedureRunPlan instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("ProcedureRunPlan instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("ProcedureRunPlan instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("ProcedureRunPlan instances cannot be serialized")


def _is_issued_procedure_run_plan(plan: object) -> bool:
    """Return whether ``plan`` carries this process's preflight authority."""
    if (
        type(plan) is not ProcedureRunPlan
        or getattr(plan, "_issuer", None) is not _PLAN_ISSUER
    ):
        return False
    try:
        states = plan._requirement_semantics
        if (
            plan.requirements is not plan._requirements_identity
            or type(states) is not tuple
            or len(states) != len(plan.requirements)
        ):
            return False
        if not all(
            _requirement_authority_is_current(requirement, state)
            for requirement, state in zip(plan.requirements, states)
        ):
            return False
        executable = tuple(item for item in plan.requirements if item.evaluator is None)
        pre_action = tuple(item for item in plan.requirements if _is_pre_action(item))
        evaluator_backed = tuple(
            item for item in pre_action if item.evaluator is not None
        )
        procedure_preconditions = tuple(
            item for item in plan.requirements if _is_procedure_precondition(item)
        )
        evaluator_backed_procedure_preconditions = tuple(
            item for item in procedure_preconditions if item.evaluator is not None
        )
        if (
            plan.attention is not plan._attention_identity
            or plan.operation_registry is not plan._operation_registry_state.registry
            or not _operation_registry_authority_is_current(
                plan._operation_registry_state
            )
            or plan.executable_requirements is not plan._executable_identity
            or not _same_identity_tuple(plan.executable_requirements, executable)
            or plan.pre_action_requirements is not plan._pre_action_identity
            or not _same_identity_tuple(plan.pre_action_requirements, pre_action)
            or plan.evaluator_backed_pre_action_requirements
            is not plan._evaluator_backed_identity
            or not _same_identity_tuple(
                plan.evaluator_backed_pre_action_requirements, evaluator_backed
            )
            or plan.procedure_precondition_requirements
            is not plan._procedure_precondition_identity
            or not _same_identity_tuple(
                plan.procedure_precondition_requirements, procedure_preconditions
            )
            or plan.evaluator_backed_procedure_precondition_requirements
            is not plan._evaluator_backed_procedure_precondition_identity
            or not _same_identity_tuple(
                plan.evaluator_backed_procedure_precondition_requirements,
                evaluator_backed_procedure_preconditions,
            )
            or not _declaration_authority_is_current(plan._procedure_semantics)
            or plan.parameters is not plan._parameters_identity
            or not json_values_equal(
                freeze_json(plan.parameters), plan._parameters_value
            )
            or plan.actions is not plan._actions_identity
            or len(plan.actions) != len(plan._action_semantics)
            or not all(
                _action_authority_is_current(action, state)
                for action, state in zip(plan.actions, plan._action_semantics)
            )
            or not _packet_authority_is_current(plan)
            or not _evaluation_inputs_are_current(plan)
            or plan.lifecycle_evaluations is not plan._lifecycle_evaluations_identity
            or not _lifecycle_evaluations_are_current(plan)
            or not _detector_registry_authority_is_current(
                plan.attention.detector_registry, plan._detector_registry_state
            )
        ):
            return False
        return _final_run_identity_check(plan)
    except Exception:
        return False


def prepare_procedure_run(
    attention: AttentionPlan,
    procedure_id: str,
    parameters: Mapping[str, object],
    operation_registry: OperationRunnerRegistry,
) -> ProcedureRunPlan:
    """Validate and freeze one effective procedure's complete action preflight."""
    try:
        return _prepare_procedure_run(
            attention, procedure_id, parameters, operation_registry
        )
    except ProcedureRunPlanningError:
        raise
    except Exception as exc:
        _fail(
            (),
            f"procedure preflight inputs cannot be read: {exception_detail(exc)}",
            cause=exc,
        )


def _prepare_procedure_run(
    attention: AttentionPlan,
    procedure_id: str,
    parameters: Mapping[str, object],
    operation_registry: OperationRunnerRegistry,
) -> ProcedureRunPlan:
    """Materialize one run behind the public preflight exception boundary."""
    if not _is_issued_attention_plan(attention):
        _fail(("attention",), "attention plan was not issued by planning")
    if not _is_builder_issued_operation_registry(operation_registry):
        _fail(
            ("operation-registry",), "operation registry was not issued by its builder"
        )
    registry = attention.resolution.registry
    if operation_registry.declarations is not registry:
        _fail(
            ("operation-registry",),
            "operation registry belongs to another declaration registry",
        )
    if type(procedure_id) is not str or not procedure_id:
        _fail(("procedure",), "procedure identifier must be non-empty text")
    if procedure_id not in {
        item.declaration for item in attention.resolution.unit.components
    }:
        _fail(("procedure",), "procedure is not effective in the attention plan")
    record = registry.records.get(procedure_id)
    if record is None or not isinstance(record.declaration, ProcedureDeclaration):
        _fail(("procedure",), "effective declaration is not a procedure")
    procedure = record.declaration
    frozen_parameters = _freeze_parameters(parameters, procedure)
    actions = tuple(
        _prepare_action(node, frozen_parameters, operation_registry, index)
        for index, node in enumerate(procedure.actions)
    )
    requirements = tuple(
        item
        for item in attention.requirements.completion
        if _belongs_to_procedure(item, procedure_id)
    )
    executable = tuple(item for item in requirements if item.evaluator is None)
    pre_action = tuple(item for item in requirements if _is_pre_action(item))
    evaluator_backed = tuple(item for item in pre_action if item.evaluator is not None)
    procedure_preconditions = tuple(
        item for item in requirements if _is_procedure_precondition(item)
    )
    evaluator_backed_procedure_preconditions = tuple(
        item for item in procedure_preconditions if item.evaluator is not None
    )
    requirement_semantics = tuple(
        _snapshot_requirement_authority(item, index)
        for index, item in enumerate(requirements)
    )
    action_semantics = tuple(
        _snapshot_action_authority(action, index)
        for index, action in enumerate(actions)
    )
    packet_semantics = _snapshot_packet_authority(attention, procedure_id)
    evaluation_inputs = _prepare_evaluation_inputs(
        procedure_id, requirement_semantics, packet_semantics
    )
    lifecycle_evaluations = _prepare_lifecycle_evaluations(
        requirement_semantics, packet_semantics
    )
    detector_registry_state = _snapshot_detector_registry_authority(
        attention.detector_registry
    )
    plan = object.__new__(ProcedureRunPlan)
    for name, value in (
        ("attention", attention),
        ("operation_registry", operation_registry),
        ("procedure", procedure),
        ("parameters", frozen_parameters),
        ("requirements", requirements),
        ("executable_requirements", executable),
        ("pre_action_requirements", pre_action),
        ("evaluator_backed_pre_action_requirements", evaluator_backed),
        ("procedure_precondition_requirements", procedure_preconditions),
        (
            "evaluator_backed_procedure_precondition_requirements",
            evaluator_backed_procedure_preconditions,
        ),
        ("actions", actions),
        ("lifecycle_evaluations", lifecycle_evaluations),
        ("_parameters_identity", frozen_parameters),
        ("_parameters_value", freeze_json(frozen_parameters)),
        ("_actions_identity", actions),
        ("_action_semantics", action_semantics),
        (
            "_procedure_semantics",
            _snapshot_declaration_authority(procedure, ("procedure",)),
        ),
        ("_executable_identity", executable),
        ("_pre_action_identity", pre_action),
        ("_evaluator_backed_identity", evaluator_backed),
        ("_procedure_precondition_identity", procedure_preconditions),
        (
            "_evaluator_backed_procedure_precondition_identity",
            evaluator_backed_procedure_preconditions,
        ),
        ("_requirements_identity", requirements),
        ("_requirement_semantics", requirement_semantics),
        ("_packet_semantics", packet_semantics),
        ("_attention_identity", attention),
        (
            "_operation_registry_state",
            _snapshot_operation_registry_authority(operation_registry),
        ),
        ("_detector_registry_state", detector_registry_state),
        ("_evaluation_inputs", evaluation_inputs),
        (
            "_evaluation_input_state",
            tuple(_snapshot_evaluation_input(item) for item in evaluation_inputs),
        ),
        ("_lifecycle_evaluations_identity", lifecycle_evaluations),
        (
            "_lifecycle_evaluation_state",
            tuple(
                _snapshot_lifecycle_evaluation(item) for item in lifecycle_evaluations
            ),
        ),
        ("_issuer", _PLAN_ISSUER),
    ):
        object.__setattr__(plan, name, value)
    if not _is_issued_procedure_run_plan(plan):
        _fail((), "preflight inputs changed while run authority was issued")
    return plan


def _snapshot_evaluation_input(
    item: PreparedProcedureEvaluationInput,
) -> _EvaluationInputAuthorityState:
    """Capture one detached evaluation-input carrier at run issuance."""
    predicate = item.predicate
    evaluator = predicate.evaluator
    return _EvaluationInputAuthorityState(
        item=item,
        source_key=item.source_key,
        procedure=item.procedure,
        predicate=predicate,
        predicate_state=(predicate.id, predicate.predicate_class),
        expression=predicate.expression,
        expression_value=freeze_json(predicate.expression),
        evaluator=evaluator,
        evaluator_state=(
            (evaluator.id, evaluator.version) if evaluator is not None else None
        ),
        observes=predicate.observes,
        observes_value=tuple(predicate.observes),
        invocation_input=item.invocation_input,
        invocation_value=(
            freeze_json(item.invocation_input)
            if item.invocation_input is not None
            else None
        ),
        input_schema=item.input_schema,
        schema_value=(
            freeze_json(item.input_schema) if item.input_schema is not None else None
        ),
    )


def _evaluation_inputs_are_current(plan: ProcedureRunPlan) -> bool:
    """Check detached evaluation carriers against their issuance authority."""
    if (
        type(plan._evaluation_inputs) is not tuple
        or type(plan._evaluation_input_state) is not tuple
        or len(plan._evaluation_inputs) != len(plan._evaluation_input_state)
    ):
        return False
    return all(
        _evaluation_input_is_current(item, state)
        for item, state in zip(plan._evaluation_inputs, plan._evaluation_input_state)
    )


def _evaluation_input_is_current(
    item: PreparedProcedureEvaluationInput,
    state: _EvaluationInputAuthorityState,
) -> bool:
    """Check one detached evaluation carrier and all nested immutable data."""
    predicate = item.predicate
    evaluator = predicate.evaluator
    return (
        type(item) is PreparedProcedureEvaluationInput
        and item is state.item
        and item.source_key is state.source_key
        and _exact_state_equal(item.procedure, state.procedure)
        and predicate is state.predicate
        and _exact_state_equal(
            (predicate.id, predicate.predicate_class), state.predicate_state
        )
        and predicate.expression is state.expression
        and json_values_equal(freeze_json(predicate.expression), state.expression_value)
        and evaluator is state.evaluator
        and _exact_state_equal(
            (evaluator.id, evaluator.version) if evaluator is not None else None,
            state.evaluator_state,
        )
        and predicate.observes is state.observes
        and _exact_state_equal(tuple(predicate.observes), state.observes_value)
        and item.invocation_input is state.invocation_input
        and (
            item.invocation_input is None
            or json_values_equal(
                freeze_json(item.invocation_input), state.invocation_value
            )
        )
        and item.input_schema is state.input_schema
        and (
            item.input_schema is None
            or json_values_equal(freeze_json(item.input_schema), state.schema_value)
        )
    )


def _prepare_evaluation_inputs(
    procedure_id: str,
    requirements: tuple[_RequirementAuthorityState, ...],
    packets: tuple[_PacketAuthorityState, ...],
) -> tuple[PreparedProcedureEvaluationInput, ...]:
    """Materialize detached provider inputs at the trusted preflight boundary."""
    result: list[PreparedProcedureEvaluationInput] = []
    for index, state in enumerate(requirements):
        if (
            type(state.key) is not ProcedurePredicateKey
            or state.key.phase is not PredicatePhase.PRECONDITION
            or state.evaluator is None
        ):
            continue
        expression = state.expression_value
        if not isinstance(expression, Mapping):
            _fail(
                ("requirements", index, "predicate", "expression"),
                "predicate expression must be an object",
            )
        reference = state.evaluator_reference
        if reference is None:
            _fail(("requirements", index, "evaluator"), "evaluator is absent")
        detached_predicate = Predicate(
            cast(str, state.predicate_state[0]),
            cast(str, state.predicate_state[1]),
            cast(Mapping[str, JsonValue], freeze_json(expression)),
            VersionedReference(reference.id, reference.version),
            tuple(state.observes_value),
        )
        packet = next((item for item in packets if item.key is state.key), None)
        if packet is None:
            _fail(("requirements", index), "precondition packet entry is absent")
        invocation_input: Mapping[str, JsonValue] | None = None
        input_schema: Mapping[str, JsonValue] | None = None
        if packet.input_value is not None:
            if not isinstance(packet.input_value, Mapping):
                _fail(("requirements", index, "invocation"), "input must be an object")
            invocation_input = cast(
                Mapping[str, JsonValue], freeze_json(packet.input_value)
            )
        if packet.input_contract_value is not None:
            if not isinstance(packet.input_contract_value, Mapping):
                _fail(
                    ("requirements", index, "invocation", "contract"),
                    "input contract must be an object",
                )
            input_schema = cast(
                Mapping[str, JsonValue], freeze_json(packet.input_contract_value)
            )
        result.append(
            PreparedProcedureEvaluationInput(
                state.key,
                procedure_id,
                detached_predicate,
                invocation_input,
                input_schema,
            )
        )
    return tuple(result)


def _prepare_lifecycle_evaluations(
    requirements: tuple[_RequirementAuthorityState, ...],
    packets: tuple[_PacketAuthorityState, ...],
) -> tuple[PreparedLifecycleEvaluation, ...]:
    """Detach every evaluator-backed requirement realized after entry."""
    result: list[PreparedLifecycleEvaluation] = []
    for ordinal, state in enumerate(requirements):
        if state.evaluator is None or not _is_lifecycle_key(state.key):
            continue
        packet = next((item for item in packets if item.key is state.key), None)
        if packet is None:
            _fail(("requirements", ordinal), "lifecycle packet entry is absent")
        requirement = cast(CompletionRequirement, _detach_value(state.requirement))
        evaluator = requirement.evaluator
        if type(evaluator) is not EvaluatorDeclaration:
            _fail(("requirements", ordinal, "evaluator"), "evaluator is absent")
        enforcement = state.enforcement
        if type(enforcement) is not EnforcementClass:
            _fail(("requirements", ordinal), "lifecycle enforcement class is invalid")
        common = (
            ordinal,
            cast(AttentionObligationKey, state.key),
            state.requirement,
            requirement,
            evaluator,
            enforcement,
        )
        if enforcement is EnforcementClass.DELIBERATIVE:
            if type(packet.entry) is not DeliberativeAttentionEntry:
                _fail(("requirements", ordinal), "manual packet entry kind differs")
            result.append(
                PreparedManualLifecycleEvaluation(
                    common[0],
                    common[1],
                    common[2],
                    cast(DeliberativeAttentionEntry, packet.entry),
                    common[3],
                    common[4],
                    common[5],
                )
            )
            continue
        invocation, input_schema = _detach_lifecycle_invocation(packet, ordinal)
        if enforcement is EnforcementClass.ASSISTED:
            if type(packet.entry) is not AssistedAttentionEntry:
                _fail(("requirements", ordinal), "assisted packet entry kind differs")
            residual = cast(AssistedAttentionEntry, packet.entry).residual_question
            result.append(
                PreparedAssistedLifecycleEvaluation(
                    common[0],
                    common[1],
                    common[2],
                    cast(AssistedAttentionEntry, packet.entry),
                    common[3],
                    common[4],
                    common[5],
                    invocation,
                    input_schema,
                    residual,
                )
            )
            continue
        if enforcement is not EnforcementClass.MECHANICAL:
            _fail(("requirements", ordinal), "lifecycle enforcement class is invalid")
        if type(packet.entry) is not MechanicalAttentionEntry:
            _fail(("requirements", ordinal), "mechanical packet entry kind differs")
        evidence = packet.evidence_value
        if not isinstance(evidence, Mapping):
            _fail(("requirements", ordinal, "evidence-schema"), "schema is absent")
        result.append(
            PreparedMechanicalLifecycleEvaluation(
                common[0],
                common[1],
                common[2],
                cast(MechanicalAttentionEntry, packet.entry),
                common[3],
                common[4],
                common[5],
                invocation,
                input_schema,
                cast(Mapping[str, JsonValue], freeze_json(evidence)),
            )
        )
    return tuple(result)


def _detach_lifecycle_invocation(
    packet: _PacketAuthorityState, ordinal: int
) -> tuple[EvaluatorInvocation, Mapping[str, JsonValue]]:
    """Detach one canonical invocation and its input-operation schema."""
    if packet.invocation is None or packet.input_contract_value is None:
        _fail(("requirements", ordinal, "invocation"), "invocation is absent")
    if not isinstance(packet.input_contract_value, Mapping):
        _fail(("requirements", ordinal, "invocation", "contract"), "schema is invalid")
    invocation = cast(EvaluatorInvocation, _detach_value(packet.invocation))
    schema = cast(Mapping[str, JsonValue], freeze_json(packet.input_contract_value))
    return invocation, schema


def _snapshot_lifecycle_evaluation(
    item: PreparedLifecycleEvaluation,
) -> _LifecycleEvaluationAuthorityState:
    """Capture live identities and detached semantics for one specification."""
    return _LifecycleEvaluationAuthorityState(
        item,
        item.source_key,
        item.source_requirement,
        item.source_entry,
        _identity_semantic_state(item),
    )


def _lifecycle_evaluations_are_current(plan: ProcedureRunPlan) -> bool:
    """Validate every lifecycle specification against its issuance snapshot."""
    items = plan.lifecycle_evaluations
    states = plan._lifecycle_evaluation_state
    if (
        type(items) is not tuple
        or type(states) is not tuple
        or len(items) != len(states)
    ):
        return False
    expected = tuple(
        state.requirement
        for state in plan._requirement_semantics
        if state.evaluator is not None and _is_lifecycle_key(state.key)
    )
    if len(expected) != len(items):
        return False
    return all(
        item is state.item
        and item.source_key is state.source_key
        and item.source_requirement is state.source_requirement
        and item.source_requirement is requirement
        and item.source_entry is state.source_entry
        and item.requirement.evaluator is item.evaluator
        and _identity_semantic_state(item) == state.detached_state
        for item, state, requirement in zip(items, states, expected)
    )


def _is_lifecycle_key(
    key: ProcedurePredicateKey | OperationPredicateKey,
) -> bool:
    if type(key) is OperationPredicateKey:
        return True
    return type(key) is ProcedurePredicateKey and key.phase in {
        PredicatePhase.INVARIANT,
        PredicatePhase.POSTCONDITION,
    }


def _detach_value(value: object) -> object:
    """Copy one authority graph into immutable value carriers."""
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
            {_detach_value(key): _detach_value(item) for key, item in value.items()}
        )
    if type(value) in {tuple, list}:
        sequence = cast(tuple[object, ...] | list[object], value)
        return tuple(_detach_value(item) for item in sequence)
    if is_dataclass(value):
        return type(value)(  # type: ignore[misc]
            **{
                field.name: _detach_value(getattr(value, field.name))
                for field in fields(value)
            }
        )
    return value


def _semantic_state(value: object) -> object:
    """Return an alias-free semantic state for detached run material."""
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
    """Capture nested carrier identity together with detached semantics."""
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


def _procedure_evaluation_material(
    plan: ProcedureRunPlan,
) -> tuple[Mapping[str, JsonValue], tuple[PreparedProcedureEvaluationInput, ...]]:
    """Return detached parameters and evaluation inputs issued with one run."""
    if not _is_issued_procedure_run_plan(plan):
        raise TypeError("procedure run plan authority is invalid")
    parameters = plan._parameters_value
    if not isinstance(parameters, Mapping):
        raise TypeError("procedure run parameters are invalid")
    return cast(Mapping[str, JsonValue], parameters), plan._evaluation_inputs


def _snapshot_requirement_authority(
    requirement: CompletionRequirement, index: int
) -> _RequirementAuthorityState:
    """Capture one run requirement without delegating authority to later readers."""
    key = requirement.key
    obligation = requirement.obligation
    if (
        type(key) is ProcedurePredicateKey
        and type(obligation) is ProcedureObligationSnapshot
    ):
        key_state: tuple[object, ...] = (
            key.declaration,
            key.phase,
            key.predicate,
        )
        key_reference = None
    elif (
        type(key) is OperationPredicateKey
        and type(obligation) is OperationObligationSnapshot
    ):
        key_state = (
            key.procedure,
            key.action,
            key.subject_operation.id,
            key.subject_operation.version,
            key.predicate,
        )
        key_reference = key.subject_operation
    else:
        _fail(("requirements",), "run requirement has an invalid predicate snapshot")
    predicate = obligation.predicate
    obligation_maps: tuple[Mapping[str, JsonValue], ...]
    obligation_sequences: tuple[tuple[str, ...], ...]
    if isinstance(obligation, ProcedureObligationSnapshot):
        obligation_state: tuple[object, ...] = (
            obligation.purpose,
            obligation.title,
            obligation.rationale,
            obligation.phase,
        )
        obligation_maps = (obligation.parameters,)
        obligation_sequences = (obligation.effects, obligation.failures)
        obligation_action = None
    else:
        assert isinstance(obligation, OperationObligationSnapshot)
        obligation_state = (
            obligation.procedure_purpose,
            obligation.procedure_title,
            obligation.procedure_rationale,
            obligation.recovery,
        )
        obligation_maps = (
            obligation.procedure_parameters,
            obligation.operation_inputs,
        )
        obligation_sequences = (
            obligation.operation_effects,
            obligation.failure_outcomes,
        )
        obligation_action = obligation.action
    obligation_map_values = tuple(
        _freeze_authority_json(
            value, ("requirements", index, "obligation", "mapping", map_index)
        )
        for map_index, value in enumerate(obligation_maps)
    )
    expression_value = _freeze_authority_json(
        predicate.expression, ("requirements", index, "predicate", "expression")
    )
    reference = predicate.evaluator
    reference_state = (
        (reference.id, reference.version) if reference is not None else None
    )
    evaluator = requirement.evaluator
    evidence_schema = evaluator.evidence_schema if evaluator is not None else None
    evidence_schema_value = (
        _freeze_authority_json(
            evidence_schema, ("requirements", index, "evaluator", "evidence-schema")
        )
        if evidence_schema is not None
        else None
    )
    evaluator_state = _evaluator_contract_state(evaluator)
    return _RequirementAuthorityState(
        requirement=requirement,
        key=key,
        key_state=key_state,
        key_reference=key_reference,
        obligation=obligation,
        obligation_state=obligation_state,
        obligation_maps=obligation_maps,
        obligation_map_values=obligation_map_values,
        obligation_sequences=obligation_sequences,
        obligation_sequence_values=tuple(
            tuple(value) for value in obligation_sequences
        ),
        obligation_action=obligation_action,
        predicate=predicate,
        predicate_state=(predicate.id, predicate.predicate_class),
        expression=predicate.expression,
        expression_value=expression_value,
        evaluator_reference=reference,
        evaluator_reference_state=reference_state,
        observes=predicate.observes,
        observes_value=tuple(predicate.observes),
        evaluator=evaluator,
        evaluator_state=evaluator_state,
        evaluator_declaration_state=(
            _snapshot_declaration_authority(
                evaluator, ("requirements", index, "evaluator")
            )
            if evaluator is not None
            else None
        ),
        evidence_schema=evidence_schema,
        evidence_schema_value=evidence_schema_value,
        enforcement=requirement.enforcement,
    )


def _snapshot_action_authority(
    action: PreparedProcedureAction, index: int
) -> _ActionAuthorityState:
    """Capture one prepared action at run issuance."""
    node = action.node
    try:
        binding_state = tuple(
            _binding_authority_state(name, binding, index)
            for name, binding in node.bindings.items()
        )
    except ProcedureRunPlanningError:
        raise
    except Exception as exc:
        _fail(
            ("actions", index, "node", "bindings"),
            f"action bindings cannot be read: {exception_detail(exc)}",
            cause=exc,
        )
    return _ActionAuthorityState(
        action=action,
        node=node,
        node_state=_node_scalar_state(node),
        bindings=cast(Mapping[str, object], node.bindings),
        binding_state=binding_state,
        failure_transitions=node.on_failure,
        failure_transition_value=_freeze_authority_json(
            node.on_failure, ("actions", index, "node", "on-failure")
        ),
        contract_state=_snapshot_declaration_authority(
            action.contract, ("actions", index, "contract")
        ),
        operation=action.operation,
        operation_state=(action.operation.id, action.operation.version),
        contract=action.contract,
        input_data=action.input_data,
        input_value=_freeze_authority_json(
            action.input_data, ("actions", index, "input")
        ),
    )


def _action_authority_is_current(
    action: PreparedProcedureAction, state: _ActionAuthorityState
) -> bool:
    """Check one prepared action against its run-issuance state."""
    return (
        type(action) is PreparedProcedureAction
        and action is state.action
        and action.node is state.node
        and _exact_state_equal(_node_scalar_state(action.node), state.node_state)
        and action.node.operation is state.operation
        and action.node.bindings is state.bindings
        and _binding_authority_is_current(action.node.bindings, state.binding_state)
        and action.node.on_failure is state.failure_transitions
        and json_values_equal(
            freeze_json(action.node.on_failure), state.failure_transition_value
        )
        and action.operation is state.operation
        and _exact_state_equal(
            (action.operation.id, action.operation.version), state.operation_state
        )
        and action.contract is state.contract
        and _declaration_authority_is_current(state.contract_state)
        and action.input_data is state.input_data
        and json_values_equal(freeze_json(action.input_data), state.input_value)
    )


def _binding_authority_state(
    name: object, binding: object, action_index: int
) -> tuple[object, ...]:
    """Capture one exact action binding and its authored semantics."""
    if type(name) is not str:
        _fail(("actions", action_index, "node", "bindings"), "binding name is invalid")
    if type(binding) is ParameterBinding:
        return (name, binding, ParameterBinding, binding.parameter)
    if type(binding) is LiteralBinding:
        return (
            name,
            binding,
            LiteralBinding,
            _freeze_authority_json(
                binding.value,
                ("actions", action_index, "node", "bindings", name),
            ),
        )
    _fail(
        ("actions", action_index, "node", "bindings", name),
        "binding kind is invalid",
    )


def _binding_authority_is_current(
    bindings: Mapping[str, object], states: tuple[tuple[object, ...], ...]
) -> bool:
    """Check an authored binding map without accepting same-output substitution."""
    try:
        items = tuple(bindings.items())
    except Exception:
        return False
    if len(items) != len(states):
        return False
    for (name, binding), state in zip(items, states):
        if type(name) is not str or name != state[0] or binding is not state[1]:
            return False
        if type(binding) is ParameterBinding and state[2] is ParameterBinding:
            current: object = binding.parameter
        elif type(binding) is LiteralBinding and state[2] is LiteralBinding:
            try:
                current = freeze_json(binding.value)
            except Exception:
                return False
        else:
            return False
        if not _exact_state_equal(current, state[3]) and not (
            type(binding) is LiteralBinding and json_values_equal(current, state[3])
        ):
            return False
    return True


def _snapshot_packet_authority(
    attention: AttentionPlan, procedure_id: str
) -> tuple[_PacketAuthorityState, ...]:
    """Capture every procedure-owned packet entry used by run planning."""
    states: list[_PacketAuthorityState] = []
    try:
        packets = (
            attention.deliberative.entries,
            attention.assisted.entries,
            attention.mechanical.entries,
        )
    except Exception as exc:
        _fail(
            ("attention", "packets"),
            f"attention packets cannot be read: {exception_detail(exc)}",
            cause=exc,
        )
    for packet_index, entries in enumerate(packets):
        if type(entries) is not tuple:
            _fail(
                ("attention", "packets", packet_index),
                "attention packet entries must be a tuple",
            )
        for entry_index, entry in enumerate(entries):
            try:
                state = _snapshot_packet_entry(
                    attention, procedure_id, entry, packet_index, entry_index
                )
            except ProcedureRunPlanningError:
                raise
            except Exception as exc:
                _fail(
                    ("attention", "packets", packet_index, entry_index),
                    f"attention packet entry cannot be read: {exception_detail(exc)}",
                    cause=exc,
                )
            if state is not None:
                states.append(state)
    return tuple(states)


def _snapshot_packet_entry(
    attention: AttentionPlan,
    procedure_id: str,
    entry: object,
    packet_index: int,
    entry_index: int,
) -> _PacketAuthorityState | None:
    """Capture one relevant packet entry or ignore an unrelated obligation."""
    location = ("attention", "packets", packet_index, entry_index)
    if type(entry) is DeliberativeAttentionEntry:
        key = entry.obligation.key
        obligation: ProcedureObligationSnapshot | OperationObligationSnapshot | None = (
            cast(
                ProcedureObligationSnapshot | OperationObligationSnapshot,
                entry.obligation,
            )
            if type(entry.obligation)
            in {ProcedureObligationSnapshot, OperationObligationSnapshot}
            else None
        )
        evaluator = entry.evaluator
        invocation = None
        evidence_schema = None
        entry_state: tuple[object, ...] = ()
    elif type(entry) is AssistedAttentionEntry:
        key = entry.obligation.key
        obligation = (
            cast(
                ProcedureObligationSnapshot | OperationObligationSnapshot,
                entry.obligation,
            )
            if type(entry.obligation)
            in {ProcedureObligationSnapshot, OperationObligationSnapshot}
            else None
        )
        evaluator = None
        invocation = entry.invocation
        evidence_schema = None
        entry_state = (entry.residual_question,)
    elif type(entry) is MechanicalAttentionEntry:
        key = entry.key
        obligation = None
        evaluator = None
        invocation = entry.invocation
        evidence_schema = entry.evidence_schema
        entry_state = ()
    else:
        _fail(location, "attention packet entry is invalid")
    if not _key_belongs_to_procedure(key, procedure_id):
        return None
    procedure_key = cast(ProcedurePredicateKey | OperationPredicateKey, key)
    if invocation is None:
        return _PacketAuthorityState(
            entry=entry,
            key=procedure_key,
            obligation=obligation,
            evaluator=evaluator,
            invocation=None,
            evaluator_reference=None,
            input_operation_reference=None,
            invocation_state=None,
            input_data=None,
            input_value=None,
            evidence_schema=None,
            evidence_value=None,
            input_contract=None,
            input_contract_schema=None,
            input_contract_value=None,
            input_contract_state=None,
            entry_state=entry_state,
        )
    evaluator_reference = invocation.evaluator
    input_operation_reference = invocation.evaluator_input_operation
    input_contract = _operation_declaration(
        attention, input_operation_reference, location + ("input-operation",)
    )
    return _PacketAuthorityState(
        entry=entry,
        key=procedure_key,
        obligation=obligation,
        evaluator=evaluator,
        invocation=invocation,
        evaluator_reference=evaluator_reference,
        input_operation_reference=input_operation_reference,
        invocation_state=(
            evaluator_reference.id,
            evaluator_reference.version,
            input_operation_reference.id,
            input_operation_reference.version,
            invocation.input_revision,
        ),
        input_data=invocation.input_data,
        input_value=_freeze_authority_json(
            invocation.input_data, location + ("invocation", "input")
        ),
        evidence_schema=evidence_schema,
        evidence_value=(
            _freeze_authority_json(evidence_schema, location + ("evidence-schema",))
            if evidence_schema is not None
            else None
        ),
        input_contract=input_contract,
        input_contract_schema=input_contract.inputs,
        input_contract_value=_freeze_authority_json(
            input_contract.inputs, location + ("input-operation", "inputs")
        ),
        input_contract_state=_snapshot_declaration_authority(
            input_contract, location + ("input-operation",)
        ),
        entry_state=entry_state,
    )


def _packet_authority_is_current(plan: ProcedureRunPlan) -> bool:
    """Check every retained procedure-owned packet entry and input contract."""
    current_entries: list[object] = []
    for entries in (
        plan.attention.deliberative.entries,
        plan.attention.assisted.entries,
        plan.attention.mechanical.entries,
    ):
        if type(entries) is not tuple:
            return False
        for entry in entries:
            if type(entry) is DeliberativeAttentionEntry:
                key = entry.obligation.key
            elif type(entry) is AssistedAttentionEntry:
                key = entry.obligation.key
            elif type(entry) is MechanicalAttentionEntry:
                key = entry.key
            else:
                return False
            if _key_belongs_to_procedure(key, plan.procedure.id):
                current_entries.append(entry)
    if len(current_entries) != len(plan._packet_semantics):
        return False
    return all(
        _packet_entry_authority_is_current(plan.attention, entry, state)
        for entry, state in zip(current_entries, plan._packet_semantics)
    )


def _key_belongs_to_procedure(key: object, procedure_id: str) -> bool:
    """Return whether one packet key belongs to the exact prepared procedure."""
    return (type(key) is ProcedurePredicateKey and key.declaration == procedure_id) or (
        type(key) is OperationPredicateKey and key.procedure == procedure_id
    )


def _packet_entry_authority_is_current(
    attention: AttentionPlan, entry: object, state: _PacketAuthorityState
) -> bool:
    """Check one packet entry against its run-issuance state."""
    if entry is not state.entry:
        return False
    if type(entry) is DeliberativeAttentionEntry:
        return (
            entry.obligation is state.obligation
            and entry.obligation.key is state.key
            and entry.evaluator is state.evaluator
            and state.invocation is None
            and _exact_state_equal((), state.entry_state)
        )
    if type(entry) is AssistedAttentionEntry:
        if (
            entry.obligation is not state.obligation
            or entry.obligation.key is not state.key
            or entry.invocation is not state.invocation
        ):
            return False
        invocation = entry.invocation
        evidence_schema = None
        entry_state: tuple[object, ...] = (entry.residual_question,)
    elif type(entry) is MechanicalAttentionEntry:
        if entry.key is not state.key or entry.invocation is not state.invocation:
            return False
        invocation = entry.invocation
        evidence_schema = entry.evidence_schema
        entry_state = ()
    else:
        return False
    if (
        invocation.evaluator is not state.evaluator_reference
        or invocation.evaluator_input_operation is not state.input_operation_reference
        or invocation.input_data is not state.input_data
        or not _exact_state_equal(
            (
                invocation.evaluator.id,
                invocation.evaluator.version,
                invocation.evaluator_input_operation.id,
                invocation.evaluator_input_operation.version,
                invocation.input_revision,
            ),
            state.invocation_state,
        )
        or not json_values_equal(freeze_json(invocation.input_data), state.input_value)
        or evidence_schema is not state.evidence_schema
        or not _exact_state_equal(entry_state, state.entry_state)
    ):
        return False
    if evidence_schema is not None and not json_values_equal(
        freeze_json(evidence_schema), state.evidence_value
    ):
        return False
    input_contract = _operation_declaration(
        attention, invocation.evaluator_input_operation, ("attention", "packets")
    )
    return (
        input_contract is state.input_contract
        and state.input_contract_state is not None
        and _declaration_authority_is_current(state.input_contract_state)
        and input_contract.inputs is state.input_contract_schema
        and json_values_equal(
            freeze_json(input_contract.inputs), state.input_contract_value
        )
    )


def _operation_declaration(
    attention: AttentionPlan,
    reference: VersionedReference,
    location: tuple[str | int, ...],
) -> OperationDeclaration:
    """Resolve one exact evaluator-input operation for authority retention."""
    family = attention.resolution.registry.families.get(reference.id)
    if family is None:
        _fail(location, "evaluator input operation family is absent")
    record = family.versions.get(reference.version)
    if record is None or type(record.declaration) is not OperationDeclaration:
        _fail(location, "evaluator input operation contract is absent")
    return record.declaration


def _freeze_authority_json(value: object, location: tuple[str | int, ...]) -> JsonValue:
    """Freeze retained authority data behind the public preflight exception."""
    try:
        return freeze_json(value)
    except Exception as exc:
        _fail(
            location,
            f"retained authority data is not finite JSON: {exception_detail(exc)}",
            cause=exc,
        )


def _requirement_authority_is_current(
    requirement: CompletionRequirement, state: _RequirementAuthorityState
) -> bool:
    """Check one retained requirement against its preflight issuance state."""
    if (
        type(requirement) is not CompletionRequirement
        or requirement is not state.requirement
        or requirement.key is not state.key
        or requirement.obligation is not state.obligation
        or requirement.evaluator is not state.evaluator
        or requirement.enforcement is not state.enforcement
    ):
        return False
    key = requirement.key
    obligation = requirement.obligation
    if (
        type(key) is ProcedurePredicateKey
        and type(obligation) is ProcedureObligationSnapshot
    ):
        current_key_state: tuple[object, ...] = (
            key.declaration,
            key.phase,
            key.predicate,
        )
        current_key_reference = None
    elif (
        type(key) is OperationPredicateKey
        and type(obligation) is OperationObligationSnapshot
    ):
        current_key_state = (
            key.procedure,
            key.action,
            key.subject_operation.id,
            key.subject_operation.version,
            key.predicate,
        )
        current_key_reference = key.subject_operation
    else:
        return False
    predicate = obligation.predicate
    reference = predicate.evaluator
    current_reference_state = (
        (reference.id, reference.version) if reference is not None else None
    )
    evaluator = requirement.evaluator
    evidence_schema = evaluator.evidence_schema if evaluator is not None else None
    return (
        _exact_state_equal(current_key_state, state.key_state)
        and current_key_reference is state.key_reference
        and _obligation_authority_is_current(obligation, state)
        and predicate is state.predicate
        and _exact_state_equal(
            (predicate.id, predicate.predicate_class), state.predicate_state
        )
        and predicate.expression is state.expression
        and json_values_equal(freeze_json(predicate.expression), state.expression_value)
        and reference is state.evaluator_reference
        and _exact_state_equal(current_reference_state, state.evaluator_reference_state)
        and predicate.observes is state.observes
        and _exact_state_equal(tuple(predicate.observes), state.observes_value)
        and _exact_state_equal(
            _evaluator_contract_state(evaluator), state.evaluator_state
        )
        and (
            (evaluator is None and state.evaluator_declaration_state is None)
            or (
                evaluator is not None
                and state.evaluator_declaration_state is not None
                and _declaration_authority_is_current(state.evaluator_declaration_state)
            )
        )
        and evidence_schema is state.evidence_schema
        and (
            evidence_schema is None
            or json_values_equal(
                freeze_json(evidence_schema), state.evidence_schema_value
            )
        )
    )


def _obligation_authority_is_current(
    obligation: ProcedureObligationSnapshot | OperationObligationSnapshot,
    state: _RequirementAuthorityState,
) -> bool:
    """Check the complete obligation context exposed by evaluation records."""
    current_maps: tuple[Mapping[str, JsonValue], ...]
    current_sequences: tuple[tuple[str, ...], ...]
    if isinstance(obligation, ProcedureObligationSnapshot):
        current_state: tuple[object, ...] = (
            obligation.purpose,
            obligation.title,
            obligation.rationale,
            obligation.phase,
        )
        current_maps = (obligation.parameters,)
        current_sequences = (obligation.effects, obligation.failures)
        current_action = None
    elif type(obligation) is OperationObligationSnapshot:
        current_state = (
            obligation.procedure_purpose,
            obligation.procedure_title,
            obligation.procedure_rationale,
            obligation.recovery,
        )
        current_maps = (
            obligation.procedure_parameters,
            obligation.operation_inputs,
        )
        current_sequences = (
            obligation.operation_effects,
            obligation.failure_outcomes,
        )
        current_action = obligation.action
    else:
        return False
    if (
        not _exact_state_equal(current_state, state.obligation_state)
        or current_action is not state.obligation_action
        or len(current_maps) != len(state.obligation_maps)
        or len(current_sequences) != len(state.obligation_sequences)
    ):
        return False
    for map_current, retained_map, map_value in zip(
        current_maps, state.obligation_maps, state.obligation_map_values
    ):
        if map_current is not retained_map or not json_values_equal(
            freeze_json(map_current), map_value
        ):
            return False
    for sequence_current, retained_sequence, sequence_value in zip(
        current_sequences,
        state.obligation_sequences,
        state.obligation_sequence_values,
    ):
        if sequence_current is not retained_sequence or not _exact_state_equal(
            tuple(sequence_current), sequence_value
        ):
            return False
    return True


def _exact_state_equal(left: object, right: object) -> bool:
    """Compare retained scalar state without invoking subclass equality hooks."""
    if type(left) is not type(right):
        return False
    if type(left) is tuple:
        left_tuple = cast(tuple[object, ...], left)
        right_tuple = cast(tuple[object, ...], right)
        return len(left_tuple) == len(right_tuple) and all(
            _exact_state_equal(left_item, right_item)
            for left_item, right_item in zip(left_tuple, right_tuple)
        )
    if left is None:
        return True
    if type(left) in {str, int, bool}:
        return left == right
    return left is right


def _same_identity_tuple(left: object, right: tuple[object, ...]) -> bool:
    """Compare an exact tuple by carrier identity and order."""
    return (
        type(left) is tuple
        and len(left) == len(right)
        and all(left_item is right_item for left_item, right_item in zip(left, right))
    )


def _snapshot_declaration_authority(
    declaration: ProcedureDeclaration | OperationDeclaration | EvaluatorDeclaration,
    location: tuple[str | int, ...],
) -> _DeclarationAuthorityState:
    """Capture every semantic field of one declaration used by a run."""
    try:
        value = freeze_json(_declaration_semantic_value(declaration))
        identities = _declaration_identities(declaration)
    except ProcedureRunPlanningError:
        raise
    except Exception as exc:
        _fail(
            location,
            f"declaration authority cannot be read: {exception_detail(exc)}",
            cause=exc,
        )
    return _DeclarationAuthorityState(
        declaration, value, identities, _declaration_scalar_state(declaration)
    )


def _declaration_authority_is_current(state: _DeclarationAuthorityState) -> bool:
    """Check complete declaration semantics and carrier identities."""
    declaration = state.declaration
    current_value = freeze_json(_declaration_semantic_value(declaration))
    current_identities = _declaration_identities(declaration)
    return (
        json_values_equal(current_value, state.semantic_value)
        and _same_identity_tuple(current_identities, state.identities)
        and _exact_state_equal(
            _declaration_scalar_state(declaration), state.scalar_state
        )
    )


def _declaration_semantic_value(
    declaration: ProcedureDeclaration | OperationDeclaration | EvaluatorDeclaration,
) -> Mapping[str, object]:
    """Project one declaration into complete JSON-compatible semantics."""
    value: dict[str, object] = {
        "schema_version": declaration.schema_version,
        "id": declaration.id,
        "kind": declaration.kind.value,
        "owner": declaration.owner,
        "status": declaration.status,
        "source_revision": declaration.source_revision,
        "applicability": declaration.applicability,
        "relations": [
            {"type": relation.type, "target": relation.target}
            for relation in declaration.relations
        ],
        "title": declaration.title,
        "rationale": declaration.rationale,
        "document": declaration.document,
    }
    if type(declaration) is ProcedureDeclaration:
        value.update(
            {
                "purpose": declaration.purpose,
                "parameters": declaration.parameters,
                "preconditions": [
                    _predicate_semantic_value(item)
                    for item in declaration.preconditions
                ],
                "actions": [_node_semantic_value(item) for item in declaration.actions],
                "entry": declaration.entry,
                "invariants": [
                    _predicate_semantic_value(item) for item in declaration.invariants
                ],
                "effects": declaration.effects,
                "postconditions": [
                    _predicate_semantic_value(item)
                    for item in declaration.postconditions
                ],
                "failures": declaration.failures,
            }
        )
    elif type(declaration) is OperationDeclaration:
        value.update(
            {
                "version": declaration.version,
                "inputs": declaration.inputs,
                "outputs": declaration.outputs,
                "preconditions": [
                    _predicate_semantic_value(item)
                    for item in declaration.preconditions
                ],
                "effects": declaration.effects,
                "failure_outcomes": declaration.failure_outcomes,
                "recovery": declaration.recovery,
            }
        )
    else:
        assert type(declaration) is EvaluatorDeclaration
        value.update(
            {
                "version": declaration.version,
                "evaluator_kind": declaration.evaluator_kind,
                "coverage": declaration.coverage,
                "adjudication": declaration.adjudication,
                "timing": declaration.timing,
                "residual_question": declaration.residual_question,
                "input_revisions": declaration.input_revisions,
                "evidence_schema": declaration.evidence_schema,
                "failure_behavior": declaration.failure_behavior,
                "known_failure_fixtures": declaration.known_failure_fixtures,
            }
        )
    return value


def _predicate_semantic_value(predicate: Predicate) -> Mapping[str, object]:
    """Project one predicate into JSON-compatible semantics."""
    evaluator = predicate.evaluator
    return {
        "id": predicate.id,
        "predicate_class": predicate.predicate_class,
        "expression": predicate.expression,
        "evaluator": (
            {"id": evaluator.id, "version": evaluator.version}
            if evaluator is not None
            else None
        ),
        "observes": predicate.observes,
    }


def _node_semantic_value(node: ProcedureNode) -> Mapping[str, object]:
    """Project one action node, including its authored binding program."""
    bindings: dict[str, object] = {}
    for name, binding in node.bindings.items():
        if type(binding) is ParameterBinding:
            bindings[name] = {"parameter": binding.parameter}
        elif type(binding) is LiteralBinding:
            bindings[name] = {"literal": binding.value}
        else:
            raise TypeError("procedure node contains an invalid binding")
    return {
        "id": node.id,
        "operation": {"id": node.operation.id, "version": node.operation.version},
        "bindings": bindings,
        "on_success": node.on_success,
        "on_failure": node.on_failure,
    }


def _declaration_identities(
    declaration: ProcedureDeclaration | OperationDeclaration | EvaluatorDeclaration,
) -> tuple[object, ...]:
    """Project declaration carrier identities after semantic traversal."""
    result: list[object] = [
        declaration,
        declaration.applicability,
        declaration.relations,
        *declaration.relations,
        declaration.document,
    ]
    if type(declaration) is ProcedureDeclaration:
        result.extend(
            [
                declaration.parameters,
                declaration.preconditions,
                *declaration.preconditions,
                declaration.actions,
                *declaration.actions,
                declaration.invariants,
                *declaration.invariants,
                declaration.effects,
                declaration.postconditions,
                *declaration.postconditions,
                declaration.failures,
            ]
        )
        for node in declaration.actions:
            result.extend(
                [
                    node.operation,
                    node.bindings,
                    *node.bindings.values(),
                    node.on_failure,
                ]
            )
        predicates = (
            *declaration.preconditions,
            *declaration.invariants,
            *declaration.postconditions,
        )
    elif type(declaration) is OperationDeclaration:
        result.extend(
            [
                declaration.inputs,
                declaration.outputs,
                declaration.preconditions,
                *declaration.preconditions,
                declaration.effects,
                declaration.failure_outcomes,
            ]
        )
        predicates = declaration.preconditions
    else:
        assert type(declaration) is EvaluatorDeclaration
        result.extend(
            [
                declaration.input_revisions,
                declaration.evidence_schema,
                declaration.known_failure_fixtures,
            ]
        )
        predicates = ()
    for predicate in predicates:
        result.extend(
            [
                predicate.expression,
                predicate.evaluator,
                predicate.observes,
            ]
        )
    return tuple(result)


def _declaration_scalar_state(
    declaration: ProcedureDeclaration | OperationDeclaration | EvaluatorDeclaration,
) -> tuple[object, ...]:
    """Project all declaration scalars for the final callback-free comparison."""
    common: tuple[object, ...] = (
        declaration.schema_version,
        declaration.id,
        declaration.kind,
        declaration.owner,
        declaration.status,
        declaration.source_revision,
        declaration.title,
        declaration.rationale,
        tuple((item.type, item.target) for item in declaration.relations),
    )
    if type(declaration) is ProcedureDeclaration:
        return common + (
            declaration.purpose,
            declaration.entry,
            tuple(_predicate_scalar_state(item) for item in declaration.preconditions),
            tuple(_node_scalar_state(item) for item in declaration.actions),
            tuple(_predicate_scalar_state(item) for item in declaration.invariants),
            declaration.effects,
            tuple(_predicate_scalar_state(item) for item in declaration.postconditions),
            declaration.failures,
        )
    if type(declaration) is OperationDeclaration:
        return common + (
            declaration.version,
            tuple(_predicate_scalar_state(item) for item in declaration.preconditions),
            declaration.effects,
            declaration.failure_outcomes,
            declaration.recovery,
        )
    assert type(declaration) is EvaluatorDeclaration
    return common + (
        declaration.version,
        declaration.evaluator_kind,
        declaration.coverage,
        declaration.adjudication,
        declaration.timing,
        declaration.residual_question,
        declaration.input_revisions,
        declaration.failure_behavior,
        declaration.known_failure_fixtures,
    )


def _predicate_scalar_state(predicate: Predicate) -> tuple[object, ...]:
    """Project callback-free predicate scalars."""
    evaluator = predicate.evaluator
    return (
        predicate.id,
        predicate.predicate_class,
        evaluator.id if evaluator is not None else None,
        evaluator.version if evaluator is not None else None,
        predicate.observes,
    )


def _node_scalar_state(node: ProcedureNode) -> tuple[object, ...]:
    """Project callback-free action-node scalars."""
    return (
        node.id,
        node.operation.id,
        node.operation.version,
        node.on_success,
    )


def _snapshot_operation_registry_authority(
    registry: OperationRunnerRegistry,
) -> _OperationRegistryAuthorityState:
    """Capture the exact operation runner authority selected for a run."""
    records: list[tuple[object, ...]] = []
    for reference, binding in registry.bindings.items():
        if type(binding) is not OperationRunnerBinding:
            _fail(("operation-registry", "bindings"), "runner binding is invalid")
        contract = registry.contracts.get(reference)
        if type(contract) is not OperationDeclaration:
            _fail(("operation-registry", "contracts"), "operation contract is invalid")
        records.append(
            (
                reference,
                reference.id,
                reference.version,
                binding,
                binding.operation,
                binding.operation.id,
                binding.operation.version,
                binding.runner,
                contract,
            )
        )
    return _OperationRegistryAuthorityState(
        registry,
        registry.declarations,
        registry.bindings,
        registry.contracts,
        tuple(records),
    )


def _operation_registry_authority_is_current(
    state: _OperationRegistryAuthorityState,
) -> bool:
    """Check one executable registry without accepting equivalent substitution."""
    registry = state.registry
    if (
        registry.declarations is not state.declarations
        or registry.bindings is not state.bindings
        or registry.contracts is not state.contracts
    ):
        return False
    current = _snapshot_operation_registry_authority(registry)
    if len(current.records) != len(state.records):
        return False
    return all(
        _exact_state_equal(current_record[1:3], retained_record[1:3])
        and _exact_state_equal(current_record[5:7], retained_record[5:7])
        and current_record[0] is retained_record[0]
        and current_record[3] is retained_record[3]
        and current_record[4] is retained_record[4]
        and current_record[7] is retained_record[7]
        and current_record[8] is retained_record[8]
        for current_record, retained_record in zip(current.records, state.records)
    )


def _snapshot_detector_registry_authority(
    registry: DetectorRunnerRegistry | None,
) -> _DetectorRegistryAuthorityState | None:
    """Capture identities and contracts from the live detector-registry origin."""
    if registry is None:
        return None
    if not _is_builder_issued_detector_registry(registry):
        _fail(("detector-registry",), "registry was not issued by its builder")
    records: list[tuple[object, ...]] = []
    for reference, binding in registry.bindings.items():
        if type(binding) is not DetectorRunnerBinding:
            _fail(("detector-registry", "bindings"), "runner binding is invalid")
        contract = registry.input_contracts.get(reference)
        registered = registry.evaluator_records.get(reference)
        if not isinstance(contract, Mapping) or registered is None:
            _fail(("detector-registry", "contracts"), "registry contract is absent")
        declaration = registered.declaration
        if type(declaration) is not EvaluatorDeclaration:
            _fail(("detector-registry", "records"), "evaluator record is invalid")
        records.append(
            (
                reference,
                reference.id,
                reference.version,
                binding,
                binding.evaluator,
                binding.evaluator.id,
                binding.evaluator.version,
                binding.operation,
                binding.operation.id,
                binding.operation.version,
                binding.runner,
                contract,
                freeze_json(contract),
                registered,
                declaration,
                _evaluator_contract_state(declaration),
            )
        )
    return _DetectorRegistryAuthorityState(
        registry,
        registry.declarations,
        registry.bindings,
        registry.input_contracts,
        registry.evaluator_records,
        tuple(records),
    )


def _detector_registry_authority_is_current(
    current_registry: DetectorRunnerRegistry | None,
    state: _DetectorRegistryAuthorityState | None,
) -> bool:
    """Check the detector origin without accepting equal-value replacement."""
    if state is None:
        return current_registry is None
    if current_registry is not state.registry:
        return False
    registry = state.registry
    if (
        not _is_builder_issued_detector_registry(registry)
        or registry.declarations is not state.declarations
        or registry.bindings is not state.bindings
        or registry.input_contracts is not state.input_contracts
        or registry.evaluator_records is not state.evaluator_records
    ):
        return False
    current = _snapshot_detector_registry_authority(registry)
    if current is None or len(current.records) != len(state.records):
        return False
    for actual, retained in zip(current.records, state.records):
        if (
            actual[0] is not retained[0]
            or actual[3] is not retained[3]
            or actual[4] is not retained[4]
            or actual[7] is not retained[7]
            or actual[10] is not retained[10]
            or actual[11] is not retained[11]
            or actual[13] is not retained[13]
            or actual[14] is not retained[14]
            or not _exact_state_equal(actual[1:3], retained[1:3])
            or not _exact_state_equal(actual[5:7], retained[5:7])
            or not _exact_state_equal(actual[8:10], retained[8:10])
            or not json_values_equal(actual[12], retained[12])
            or not _exact_state_equal(actual[15], retained[15])
        ):
            return False
    return True


def _final_run_identity_check(plan: ProcedureRunPlan) -> bool:
    """Recheck callback-free carrier identities after every semantic traversal."""
    if not _final_run_mapping_check(plan):
        return False
    if (
        plan.attention is not plan._attention_identity
        or plan.operation_registry is not plan._operation_registry_state.registry
        or plan.operation_registry.declarations
        is not plan._operation_registry_state.declarations
        or plan.operation_registry.bindings
        is not plan._operation_registry_state.bindings
        or plan.operation_registry.contracts
        is not plan._operation_registry_state.contracts
        or not _final_operation_registry_record_check(plan._operation_registry_state)
        or not _detector_registry_authority_is_current(
            plan.attention.detector_registry, plan._detector_registry_state
        )
        or plan.procedure is not plan._procedure_semantics.declaration
        or not _exact_state_equal(
            _declaration_scalar_state(plan.procedure),
            plan._procedure_semantics.scalar_state,
        )
        or plan.parameters is not plan._parameters_identity
        or plan.actions is not plan._actions_identity
        or plan.requirements is not plan._requirements_identity
        or plan.executable_requirements is not plan._executable_identity
        or plan.pre_action_requirements is not plan._pre_action_identity
        or plan.evaluator_backed_pre_action_requirements
        is not plan._evaluator_backed_identity
        or plan.procedure_precondition_requirements
        is not plan._procedure_precondition_identity
        or plan.evaluator_backed_procedure_precondition_requirements
        is not plan._evaluator_backed_procedure_precondition_identity
        or plan.lifecycle_evaluations is not plan._lifecycle_evaluations_identity
    ):
        return False
    for action, action_state in zip(plan.actions, plan._action_semantics):
        if (
            action is not action_state.action
            or action.node is not action_state.node
            or action.operation is not action_state.operation
            or action.contract is not action_state.contract
            or action.input_data is not action_state.input_data
            or not _exact_state_equal(
                _node_scalar_state(action.node), action_state.node_state
            )
            or not _exact_state_equal(
                _declaration_scalar_state(action.contract),
                action_state.contract_state.scalar_state,
            )
        ):
            return False
    for requirement, requirement_state in zip(
        plan.requirements, plan._requirement_semantics
    ):
        if (
            requirement is not requirement_state.requirement
            or requirement.key is not requirement_state.key
            or requirement.obligation is not requirement_state.obligation
            or requirement.evaluator is not requirement_state.evaluator
            or requirement.enforcement is not requirement_state.enforcement
            or requirement_state.obligation.predicate is not requirement_state.predicate
            or requirement_state.predicate.expression
            is not requirement_state.expression
            or not _exact_state_equal(
                _current_obligation_scalar_state(requirement_state.obligation),
                requirement_state.obligation_state,
            )
            or not all(
                _exact_state_equal(tuple(current), retained)
                for current, retained in zip(
                    requirement_state.obligation_sequences,
                    requirement_state.obligation_sequence_values,
                )
            )
            or not _exact_state_equal(
                (
                    requirement_state.predicate.id,
                    requirement_state.predicate.predicate_class,
                ),
                requirement_state.predicate_state,
            )
            or not _exact_state_equal(
                (
                    (
                        requirement_state.predicate.evaluator.id,
                        requirement_state.predicate.evaluator.version,
                    )
                    if requirement_state.predicate.evaluator is not None
                    else None
                ),
                requirement_state.evaluator_reference_state,
            )
            or not _exact_state_equal(
                _evaluator_contract_state(requirement.evaluator),
                requirement_state.evaluator_state,
            )
            or (
                requirement_state.evaluator_declaration_state is not None
                and requirement.evaluator is not None
                and not _exact_state_equal(
                    _declaration_scalar_state(requirement.evaluator),
                    requirement_state.evaluator_declaration_state.scalar_state,
                )
            )
        ):
            return False
    for packet_state in plan._packet_semantics:
        entry = packet_state.entry
        if type(entry) is DeliberativeAttentionEntry:
            if entry.obligation is not packet_state.obligation:
                return False
        elif type(entry) is AssistedAttentionEntry:
            if (
                entry.obligation is not packet_state.obligation
                or entry.invocation is not packet_state.invocation
                or entry.invocation.input_data is not packet_state.input_data
                or not _exact_state_equal(
                    (
                        entry.invocation.evaluator.id,
                        entry.invocation.evaluator.version,
                        entry.invocation.evaluator_input_operation.id,
                        entry.invocation.evaluator_input_operation.version,
                        entry.invocation.input_revision,
                    ),
                    packet_state.invocation_state,
                )
                or not _exact_state_equal(
                    (entry.residual_question,), packet_state.entry_state
                )
            ):
                return False
        elif type(entry) is MechanicalAttentionEntry:
            if (
                entry.key is not packet_state.key
                or entry.invocation is not packet_state.invocation
                or entry.invocation.input_data is not packet_state.input_data
                or entry.evidence_schema is not packet_state.evidence_schema
                or not _exact_state_equal(
                    (
                        entry.invocation.evaluator.id,
                        entry.invocation.evaluator.version,
                        entry.invocation.evaluator_input_operation.id,
                        entry.invocation.evaluator_input_operation.version,
                        entry.invocation.input_revision,
                    ),
                    packet_state.invocation_state,
                )
            ):
                return False
        else:
            return False
        if packet_state.input_contract_state is not None and not _exact_state_equal(
            _declaration_scalar_state(packet_state.input_contract_state.declaration),
            packet_state.input_contract_state.scalar_state,
        ):
            return False
    for item, input_state in zip(plan._evaluation_inputs, plan._evaluation_input_state):
        evaluator = item.predicate.evaluator
        if (
            item is not input_state.item
            or item.source_key is not input_state.source_key
            or not _exact_state_equal(item.procedure, input_state.procedure)
            or item.predicate is not input_state.predicate
            or not _exact_state_equal(
                (item.predicate.id, item.predicate.predicate_class),
                input_state.predicate_state,
            )
            or item.predicate.expression is not input_state.expression
            or evaluator is not input_state.evaluator
            or not _exact_state_equal(
                (evaluator.id, evaluator.version) if evaluator is not None else None,
                input_state.evaluator_state,
            )
            or item.predicate.observes is not input_state.observes
            or not _exact_state_equal(
                tuple(item.predicate.observes), input_state.observes_value
            )
            or item.invocation_input is not input_state.invocation_input
            or item.input_schema is not input_state.input_schema
        ):
            return False
    for lifecycle_item, state in zip(
        plan.lifecycle_evaluations, plan._lifecycle_evaluation_state
    ):
        if (
            lifecycle_item is not state.item
            or lifecycle_item.source_key is not state.source_key
            or lifecycle_item.source_requirement is not state.source_requirement
            or lifecycle_item.source_entry is not state.source_entry
            or lifecycle_item.requirement.evaluator is not lifecycle_item.evaluator
            or _identity_semantic_state(lifecycle_item) != state.detached_state
        ):
            return False
    return True


def _final_run_mapping_check(plan: ProcedureRunPlan) -> bool:
    """Compare live map contents before the callback-free final pass."""
    for packet_state in plan._packet_semantics:
        if packet_state.input_data is not None and not json_values_equal(
            freeze_json(packet_state.input_data), packet_state.input_value
        ):
            return False
        if packet_state.evidence_schema is not None and not json_values_equal(
            freeze_json(packet_state.evidence_schema), packet_state.evidence_value
        ):
            return False
        if packet_state.input_contract_state is not None and not json_values_equal(
            freeze_json(
                _declaration_semantic_value(
                    packet_state.input_contract_state.declaration
                )
            ),
            packet_state.input_contract_state.semantic_value,
        ):
            return False
    for requirement_state in plan._requirement_semantics:
        for current, retained in zip(
            requirement_state.obligation_maps,
            requirement_state.obligation_map_values,
        ):
            if not json_values_equal(freeze_json(current), retained):
                return False
        if not json_values_equal(
            freeze_json(requirement_state.predicate.expression),
            requirement_state.expression_value,
        ):
            return False
        if requirement_state.evidence_schema is not None and not json_values_equal(
            freeze_json(requirement_state.evidence_schema),
            requirement_state.evidence_schema_value,
        ):
            return False
        evaluator_state = requirement_state.evaluator_declaration_state
        if evaluator_state is not None and not json_values_equal(
            freeze_json(_declaration_semantic_value(evaluator_state.declaration)),
            evaluator_state.semantic_value,
        ):
            return False
    if not json_values_equal(
        freeze_json(_declaration_semantic_value(plan.procedure)),
        plan._procedure_semantics.semantic_value,
    ):
        return False
    for action_state in plan._action_semantics:
        if not json_values_equal(
            freeze_json(_declaration_semantic_value(action_state.contract)),
            action_state.contract_state.semantic_value,
        ) or not json_values_equal(
            freeze_json(action_state.input_data), action_state.input_value
        ):
            return False
    return json_values_equal(freeze_json(plan.parameters), plan._parameters_value)


def _final_operation_registry_record_check(
    state: _OperationRegistryAuthorityState,
) -> bool:
    """Recheck retained runner and contract records without mapping traversal."""
    for record in state.records:
        reference = cast(VersionedReference, record[0])
        binding = cast(OperationRunnerBinding, record[3])
        if (
            not _exact_state_equal((reference.id, reference.version), record[1:3])
            or binding.operation is not record[4]
            or not _exact_state_equal(
                (binding.operation.id, binding.operation.version), record[5:7]
            )
            or binding.runner is not record[7]
        ):
            return False
    return True


def _current_obligation_scalar_state(
    obligation: ProcedureObligationSnapshot | OperationObligationSnapshot,
) -> tuple[object, ...]:
    """Project callback-free obligation-context scalars."""
    if isinstance(obligation, ProcedureObligationSnapshot):
        return (
            obligation.purpose,
            obligation.title,
            obligation.rationale,
            obligation.phase,
        )
    assert isinstance(obligation, OperationObligationSnapshot)
    return (
        obligation.procedure_purpose,
        obligation.procedure_title,
        obligation.procedure_rationale,
        obligation.recovery,
    )


def _evaluator_contract_state(
    evaluator: EvaluatorDeclaration | None,
) -> tuple[object, ...] | None:
    """Return the evaluator fields that govern precondition-input planning."""
    if evaluator is None:
        return None
    return (
        evaluator.id,
        evaluator.version,
        evaluator.evaluator_kind,
        evaluator.coverage,
        evaluator.adjudication,
        evaluator.timing,
        evaluator.residual_question,
        evaluator.input_revisions,
        evaluator.failure_behavior,
        evaluator.known_failure_fixtures,
    )


def _freeze_parameters(
    parameters: Mapping[str, object], procedure: ProcedureDeclaration
) -> Mapping[str, JsonValue]:
    try:
        frozen = freeze_json(parameters)
    except Exception as exc:
        _fail(
            ("parameters",),
            f"parameters are not finite JSON: {exception_detail(exc)}",
            cause=exc,
        )
    if not isinstance(frozen, Mapping):
        _fail(("parameters",), "parameters must be a JSON object")
    result = cast(Mapping[str, JsonValue], frozen)
    error = validate_json_instance(
        cast(Mapping[str, object], procedure.parameters), result
    )
    if error is not None:
        _fail(
            ("parameters", *error.absolute_path),
            f"parameters violate the procedure contract: {error.message}",
        )
    return result


def _prepare_action(
    node: ProcedureNode,
    parameters: Mapping[str, JsonValue],
    registry: OperationRunnerRegistry,
    index: int,
) -> PreparedProcedureAction:
    if node.operation not in registry.bindings:
        _fail(("actions", index, "operation"), "operation has no runner binding")
    contract = registry.contracts.get(node.operation)
    if contract is None:
        _fail(("actions", index, "operation"), "operation contract is absent")
    values: dict[str, JsonValue] = {}
    for name, binding in node.bindings.items():
        if isinstance(binding, ParameterBinding):
            if binding.parameter not in parameters:
                _fail(("actions", index, "bindings", name), "bound parameter is absent")
            values[name] = parameters[binding.parameter]
        elif isinstance(binding, LiteralBinding):
            values[name] = binding.value
        else:
            _fail(("actions", index, "bindings", name), "binding kind is invalid")
    frozen = cast(Mapping[str, JsonValue], freeze_json(values))
    error = validate_json_instance(cast(Mapping[str, object], contract.inputs), frozen)
    if error is not None:
        _fail(
            ("actions", index, "input", *error.absolute_path),
            f"bound input violates the operation contract: {error.message}",
        )
    return PreparedProcedureAction(node, node.operation, contract, frozen)


def _belongs_to_procedure(item: CompletionRequirement, identifier: str) -> bool:
    key = item.key
    return (
        isinstance(key, ProcedurePredicateKey) and key.declaration == identifier
    ) or (isinstance(key, OperationPredicateKey) and key.procedure == identifier)


def _is_pre_action(item: CompletionRequirement) -> bool:
    key = item.key
    return isinstance(key, OperationPredicateKey) or (
        isinstance(key, ProcedurePredicateKey)
        and key.phase in {PredicatePhase.PRECONDITION, PredicatePhase.INVARIANT}
    )


def _is_procedure_precondition(item: CompletionRequirement) -> bool:
    key = item.key
    return (
        isinstance(key, ProcedurePredicateKey)
        and key.phase is PredicatePhase.PRECONDITION
    )


def _fail(
    parts: tuple[str | int, ...], message: str, *, cause: Exception | None = None
) -> NoReturn:
    error = ProcedureRunPlanningError(format_document_path(parts), message)
    if cause is not None:
        raise error from cause
    raise error
