"""Correlate evaluator inputs with one prepared procedure run."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import NoReturn, Protocol, SupportsIndex, TypeAlias, cast

from ._runner_support import exception_detail, validate_synchronous_runner
from .attention import (
    AssistedAttentionEntry,
    AssistedPacket,
    AttentionPlan,
    CompletionRequirement,
    DeliberationPacket,
    DeliberativeAttentionEntry,
    EvaluatorInput,
    EvaluatorInvocation,
    MechanicalPacket,
    MechanicalAttentionEntry,
    OperationObligationSnapshot,
    OperationPredicateKey,
    ProcedureObligationSnapshot,
    ProcedurePredicateKey,
    RuleCriterionKey,
    RuleObligationSnapshot,
    _is_issued_attention_plan,
    _validate_assurance,
)
from .embedded_schema import validate_json_instance
from .enforcement import EnforcementClass, PredicatePhase, derive_enforcement_class
from .exceptions import AttentionPlanningError, ProcedureEvaluationPlanningError
from .execution import KnownFailureAssurance
from .facets import validate_applicability_expression
from .models import (
    Criterion,
    DeclarationKind,
    JsonValue,
    EvaluatorDeclaration,
    OperationDeclaration,
    Predicate,
    VersionedReference,
    freeze_json,
    json_values_equal,
)
from .operations import OperationRunnerBinding, _is_builder_issued_operation_registry
from .registry import DeclarationRegistry
from .resolution import _is_issued_resolution_result
from .runners import (
    CheckerRunnerBinding,
    CheckerRunnerRegistry,
    DetectorRunnerBinding,
    DetectorRunnerRegistry,
    _is_builder_issued_checker_registry,
    _is_builder_issued_detector_registry,
)
from .schema import validate_declaration_definition
from .procedure_runs import (
    PreparedProcedureAction,
    ProcedureRunPlan,
    _is_issued_procedure_run_plan,
    _prepare_action,
    _procedure_evaluation_material,
)
from .source import format_document_path

_PLAN_ISSUER = object()
_PROVIDER_SNAPSHOT_ISSUER = object()
_PATH_VALUE_TYPE = type(Path())


class _ProviderSnapshot(
    Mapping[ProcedurePredicateKey, "ProcedureEvaluatorInputProvider"]
):
    """Retain one privately issued immutable provider mapping."""

    __slots__ = ("_issuer", "_values")
    _issuer: object
    _values: Mapping[ProcedurePredicateKey, "ProcedureEvaluatorInputProvider"]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("provider snapshots must be issued by planning")

    def __getitem__(
        self, key: ProcedurePredicateKey
    ) -> ProcedureEvaluatorInputProvider:
        return self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


@dataclass(frozen=True, init=False)
class ProcedureEvaluatorInputRequest:
    """Expose the run data needed to derive one evaluator input."""

    key: ProcedurePredicateKey
    procedure: str
    phase: PredicatePhase
    occurrence: int
    parameters: Mapping[str, JsonValue]
    predicate: Predicate

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "ProcedureEvaluatorInputRequest instances must be issued by planning"
        )


class ProcedureEvaluatorInputProvider(Protocol):
    """Derive one evaluator input from an exact prepared procedure run."""

    def __call__(self, request: ProcedureEvaluatorInputRequest, /) -> EvaluatorInput:
        """Return the evaluator input independently derived for ``request``."""


@dataclass(frozen=True)
class _EvaluationSpec:
    """Retain the immutable values consumed at one evaluation boundary."""

    procedure: str
    predicate: Predicate
    invocation_input: Mapping[str, JsonValue] | None
    input_schema: Mapping[str, JsonValue] | None


@dataclass(frozen=True)
class ManualPreconditionEvaluation:
    """Retain one manual precondition and its exact attention entry."""

    requirement: CompletionRequirement
    entry: DeliberativeAttentionEntry


@dataclass(frozen=True)
class AssistedPreconditionEvaluation:
    """Retain one assisted precondition and its run-checked invocation."""

    requirement: CompletionRequirement
    entry: AssistedAttentionEntry
    evaluator_input: EvaluatorInput
    provider: ProcedureEvaluatorInputProvider


@dataclass(frozen=True)
class MechanicalPreconditionEvaluation:
    """Retain one mechanical precondition and its run-checked invocation."""

    requirement: CompletionRequirement
    entry: MechanicalAttentionEntry
    evaluator_input: EvaluatorInput
    provider: ProcedureEvaluatorInputProvider


ProcedurePreconditionEvaluation: TypeAlias = (
    ManualPreconditionEvaluation
    | AssistedPreconditionEvaluation
    | MechanicalPreconditionEvaluation
)


@dataclass(frozen=True, init=False, eq=False)
class ProcedurePreconditionEvaluationPlan:
    """Process-local run authority for evaluator-backed preconditions."""

    run: ProcedureRunPlan
    parameters: Mapping[str, JsonValue]
    phase: PredicatePhase
    occurrence: int
    records: tuple[ProcedurePreconditionEvaluation, ...]
    manual: tuple[ManualPreconditionEvaluation, ...]
    assisted: tuple[AssistedPreconditionEvaluation, ...]
    mechanical: tuple[MechanicalPreconditionEvaluation, ...]
    providers: Mapping[ProcedurePredicateKey, ProcedureEvaluatorInputProvider]
    _registry_authorities: tuple[object, ...]
    _registry_maps: tuple[object, ...]
    _registry_contents: tuple[object, ...]
    _invocation_state: tuple[object, ...]
    _predicate_state: tuple[object, ...]
    _evaluator_input_state: tuple[object, ...]
    _run_graph: tuple[object, ...]
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "ProcedurePreconditionEvaluationPlan instances must be issued by planning"
        )

    def __copy__(self) -> NoReturn:
        raise TypeError(
            "ProcedurePreconditionEvaluationPlan instances cannot be copied"
        )

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError(
            "ProcedurePreconditionEvaluationPlan instances cannot be copied"
        )

    def __reduce__(self) -> NoReturn:
        raise TypeError(
            "ProcedurePreconditionEvaluationPlan instances cannot be serialized"
        )

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError(
            "ProcedurePreconditionEvaluationPlan instances cannot be serialized"
        )


def plan_procedure_precondition_evaluations(
    run: ProcedureRunPlan,
    providers: Mapping[ProcedurePredicateKey, ProcedureEvaluatorInputProvider],
) -> ProcedurePreconditionEvaluationPlan:
    """Correlate every evaluator-backed precondition with the prepared run."""
    if not _is_issued_procedure_run_plan(run):
        _fail(("run",), "procedure run plan was not issued by preflight")
    attention = run.attention
    if not _is_issued_attention_plan(attention):
        _fail(("run", "attention"), "attention plan was not issued by planning")
    if not _is_issued_resolution_result(attention.resolution):
        _fail(("run", "attention", "resolution"), "resolution authority changed")
    if type(run.parameters) is not MappingProxyType:
        _fail(("run", "parameters"), "run parameters are not an issued immutable map")
    _validate_packet_container_shapes(attention)
    _validate_registry_path_shapes(attention)
    _validate_pregraph_contracts(run)
    run_graph = _capture_run_graph(run, ("run",))
    provider_snapshot = _snapshot_providers(providers)
    _require_run_graph(run, run_graph, ("providers", "mapping-side-effects"))
    (
        requirements,
        registry_authorities,
        registry_maps,
        registry_contents,
        parameters,
        packet_entries,
        invocation_state,
        predicate_state,
        evaluation_specs,
    ) = _prepare_initial_state(run, provider_snapshot)
    _require_run_graph(run, run_graph, ("run",))

    records: list[ProcedurePreconditionEvaluation] = []
    for index, (requirement, specification) in enumerate(
        zip(requirements, evaluation_specs)
    ):
        key = cast(ProcedurePredicateKey, requirement.key)
        enforcement = requirement.enforcement
        if enforcement is EnforcementClass.DELIBERATIVE:
            records.append(
                ManualPreconditionEvaluation(
                    requirement, cast(DeliberativeAttentionEntry, packet_entries[key])
                )
            )
            continue
        provider = provider_snapshot[key]
        entry = packet_entries[key]
        invocation = _entry_invocation(entry, enforcement, index)
        invocation_snapshot = _invocation_fields(invocation, index)
        request = _issue_request(parameters, requirement, specification)
        _revalidate_after_provider(
            run,
            parameters,
            requirements,
            provider_snapshot,
            registry_authorities,
            registry_maps,
            registry_contents,
            invocation_state,
            predicate_state,
            run_graph,
        )
        try:
            returned = provider(request)
        except Exception as exc:
            _fail(
                ("providers", index),
                f"input provider raised {exception_detail(exc)}",
                cause=exc,
            )
        current_entries = _revalidate_after_provider(
            run,
            parameters,
            requirements,
            provider_snapshot,
            registry_authorities,
            registry_maps,
            registry_contents,
            invocation_state,
            predicate_state,
            run_graph,
        )
        if current_entries.get(key) is not entry:
            _fail(("requirements", index), "provider replaced the packet entry")
        if _entry_invocation(entry, enforcement, index) is not invocation:
            _fail(("requirements", index), "provider replaced the packet invocation")
        revision, immutable = _materialize_provider_input(
            returned,
            invocation,
            invocation_snapshot,
            specification,
            index,
        )
        _revalidate_after_provider(
            run,
            parameters,
            requirements,
            provider_snapshot,
            registry_authorities,
            registry_maps,
            registry_contents,
            invocation_state,
            predicate_state,
            run_graph,
        )
        _validate_provider_input(
            revision,
            immutable,
            invocation,
            invocation_snapshot,
            specification,
            index,
        )
        _revalidate_after_provider(
            run,
            parameters,
            requirements,
            provider_snapshot,
            registry_authorities,
            registry_maps,
            registry_contents,
            invocation_state,
            predicate_state,
            run_graph,
        )
        if enforcement is EnforcementClass.ASSISTED:
            records.append(
                AssistedPreconditionEvaluation(
                    requirement,
                    cast(AssistedAttentionEntry, entry),
                    EvaluatorInput(revision, immutable),
                    provider,
                )
            )
        else:
            records.append(
                MechanicalPreconditionEvaluation(
                    requirement,
                    cast(MechanicalAttentionEntry, entry),
                    EvaluatorInput(revision, immutable),
                    provider,
                )
            )
    plan = _issue_plan(
        run,
        parameters,
        tuple(records),
        provider_snapshot,
        registry_authorities,
        registry_maps,
        registry_contents,
        invocation_state,
        predicate_state,
        run_graph,
    )
    if not _is_issued_procedure_precondition_evaluation_plan(plan):
        _fail(("plan",), "candidate was invalidated during provider execution")
    return plan


def _capture_run_graph(
    run: ProcedureRunPlan, location: tuple[str | int, ...]
) -> tuple[object, ...]:
    try:
        return tuple(_identity_projection(run, set()))
    except Exception as exc:
        _fail(
            location,
            f"run authority graph cannot be read: {exception_detail(exc)}",
            cause=exc,
        )


def _require_run_graph(
    run: ProcedureRunPlan,
    expected: tuple[object, ...],
    location: tuple[str | int, ...],
) -> None:
    current = _capture_run_graph(run, location)
    if not _same_identity_projection(current, expected):
        _fail(location, "run authority graph changed during public traversal")


def _validate_packet_container_shapes(attention: AttentionPlan) -> None:
    for name, expected in (
        ("deliberative", DeliberationPacket),
        ("assisted", AssistedPacket),
        ("mechanical", MechanicalPacket),
    ):
        packet = getattr(attention, name)
        if type(packet) is not expected:
            _fail(("attention", name), f"{name} packet is invalid")
        if type(packet.entries) is not tuple:
            _fail(("attention", name, "entries"), "packet entries must be a tuple")


def _validate_registry_path_shapes(attention: AttentionPlan) -> None:
    paths = attention.resolution.registry.paths
    if type(paths) is not tuple:
        _fail(("run", "declaration-registry", "paths"), "paths must be a tuple")
    for index, path in enumerate(paths):
        if not isinstance(path, Path):
            _fail(
                ("run", "declaration-registry", "paths", index),
                "registry path is invalid",
            )


def _validate_pregraph_contracts(run: ProcedureRunPlan) -> None:
    requirements = object.__getattribute__(run, "requirements")
    if type(requirements) is not tuple:
        _fail(("run", "requirements"), "run requirements must be a tuple")
    for index, requirement in enumerate(requirements):
        if type(requirement) is not CompletionRequirement:
            continue
        try:
            key = object.__getattribute__(requirement, "key")
            evaluator = object.__getattribute__(requirement, "evaluator")
            enforcement = object.__getattribute__(requirement, "enforcement")
        except AttributeError:
            continue
        if type(key) is not ProcedurePredicateKey:
            continue
        try:
            phase = object.__getattribute__(key, "phase")
        except AttributeError:
            continue
        if phase is not PredicatePhase.PRECONDITION:
            continue
        if evaluator is None:
            continue
        try:
            timing = object.__getattribute__(evaluator, "timing")
        except AttributeError:
            continue
        if type(timing) is not str or timing != "pre-action":
            _fail(
                ("requirements", index, "evaluator", "timing"),
                "evaluator timing must be pre-action",
            )
        if enforcement is not EnforcementClass.ASSISTED:
            continue
        try:
            expected = object.__getattribute__(evaluator, "residual_question")
        except AttributeError:
            continue
        if type(expected) is not str:
            _fail(("requirements", index), "residual question differs")

    entries = object.__getattribute__(run.attention.assisted, "entries")
    if type(entries) is not tuple:
        _fail(("attention", "assisted", "entries"), "packet entries must be a tuple")
    for index, entry in enumerate(entries):
        if type(entry) is not AssistedAttentionEntry:
            continue
        try:
            obligation = object.__getattribute__(entry, "obligation")
            residual = object.__getattribute__(entry, "residual_question")
        except AttributeError:
            continue
        if type(obligation) is not ProcedureObligationSnapshot:
            continue
        key = object.__getattribute__(obligation, "key")
        if type(key) is not ProcedurePredicateKey:
            continue
        try:
            phase = object.__getattribute__(key, "phase")
        except AttributeError:
            continue
        if phase is not PredicatePhase.PRECONDITION:
            continue
        if type(residual) is not str:
            _fail(("requirements", index), "residual question differs")


def _identity_projection(value: object, active: set[int]) -> list[object]:
    result: list[object] = [type(value), value]
    value_type = type(value)
    value_mro = cast(
        tuple[type[object], ...], type.__getattribute__(value_type, "__mro__")
    )
    value_module = cast(str, type.__getattribute__(value_type, "__module__"))
    value_qualname = cast(str, type.__getattribute__(value_type, "__qualname__"))
    if value_type in {str, bytes, int, float, bool, type(None)}:
        return result
    if Enum in value_mro:
        if not _is_loaded_declaration_type(value_type, value_module, value_qualname):
            raise TypeError("run authority graph contains an untrusted enumeration")
        return result
    if any(base in value_mro[1:] for base in (str, bytes, int, float, bool)):
        raise TypeError("run authority graph contains an untrusted scalar")
    if (
        (dict in value_mro or Mapping in value_mro)
        and value_type is not MappingProxyType
        and value_type is not KnownFailureAssurance
    ):
        raise TypeError(
            "run authority graph contains an untrusted mapping of type "
            f"{value_module}.{value_qualname}"
        )
    if any(base in value_mro[1:] for base in (tuple, frozenset)) and value_type not in {
        tuple,
        frozenset,
    }:
        raise TypeError("run authority graph contains an untrusted sequence")
    if list in value_mro or set in value_mro:
        raise TypeError("run authority graph contains a mutable sequence")
    if callable(value):
        return result
    try:
        dataclass_fields = type.__getattribute__(value_type, "__dataclass_fields__")
    except AttributeError:
        dataclass_fields = None
    if dataclass_fields is not None and (
        type(dataclass_fields) is not dict
        or not _is_loaded_declaration_type(value_type, value_module, value_qualname)
        or type.__getattribute__(value_type, "__getattribute__")
        is not object.__getattribute__
    ):
        raise TypeError("run authority graph contains an untrusted dataclass")
    field_names = (
        tuple(field.name for field in dataclass_fields.values())
        if type(dataclass_fields) is dict
        else ()
    )
    if (
        not field_names
        and value_type not in {object, MappingProxyType, tuple, frozenset}
        and value_type is not _PATH_VALUE_TYPE
    ):
        raise TypeError(
            "run authority graph contains an untrusted value of type "
            f"{value_module}.{value_qualname}"
        )
    identity = id(value)
    if identity in active:
        return result
    active.add(identity)
    try:
        if field_names:
            for field_name in field_names:
                result.append(field_name)
                result.extend(
                    _identity_projection(
                        object.__getattribute__(value, field_name), active
                    )
                )
        elif type(value) in {tuple, frozenset}:
            for item in cast(tuple[object, ...] | frozenset[object], value):
                result.extend(_identity_projection(item, active))
    finally:
        active.remove(identity)
    return result


def _is_loaded_declaration_type(
    value_type: type[object], module_name: str, qualname: str
) -> bool:
    if not module_name.startswith("eutaxis.declarations.") or "." in qualname:
        return False
    module = sys.modules.get(module_name)
    return module is not None and vars(module).get(qualname) is value_type


def _prepare_initial_state(
    run: ProcedureRunPlan,
    providers: Mapping[ProcedurePredicateKey, ProcedureEvaluatorInputProvider],
) -> tuple[
    tuple[CompletionRequirement, ...],
    tuple[object, ...],
    tuple[object, ...],
    tuple[object, ...],
    Mapping[str, JsonValue],
    dict[ProcedurePredicateKey, object],
    tuple[object, ...],
    tuple[object, ...],
    tuple[_EvaluationSpec, ...],
]:
    try:
        requirements = _requirements(run)
        registry_authorities, registry_maps, registry_contents = (
            _capture_registry_state(run, validate_runners=True)
        )
        parameters, _ = _procedure_evaluation_material(run)
        expected_provider_keys = tuple(
            cast(ProcedurePredicateKey, item.key)
            for item in requirements
            if item.enforcement
            in {EnforcementClass.ASSISTED, EnforcementClass.MECHANICAL}
        )
        _require_exact_providers(providers, expected_provider_keys)
        packet_entries = _packet_entries(run.attention)
        _validate_static_contracts(run, requirements, providers, packet_entries)
        invocation_state = _capture_invocation_state(run, requirements, packet_entries)
        predicate_state = _capture_predicate_state(requirements)
        evaluation_specs = _build_evaluation_specs(
            run, requirements, invocation_state, predicate_state
        )
        if any(
            item.enforcement is EnforcementClass.MECHANICAL for item in requirements
        ):
            _revalidate_assurance(run.attention)
    except ProcedureEvaluationPlanningError:
        raise
    except Exception as exc:
        _fail(
            ("providers", "mapping-side-effects"),
            f"provider mapping invalidated retained authority: {exception_detail(exc)}",
            cause=exc,
        )
    return (
        requirements,
        registry_authorities,
        registry_maps,
        registry_contents,
        parameters,
        packet_entries,
        invocation_state,
        predicate_state,
        evaluation_specs,
    )


def _revalidate_after_provider(
    run: ProcedureRunPlan,
    parameters: Mapping[str, JsonValue],
    requirements: tuple[CompletionRequirement, ...],
    providers: Mapping[ProcedurePredicateKey, ProcedureEvaluatorInputProvider],
    registry_authorities: tuple[object, ...],
    registry_maps: tuple[object, ...],
    registry_contents: tuple[object, ...],
    invocation_state: tuple[object, ...],
    predicate_state: tuple[object, ...],
    run_graph: tuple[object, ...],
) -> dict[ProcedurePredicateKey, object]:
    try:
        _require_run_graph(run, run_graph, ("providers", "side-effects"))
        current_authorities, current_maps, current_contents = _capture_registry_state(
            run
        )
        if not _same_identity_projection(current_authorities, registry_authorities):
            _fail(("run", "registries"), "provider changed registry authorities")
        if not _same_identity_projection(current_maps, registry_maps):
            _fail(("run", "registries"), "provider changed registry mappings")
        if not _same_identity_projection(current_contents, registry_contents):
            _fail(("run", "registries"), "provider changed registry contents")
        current_requirements = _requirements(run)
        if not _same_identity_projection(current_requirements, requirements):
            _fail(("run", "requirements"), "provider changed canonical requirements")
        current_parameters = _snapshot_run_parameters(run)
        if not json_values_equal(current_parameters, parameters):
            _fail(("run", "parameters"), "provider changed procedure parameters")
        entries = _packet_entries(run.attention)
        _validate_static_contracts(run, requirements, providers, entries)
        if not _same_semantic_state(
            _capture_invocation_state(run, requirements, entries), invocation_state
        ):
            _fail(("run", "attention"), "provider changed invocation state")
        if not _same_semantic_state(
            _capture_predicate_state(requirements), predicate_state
        ):
            _fail(("run", "attention"), "provider changed predicate state")
        if any(
            item.enforcement is EnforcementClass.MECHANICAL for item in requirements
        ):
            _revalidate_assurance(run.attention)
        _require_run_graph(run, run_graph, ("providers", "side-effects"))
        return entries
    except ProcedureEvaluationPlanningError:
        raise
    except Exception as exc:
        _fail(
            ("providers", "side-effects"),
            f"provider invalidated retained authority: {exception_detail(exc)}",
            cause=exc,
        )


def _entry_invocation(
    entry: object, enforcement: EnforcementClass | None, index: int
) -> EvaluatorInvocation:
    if enforcement is EnforcementClass.ASSISTED:
        if type(entry) is not AssistedAttentionEntry:
            _fail(("requirements", index), "assisted packet entry kind differs")
    elif enforcement is EnforcementClass.MECHANICAL:
        if type(entry) is not MechanicalAttentionEntry:
            _fail(("requirements", index), "mechanical packet entry kind differs")
    else:
        _fail(("requirements", index), "runnable enforcement class differs")
    invocation = _packet_field(entry, "invocation", ("requirements", index, "entry"))
    if type(invocation) is not EvaluatorInvocation:
        _fail(("requirements", index, "entry", "invocation"), "invocation is invalid")
    return invocation


def _capture_invocation_state(
    run: ProcedureRunPlan,
    requirements: tuple[CompletionRequirement, ...],
    entries: Mapping[ProcedurePredicateKey, object],
) -> tuple[object, ...]:
    state: list[object] = []
    for index, requirement in enumerate(requirements):
        enforcement = requirement.enforcement
        if enforcement not in {EnforcementClass.ASSISTED, EnforcementClass.MECHANICAL}:
            continue
        key = cast(ProcedurePredicateKey, requirement.key)
        entry = entries[key]
        invocation = _entry_invocation(entry, enforcement, index)
        invocation_fields = _invocation_fields(invocation, index)
        input_snapshot = _freeze_mapping_snapshot(
            invocation_fields[3], ("requirements", index, "invocation", "input")
        )
        contract = _input_contract(run, invocation_fields[1])
        contract_inputs = contract.inputs
        contract_snapshot = _freeze_mapping_snapshot(
            contract_inputs, ("requirements", index, "invocation", "contract")
        )
        state.append(
            (
                (
                    key,
                    entry,
                    invocation,
                    *invocation_fields,
                    contract,
                    contract_inputs,
                ),
                (input_snapshot, contract_snapshot),
            )
        )
    return tuple(state)


def _capture_predicate_state(
    requirements: tuple[CompletionRequirement, ...],
) -> tuple[object, ...]:
    state: list[object] = []
    for index, requirement in enumerate(requirements):
        key = requirement.key
        obligation = requirement.obligation
        if (
            type(key) is not ProcedurePredicateKey
            or type(obligation) is not ProcedureObligationSnapshot
        ):
            _fail(("requirements", index), "procedure requirement correlation differs")
        predicate = _packet_field(
            obligation, "predicate", ("requirements", index, "obligation")
        )
        if type(predicate) is not Predicate:
            _fail(("requirements", index, "predicate"), "predicate is invalid")
        try:
            identifier = predicate.id
            predicate_class = predicate.predicate_class
            expression = predicate.expression
            evaluator = predicate.evaluator
            observes = predicate.observes
        except Exception as exc:
            _fail(
                ("requirements", index, "predicate"),
                f"predicate is incomplete: {exception_detail(exc)}",
                cause=exc,
            )
        if (
            type(identifier) is not str
            or type(predicate_class) is not str
            or type(expression) is not MappingProxyType
            or type(observes) is not tuple
        ):
            _fail(("requirements", index, "predicate"), "predicate fields are invalid")
        expression_snapshot = _freeze_mapping_snapshot(
            expression, ("requirements", index, "predicate", "expression")
        )
        evaluator_declaration = requirement.evaluator
        if evaluator_declaration is None:
            _fail(("requirements", index, "evaluator"), "evaluator is absent")
        evidence_schema = evaluator_declaration.evidence_schema
        evidence_snapshot = _freeze_mapping_snapshot(
            evidence_schema,
            ("requirements", index, "evaluator", "evidence-schema"),
        )
        state.append(
            (
                (
                    key,
                    key.declaration,
                    key.phase,
                    key.predicate,
                    predicate,
                    identifier,
                    predicate_class,
                    expression,
                    evaluator,
                    observes,
                    *observes,
                    evaluator_declaration,
                    evidence_schema,
                ),
                (expression_snapshot, evidence_snapshot),
            )
        )
    return tuple(state)


def _freeze_mapping_snapshot(
    value: object, location: tuple[str | int, ...]
) -> Mapping[str, JsonValue]:
    try:
        frozen = freeze_json(value)
    except Exception as exc:
        _fail(
            location,
            f"mapping content cannot be frozen: {exception_detail(exc)}",
            cause=exc,
        )
    if type(frozen) is not MappingProxyType:
        _fail(location, "mapping content must be a JSON object")
    return cast(Mapping[str, JsonValue], frozen)


def _same_semantic_state(first: tuple[object, ...], second: tuple[object, ...]) -> bool:
    if len(first) != len(second):
        return False
    for actual_record, expected_record in zip(first, second):
        if type(actual_record) is not tuple or type(expected_record) is not tuple:
            return False
        actual_identity, actual_json = actual_record
        expected_identity, expected_json = expected_record
        if (
            type(actual_identity) is not tuple
            or type(expected_identity) is not tuple
            or not _same_identity_projection(actual_identity, expected_identity)
            or type(actual_json) is not tuple
            or type(expected_json) is not tuple
            or len(actual_json) != len(expected_json)
        ):
            return False
        if not all(
            json_values_equal(actual, expected)
            for actual, expected in zip(actual_json, expected_json)
        ):
            return False
    return True


def _build_evaluation_specs(
    run: ProcedureRunPlan,
    requirements: tuple[CompletionRequirement, ...],
    invocation_state: tuple[object, ...],
    predicate_state: tuple[object, ...],
) -> tuple[_EvaluationSpec, ...]:
    try:
        _, authority_inputs = _procedure_evaluation_material(run)
    except Exception as exc:
        _fail(
            ("run", "evaluation-inputs"),
            f"detached evaluation inputs are unavailable: {exception_detail(exc)}",
            cause=exc,
        )
    procedure = run.procedure.id
    if (
        type(procedure) is not str
        or len(predicate_state) != len(requirements)
        or len(authority_inputs) != len(requirements)
    ):
        _fail(("run", "procedure"), "procedure evaluation specification is invalid")
    specifications: list[_EvaluationSpec] = []
    for index, (requirement, retained) in enumerate(
        zip(requirements, authority_inputs)
    ):
        if requirement.key is not retained.source_key:
            _fail(("requirements", index), "detached requirement key differs")
        detached_predicate = retained.predicate
        expression_error = validate_declaration_definition(
            "applicability", detached_predicate.expression
        )
        if expression_error is not None:
            _fail(
                (
                    "requirements",
                    index,
                    "predicate",
                    "expression",
                    *expression_error.absolute_path,
                ),
                "retained predicate expression violates the declaration contract: "
                f"{expression_error.message}",
            )
        facet_violation = validate_applicability_expression(
            cast(Mapping[str, object], detached_predicate.expression),
            run.attention.resolution.registry.facet_registry,
        )
        if facet_violation is not None:
            _fail(
                (
                    "requirements",
                    index,
                    "predicate",
                    "expression",
                    *facet_violation.path,
                ),
                facet_violation.message,
            )
        invocation_input = retained.invocation_input
        input_schema = retained.input_schema
        if requirement.enforcement in {
            EnforcementClass.ASSISTED,
            EnforcementClass.MECHANICAL,
        }:
            if invocation_input is None or input_schema is None:
                _fail(("requirements", index), "invocation snapshot is absent")
            schema_error = validate_declaration_definition(
                "closed-object-schema", input_schema
            )
            if schema_error is not None:
                _fail(
                    (
                        "requirements",
                        index,
                        "invocation",
                        "contract",
                        *schema_error.absolute_path,
                    ),
                    "retained operation input schema violates the declaration "
                    f"contract: {schema_error.message}",
                )
            error = validate_json_instance(
                cast(Mapping[str, object], input_schema), invocation_input
            )
            if error is not None:
                _fail(
                    (
                        "requirements",
                        index,
                        "invocation",
                        "input",
                        *error.absolute_path,
                    ),
                    "retained invocation input violates its retained operation "
                    f"contract: {error.message}",
                )
        specifications.append(
            _EvaluationSpec(
                retained.procedure,
                detached_predicate,
                invocation_input,
                input_schema,
            )
        )
    return tuple(specifications)


def _requirements(run: ProcedureRunPlan) -> tuple[CompletionRequirement, ...]:
    attention = run.attention
    registry = attention.resolution.registry
    if run.operation_registry.declarations is not registry:
        _fail(("run", "operation-registry"), "run uses another declaration registry")
    procedure_record = registry.records.get(run.procedure.id)
    if procedure_record is None or procedure_record.declaration is not run.procedure:
        _fail(("run", "procedure"), "run procedure differs from its registry record")
    completion = attention.requirements.completion
    if type(completion) is not tuple:
        _fail(("run", "attention", "requirements"), "completion sequence is invalid")
    expected_items: list[CompletionRequirement] = []
    for index, item in enumerate(completion):
        key, _, _ = _validate_completion_requirement(item, index, registry)
        if _key_belongs_to_procedure(key, run.procedure.id):
            expected_items.append(item)
    expected_run_requirements = tuple(expected_items)
    if type(run.requirements) is not tuple or not _same_identity_projection(
        run.requirements, expected_run_requirements
    ):
        _fail(
            ("run", "requirements"),
            "run requirements differ from canonical attention requirements",
        )
    selected: list[CompletionRequirement] = []
    for index, item in enumerate(expected_run_requirements):
        key, evaluator, _ = _validate_completion_requirement(item, index, registry)
        if (
            evaluator is not None
            and type(key) is ProcedurePredicateKey
            and cast(ProcedurePredicateKey, key).phase is PredicatePhase.PRECONDITION
        ):
            selected.append(item)
    return tuple(selected)


def _key_belongs_to_procedure(key: object, identifier: str) -> bool:
    return (type(key) is ProcedurePredicateKey and key.declaration == identifier) or (
        type(key) is OperationPredicateKey and key.procedure == identifier
    )


def _validate_completion_requirement(
    item: object, index: int, registry: DeclarationRegistry
) -> tuple[object, EvaluatorDeclaration | None, EnforcementClass | None]:
    location = ("run", "attention", "requirements", index)
    if type(item) is not CompletionRequirement:
        _fail(location, "completion requirement carrier is invalid")
    typed = cast(CompletionRequirement, item)
    try:
        key = typed.key
        obligation = typed.obligation
        evaluator = typed.evaluator
        enforcement = typed.enforcement
    except Exception as exc:
        _fail(
            location,
            f"completion requirement is incomplete: {exception_detail(exc)}",
            cause=exc,
        )
    expected_obligation: type[object]
    if type(key) is ProcedurePredicateKey:
        _validate_procedure_key(key, location + ("key",))
        expected_obligation = ProcedureObligationSnapshot
    elif type(key) is OperationPredicateKey:
        _validate_operation_key(key, location + ("key",))
        expected_obligation = OperationObligationSnapshot
    elif type(key) is RuleCriterionKey:
        _validate_rule_key(key, location + ("key",))
        expected_obligation = RuleObligationSnapshot
    else:
        _fail(location + ("key",), "completion requirement key is invalid")
    if type(obligation) is not expected_obligation:
        _fail(location + ("obligation",), "obligation snapshot kind differs")
    obligation_key = _packet_field(obligation, "key", location + ("obligation",))
    if obligation_key is not key:
        _fail(location + ("obligation", "key"), "obligation key identity differs")
    declared_evaluator = _obligation_evaluator_reference(obligation, location)
    if declared_evaluator is None:
        if evaluator is not None or enforcement is not None:
            _fail(location, "evaluator-less requirement retains evaluator authority")
        return key, None, None
    if evaluator is None or type(evaluator) is not EvaluatorDeclaration:
        _fail(location + ("evaluator",), "evaluator contract is invalid")
    family = registry.families.get(declared_evaluator.id)
    if family is None or family.kind is not DeclarationKind.EVALUATOR:
        _fail(location + ("evaluator",), "declared evaluator is unresolved")
    record = family.versions.get(declared_evaluator.version)
    if record is None or record.declaration is not evaluator:
        _fail(location + ("evaluator",), "evaluator is not the canonical declaration")
    try:
        evaluator_reference = VersionedReference(evaluator.id, evaluator.version)
        derived = derive_enforcement_class(evaluator)
    except Exception as exc:
        _fail(
            location + ("evaluator",),
            f"evaluator contract is invalid: {exception_detail(exc)}",
            cause=exc,
        )
    if evaluator_reference != declared_evaluator:
        _fail(location + ("evaluator",), "evaluator reference differs from predicate")
    if enforcement is not derived:
        _fail(location + ("enforcement",), "enforcement class differs from evaluator")
    return key, evaluator, enforcement


def _obligation_evaluator_reference(
    obligation: object, location: tuple[str | int, ...]
) -> VersionedReference | None:
    if type(obligation) is RuleObligationSnapshot:
        subject = _packet_field(obligation, "criterion", location + ("obligation",))
        if type(subject) is not Criterion:
            _fail(location + ("obligation", "criterion"), "criterion is invalid")
    else:
        subject = _packet_field(obligation, "predicate", location + ("obligation",))
        if type(subject) is not Predicate:
            _fail(location + ("obligation", "predicate"), "predicate is invalid")
    reference = _packet_field(subject, "evaluator", location + ("obligation",))
    if reference is None:
        return None
    if (
        type(reference) is not VersionedReference
        or type(reference.id) is not str
        or not reference.id
        or type(reference.version) is not int
        or reference.version < 1
    ):
        _fail(location + ("obligation", "evaluator"), "evaluator reference is invalid")
    return reference


def _validate_rule_key(key: RuleCriterionKey, location: tuple[str | int, ...]) -> None:
    try:
        values = (key.declaration, key.criterion)
    except Exception as exc:
        _fail(location, f"rule key is incomplete: {exception_detail(exc)}", cause=exc)
    if any(type(value) is not str or not value for value in values):
        _fail(location, "rule key identifiers must be non-empty text")


def _validate_operation_key(
    key: OperationPredicateKey, location: tuple[str | int, ...]
) -> None:
    try:
        values = (key.procedure, key.action, key.predicate)
        operation = key.subject_operation
    except Exception as exc:
        _fail(
            location,
            f"operation predicate key is incomplete: {exception_detail(exc)}",
            cause=exc,
        )
    if any(type(value) is not str or not value for value in values):
        _fail(location, "operation key identifiers must be non-empty text")
    if (
        type(operation) is not VersionedReference
        or type(operation.id) is not str
        or not operation.id
        or type(operation.version) is not int
        or operation.version < 1
    ):
        _fail(location + ("operation",), "operation reference is invalid")


def _capture_registry_state(
    run: ProcedureRunPlan,
    *,
    validate_runners: bool = False,
) -> tuple[tuple[object, ...], tuple[object, ...], tuple[object, ...]]:
    attention = run.attention
    if not _is_issued_resolution_result(attention.resolution):
        _fail(("run", "attention", "resolution"), "resolution authority changed")
    declarations = attention.resolution.registry
    operation = run.operation_registry
    checker = attention.checker_registry
    detector = attention.detector_registry
    if (
        not _is_builder_issued_operation_registry(operation)
        or operation.declarations is not declarations
    ):
        _fail(("run", "operation-registry"), "operation registry authority differs")
    if checker is not attention.requirements.checker_registry:
        _fail(("run", "checker-registry"), "checker registry identity differs")
    if detector is not attention.requirements.detector_registry:
        _fail(("run", "detector-registry"), "detector registry identity differs")
    if checker is not None and (
        not _is_builder_issued_checker_registry(checker)
        or checker.declarations is not declarations
    ):
        _fail(("run", "checker-registry"), "checker registry authority differs")
    if detector is not None and (
        not _is_builder_issued_detector_registry(detector)
        or detector.declarations is not declarations
    ):
        _fail(("run", "detector-registry"), "detector registry authority differs")
    try:
        declaration_paths = declarations.paths
        facet_registry = declarations.facet_registry
        declaration_records = declarations.records
        declaration_families = declarations.families
        declaration_conflicts = declarations.conflicts
        maps: tuple[object, ...] = (
            declaration_records,
            declaration_families,
            operation.bindings,
            operation.contracts,
            None if checker is None else checker.bindings,
            None if checker is None else checker.input_contracts,
            None if checker is None else checker.evaluator_records,
            None if detector is None else detector.bindings,
            None if detector is None else detector.input_contracts,
            None if detector is None else detector.evaluator_records,
        )
    except Exception as exc:
        _fail(
            ("run", "registries"),
            f"registry mappings cannot be read: {exception_detail(exc)}",
            cause=exc,
        )
    if any(value is not None and type(value) is not MappingProxyType for value in maps):
        _fail(("run", "registries"), "registry mappings are not issued immutable maps")
    if (
        type(declaration_paths) is not tuple
        or type(declaration_conflicts) is not frozenset
    ):
        _fail(
            ("run", "declaration-registry"), "declaration registry fields are invalid"
        )
    contents: list[object] = [
        declarations,
        declaration_paths,
        facet_registry,
        declaration_conflicts,
        *declaration_paths,
    ]
    try:
        for declaration_key, declaration_record in declaration_records.items():
            contents.extend(
                (
                    declaration_key,
                    declaration_record,
                    declaration_record.declaration,
                    declaration_record.source,
                    declaration_record.root,
                    declaration_record.containing_rule_set,
                )
            )
        for family_key, family in declaration_families.items():
            if type(family.versions) is not MappingProxyType:
                _fail(
                    ("run", "declaration-registry"),
                    "declaration family versions are not immutable",
                )
            contents.extend(
                (
                    family_key,
                    family,
                    family.id,
                    family.kind,
                    family.owner,
                    family.versions,
                )
            )
            for family_version, family_record in family.versions.items():
                contents.extend((family_version, family_record))
        for operation_key, operation_binding in operation.bindings.items():
            if (
                type(operation_binding) is not OperationRunnerBinding
                or operation_binding.operation is not operation_key
            ):
                _fail(("run", "operation-registry"), "operation binding differs")
            if validate_runners:
                _validate_registry_runner(operation_binding.runner, "operation")
            contents.extend(
                (
                    operation_key,
                    operation_binding,
                    operation_binding.operation,
                    operation_binding.runner,
                )
            )
        for contract_key, contract in operation.contracts.items():
            contents.extend((contract_key, contract))
        if checker is not None:
            for checker_key, checker_binding in checker.bindings.items():
                if (
                    type(checker_binding) is not CheckerRunnerBinding
                    or checker_binding.evaluator is not checker_key
                ):
                    _fail(("run", "checker-registry"), "checker binding differs")
                if validate_runners:
                    _validate_registry_runner(checker_binding.runner, "checker")
                contents.extend(
                    (
                        checker_key,
                        checker_binding,
                        checker_binding.evaluator,
                        checker_binding.operation,
                        checker_binding.runner,
                    )
                )
            for mapping in (checker.input_contracts, checker.evaluator_records):
                for checker_map_key, checker_value in mapping.items():
                    contents.extend((checker_map_key, checker_value))
        if detector is not None:
            for detector_key, detector_binding in detector.bindings.items():
                if (
                    type(detector_binding) is not DetectorRunnerBinding
                    or detector_binding.evaluator is not detector_key
                ):
                    _fail(("run", "detector-registry"), "detector binding differs")
                if validate_runners:
                    _validate_registry_runner(detector_binding.runner, "detector")
                contents.extend(
                    (
                        detector_key,
                        detector_binding,
                        detector_binding.evaluator,
                        detector_binding.operation,
                        detector_binding.runner,
                    )
                )
            for mapping in (detector.input_contracts, detector.evaluator_records):
                for detector_map_key, detector_value in mapping.items():
                    contents.extend((detector_map_key, detector_value))
    except ProcedureEvaluationPlanningError:
        raise
    except Exception as exc:
        _fail(
            ("run", "registries"),
            f"registry contents cannot be read: {exception_detail(exc)}",
            cause=exc,
        )
    return (operation, checker, detector), maps, tuple(contents)


def _validate_registry_runner(runner: object, registry: str) -> None:
    def make_error(message: str) -> Exception:
        return ProcedureEvaluationPlanningError(
            format_document_path(("run", f"{registry}-registry")), message
        )

    validate_synchronous_runner(runner, make_error)


def _snapshot_run_parameters(run: ProcedureRunPlan) -> Mapping[str, JsonValue]:
    if type(run.parameters) is not MappingProxyType:
        _fail(("run", "parameters"), "run parameters are not an issued immutable map")
    try:
        frozen = freeze_json(run.parameters)
    except Exception as exc:
        _fail(
            ("run", "parameters"),
            f"run parameters are not finite JSON: {exception_detail(exc)}",
            cause=exc,
        )
    if type(frozen) is not MappingProxyType:
        _fail(("run", "parameters"), "run parameters are not a JSON object")
    snapshot = cast(Mapping[str, JsonValue], frozen)
    error = validate_json_instance(
        cast(Mapping[str, object], run.procedure.parameters), snapshot
    )
    if error is not None:
        _fail(
            ("run", "parameters", *error.absolute_path),
            f"run parameters violate the procedure contract: {error.message}",
        )
    try:
        expected_actions = tuple(
            _prepare_action(node, snapshot, run.operation_registry, index)
            for index, node in enumerate(run.procedure.actions)
        )
    except Exception as exc:
        _fail(
            ("run", "actions"),
            f"run actions cannot be reconstructed: {exception_detail(exc)}",
            cause=exc,
        )
    if type(run.actions) is not tuple or len(run.actions) != len(expected_actions):
        _fail(("run", "actions"), "run action sequence differs from preflight")
    for index, (actual, expected) in enumerate(zip(run.actions, expected_actions)):
        if (
            type(actual) is not PreparedProcedureAction
            or actual.node is not expected.node
            or actual.operation is not expected.operation
            or actual.contract is not expected.contract
            or type(actual.input_data) is not MappingProxyType
            or not json_values_equal(actual.input_data, expected.input_data)
        ):
            _fail(("run", "actions", index), "run action differs from its parameters")
    return snapshot


def _snapshot_providers(
    providers: object,
) -> _ProviderSnapshot:
    if not isinstance(providers, Mapping):
        _fail(("providers",), "input providers must be a mapping")
    try:
        pairs = tuple(providers.items())
    except Exception as exc:
        _fail(
            ("providers",),
            f"input providers could not be read: {exception_detail(exc)}",
            cause=exc,
        )
    snapshot: dict[ProcedurePredicateKey, ProcedureEvaluatorInputProvider] = {}
    for index, pair in enumerate(pairs):
        try:
            key, provider = pair
        except Exception as exc:
            _fail(
                ("providers", index),
                f"provider item is not a key-value pair: {exception_detail(exc)}",
                cause=exc,
            )
        _validate_key(key, index)
        typed_key = cast(ProcedurePredicateKey, key)
        if typed_key in snapshot:
            _fail(("providers", index, "key"), "provider key is duplicated")

        _validate_provider(provider, index)
        snapshot[typed_key] = cast(ProcedureEvaluatorInputProvider, provider)
    issued = object.__new__(_ProviderSnapshot)
    object.__setattr__(issued, "_values", MappingProxyType(snapshot))
    object.__setattr__(issued, "_issuer", _PROVIDER_SNAPSHOT_ISSUER)
    return issued


def _validate_provider(provider: object, index: int) -> None:
    def make_error(message: str) -> Exception:
        return ProcedureEvaluationPlanningError(
            format_document_path(("providers", index)), message
        )

    validate_synchronous_runner(provider, make_error)


def _validate_provider_snapshot(providers: object) -> bool:
    if (
        type(providers) is not _ProviderSnapshot
        or getattr(providers, "_issuer", None) is not _PROVIDER_SNAPSHOT_ISSUER
        or type(getattr(providers, "_values", None)) is not MappingProxyType
    ):
        return False
    try:
        for index, (key, _provider) in enumerate(providers.items()):
            _validate_key(key, index)
    except Exception:
        return False
    return True


def _validate_key(key: object, index: int) -> None:
    _validate_procedure_key(key, ("providers", index, "key"))


def _validate_procedure_key(key: object, location: tuple[str | int, ...]) -> None:
    if type(key) is not ProcedurePredicateKey:
        _fail(location, "provider key must identify a procedure predicate")
    typed = cast(ProcedurePredicateKey, key)
    try:
        declaration = typed.declaration
        predicate = typed.predicate
        phase = typed.phase
    except Exception as exc:
        _fail(
            location,
            f"procedure predicate key is incomplete: {exception_detail(exc)}",
            cause=exc,
        )
    for name, value in (
        ("declaration", declaration),
        ("predicate", predicate),
    ):
        if type(value) is not str or not value or any(char.isspace() for char in value):
            _fail(location + (name,), "key identifier must be non-empty text")
    if type(phase) is not PredicatePhase:
        _fail(location + ("phase",), "procedure phase is not admitted")


def _require_exact_providers(
    providers: Mapping[ProcedurePredicateKey, ProcedureEvaluatorInputProvider],
    expected: tuple[ProcedurePredicateKey, ...],
) -> None:
    actual = tuple(providers)
    if len(actual) < len(expected):
        _fail(("providers",), "missing provider for a runnable precondition")
    if len(actual) > len(expected):
        _fail(("providers",), "unexpected provider for a non-runnable precondition")
    for key in expected:
        if not any(candidate is key for candidate in actual):
            _fail(("providers",), "provider key is not the canonical requirement key")
    for key in actual:
        if not any(key is candidate for candidate in expected):
            _fail(("providers",), "unexpected non-canonical provider key")


def _packet_entries(attention: AttentionPlan) -> dict[ProcedurePredicateKey, object]:
    result: dict[ProcedurePredicateKey, object] = {}
    if type(attention.deliberative) is not DeliberationPacket:
        _fail(("attention", "deliberative"), "deliberation packet is invalid")
    manual_entries = _packet_field(
        attention.deliberative, "entries", ("attention", "deliberative")
    )
    if type(manual_entries) is not tuple:
        _fail(
            ("attention", "deliberative", "entries"), "packet entries must be a tuple"
        )
    for index, manual_entry in enumerate(manual_entries):
        if type(manual_entry) is not DeliberativeAttentionEntry:
            _fail(("attention", "deliberative", "entries", index), "entry is invalid")
        obligation = _packet_field(
            manual_entry,
            "obligation",
            ("attention", "deliberative", "entries", index),
        )
        key = _obligation_key(
            obligation, ("attention", "deliberative", "entries", index)
        )
        _collect_packet_entry(result, key, manual_entry, "deliberative", index)

    if type(attention.assisted) is not AssistedPacket:
        _fail(("attention", "assisted"), "assisted packet is invalid")
    assisted_entries = _packet_field(
        attention.assisted, "entries", ("attention", "assisted")
    )
    if type(assisted_entries) is not tuple:
        _fail(("attention", "assisted", "entries"), "packet entries must be a tuple")
    for index, assisted_entry in enumerate(assisted_entries):
        if type(assisted_entry) is not AssistedAttentionEntry:
            _fail(("attention", "assisted", "entries", index), "entry is invalid")
        obligation = _packet_field(
            assisted_entry,
            "obligation",
            ("attention", "assisted", "entries", index),
        )
        key = _obligation_key(obligation, ("attention", "assisted", "entries", index))
        _collect_packet_entry(result, key, assisted_entry, "assisted", index)

    if type(attention.mechanical) is not MechanicalPacket:
        _fail(("attention", "mechanical"), "mechanical packet is invalid")
    mechanical_entries = _packet_field(
        attention.mechanical, "entries", ("attention", "mechanical")
    )
    if type(mechanical_entries) is not tuple:
        _fail(("attention", "mechanical", "entries"), "packet entries must be a tuple")
    for index, mechanical_entry in enumerate(mechanical_entries):
        if type(mechanical_entry) is not MechanicalAttentionEntry:
            _fail(("attention", "mechanical", "entries", index), "entry is invalid")
        key = _packet_field(
            mechanical_entry,
            "key",
            ("attention", "mechanical", "entries", index),
        )
        if type(key) not in {
            RuleCriterionKey,
            ProcedurePredicateKey,
            OperationPredicateKey,
        }:
            _fail(
                ("attention", "mechanical", "entries", index, "key"), "key is invalid"
            )
        _collect_packet_entry(result, key, mechanical_entry, "mechanical", index)
    return result


def _packet_field(value: object, name: str, location: tuple[str | int, ...]) -> object:
    try:
        return getattr(value, name)
    except Exception as exc:
        _fail(
            location + (name,),
            f"packet field cannot be read: {exception_detail(exc)}",
            cause=exc,
        )


def _obligation_key(obligation: object, location: tuple[str | int, ...]) -> object:
    if type(obligation) not in {
        RuleObligationSnapshot,
        ProcedureObligationSnapshot,
        OperationObligationSnapshot,
    }:
        _fail(location + ("obligation",), "obligation snapshot is invalid")
    return _packet_field(obligation, "key", location + ("obligation",))


def _collect_packet_entry(
    result: dict[ProcedurePredicateKey, object],
    key: object,
    entry: object,
    packet: str,
    index: int,
) -> None:
    if type(key) is not ProcedurePredicateKey:
        return
    _validate_procedure_key(key, ("attention", packet, "entries", index, "key"))
    typed = cast(ProcedurePredicateKey, key)
    if typed in result:
        _fail(("attention",), "duplicate procedure predicate packet entry")
    result[typed] = entry


def _validate_static_contracts(
    run: ProcedureRunPlan,
    requirements: tuple[CompletionRequirement, ...],
    providers: Mapping[ProcedurePredicateKey, ProcedureEvaluatorInputProvider],
    entries: Mapping[ProcedurePredicateKey, object],
) -> None:
    for index, requirement in enumerate(requirements):
        key = cast(ProcedurePredicateKey, requirement.key)
        evaluator = requirement.evaluator
        if evaluator is None or requirement.enforcement is None:
            _fail(("requirements", index), "precondition lacks evaluator authority")
        try:
            timing = evaluator.timing
        except Exception as exc:
            _fail(
                ("requirements", index, "evaluator", "timing"),
                f"evaluator timing cannot be read: {exception_detail(exc)}",
                cause=exc,
            )
        if type(timing) is not str or timing != "pre-action":
            _fail(
                ("requirements", index, "evaluator", "timing"),
                "evaluator timing must be pre-action",
            )
        entry = entries.get(key)
        if entry is None:
            _fail(("requirements", index), "matching attention packet entry is absent")
        if requirement.enforcement is EnforcementClass.DELIBERATIVE:
            if type(entry) is not DeliberativeAttentionEntry:
                _fail(("requirements", index), "manual packet entry kind differs")
            manual = cast(DeliberativeAttentionEntry, entry)
            manual_obligation = _packet_field(
                manual, "obligation", ("requirements", index, "entry")
            )
            manual_evaluator = _packet_field(
                manual, "evaluator", ("requirements", index, "entry")
            )
            if (
                manual_obligation is not requirement.obligation
                or manual_evaluator is not evaluator
            ):
                _fail(("requirements", index), "manual packet correlation differs")
            if key in providers:
                _fail(
                    ("providers",),
                    "manual precondition must not have an input provider",
                )
            continue
        if requirement.enforcement is EnforcementClass.ASSISTED:
            if type(entry) is not AssistedAttentionEntry:
                _fail(("requirements", index), "assisted packet entry kind differs")
            assisted = cast(AssistedAttentionEntry, entry)
            assisted_obligation = _packet_field(
                assisted, "obligation", ("requirements", index, "entry")
            )
            invocation = _packet_field(
                assisted, "invocation", ("requirements", index, "entry")
            )
            residual = _packet_field(
                assisted, "residual_question", ("requirements", index, "entry")
            )
            try:
                expected_residual = evaluator.residual_question
            except Exception as exc:
                _fail(
                    ("requirements", index, "evaluator", "residual-question"),
                    f"residual question cannot be read: {exception_detail(exc)}",
                    cause=exc,
                )
            if assisted_obligation is not requirement.obligation:
                _fail(("requirements", index), "assisted obligation identity differs")
            _validate_invocation(
                run, requirement, cast(EvaluatorInvocation, invocation), index
            )
            if (
                type(residual) is not str
                or type(expected_residual) is not str
                or residual != expected_residual
            ):
                _fail(("requirements", index), "residual question differs")
            continue
        if requirement.enforcement is EnforcementClass.MECHANICAL:
            if type(entry) is not MechanicalAttentionEntry:
                _fail(("requirements", index), "mechanical packet entry kind differs")
            mechanical = cast(MechanicalAttentionEntry, entry)
            mechanical_key = _packet_field(
                mechanical, "key", ("requirements", index, "entry")
            )
            invocation = _packet_field(
                mechanical, "invocation", ("requirements", index, "entry")
            )
            evidence_schema = _packet_field(
                mechanical, "evidence_schema", ("requirements", index, "entry")
            )
            if mechanical_key is not requirement.key:
                _fail(("requirements", index), "mechanical key identity differs")
            _validate_invocation(
                run, requirement, cast(EvaluatorInvocation, invocation), index
            )
            if evidence_schema is not evaluator.evidence_schema:
                _fail(("requirements", index), "evidence schema identity differs")
            continue
        _fail(("requirements", index), "enforcement class is not admitted")


def _validate_invocation(
    run: ProcedureRunPlan,
    requirement: CompletionRequirement,
    invocation: EvaluatorInvocation,
    index: int,
) -> None:
    evaluator = requirement.evaluator
    enforcement = requirement.enforcement
    if evaluator is None or enforcement is None:
        _fail(("requirements", index), "invocation lacks evaluator authority")
    evaluator_reference, input_operation, input_revision, input_data = (
        _invocation_fields(invocation, index)
    )
    reference = VersionedReference(evaluator.id, evaluator.version)
    if evaluator_reference != reference:
        _fail(("requirements", index), "invocation evaluator differs")
    registry: CheckerRunnerRegistry | DetectorRunnerRegistry | None
    expected_registry: CheckerRunnerRegistry | DetectorRunnerRegistry | None
    if enforcement is EnforcementClass.ASSISTED:
        registry = run.attention.detector_registry
        expected_registry = run.attention.requirements.detector_registry
        issued = _is_builder_issued_detector_registry(registry)
    else:
        registry = run.attention.checker_registry
        expected_registry = run.attention.requirements.checker_registry
        issued = _is_builder_issued_checker_registry(registry)
    if registry is None or not issued:
        _fail(("requirements", index), "evaluator runner registry is not issued")
    if registry is not expected_registry:
        _fail(("requirements", index), "evaluator runner registry identity differs")
    if registry.declarations is not run.attention.resolution.registry:
        _fail(
            ("requirements", index),
            "evaluator runner registry uses another declaration registry",
        )
    binding = registry.bindings.get(reference)
    if binding is None or input_operation != binding.operation:
        _fail(("requirements", index), "evaluator input operation differs")
    if input_revision not in evaluator.input_revisions:
        _fail(("requirements", index), "invocation input revision is not admitted")
    if type(input_data) is not MappingProxyType:
        _fail(
            ("requirements", index, "invocation", "input"),
            "retained invocation input is not an issued immutable map",
        )
    try:
        frozen = freeze_json(input_data)
    except Exception as exc:
        _fail(
            ("requirements", index, "invocation", "input"),
            f"invocation input is not finite JSON: {exception_detail(exc)}",
            cause=exc,
        )
    if not isinstance(frozen, Mapping):
        _fail(
            ("requirements", index, "invocation", "input"),
            "invocation input must be a JSON object",
        )
    immutable = cast(Mapping[str, JsonValue], frozen)
    error = validate_json_instance(registry.input_contracts[reference], immutable)
    if error is not None:
        _fail(
            ("requirements", index, "invocation", "input", *error.absolute_path),
            f"invocation input violates its operation contract: {error.message}",
        )
    if not json_values_equal(immutable, input_data):
        _fail(("requirements", index), "invocation input is not stable JSON")


def _invocation_fields(
    invocation: object, index: int
) -> tuple[VersionedReference, VersionedReference, str, object]:
    location = ("requirements", index, "invocation")
    if type(invocation) is not EvaluatorInvocation:
        _fail(location, "invocation carrier is invalid")
    typed = cast(EvaluatorInvocation, invocation)
    try:
        evaluator = typed.evaluator
        operation = typed.evaluator_input_operation
        revision = typed.input_revision
        input_data = typed.input_data
    except Exception as exc:
        _fail(
            location,
            f"invocation carrier is incomplete: {exception_detail(exc)}",
            cause=exc,
        )
    for name, reference in (("evaluator", evaluator), ("operation", operation)):
        if (
            type(reference) is not VersionedReference
            or type(reference.id) is not str
            or not reference.id
            or type(reference.version) is not int
            or reference.version < 1
        ):
            _fail(location + (name,), "invocation reference is invalid")
    if type(revision) is not str:
        _fail(location + ("input-revision",), "invocation revision must be text")
    return evaluator, operation, revision, input_data


def _issue_request(
    parameters: Mapping[str, JsonValue],
    requirement: CompletionRequirement,
    specification: _EvaluationSpec,
) -> ProcedureEvaluatorInputRequest:
    key = cast(ProcedurePredicateKey, requirement.key)
    detached_key = ProcedurePredicateKey(key.declaration, key.phase, key.predicate)
    request = object.__new__(ProcedureEvaluatorInputRequest)
    predicate = specification.predicate
    evaluator = predicate.evaluator
    detached_predicate = Predicate(
        predicate.id,
        predicate.predicate_class,
        cast(Mapping[str, JsonValue], freeze_json(predicate.expression)),
        (
            VersionedReference(evaluator.id, evaluator.version)
            if evaluator is not None
            else None
        ),
        tuple(predicate.observes),
    )
    object.__setattr__(request, "key", detached_key)
    object.__setattr__(request, "procedure", specification.procedure)
    object.__setattr__(request, "phase", PredicatePhase.PRECONDITION)
    object.__setattr__(request, "occurrence", 0)
    object.__setattr__(request, "parameters", parameters)
    object.__setattr__(request, "predicate", detached_predicate)
    return request


def _materialize_provider_input(
    returned: object,
    invocation: EvaluatorInvocation,
    invocation_snapshot: tuple[VersionedReference, VersionedReference, str, object],
    specification: _EvaluationSpec,
    index: int,
) -> tuple[str, Mapping[str, JsonValue]]:
    location = ("providers", index, "result")
    if type(returned) is not EvaluatorInput:
        _fail(location, "input provider must return EvaluatorInput")
    _require_invocation_snapshot(invocation, invocation_snapshot, index)
    supplied = cast(EvaluatorInput, returned)
    try:
        revision = supplied.input_revision
        input_data = supplied.input_data
    except Exception as exc:
        _fail(
            location,
            f"input provider returned an incomplete carrier: {exception_detail(exc)}",
            cause=exc,
        )
    if type(revision) is not str:
        _fail(location + ("input-revision",), "input revision must be text")
    if revision != invocation_snapshot[2]:
        _fail(location + ("input-revision",), "input revision differs from attention")
    try:
        frozen = freeze_json(input_data)
    except Exception as exc:
        _fail(
            location + ("input",),
            f"input is not finite JSON: {exception_detail(exc)}",
            cause=exc,
        )
    if not isinstance(frozen, Mapping):
        _fail(location + ("input",), "input must be a JSON object")
    _require_invocation_snapshot(invocation, invocation_snapshot, index)
    immutable = cast(Mapping[str, JsonValue], frozen)
    if specification.invocation_input is None or not json_values_equal(
        immutable, specification.invocation_input
    ):
        _fail(location + ("input",), "input differs from the attention invocation")
    return revision, immutable


def _validate_provider_input(
    revision: str,
    immutable: Mapping[str, JsonValue],
    invocation: EvaluatorInvocation,
    invocation_snapshot: tuple[VersionedReference, VersionedReference, str, object],
    specification: _EvaluationSpec,
    index: int,
) -> None:
    location = ("providers", index, "result")
    _require_invocation_snapshot(invocation, invocation_snapshot, index)
    if revision != invocation_snapshot[2]:
        _fail(location + ("input-revision",), "input revision differs from attention")
    if specification.input_schema is None:
        _fail(location + ("input",), "input schema snapshot is absent")
    error = validate_json_instance(
        cast(Mapping[str, object], specification.input_schema), immutable
    )
    if error is not None:
        _fail(
            location + ("input", *error.absolute_path),
            f"input violates the evaluator operation contract: {error.message}",
        )
    _require_invocation_snapshot(invocation, invocation_snapshot, index)
    if specification.invocation_input is None or not json_values_equal(
        immutable, specification.invocation_input
    ):
        _fail(location + ("input",), "input differs from the attention invocation")


def _require_invocation_snapshot(
    invocation: EvaluatorInvocation,
    snapshot: tuple[VersionedReference, VersionedReference, str, object],
    index: int,
) -> None:
    current = _invocation_fields(invocation, index)
    if not all(actual is expected for actual, expected in zip(current, snapshot)):
        _fail(("requirements", index, "invocation"), "invocation fields changed")


def _input_contract(
    run: ProcedureRunPlan, reference: VersionedReference
) -> OperationDeclaration:
    registry = run.attention.resolution.registry
    family = registry.families.get(reference.id)
    if family is None or family.kind is not DeclarationKind.OPERATION:
        _fail(("attention", "invocation"), "evaluator input operation is unresolved")
    record = family.versions.get(reference.version)
    if record is None or not isinstance(record.declaration, OperationDeclaration):
        _fail(("attention", "invocation"), "evaluator input operation is unresolved")
    return record.declaration


def _revalidate_assurance(attention: AttentionPlan) -> None:
    if attention.fixture_index is None or attention.assurance is None:
        _fail(("assurance",), "mechanical preconditions require checker assurance")
    try:
        _validate_assurance(
            attention.requirements, attention.fixture_index, attention.assurance
        )
    except AttentionPlanningError as exc:
        _fail(("assurance",), exc.detail, cause=exc)


def _issue_plan(
    run: ProcedureRunPlan,
    parameters: Mapping[str, JsonValue],
    records: tuple[ProcedurePreconditionEvaluation, ...],
    providers: Mapping[ProcedurePredicateKey, ProcedureEvaluatorInputProvider],
    registry_authorities: tuple[object, ...],
    registry_maps: tuple[object, ...],
    registry_contents: tuple[object, ...],
    invocation_state: tuple[object, ...],
    predicate_state: tuple[object, ...],
    run_graph: tuple[object, ...],
) -> ProcedurePreconditionEvaluationPlan:
    evaluator_input_state = _capture_retained_evaluator_input_state(records)
    plan = object.__new__(ProcedurePreconditionEvaluationPlan)
    object.__setattr__(plan, "run", run)
    object.__setattr__(plan, "parameters", parameters)
    object.__setattr__(plan, "phase", PredicatePhase.PRECONDITION)
    object.__setattr__(plan, "occurrence", 0)
    object.__setattr__(plan, "records", records)
    object.__setattr__(
        plan,
        "manual",
        tuple(item for item in records if type(item) is ManualPreconditionEvaluation),
    )
    object.__setattr__(
        plan,
        "assisted",
        tuple(item for item in records if type(item) is AssistedPreconditionEvaluation),
    )
    object.__setattr__(
        plan,
        "mechanical",
        tuple(
            item for item in records if type(item) is MechanicalPreconditionEvaluation
        ),
    )
    object.__setattr__(plan, "providers", providers)
    object.__setattr__(plan, "_registry_authorities", registry_authorities)
    object.__setattr__(plan, "_registry_maps", registry_maps)
    object.__setattr__(plan, "_registry_contents", registry_contents)
    object.__setattr__(plan, "_invocation_state", invocation_state)
    object.__setattr__(plan, "_predicate_state", predicate_state)
    object.__setattr__(plan, "_evaluator_input_state", evaluator_input_state)
    object.__setattr__(plan, "_run_graph", run_graph)
    object.__setattr__(plan, "_issuer", _PLAN_ISSUER)
    return plan


def _is_issued_procedure_precondition_evaluation_plan(plan: object) -> bool:
    """Return whether ``plan`` retains every issued correlation invariant."""
    if (
        type(plan) is not ProcedurePreconditionEvaluationPlan
        or getattr(plan, "_issuer", None) is not _PLAN_ISSUER
    ):
        return False
    try:
        run = plan.run
        if not _is_issued_procedure_run_plan(run):
            return False
        if not _is_issued_attention_plan(run.attention):
            return False
        if type(plan._run_graph) is not tuple:
            return False
        _require_run_graph(run, plan._run_graph, ("run",))
        if plan.phase is not PredicatePhase.PRECONDITION:
            return False
        if type(plan.occurrence) is not int or plan.occurrence != 0:
            return False
        if type(plan.records) is not tuple:
            return False
        if type(plan.manual) is not tuple or type(plan.assisted) is not tuple:
            return False
        if type(plan.mechanical) is not tuple or not _validate_provider_snapshot(
            plan.providers
        ):
            return False

        authorities, registry_maps, registry_contents = _capture_registry_state(run)
        if (
            type(plan._registry_authorities) is not tuple
            or not _same_identity_projection(plan._registry_authorities, authorities)
            or type(plan._registry_maps) is not tuple
            or not _same_identity_projection(plan._registry_maps, registry_maps)
            or type(plan._registry_contents) is not tuple
            or not _same_identity_projection(plan._registry_contents, registry_contents)
        ):
            return False
        requirements = _requirements(run)
        entries = _packet_entries(run.attention)
        if (
            type(plan._invocation_state) is not tuple
            or not _same_semantic_state(
                plan._invocation_state,
                _capture_invocation_state(run, requirements, entries),
            )
            or type(plan._predicate_state) is not tuple
            or not _same_semantic_state(
                plan._predicate_state, _capture_predicate_state(requirements)
            )
            or type(plan._evaluator_input_state) is not tuple
            or not _same_semantic_state(
                plan._evaluator_input_state,
                _capture_retained_evaluator_input_state(plan.records),
            )
        ):
            return False
        parameters = _snapshot_run_parameters(run)
        if type(plan.parameters) is not MappingProxyType or not json_values_equal(
            plan.parameters, parameters
        ):
            return False
        expected_provider_keys = tuple(
            cast(ProcedurePredicateKey, item.key)
            for item in requirements
            if item.enforcement
            in {EnforcementClass.ASSISTED, EnforcementClass.MECHANICAL}
        )
        _require_exact_providers(plan.providers, expected_provider_keys)
        _validate_static_contracts(run, requirements, plan.providers, entries)
        if len(plan.records) != len(requirements):
            return False
        for requirement, record in zip(requirements, plan.records):
            key = cast(ProcedurePredicateKey, requirement.key)
            if record.requirement is not requirement:
                return False
            if record.entry is not entries[key]:
                return False
            if requirement.enforcement is EnforcementClass.DELIBERATIVE:
                if type(record) is not ManualPreconditionEvaluation:
                    return False
            elif requirement.enforcement is EnforcementClass.ASSISTED:
                if type(record) is not AssistedPreconditionEvaluation:
                    return False
                if record.provider is not plan.providers[key]:
                    return False
                if not _retained_input_matches_invocation(
                    record.evaluator_input, record.entry.invocation
                ):
                    return False
            elif requirement.enforcement is EnforcementClass.MECHANICAL:
                if type(record) is not MechanicalPreconditionEvaluation:
                    return False
                if record.provider is not plan.providers[key]:
                    return False
                if not _retained_input_matches_invocation(
                    record.evaluator_input, record.entry.invocation
                ):
                    return False
            else:
                return False
        if not _same_identity_projection(
            plan.manual,
            tuple(
                item
                for item in plan.records
                if type(item) is ManualPreconditionEvaluation
            ),
        ):
            return False
        if not _same_identity_projection(
            plan.assisted,
            tuple(
                item
                for item in plan.records
                if type(item) is AssistedPreconditionEvaluation
            ),
        ):
            return False
        if not _same_identity_projection(
            plan.mechanical,
            tuple(
                item
                for item in plan.records
                if type(item) is MechanicalPreconditionEvaluation
            ),
        ):
            return False
        if plan.mechanical:
            _revalidate_assurance(run.attention)
        _require_run_graph(run, plan._run_graph, ("run",))
    except Exception:
        return False
    return True


def _capture_retained_evaluator_input_state(
    records: tuple[ProcedurePreconditionEvaluation, ...],
) -> tuple[object, ...]:
    """Bind each runnable record to its exact detached evaluator input."""
    state: list[object] = []
    for index, record in enumerate(records):
        if type(record) is ManualPreconditionEvaluation:
            continue
        if type(record) not in {
            AssistedPreconditionEvaluation,
            MechanicalPreconditionEvaluation,
        }:
            _fail(("records", index), "precondition evaluation record is invalid")
        runnable = cast(
            AssistedPreconditionEvaluation | MechanicalPreconditionEvaluation,
            record,
        )
        evaluator_input = runnable.evaluator_input
        if type(evaluator_input) is not EvaluatorInput:
            _fail(("records", index, "evaluator-input"), "carrier is invalid")
        if type(evaluator_input.input_revision) is not str:
            _fail(
                ("records", index, "evaluator-input", "input-revision"),
                "revision must be text",
            )
        if type(evaluator_input.input_data) is not MappingProxyType:
            _fail(
                ("records", index, "evaluator-input", "input"),
                "input must be an immutable JSON object",
            )
        frozen = _freeze_mapping_snapshot(
            evaluator_input.input_data,
            ("records", index, "evaluator-input", "input"),
        )
        state.append(
            (
                (evaluator_input, evaluator_input.input_data),
                (evaluator_input.input_revision, frozen),
            )
        )
    return tuple(state)


def _retained_input_matches_invocation(
    evaluator_input: object, invocation: object
) -> bool:
    """Return whether one detached input reproduces its admitted invocation."""
    if (
        type(evaluator_input) is not EvaluatorInput
        or type(invocation) is not EvaluatorInvocation
    ):
        return False
    typed = cast(EvaluatorInput, evaluator_input)
    admitted = cast(EvaluatorInvocation, invocation)
    return (
        type(typed.input_revision) is str
        and typed.input_revision == admitted.input_revision
        and type(typed.input_data) is MappingProxyType
        and typed.input_data is not admitted.input_data
        and json_values_equal(typed.input_data, admitted.input_data)
    )


def _same_identity_projection(
    first: tuple[object, ...], second: tuple[object, ...]
) -> bool:
    """Compare one projection by length, order, and exact record identity."""
    return len(first) == len(second) and all(
        actual is expected for actual, expected in zip(first, second)
    )


def _fail(
    parts: tuple[str | int, ...], message: str, *, cause: Exception | None = None
) -> NoReturn:
    error = ProcedureEvaluationPlanningError(format_document_path(parts), message)
    if cause is not None:
        raise error from cause
    raise error
