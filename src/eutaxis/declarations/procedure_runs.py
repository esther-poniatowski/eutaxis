"""Prepare immutable procedure inputs without executing actions or predicates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import NoReturn, SupportsIndex, cast

from ._runner_support import exception_detail
from .attention import (
    AttentionPlan,
    CompletionRequirement,
    OperationPredicateKey,
    ProcedurePredicateKey,
    _is_issued_attention_plan,
)
from .embedded_schema import validate_json_instance
from .enforcement import PredicatePhase
from .exceptions import ProcedureRunPlanningError
from .models import (
    JsonValue,
    LiteralBinding,
    OperationDeclaration,
    ParameterBinding,
    ProcedureDeclaration,
    ProcedureNode,
    VersionedReference,
    freeze_json,
)
from .operations import (
    OperationRunnerRegistry,
    _is_builder_issued_operation_registry,
)
from .source import format_document_path

_PLAN_ISSUER = object()


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
    actions: tuple[PreparedProcedureAction, ...]
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
    return (
        type(plan) is ProcedureRunPlan
        and getattr(plan, "_issuer", None) is _PLAN_ISSUER
    )


def prepare_procedure_run(
    attention: AttentionPlan,
    procedure_id: str,
    parameters: Mapping[str, object],
    operation_registry: OperationRunnerRegistry,
) -> ProcedureRunPlan:
    """Validate and freeze one effective procedure's complete action preflight."""
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
        ("actions", actions),
        ("_issuer", _PLAN_ISSUER),
    ):
        object.__setattr__(plan, name, value)
    return plan


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


def _fail(
    parts: tuple[str | int, ...], message: str, *, cause: Exception | None = None
) -> NoReturn:
    error = ProcedureRunPlanningError(format_document_path(parts), message)
    if cause is not None:
        raise error from cause
    raise error
