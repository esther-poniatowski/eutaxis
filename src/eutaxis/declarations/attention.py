"""Derive effective obligations and issue enforcement-directed attention packets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import NoReturn, SupportsIndex, TypeAlias, cast

from ._runner_support import exception_detail
from .embedded_schema import validate_json_instance
from .enforcement import (
    EnforcementClass,
    OperationPredicateEnforcement,
    PredicatePhase,
    ProcedurePredicateEnforcement,
    RuleCriterionEnforcement,
    _EnforcementRecordSource,
    _enumerate_enforcement,
)
from .exceptions import AttentionPlanningError, CheckerExecutionError
from .execution import (
    KnownFailureAssurance,
    _is_issued_known_failure_assurance,
    _verify_fixture_digests,
)
from .fixtures import EvaluatorFixtureIndex, _is_loader_issued_fixture_index
from .models import (
    AnyDeclaration,
    Criterion,
    DeclarationKind,
    EvaluatorDeclaration,
    JsonValue,
    Norm,
    OperationDeclaration,
    Predicate,
    ProcedureDeclaration,
    ProcedureNode,
    RuleAxis,
    RuleDeclaration,
    VersionedReference,
    freeze_json,
)
from .registry import DeclarationRegistry
from .resolution import (
    ResolutionResult,
    ResolvedRuleProjection,
    _is_issued_resolution_result,
)
from .runners import (
    CheckerRunnerRegistry,
    DetectorRunnerRegistry,
    _is_builder_issued_checker_registry,
    _is_builder_issued_detector_registry,
)

_REQUIREMENTS_ISSUER = object()
_PLAN_ISSUER = object()


@dataclass(frozen=True)
class RuleCriterionKey:
    """Identify one criterion of one effective rule."""

    declaration: str
    criterion: str


@dataclass(frozen=True)
class ProcedurePredicateKey:
    """Identify one phased predicate of one effective procedure."""

    declaration: str
    phase: PredicatePhase
    predicate: str


@dataclass(frozen=True)
class OperationPredicateKey:
    """Identify one operation precondition at one procedure action."""

    procedure: str
    action: str
    subject_operation: VersionedReference
    predicate: str


AttentionObligationKey: TypeAlias = (
    RuleCriterionKey | ProcedurePredicateKey | OperationPredicateKey
)


@dataclass(frozen=True)
class RuleObligationSnapshot:
    """Retain the selected rule context needed to judge one criterion."""

    key: RuleCriterionKey
    axis: RuleAxis
    failure_mode: str
    required_visibility: str | None
    title: str | None
    rationale: str | None
    criterion: Criterion
    norms: tuple[Norm, ...]


@dataclass(frozen=True)
class ProcedureObligationSnapshot:
    """Retain the selected procedure context needed to judge one predicate."""

    key: ProcedurePredicateKey
    purpose: str
    title: str | None
    rationale: str | None
    parameters: Mapping[str, JsonValue]
    effects: tuple[str, ...]
    failures: tuple[str, ...]
    phase: PredicatePhase
    predicate: Predicate


@dataclass(frozen=True)
class OperationObligationSnapshot:
    """Retain one expanded operation-precondition occurrence and its context."""

    key: OperationPredicateKey
    procedure_purpose: str
    procedure_title: str | None
    procedure_rationale: str | None
    procedure_parameters: Mapping[str, JsonValue]
    action: ProcedureNode
    operation_inputs: Mapping[str, JsonValue]
    operation_effects: tuple[str, ...]
    failure_outcomes: tuple[str, ...]
    recovery: str
    predicate: Predicate


AttentionObligationSnapshot: TypeAlias = (
    RuleObligationSnapshot | ProcedureObligationSnapshot | OperationObligationSnapshot
)


@dataclass(frozen=True)
class RunnableAttentionRequirement:
    """Describe one canonical machine invocation before its input is supplied."""

    key: AttentionObligationKey
    obligation: AttentionObligationSnapshot
    evaluator: EvaluatorDeclaration
    enforcement: EnforcementClass
    evaluator_input_operation: VersionedReference
    input_revisions: tuple[str, ...]
    input_schema: Mapping[str, object]


@dataclass(frozen=True)
class DeliberativeAttentionRequirement:
    """Describe one complete manual obligation and its evidence contract."""

    key: AttentionObligationKey
    obligation: AttentionObligationSnapshot
    evaluator: EvaluatorDeclaration


@dataclass(frozen=True, init=False, eq=False)
class AttentionRequirements:
    """Process-local canonical requirements derived from one resolution result."""

    resolution: ResolutionResult
    deliberative: tuple[DeliberativeAttentionRequirement, ...]
    assisted: tuple[RunnableAttentionRequirement, ...]
    mechanical: tuple[RunnableAttentionRequirement, ...]
    checker_registry: CheckerRunnerRegistry | None
    detector_registry: DetectorRunnerRegistry | None
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Reject construction outside requirement derivation."""
        raise TypeError(
            "AttentionRequirements instances must be issued by requirement derivation"
        )

    def __copy__(self) -> NoReturn:
        raise TypeError("AttentionRequirements instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("AttentionRequirements instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("AttentionRequirements instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("AttentionRequirements instances cannot be serialized")


@dataclass(frozen=True)
class EvaluatorInput:
    """Supply one candidate evaluator revision and JSON input object."""

    input_revision: str
    input_data: Mapping[str, object]


@dataclass(frozen=True)
class EvaluatorInvocation:
    """Retain one validated immutable evaluator invocation."""

    evaluator: VersionedReference
    evaluator_input_operation: VersionedReference
    input_revision: str
    input_data: Mapping[str, JsonValue]


@dataclass(frozen=True)
class DeliberativeAttentionEntry:
    """Carry one complete manual obligation and its exact evaluator contract."""

    obligation: AttentionObligationSnapshot
    evaluator: EvaluatorDeclaration


@dataclass(frozen=True)
class AssistedAttentionEntry:
    """Carry one detector invocation and the judgment that remains afterward."""

    obligation: AttentionObligationSnapshot
    invocation: EvaluatorInvocation
    residual_question: str


@dataclass(frozen=True)
class MechanicalAttentionEntry:
    """Carry one compact checker invocation and its expected evidence shape."""

    key: AttentionObligationKey
    invocation: EvaluatorInvocation
    evidence_schema: Mapping[str, JsonValue]


@dataclass(frozen=True)
class DeliberationPacket:
    """Contain effective obligations that require unaided judgment."""

    entries: tuple[DeliberativeAttentionEntry, ...]


@dataclass(frozen=True)
class AssistedPacket:
    """Contain effective obligations supported by candidate detectors."""

    entries: tuple[AssistedAttentionEntry, ...]


@dataclass(frozen=True)
class MechanicalPacket:
    """Contain effective obligations decided by assured checkers."""

    entries: tuple[MechanicalAttentionEntry, ...]


@dataclass(frozen=True, init=False, eq=False)
class AttentionPlan:
    """Process-local correlated attention packets and readiness authorities."""

    requirements: AttentionRequirements
    resolution: ResolutionResult
    deliberative: DeliberationPacket
    assisted: AssistedPacket
    mechanical: MechanicalPacket
    checker_registry: CheckerRunnerRegistry | None
    fixture_index: EvaluatorFixtureIndex | None
    assurance: KnownFailureAssurance | None
    detector_registry: DetectorRunnerRegistry | None
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Reject construction outside attention planning."""
        raise TypeError("AttentionPlan instances must be issued by attention planning")

    def __copy__(self) -> NoReturn:
        raise TypeError("AttentionPlan instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("AttentionPlan instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("AttentionPlan instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("AttentionPlan instances cannot be serialized")


def derive_attention_requirements(
    resolution: ResolutionResult,
    *,
    checker_registry: CheckerRunnerRegistry | None = None,
    detector_registry: DetectorRunnerRegistry | None = None,
) -> AttentionRequirements:
    """Derive canonical effective obligations and their runnable contracts."""
    if not _is_issued_resolution_result(resolution):
        _fail((), "resolution result was not issued by semantic resolution")
    registry = resolution.registry
    locator_maps = _locator_maps(registry)
    selected = _selected_obligations(resolution, locator_maps)

    mechanical_selected = tuple(
        item for item in selected if item[2] is EnforcementClass.MECHANICAL
    )
    assisted_selected = tuple(
        item for item in selected if item[2] is EnforcementClass.ASSISTED
    )
    deliberative_selected = tuple(
        item for item in selected if item[2] is EnforcementClass.DELIBERATIVE
    )

    _validate_runner_authority(
        registry,
        checker_registry,
        required=bool(mechanical_selected),
        checker=True,
    )
    _validate_runner_authority(
        registry,
        detector_registry,
        required=bool(assisted_selected),
        checker=False,
    )

    mechanical = tuple(
        _runnable_requirement(item, cast(CheckerRunnerRegistry, checker_registry))
        for item in mechanical_selected
    )
    assisted = tuple(
        _runnable_requirement(item, cast(DetectorRunnerRegistry, detector_registry))
        for item in assisted_selected
    )
    deliberative = tuple(
        DeliberativeAttentionRequirement(
            key=key,
            obligation=obligation,
            evaluator=_evaluator_contract(registry, evaluator),
        )
        for key, obligation, _enforcement, evaluator in deliberative_selected
    )
    return _issue_requirements(
        resolution,
        deliberative,
        assisted,
        mechanical,
        checker_registry,
        detector_registry,
    )


def plan_attention(
    requirements: AttentionRequirements,
    inputs: Mapping[AttentionObligationKey, EvaluatorInput],
    *,
    fixture_index: EvaluatorFixtureIndex | None = None,
    assurance: KnownFailureAssurance | None = None,
) -> AttentionPlan:
    """Validate exact inputs and readiness, then issue three attention packets."""
    if not _is_issued_requirements(requirements):
        _fail((), "attention requirements were not issued by derivation")
    mechanical = requirements.mechanical
    if mechanical:
        if fixture_index is None or assurance is None:
            _fail(
                ("mechanical",),
                "mechanical requirements need a fixture index and known-failure assurance",
            )
        _validate_assurance(requirements, fixture_index, assurance)
    elif fixture_index is not None or assurance is not None:
        _fail(
            ("mechanical",),
            "fixture readiness was supplied for an empty mechanical requirement set",
        )

    supplied = _snapshot_inputs(inputs)
    runnable = (*requirements.assisted, *mechanical)
    expected = tuple(item.key for item in runnable)
    expected_set = set(expected)
    supplied_set = set(supplied)
    missing = tuple(key for key in expected if key not in supplied_set)
    additional = tuple(key for key in supplied if key not in expected_set)
    if missing:
        _fail(("inputs",), f"missing evaluator input for {_key_text(missing[0])}")
    if additional:
        _fail(("inputs",), f"unexpected evaluator input for {_key_text(additional[0])}")

    invocations = {
        requirement.key: _invocation(requirement, supplied[requirement.key], index)
        for index, requirement in enumerate(runnable)
    }
    deliberative_packet = DeliberationPacket(
        tuple(
            DeliberativeAttentionEntry(item.obligation, item.evaluator)
            for item in requirements.deliberative
        )
    )
    assisted_packet = AssistedPacket(
        tuple(
            AssistedAttentionEntry(
                item.obligation,
                invocations[item.key],
                cast(str, item.evaluator.residual_question),
            )
            for item in requirements.assisted
        )
    )
    mechanical_packet = MechanicalPacket(
        tuple(
            MechanicalAttentionEntry(
                item.key,
                invocations[item.key],
                item.evaluator.evidence_schema,
            )
            for item in mechanical
        )
    )
    return _issue_plan(
        requirements,
        deliberative_packet,
        assisted_packet,
        mechanical_packet,
        fixture_index,
        assurance,
    )


def _snapshot_inputs(
    inputs: object,
) -> Mapping[AttentionObligationKey, object]:
    """Validate and freeze one traversal of the public input mapping."""
    if not isinstance(inputs, Mapping):
        _fail(("inputs",), "evaluator inputs must be a mapping")
    try:
        pairs = tuple(inputs.items())
    except Exception as exc:
        _fail(
            ("inputs",),
            f"evaluator inputs could not be read: {exception_detail(exc)}",
            cause=exc,
        )
    snapshot: dict[AttentionObligationKey, object] = {}
    for index, pair in enumerate(pairs):
        try:
            key, value = pair
        except Exception as exc:
            _fail(
                ("inputs", index),
                f"input item is not a key-value pair: {exception_detail(exc)}",
                cause=exc,
            )
        validated_key = _validate_input_key(key, index)
        if validated_key in snapshot:
            _fail(("inputs", index, "key"), "input key is duplicated")
        snapshot[validated_key] = value
    return MappingProxyType(snapshot)


def _validate_input_key(key: object, index: int) -> AttentionObligationKey:
    """Validate one public obligation key before hashing or formatting it."""
    location = ("inputs", index, "key")
    if type(key) is RuleCriterionKey:
        rule_key = cast(RuleCriterionKey, key)
        _validate_key_identifier(rule_key.declaration, location + ("declaration",))
        _validate_key_identifier(rule_key.criterion, location + ("criterion",))
        return rule_key
    if type(key) is ProcedurePredicateKey:
        procedure_key = cast(ProcedurePredicateKey, key)
        _validate_key_identifier(procedure_key.declaration, location + ("declaration",))
        if type(procedure_key.phase) is not PredicatePhase:
            _fail(location + ("phase",), "procedure phase is not admitted")
        _validate_key_identifier(procedure_key.predicate, location + ("predicate",))
        return procedure_key
    if type(key) is OperationPredicateKey:
        operation_key = cast(OperationPredicateKey, key)
        _validate_key_identifier(operation_key.procedure, location + ("procedure",))
        _validate_key_identifier(operation_key.action, location + ("action",))
        _validate_key_reference(
            operation_key.subject_operation,
            location + ("subject-operation",),
        )
        _validate_key_identifier(operation_key.predicate, location + ("predicate",))
        return operation_key
    _fail(
        location,
        "input key must identify a rule criterion, procedure predicate, "
        "or operation predicate",
    )


def _validate_key_identifier(value: object, location: tuple[str | int, ...]) -> None:
    """Require the non-empty, whitespace-free identifier form of the schema."""
    if (
        type(value) is not str
        or not value
        or any(character.isspace() for character in value)
    ):
        _fail(location, "key identifier must be non-empty text without whitespace")


def _validate_key_reference(reference: object, location: tuple[str | int, ...]) -> None:
    """Require one structurally valid exact operation reference."""
    if type(reference) is not VersionedReference:
        _fail(location, "subject operation must be a versioned reference")
    _validate_key_identifier(reference.id, location + ("id",))
    if type(reference.version) is not int or reference.version < 1:
        _fail(location + ("version",), "operation version must be a positive integer")


def _locator_maps(
    registry: DeclarationRegistry,
) -> tuple[
    dict[tuple[str, str], RuleCriterionEnforcement],
    dict[tuple[str, PredicatePhase, str], ProcedurePredicateEnforcement],
    dict[tuple[VersionedReference, str], OperationPredicateEnforcement],
]:
    """Index the shared canonical locator sequence by source coordinates."""
    source = _registry_enforcement_source(registry)
    rules: dict[tuple[str, str], RuleCriterionEnforcement] = {}
    procedures: dict[tuple[str, PredicatePhase, str], ProcedurePredicateEnforcement] = (
        {}
    )
    operations: dict[tuple[VersionedReference, str], OperationPredicateEnforcement] = {}
    for locator in _enumerate_enforcement(source):
        if isinstance(locator, RuleCriterionEnforcement):
            rules[(locator.declaration, locator.criterion)] = locator
        elif isinstance(locator, ProcedurePredicateEnforcement):
            procedures[(locator.declaration, locator.phase, locator.predicate)] = (
                locator
            )
        else:
            operations[(locator.operation, locator.predicate)] = locator
    return rules, procedures, operations


def _registry_enforcement_source(
    registry: DeclarationRegistry,
) -> _EnforcementRecordSource:
    """Adapt one exact registry to neutral authored-obligation enumeration."""
    declarations: dict[str, AnyDeclaration] = {
        identifier: record.declaration
        for identifier, record in registry.records.items()
    }
    operations: list[tuple[VersionedReference, OperationDeclaration]] = []
    for family_id in sorted(registry.families):
        family = registry.families[family_id]
        if family.kind is not DeclarationKind.OPERATION:
            continue
        for version in sorted(family.versions):
            declaration = family.versions[version].declaration
            if not isinstance(declaration, OperationDeclaration):
                _fail(("registry",), "operation family contains a wrong-kind record")
            operations.append((VersionedReference(family.id, version), declaration))
    return _EnforcementRecordSource(
        declarations=MappingProxyType(declarations),
        operations=tuple(operations),
        evaluator=lambda reference: _evaluator_contract(registry, reference),
    )


SelectedObligation: TypeAlias = tuple[
    AttentionObligationKey,
    AttentionObligationSnapshot,
    EnforcementClass,
    VersionedReference,
]


def _selected_obligations(
    resolution: ResolutionResult,
    locator_maps: tuple[
        dict[tuple[str, str], RuleCriterionEnforcement],
        dict[tuple[str, PredicatePhase, str], ProcedurePredicateEnforcement],
        dict[tuple[VersionedReference, str], OperationPredicateEnforcement],
    ],
) -> tuple[SelectedObligation, ...]:
    """Intersect authored locators with one certified effective unit."""
    rules, procedures, operations = locator_maps
    registry = resolution.registry
    components = resolution.unit.components
    component_ids = tuple(component.declaration for component in components)
    if len(component_ids) != len(set(component_ids)):
        _fail(("resolution", "unit", "components"), "duplicate effective component")
    projections = resolution.unit.rule_projections
    projection_by_rule = {
        projection.declaration: projection for projection in projections
    }
    if len(projection_by_rule) != len(projections):
        _fail(("resolution", "unit", "rule-projections"), "duplicate rule projection")

    selected: list[SelectedObligation] = []
    effective_rules: set[str] = set()
    for component_index, component in enumerate(components):
        record = registry.records.get(component.declaration)
        if record is None:
            _fail(
                ("resolution", "unit", "components", component_index),
                f"unknown effective declaration {component.declaration!r}",
            )
        declaration = record.declaration
        if isinstance(declaration, RuleDeclaration):
            effective_rules.add(declaration.id)
            projection = projection_by_rule.get(declaration.id)
            if projection is None:
                _fail(
                    ("resolution", "unit", "rule-projections"),
                    f"effective rule {declaration.id!r} lacks a projection",
                )
            selected.extend(_rule_obligations(declaration, projection, rules))
        elif isinstance(declaration, ProcedureDeclaration):
            selected.extend(
                _procedure_obligations(declaration, procedures, operations, registry)
            )
        else:
            _fail(
                ("resolution", "unit", "components", component_index),
                f"effective declaration {declaration.id!r} has inadmissible kind",
            )
    extra_projections = set(projection_by_rule) - effective_rules
    if extra_projections:
        _fail(
            ("resolution", "unit", "rule-projections"),
            f"projection names non-effective rule {min(extra_projections)!r}",
        )
    keys = tuple(item[0] for item in selected)
    if len(keys) != len(set(keys)):
        _fail(("resolution",), "effective obligation keys are not unique")
    return tuple(selected)


def _rule_obligations(
    rule: RuleDeclaration,
    projection: ResolvedRuleProjection,
    locators: Mapping[tuple[str, str], RuleCriterionEnforcement],
) -> tuple[SelectedObligation, ...]:
    """Select projected criteria and retain their effective norm context."""
    norm_by_id = {norm.id: norm for norm in rule.norms}
    if len(set(projection.norms)) != len(projection.norms) or any(
        identifier not in norm_by_id for identifier in projection.norms
    ):
        _fail(("resolution", "unit", "rule-projections"), "invalid projected norms")
    criterion_by_id = {criterion.id: criterion for criterion in rule.criteria}
    if len(set(projection.criteria)) != len(projection.criteria) or any(
        identifier not in criterion_by_id for identifier in projection.criteria
    ):
        _fail(
            ("resolution", "unit", "rule-projections"),
            "invalid projected criteria",
        )
    selected: list[SelectedObligation] = []
    projected = set(projection.criteria)
    effective_norms = set(projection.norms)
    for criterion in rule.criteria:
        if criterion.id not in projected:
            continue
        if any(identifier not in effective_norms for identifier in criterion.norms):
            _fail(
                ("resolution", "unit", "rule-projections"),
                f"criterion {criterion.id!r} references an inactive norm",
            )
        locator = locators.get((rule.id, criterion.id))
        if locator is None:
            _fail(("registry",), f"criterion {criterion.id!r} lacks enforcement")
        key = RuleCriterionKey(rule.id, criterion.id)
        snapshot = RuleObligationSnapshot(
            key=key,
            axis=rule.axis,
            failure_mode=rule.failure_mode,
            required_visibility=rule.required_visibility,
            title=rule.title,
            rationale=rule.rationale,
            criterion=criterion,
            norms=tuple(norm_by_id[identifier] for identifier in criterion.norms),
        )
        selected.append((key, snapshot, locator.enforcement, locator.evaluator))
    return tuple(selected)


def _procedure_obligations(
    procedure: ProcedureDeclaration,
    procedure_locators: Mapping[
        tuple[str, PredicatePhase, str], ProcedurePredicateEnforcement
    ],
    operation_locators: Mapping[
        tuple[VersionedReference, str], OperationPredicateEnforcement
    ],
    registry: DeclarationRegistry,
) -> tuple[SelectedObligation, ...]:
    """Select procedure predicates and expand each operation precondition."""
    selected: list[SelectedObligation] = []
    selected.extend(
        _procedure_predicates(
            procedure,
            PredicatePhase.PRECONDITION,
            procedure.preconditions,
            procedure_locators,
        )
    )
    for action in procedure.actions:
        operation = _operation_contract(registry, action.operation)
        for predicate in operation.preconditions:
            if predicate.evaluator is None:
                continue
            locator = operation_locators.get((action.operation, predicate.id))
            if locator is None:
                _fail(
                    ("registry",),
                    f"operation predicate {predicate.id!r} lacks enforcement",
                )
            key = OperationPredicateKey(
                procedure.id, action.id, action.operation, predicate.id
            )
            snapshot = OperationObligationSnapshot(
                key=key,
                procedure_purpose=procedure.purpose,
                procedure_title=procedure.title,
                procedure_rationale=procedure.rationale,
                procedure_parameters=procedure.parameters,
                action=action,
                operation_inputs=operation.inputs,
                operation_effects=operation.effects,
                failure_outcomes=operation.failure_outcomes,
                recovery=operation.recovery,
                predicate=predicate,
            )
            selected.append((key, snapshot, locator.enforcement, locator.evaluator))
    selected.extend(
        _procedure_predicates(
            procedure,
            PredicatePhase.INVARIANT,
            procedure.invariants,
            procedure_locators,
        )
    )
    selected.extend(
        _procedure_predicates(
            procedure,
            PredicatePhase.POSTCONDITION,
            procedure.postconditions,
            procedure_locators,
        )
    )
    return tuple(selected)


def _procedure_predicates(
    procedure: ProcedureDeclaration,
    phase: PredicatePhase,
    predicates: tuple[Predicate, ...],
    locators: Mapping[tuple[str, PredicatePhase, str], ProcedurePredicateEnforcement],
) -> tuple[SelectedObligation, ...]:
    """Retain evaluator-backed predicates from one authored procedure phase."""
    selected: list[SelectedObligation] = []
    for predicate in predicates:
        if predicate.evaluator is None:
            continue
        locator = locators.get((procedure.id, phase, predicate.id))
        if locator is None:
            _fail(
                ("registry",), f"procedure predicate {predicate.id!r} lacks enforcement"
            )
        key = ProcedurePredicateKey(procedure.id, phase, predicate.id)
        snapshot = ProcedureObligationSnapshot(
            key=key,
            purpose=procedure.purpose,
            title=procedure.title,
            rationale=procedure.rationale,
            parameters=procedure.parameters,
            effects=procedure.effects,
            failures=procedure.failures,
            phase=phase,
            predicate=predicate,
        )
        selected.append((key, snapshot, locator.enforcement, locator.evaluator))
    return tuple(selected)


def _validate_runner_authority(
    registry: DeclarationRegistry,
    runners: CheckerRunnerRegistry | DetectorRunnerRegistry | None,
    *,
    required: bool,
    checker: bool,
) -> None:
    """Require one exact builder-issued registry only for a non-empty class."""
    name = "checker" if checker else "detector"
    if not required:
        if runners is not None:
            _fail((f"{name}-registry",), f"{name} registry supplied for an empty class")
        return
    if runners is None:
        _fail((f"{name}-registry",), f"{name} registry is required")
    issued = (
        _is_builder_issued_checker_registry(runners)
        if checker
        else _is_builder_issued_detector_registry(runners)
    )
    if not issued:
        _fail((f"{name}-registry",), f"{name} registry was not issued by its builder")
    if runners.declarations is not registry:
        _fail(
            (f"{name}-registry",),
            f"{name} registry uses a different declaration registry",
        )


def _runnable_requirement(
    item: SelectedObligation,
    runners: CheckerRunnerRegistry | DetectorRunnerRegistry,
) -> RunnableAttentionRequirement:
    """Bind one selected obligation to its exact evaluator input contract."""
    key, obligation, enforcement, reference = item
    binding = runners.bindings.get(reference)
    if binding is None:
        _fail(
            ("requirements",),
            f"no runner is registered for {_reference_text(reference)}",
        )
    evaluator = _evaluator_contract(runners.declarations, reference)
    return RunnableAttentionRequirement(
        key=key,
        obligation=obligation,
        evaluator=evaluator,
        enforcement=enforcement,
        evaluator_input_operation=binding.operation,
        input_revisions=evaluator.input_revisions,
        input_schema=runners.input_contracts[reference],
    )


def _invocation(
    requirement: RunnableAttentionRequirement,
    supplied: object,
    index: int,
) -> EvaluatorInvocation:
    """Freeze and validate one supplied input against its issued requirement."""
    location = ("inputs", index)
    if not isinstance(supplied, EvaluatorInput):
        _fail(location, "input value must be EvaluatorInput")
    if supplied.input_revision not in requirement.input_revisions:
        _fail(
            location + ("input-revision",),
            f"input revision {supplied.input_revision!r} is not admitted",
        )
    try:
        frozen = freeze_json(supplied.input_data)
    except Exception as exc:
        _fail(
            location + ("input",),
            f"input is not finite JSON: {exception_detail(exc)}",
            cause=exc,
        )
    if not isinstance(frozen, Mapping):
        _fail(location + ("input",), "input must be a JSON object")
    immutable = cast(Mapping[str, JsonValue], frozen)
    error = validate_json_instance(requirement.input_schema, immutable)
    if error is not None:
        path = location + ("input",) + tuple(error.absolute_path)
        _fail(path, f"input violates the evaluator operation contract: {error.message}")
    evaluator = VersionedReference(
        requirement.evaluator.id, requirement.evaluator.version
    )
    return EvaluatorInvocation(
        evaluator=evaluator,
        evaluator_input_operation=requirement.evaluator_input_operation,
        input_revision=supplied.input_revision,
        input_data=immutable,
    )


def _validate_assurance(
    requirements: AttentionRequirements,
    fixtures: EvaluatorFixtureIndex,
    assurance: KnownFailureAssurance,
) -> None:
    """Revalidate the exact checker assurance immediately before plan issuance."""
    runners = requirements.checker_registry
    assert runners is not None
    registry = requirements.resolution.registry
    if not _is_loader_issued_fixture_index(fixtures):
        _fail(("fixture-index",), "fixture index was not issued by its loader")
    if not _is_issued_known_failure_assurance(assurance):
        _fail(("assurance",), "known-failure assurance was not issued by execution")
    if assurance.declarations is not registry:
        _fail(("assurance",), "assurance uses a different declaration registry")
    if assurance.fixtures is not fixtures:
        _fail(("assurance",), "assurance uses a different fixture index")
    if assurance.runners is not runners:
        _fail(("assurance",), "assurance uses a different checker registry")

    expected: dict[VersionedReference, tuple[str, ...]] = {}
    for family_id in sorted(registry.families):
        family = registry.families[family_id]
        if family.kind is not DeclarationKind.EVALUATOR:
            continue
        for version in sorted(family.versions):
            declaration = family.versions[version].declaration
            if not isinstance(declaration, EvaluatorDeclaration):
                _fail(("assurance",), "evaluator family contains a wrong-kind record")
            if declaration.evaluator_kind == "checker":
                expected[VersionedReference(family.id, version)] = (
                    declaration.known_failure_fixtures
                )
    if set(assurance.evaluators) != set(expected):
        _fail(("assurance", "evaluators"), "assurance checker coverage is incomplete")
    for reference, fixture_ids in expected.items():
        evaluator_assurance = assurance.evaluators[reference]
        if evaluator_assurance.evaluator != reference:
            _fail(("assurance", "evaluators"), "assurance evaluator identity differs")
        actual_ids = tuple(item.fixture_id for item in evaluator_assurance.fixtures)
        if actual_ids != fixture_ids:
            _fail(
                ("assurance", "evaluators"),
                f"assurance fixture sequence differs for {_reference_text(reference)}",
            )
        for fixture_id in fixture_ids:
            fixture = fixtures.fixtures.get(fixture_id)
            if fixture is None or fixture.evaluator != reference:
                _fail(
                    ("assurance", "evaluators"),
                    f"fixture {fixture_id!r} no longer matches its checker",
                )
            try:
                _verify_fixture_digests(fixture)
            except CheckerExecutionError as exc:
                _fail(("assurance",), exc.detail, cause=exc)


def _evaluator_contract(
    registry: DeclarationRegistry, reference: VersionedReference
) -> EvaluatorDeclaration:
    """Resolve one exact evaluator from the correlated registry."""
    family = registry.families.get(reference.id)
    if family is None or family.kind is not DeclarationKind.EVALUATOR:
        _fail(("registry",), f"unknown evaluator {_reference_text(reference)}")
    record = family.versions.get(reference.version)
    if record is None or not isinstance(record.declaration, EvaluatorDeclaration):
        _fail(("registry",), f"unknown evaluator {_reference_text(reference)}")
    return record.declaration


def _operation_contract(
    registry: DeclarationRegistry, reference: VersionedReference
) -> OperationDeclaration:
    """Resolve one exact subject operation from the correlated registry."""
    family = registry.families.get(reference.id)
    if family is None or family.kind is not DeclarationKind.OPERATION:
        _fail(("registry",), f"unknown operation {_reference_text(reference)}")
    record = family.versions.get(reference.version)
    if record is None or not isinstance(record.declaration, OperationDeclaration):
        _fail(("registry",), f"unknown operation {_reference_text(reference)}")
    return record.declaration


def _issue_requirements(
    resolution: ResolutionResult,
    deliberative: tuple[DeliberativeAttentionRequirement, ...],
    assisted: tuple[RunnableAttentionRequirement, ...],
    mechanical: tuple[RunnableAttentionRequirement, ...],
    checker_registry: CheckerRunnerRegistry | None,
    detector_registry: DetectorRunnerRegistry | None,
) -> AttentionRequirements:
    """Issue one immutable requirement aggregate after complete derivation."""
    requirements = object.__new__(AttentionRequirements)
    object.__setattr__(requirements, "resolution", resolution)
    object.__setattr__(requirements, "deliberative", deliberative)
    object.__setattr__(requirements, "assisted", assisted)
    object.__setattr__(requirements, "mechanical", mechanical)
    object.__setattr__(requirements, "checker_registry", checker_registry)
    object.__setattr__(requirements, "detector_registry", detector_registry)
    object.__setattr__(requirements, "_issuer", _REQUIREMENTS_ISSUER)
    return requirements


def _is_issued_requirements(requirements: object) -> bool:
    """Return whether requirements carry this process's derivation authority."""
    return (
        isinstance(requirements, AttentionRequirements)
        and getattr(requirements, "_issuer", None) is _REQUIREMENTS_ISSUER
    )


def _issue_plan(
    requirements: AttentionRequirements,
    deliberative: DeliberationPacket,
    assisted: AssistedPacket,
    mechanical: MechanicalPacket,
    fixture_index: EvaluatorFixtureIndex | None,
    assurance: KnownFailureAssurance | None,
) -> AttentionPlan:
    """Issue one immutable plan after every class-specific gate passes."""
    plan = object.__new__(AttentionPlan)
    object.__setattr__(plan, "requirements", requirements)
    object.__setattr__(plan, "resolution", requirements.resolution)
    object.__setattr__(plan, "deliberative", deliberative)
    object.__setattr__(plan, "assisted", assisted)
    object.__setattr__(plan, "mechanical", mechanical)
    object.__setattr__(plan, "checker_registry", requirements.checker_registry)
    object.__setattr__(plan, "fixture_index", fixture_index)
    object.__setattr__(plan, "assurance", assurance)
    object.__setattr__(plan, "detector_registry", requirements.detector_registry)
    object.__setattr__(plan, "_issuer", _PLAN_ISSUER)
    return plan


def _is_issued_attention_plan(plan: object) -> bool:
    """Return whether a plan carries this process's planning authority."""
    return (
        isinstance(plan, AttentionPlan)
        and getattr(plan, "_issuer", None) is _PLAN_ISSUER
    )


def _key_text(key: AttentionObligationKey) -> str:
    """Return one stable diagnostic representation for an obligation key."""
    if isinstance(key, RuleCriterionKey):
        return f"rule {key.declaration!r} criterion {key.criterion!r}"
    if isinstance(key, ProcedurePredicateKey):
        return (
            f"procedure {key.declaration!r} {key.phase.value} "
            f"predicate {key.predicate!r}"
        )
    return (
        f"procedure {key.procedure!r} action {key.action!r} operation "
        f"{_reference_text(key.subject_operation)} predicate {key.predicate!r}"
    )


def _reference_text(reference: VersionedReference) -> str:
    """Return one stable exact-reference diagnostic label."""
    return f"{reference.id!r}@{reference.version}"


def _format_location(parts: tuple[str | int, ...]) -> str:
    """Format one internal structured path for a planning diagnostic."""
    location = "$"
    for part in parts:
        if isinstance(part, int):
            location += f"[{part}]"
        else:
            location += f".{part}"
    return location


def _fail(
    parts: tuple[str | int, ...],
    message: str,
    *,
    cause: Exception | None = None,
) -> NoReturn:
    """Raise one located attention-planning failure."""
    error = AttentionPlanningError(_format_location(parts), message)
    if cause is not None:
        raise error from cause
    raise error
