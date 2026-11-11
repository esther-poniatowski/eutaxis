"""Adversarial tests for effective attention requirements and packet issuance."""

from __future__ import annotations

import copy
import gc
import inspect
import pickle
import shutil
import sys
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Barrier, Event
from types import MappingProxyType
from typing import Literal, cast
from weakref import ref as weakref_ref

import pytest
import yaml

from eutaxis.declarations import (
    AssistedAttentionEntry,
    AssistedPreconditionEvidence,
    AttentionPlan,
    AttentionPlanningError,
    AttentionRequirements,
    CheckerResult,
    CheckerRunner,
    CheckerRunnerBinding,
    CompletionRequirement,
    ContextFacet,
    DeliberativeAttentionEntry,
    DetectorResult,
    DetectorRunner,
    DetectorRunnerBinding,
    EnforcementClass,
    EvaluationState,
    EvaluatorDeclaration,
    EvaluatorInput,
    EvaluatorInvocation,
    LiteralBinding,
    ManualJudgmentSubmission,
    ManualPreconditionEvidence,
    MechanicalAttentionEntry,
    MechanicalPreconditionEvidence,
    ObservationProvider,
    ObservedPreconditionEvidence,
    OperationDeclaration,
    OperationFailure,
    OperationObligationSnapshot,
    OperationPredicateEnforcement,
    OperationPredicateKey,
    OperationRunner,
    OperationRunnerBinding,
    OperationRunnerRegistry,
    PredicatePhase,
    PreparedAssistedLifecycleEvaluation,
    PreparedManualLifecycleEvaluation,
    PreparedMechanicalLifecycleEvaluation,
    PreparedProcedureAction,
    ProcedureEvaluationPlanningError,
    ProcedureEvaluatorInputProvider,
    ProcedureEvaluatorInputRequest,
    ProcedurePreconditionEvaluationPlan,
    ProcedureObligationSnapshot,
    ProcedurePredicateEnforcement,
    ProcedurePredicateKey,
    ProcedureRunPlan,
    ProcedureRunPlanningError,
    PreActionEvidenceError,
    PreActionEvidenceSession,
    PreActionEvidenceSessionState,
    ResidualJudgmentProvider,
    ResidualJudgmentRequest,
    ResidualJudgmentSubmission,
    RuleCriterionEnforcement,
    RuleCriterionKey,
    RuleObligationSnapshot,
    RunnableAttentionRequirement,
    VersionedReference,
    build_checker_runner_registry,
    build_detector_runner_registry,
    build_operation_runner_registry,
    build_observation_provider_registry,
    create_pre_action_evidence_session,
    derive_attention_requirements,
    execute_known_failure_fixtures,
    load_declaration_registry,
    load_evaluator_fixture_index,
    observe_procedure_preconditions,
    plan_attention,
    plan_procedure_precondition_evaluations,
    prepare_procedure_run,
    resolve_compilation_unit,
)
from eutaxis.declarations.catalog import (
    _build_declaration_catalog_from_registry as build_declaration_catalog,
)
from eutaxis.declarations.attention import (
    _capture_plan_authority_state,
    _capture_requirements_authority_state,
    _is_issued_attention_plan,
    _is_issued_requirements,
)
from eutaxis.declarations.models import JsonValue
from eutaxis.declarations.procedure_evaluations import (
    _is_issued_procedure_precondition_evaluation_plan,
)
from eutaxis.declarations.procedure_runs import _is_issued_procedure_run_plan
from tests._facet_authority import issue_test_composite
from eutaxis.declarations.pre_action_evidence import (
    _SESSION_CONTROLS,
    _is_issued_pre_action_evidence,
)

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY_FIXTURES = FIXTURES / "registry" / "valid"
CHECKER = VersionedReference("registry/checker", 1)
DETECTOR = VersionedReference("registry/detector", 1)
MANUAL = VersionedReference("registry/manual", 1)
CHECK_INPUT = VersionedReference("registry/check-input", 1)
WRITE = VersionedReference("registry/write", 1)
KNOWN_FAILURE = "registry/checker/known-failure"
Mode = Literal["mixed", "manual", "mechanical", "assisted", "preconditions", "none"]


class _HostileMessageError(RuntimeError):
    """Refuse string conversion to test contained public-boundary failures."""

    def __str__(self) -> str:
        raise LookupError("message unavailable")


class _UnhashableText(str):
    """Retain string behavior while refusing the schema primitive's hash."""

    __hash__ = None  # type: ignore[assignment]


class _SpoofedRevision:
    """Claim equality with every value if an unsafe comparison reaches it."""

    def __eq__(self, other: object) -> bool:
        return True


class _HostileRevision:
    """Raise if an unsafe comparison reaches the revision value."""

    def __eq__(self, other: object) -> bool:
        raise RuntimeError("revision comparison escaped")


class _SingleTraversalInputs(Mapping[object, object]):
    """Expose stable items once and fail if a consumer traverses again."""

    def __init__(self, values: Mapping[object, object]) -> None:
        self._values = dict(values)
        self.traversals = 0

    def __getitem__(self, key: object) -> object:
        return self._values[key]

    def __iter__(self):
        self.traversals += 1
        if self.traversals > 1:
            self._values.clear()
            raise RuntimeError("input mapping was traversed again")
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


class _FailingInputs(Mapping[object, object]):
    """Raise one selected failure when a consumer traverses the mapping."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def __getitem__(self, key: object) -> object:
        raise KeyError(key)

    def __iter__(self):
        raise self._error

    def __len__(self) -> int:
        return 1


class _OnePairInputs(Mapping[object, object]):
    """Expose one pair without hashing its key inside the test carrier."""

    def __init__(self, key: object, value: object) -> None:
        self._key = key
        self._value = value

    def __getitem__(self, key: object) -> object:
        return self._value

    def __iter__(self):
        yield self._key

    def __len__(self) -> int:
        return 1


def _read(root: Path, name: str) -> dict[str, object]:
    """Read one mutable YAML fixture document."""
    return yaml.safe_load((root / name).read_text(encoding="utf-8"))


def _write(root: Path, name: str, document: Mapping[str, object]) -> None:
    """Write one deterministic YAML fixture document."""
    (root / name).write_text(
        yaml.safe_dump(dict(document), sort_keys=False), encoding="utf-8"
    )


def _criterion(identifier: str, evaluator: VersionedReference) -> dict[str, object]:
    """Return one rule criterion over the fixture's base norm."""
    return {
        "id": identifier,
        "norms": ["base"],
        "evaluator": {"id": evaluator.id, "version": evaluator.version},
        "statement": f"The {identifier} obligation is satisfied",
    }


def _predicate(
    identifier: str,
    predicate_class: str,
    evaluator: VersionedReference | None,
) -> dict[str, object]:
    """Return one context predicate with an optional evaluator."""
    predicate: dict[str, object] = {
        "id": identifier,
        "class": predicate_class,
        "expression": {
            "facet": "context.available",
            "operator": "exists",
        },
    }
    if evaluator is not None:
        predicate["evaluator"] = {
            "id": evaluator.id,
            "version": evaluator.version,
        }
    return predicate


def _context() -> dict[str, object]:
    """Return the complete applicable fixture context."""
    return {
        "artifact.created": True,
        "artifact.written": True,
        "context.available": True,
        "filesystem.writable": True,
        "scope.project": True,
        "source.available": True,
        "target.codex": True,
    }


def _checker_result() -> CheckerResult:
    """Return the planted checker's declared failure result."""
    return CheckerResult(
        evaluator=CHECKER,
        input_revision="declaration-v1",
        state=EvaluationState.VIOLATED,
        evidence={"accepted": True},
    )


def _checker_result_for_input(input_data: Mapping[str, JsonValue]) -> CheckerResult:
    """Fail the known-failure fixture and satisfy ordinary candidate input."""
    sources = cast(tuple[str, ...], input_data["sources"])
    state = (
        EvaluationState.VIOLATED
        if any(source.endswith("invalid.yaml") for source in sources)
        else EvaluationState.SATISFIED
    )
    return CheckerResult(
        evaluator=CHECKER,
        input_revision="declaration-v1",
        state=state,
        evidence={"accepted": True},
    )


def _detector_result() -> DetectorResult:
    """Return one schema-valid detector carrier for registry construction."""
    return DetectorResult(
        evaluator=DETECTOR,
        input_revision="declaration-v1",
        evidence={"accepted": True},
    )


def _prepare_registry(
    tmp_path: Path,
    mode: Mode,
    *,
    checker_runner: CheckerRunner = cast(CheckerRunner, _checker_result_for_input),
    detector_runner: DetectorRunner = cast(
        DetectorRunner, lambda input_data: _detector_result()
    ),
    duplicate_preconditions: bool = False,
    local_precondition_operator: str = "exists",
    later_requirements: bool = False,
    evaluator_backed_lifecycle: bool | str = False,
    lifecycle_location: str = "invariant",
    lifecycle_timing: str | None = None,
    two_actions: bool = False,
):
    """Build one registry whose effective obligations match ``mode``."""
    root = tmp_path / "registry"
    shutil.copytree(REGISTRY_FIXTURES, root)

    manual = _read(root, "evaluator.yaml")
    if mode == "preconditions":
        manual["timing"] = "pre-action"
        _write(root, "evaluator.yaml", manual)
    checker = copy.deepcopy(manual)
    checker.update(
        {
            "id": CHECKER.id,
            "evaluator-kind": "checker",
            "coverage": "total",
            "adjudication": "authoritative",
            "known-failure-fixtures": [KNOWN_FAILURE],
            "evidence-schema": {
                "type": "object",
                "properties": {"accepted": {"type": "boolean"}},
                "required": ["accepted"],
                "additionalProperties": False,
            },
        }
    )
    _write(root, "checker.yaml", checker)
    detector = copy.deepcopy(manual)
    detector.update(
        {
            "id": DETECTOR.id,
            "evaluator-kind": "detector",
            "coverage": "partial",
            "adjudication": "candidate",
            "residual-question": "Does the candidate violate the obligation?",
            "failure-behavior": "block",
            "evidence-schema": {
                "type": "object",
                "properties": {"accepted": {"type": "boolean"}},
                "required": ["accepted"],
                "additionalProperties": False,
            },
        }
    )
    _write(root, "detector.yaml", detector)
    lifecycle_reference = None
    if lifecycle_timing is not None and evaluator_backed_lifecycle:
        lifecycle_document = copy.deepcopy(
            manual if evaluator_backed_lifecycle == "manual" else detector
        )
        lifecycle_reference = VersionedReference(
            f"registry/lifecycle-{evaluator_backed_lifecycle}", 1
        )
        lifecycle_document["id"] = lifecycle_reference.id
        lifecycle_document["timing"] = lifecycle_timing
        _write(root, "lifecycle-evaluator.yaml", lifecycle_document)

    checker_operation = _read(root, "operation.yaml")
    checker_operation.update(
        {
            "id": CHECK_INPUT.id,
            "inputs": {
                "type": "object",
                "required": ["sources", "facet-registry"],
                "properties": {
                    "sources": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                    "facet-registry": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "effects": [],
        }
    )
    _write(root, "check-input.yaml", checker_operation)

    package = _read(root, "rule-set.yaml")
    rule = cast(dict[str, object], cast(list[object], package["rules"])[0])
    if mode == "mixed":
        rule["criteria"] = [
            _criterion("manual-check", MANUAL),
            _criterion("detector-check", DETECTOR),
            _criterion("checker-check", CHECKER),
        ]
    elif mode == "manual":
        rule["criteria"] = [_criterion("manual-check", MANUAL)]
    elif mode == "mechanical":
        rule["criteria"] = [_criterion("checker-check", CHECKER)]
    elif mode == "assisted":
        rule["criteria"] = [_criterion("detector-check", DETECTOR)]
    _write(root, "rule-set.yaml", package)

    procedure = _read(root, "procedure.yaml")
    operation = _read(root, "operation.yaml")
    if mode == "mixed":
        procedure["preconditions"] = [
            _predicate("manual-precondition", "assumption", MANUAL),
            _predicate("local-precondition", "assumption", None),
        ]
        detected_invariant = _predicate("detected-invariant", "invariant", DETECTOR)
        detected_invariant["observes"] = ["registry/stable"]
        procedure["invariants"] = [detected_invariant]
        procedure["postconditions"] = [
            _predicate("checked-postcondition", "postcondition", CHECKER)
        ]
        actions = cast(list[object], procedure["actions"])
        first_action = cast(dict[str, object], actions[0])
        first_action["id"] = "write-first"
        first_action["on-success"] = "write-second"
        second_action = copy.deepcopy(first_action)
        second_action["id"] = "write-second"
        second_action["on-success"] = "checked-postcondition"
        cast(
            dict[str, object], cast(dict[str, object], second_action["with"])["content"]
        )["literal"] = "Second content"
        actions[:] = [first_action, second_action]
        procedure["entry"] = "write-first"
        operation["preconditions"] = [
            _predicate("manual-operation", "authorization", MANUAL),
            _predicate("local-operation", "authorization", None),
        ]
    elif mode == "preconditions":
        lifecycle_evaluator = None
        procedure["preconditions"] = [
            _predicate("manual-precondition", "assumption", MANUAL),
            _predicate("detected-precondition", "assumption", DETECTOR),
            _predicate("checked-precondition", "assumption", CHECKER),
            _predicate("local-precondition", "assumption", None),
        ]
        if duplicate_preconditions:
            cast(list[object], procedure["preconditions"]).extend(
                [
                    _predicate("manual-precondition-two", "assumption", MANUAL),
                    _predicate("detected-precondition-two", "assumption", DETECTOR),
                ]
            )
        if local_precondition_operator == "equals":
            local = cast(
                dict[str, object], cast(list[object], procedure["preconditions"])[3]
            )
            local["expression"] = {
                "facet": "scope.project",
                "operator": "equals",
                "value": True,
            }
        if later_requirements:
            lifecycle_evaluator = (
                MANUAL
                if evaluator_backed_lifecycle == "manual"
                else (
                    CHECKER
                    if evaluator_backed_lifecycle == "mechanical"
                    else (DETECTOR if evaluator_backed_lifecycle else None)
                )
            )
            lifecycle_evaluator = lifecycle_reference or lifecycle_evaluator
            stable = _predicate(
                "stable",
                "invariant",
                lifecycle_evaluator if lifecycle_location == "invariant" else None,
            )
            stable["observes"] = ["registry/stable"]
            procedure["invariants"] = [stable]
        else:
            procedure["invariants"] = []
        procedure["postconditions"] = [
            _predicate(
                "written",
                "postcondition",
                lifecycle_evaluator if lifecycle_location == "postcondition" else None,
            )
        ]
        operation["preconditions"] = (
            [
                _predicate(
                    "authorized",
                    "authorization",
                    (
                        lifecycle_evaluator
                        if lifecycle_location == "operation-precondition"
                        else None
                    ),
                )
            ]
            if later_requirements
            else []
        )
        if two_actions:
            actions = cast(list[object], procedure["actions"])
            first_action = cast(dict[str, object], actions[0])
            first_action["id"] = "write-first"
            first_action["on-success"] = "write-second"
            first_action["on-failure"] = {"write-failed": "write-second"}
            second_action = copy.deepcopy(first_action)
            second_action["id"] = "write-second"
            second_action["on-success"] = "written"
            second_action["on-failure"] = {"write-failed": "write-failed"}
            actions[:] = [first_action, second_action]
            procedure["entry"] = "write-first"
    else:
        procedure["preconditions"] = []
        procedure["invariants"] = []
        procedure["postconditions"] = [_predicate("written", "postcondition", None)]
        operation["preconditions"] = []
    _write(root, "procedure.yaml", procedure)
    _write(root, "operation.yaml", operation)

    manifest = _read(root, "manifest.yaml")
    section = cast(dict[str, object], cast(list[object], manifest["sections"])[0])
    if mode == "none":
        section["declarations"] = ["content/write"]
        procedure["relations"] = []
        _write(root, "procedure.yaml", procedure)
    elif mode in {"mixed", "preconditions"}:
        section["declarations"] = ["content/package", "content/write"]
    else:
        section["declarations"] = ["content/package"]
    manifest["policies"] = []
    _write(root, "manifest.yaml", manifest)

    declarations = load_declaration_registry(
        tuple(sorted(root.glob("*.yaml"))), issue_test_composite()
    )
    resolution = resolve_compilation_unit(declarations, "registry/manifest", _context())
    checker_registry = None
    if mode in {"mixed", "mechanical", "preconditions"}:
        checker_registry = build_checker_runner_registry(
            declarations,
            [
                CheckerRunnerBinding(
                    CHECKER,
                    CHECK_INPUT,
                    checker_runner,
                )
            ],
        )
    detector_registry = None
    if mode in {"mixed", "assisted", "preconditions"}:
        detector_bindings = [
            DetectorRunnerBinding(
                DETECTOR,
                WRITE,
                detector_runner,
            )
        ]
        if lifecycle_reference is not None and evaluator_backed_lifecycle is True:
            detector_bindings.append(
                DetectorRunnerBinding(
                    lifecycle_reference,
                    WRITE,
                    detector_runner,
                )
            )
        detector_registry = build_detector_runner_registry(
            declarations,
            detector_bindings,
        )
    return root, declarations, resolution, checker_registry, detector_registry


def _fixture_index(tmp_path: Path, checker_registry):
    """Create one loader-issued fixture index for the planted checker."""
    root = tmp_path / "evaluator-fixtures"
    resources = root / "resources"
    resources.mkdir(parents=True)
    (resources / "invalid.yaml").write_text("invalid: true\n", encoding="utf-8")
    (resources / "facets.yaml").write_text("facets: []\n", encoding="utf-8")
    descriptor = root / "known-failure.yaml"
    descriptor.write_text(
        yaml.safe_dump(
            {
                "schema-version": 1,
                "id": KNOWN_FAILURE,
                "evaluator": {"id": CHECKER.id, "version": CHECKER.version},
                "input-revision": "declaration-v1",
                "input": {
                    "sources": ["resources/invalid.yaml"],
                    "facet-registry": "resources/facets.yaml",
                },
                "expected-state": "violated",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return load_evaluator_fixture_index(
        [descriptor], root=root, input_contracts=checker_registry.input_contracts
    )


def _inputs(requirements: AttentionRequirements):
    """Return exact valid inputs discovered from issued requirements."""
    supplied = {}
    for requirement in requirements.assisted:
        supplied[requirement.key] = EvaluatorInput(
            "declaration-v1", {"path": "artifact.txt", "content": "candidate"}
        )
    for requirement in requirements.mechanical:
        supplied[requirement.key] = EvaluatorInput(
            "declaration-v1",
            {"sources": ["candidate.yaml"], "facet-registry": "facets.yaml"},
        )
    return supplied


def _mixed_plan(tmp_path: Path):
    """Build one complete mixed-class plan and all retained authorities."""
    root, declarations, resolution, checker_registry, detector_registry = (
        _prepare_registry(tmp_path, "mixed")
    )
    assert checker_registry is not None and detector_registry is not None
    requirements = derive_attention_requirements(
        resolution,
        checker_registry=checker_registry,
        detector_registry=detector_registry,
    )
    fixtures = _fixture_index(tmp_path, checker_registry)
    assurance = execute_known_failure_fixtures(declarations, fixtures, checker_registry)
    plan = plan_attention(
        requirements,
        _inputs(requirements),
        fixture_index=fixtures,
        assurance=assurance,
    )
    return root, requirements, fixtures, assurance, plan


def _procedure_run(
    attention: AttentionPlan,
    operation_runner: OperationRunner = cast(
        OperationRunner, lambda input_data: OperationFailure(WRITE, "write-failed")
    ),
) -> ProcedureRunPlan:
    """Prepare one content/write run under ``attention``."""
    operation_registry = build_operation_runner_registry(
        attention.resolution.registry,
        [
            OperationRunnerBinding(
                WRITE,
                cast(
                    OperationRunner,
                    operation_runner,
                ),
            )
        ],
    )
    return prepare_procedure_run(
        attention, "content/write", {"path": "artifact.txt"}, operation_registry
    )


def _precondition_run(
    tmp_path: Path,
    *,
    checker_runner: CheckerRunner = cast(CheckerRunner, _checker_result_for_input),
    detector_runner: DetectorRunner = cast(
        DetectorRunner, lambda input_data: _detector_result()
    ),
    duplicate_preconditions: bool = False,
    local_precondition_operator: str = "exists",
    later_requirements: bool = False,
    evaluator_backed_lifecycle: bool | str = False,
    lifecycle_location: str = "invariant",
    lifecycle_timing: str | None = None,
    two_actions: bool = False,
    operation_runner: OperationRunner = cast(
        OperationRunner, lambda input_data: OperationFailure(WRITE, "write-failed")
    ),
):
    """Build one prepared run with every evaluator enforcement class."""
    root, declarations, resolution, checker_registry, detector_registry = (
        _prepare_registry(
            tmp_path,
            "preconditions",
            checker_runner=checker_runner,
            detector_runner=detector_runner,
            duplicate_preconditions=duplicate_preconditions,
            local_precondition_operator=local_precondition_operator,
            later_requirements=later_requirements,
            evaluator_backed_lifecycle=evaluator_backed_lifecycle,
            lifecycle_location=lifecycle_location,
            lifecycle_timing=lifecycle_timing,
            two_actions=two_actions,
        )
    )
    assert checker_registry is not None and detector_registry is not None
    requirements = derive_attention_requirements(
        resolution,
        checker_registry=checker_registry,
        detector_registry=detector_registry,
    )
    fixtures = _fixture_index(tmp_path, checker_registry)
    assurance = execute_known_failure_fixtures(declarations, fixtures, checker_registry)
    attention = plan_attention(
        requirements,
        _inputs(requirements),
        fixture_index=fixtures,
        assurance=assurance,
    )
    return root, fixtures, assurance, _procedure_run(attention, operation_runner)


def _provider_inputs(
    run: ProcedureRunPlan,
) -> dict[ProcedurePredicateKey, EvaluatorInput]:
    """Recover exact public inputs from the run's retained attention packets."""
    result: dict[ProcedurePredicateKey, EvaluatorInput] = {}
    for assisted_entry in run.attention.assisted.entries:
        if type(assisted_entry.obligation.key) is ProcedurePredicateKey:
            result[cast(ProcedurePredicateKey, assisted_entry.obligation.key)] = (
                EvaluatorInput(
                    assisted_entry.invocation.input_revision,
                    assisted_entry.invocation.input_data,
                )
            )
    for mechanical_entry in run.attention.mechanical.entries:
        if type(mechanical_entry.key) is ProcedurePredicateKey:
            result[cast(ProcedurePredicateKey, mechanical_entry.key)] = EvaluatorInput(
                mechanical_entry.invocation.input_revision,
                mechanical_entry.invocation.input_data,
            )
    return result


def test_procedure_run_preflight_retains_authorities_inputs_and_requirements(
    tmp_path: Path,
) -> None:
    _, requirements, _, _, attention = _mixed_plan(tmp_path)

    def runner(input_data: Mapping[str, JsonValue], /) -> OperationFailure:
        return OperationFailure(WRITE, "write-failed")

    operation_registry = build_operation_runner_registry(
        attention.resolution.registry,
        [OperationRunnerBinding(WRITE, cast(OperationRunner, runner))],
    )
    source_parameters = {"path": "artifact.txt"}
    first = prepare_procedure_run(
        attention, "content/write", source_parameters, operation_registry
    )
    second = prepare_procedure_run(
        attention, "content/write", {"path": "artifact.txt"}, operation_registry
    )

    assert first is not second
    assert first != second
    assert _is_issued_procedure_run_plan(first)
    source_parameters["path"] = "changed.txt"
    assert first.attention is attention
    assert first.operation_registry is operation_registry
    assert (
        first.procedure
        is attention.resolution.registry.records["content/write"].declaration
    )
    assert first.parameters == {"path": "artifact.txt"}
    assert tuple(item.key for item in first.requirements) == tuple(
        item.key
        for item in requirements.completion
        if isinstance(item.key, (ProcedurePredicateKey, OperationPredicateKey))
        and (
            getattr(item.key, "declaration", None) == "content/write"
            or getattr(item.key, "procedure", None) == "content/write"
        )
    )
    expected_requirements = tuple(
        item
        for item in requirements.completion
        if isinstance(item.key, (ProcedurePredicateKey, OperationPredicateKey))
        and (
            getattr(item.key, "declaration", None) == "content/write"
            or getattr(item.key, "procedure", None) == "content/write"
        )
    )
    assert all(
        actual is expected
        for actual, expected in zip(first.requirements, expected_requirements)
    )
    assert any(
        isinstance(item.key, ProcedurePredicateKey)
        and item.key.phase is PredicatePhase.POSTCONDITION
        and item.evaluator is not None
        for item in first.requirements
    )
    assert all(item.evaluator is None for item in first.executable_requirements)
    assert all(
        not (
            isinstance(item.key, ProcedurePredicateKey)
            and item.key.phase is PredicatePhase.POSTCONDITION
        )
        for item in first.pre_action_requirements
    )
    assert all(
        item.evaluator is not None
        for item in first.evaluator_backed_pre_action_requirements
    )
    assert len(first.procedure_precondition_requirements) == 2
    assert all(
        actual is expected
        for actual, expected in zip(
            first.procedure_precondition_requirements,
            first.requirements[:2],
        )
    )
    assert len(first.evaluator_backed_procedure_precondition_requirements) == 1
    assert first.evaluator_backed_procedure_precondition_requirements[0] is (
        first.requirements[0]
    )
    assert any(
        isinstance(item.key, OperationPredicateKey)
        for item in first.pre_action_requirements
    )
    assert any(
        isinstance(item.key, ProcedurePredicateKey)
        and item.key.phase is PredicatePhase.INVARIANT
        for item in first.pre_action_requirements
    )
    assert [item.node.id for item in first.actions] == ["write-first", "write-second"]
    lifecycle_requirements = tuple(
        (index, item)
        for index, item in enumerate(first.requirements)
        if item.evaluator is not None
        and (
            isinstance(item.key, OperationPredicateKey)
            or (
                isinstance(item.key, ProcedurePredicateKey)
                and item.key.phase
                in {PredicatePhase.INVARIANT, PredicatePhase.POSTCONDITION}
            )
        )
    )
    assert tuple(type(item) for item in first.lifecycle_evaluations) == (
        PreparedManualLifecycleEvaluation,
        PreparedManualLifecycleEvaluation,
        PreparedAssistedLifecycleEvaluation,
        PreparedMechanicalLifecycleEvaluation,
    )
    assert tuple(item.ordinal for item in first.lifecycle_evaluations) == tuple(
        index for index, _ in lifecycle_requirements
    )
    assert all(
        item.source_requirement is requirement
        and item.source_key is requirement.key
        and item.requirement is not requirement
        and item.requirement.key == requirement.key
        and item.evaluator is not requirement.evaluator
        and item.requirement.evaluator is item.evaluator
        for item, (_, requirement) in zip(
            first.lifecycle_evaluations, lifecycle_requirements
        )
    )
    assert first.actions[0].contract is first.actions[1].contract
    assert first.actions[0].input_data == {
        "path": "artifact.txt",
        "content": "Reviewed content",
    }
    assert first.actions[1].input_data == {
        "path": "artifact.txt",
        "content": "Second content",
    }
    with pytest.raises(TypeError, match="issued by preflight"):
        ProcedureRunPlan()
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(first)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.deepcopy(first)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(first)
    reconstructed = object.__new__(ProcedureRunPlan)
    for field in (
        "attention",
        "operation_registry",
        "procedure",
        "parameters",
        "requirements",
        "executable_requirements",
        "pre_action_requirements",
        "evaluator_backed_pre_action_requirements",
        "procedure_precondition_requirements",
        "evaluator_backed_procedure_precondition_requirements",
        "actions",
        "lifecycle_evaluations",
    ):
        object.__setattr__(reconstructed, field, getattr(first, field))
    assert not _is_issued_procedure_run_plan(reconstructed)


def test_procedure_run_lifecycle_authority_rejects_origin_and_snapshot_mutation(
    tmp_path: Path,
) -> None:
    _, _, _, _, packet_attention = _mixed_plan(tmp_path / "packet")
    packet_run = _procedure_run(packet_attention)
    assisted = next(
        item
        for item in packet_run.lifecycle_evaluations
        if type(item) is PreparedAssistedLifecycleEvaluation
    )
    object.__setattr__(assisted.source_entry, "residual_question", "changed")
    assert not _is_issued_procedure_run_plan(packet_run)

    _, _, _, _, detached_attention = _mixed_plan(tmp_path / "detached")
    detached_run = _procedure_run(detached_attention)
    detached = detached_run.lifecycle_evaluations[0]
    object.__setattr__(detached.evaluator, "timing", "pre-design")
    assert not _is_issued_procedure_run_plan(detached_run)

    _, _, _, _, registry_attention = _mixed_plan(tmp_path / "registry")
    registry_run = _procedure_run(registry_attention)
    detector_registry = registry_attention.detector_registry
    assert detector_registry is not None
    object.__setattr__(
        detector_registry,
        "bindings",
        MappingProxyType(dict(detector_registry.bindings)),
    )
    assert not _is_issued_procedure_run_plan(registry_run)

    _, _, _, _, missing_attention = _mixed_plan(tmp_path / "missing-registry")
    missing_run = _procedure_run(missing_attention)
    object.__setattr__(missing_attention, "detector_registry", None)
    assert not _is_issued_procedure_run_plan(missing_run)

    _, _, _, _, equal_attention = _mixed_plan(tmp_path / "equal-registry")
    equal_run = _procedure_run(equal_attention)
    equal_origin = equal_attention.detector_registry
    assert equal_origin is not None
    equal_registry = build_detector_runner_registry(
        equal_origin.declarations, equal_origin.bindings.values()
    )
    object.__setattr__(equal_attention, "detector_registry", equal_registry)
    assert not _is_issued_procedure_run_plan(equal_run)

    _, _, _, _, foreign_attention = _mixed_plan(tmp_path / "foreign-registry")
    foreign_run = _procedure_run(foreign_attention)
    _, _, _, _, other_attention = _mixed_plan(tmp_path / "other-registry")
    object.__setattr__(
        foreign_attention, "detector_registry", other_attention.detector_registry
    )
    assert not _is_issued_procedure_run_plan(foreign_run)


@pytest.mark.parametrize(
    "field",
    (
        "requirement",
        "evaluator",
        "invocation",
        "input_schema",
        "evidence_schema",
        "lifecycle_evaluations",
    ),
)
def test_procedure_run_lifecycle_authority_rejects_equal_value_replacement(
    tmp_path: Path, field: str
) -> None:
    _, _, _, _, attention = _mixed_plan(tmp_path / field)
    run = _procedure_run(attention)
    if field == "lifecycle_evaluations":
        object.__setattr__(run, field, tuple(list(run.lifecycle_evaluations)))
    else:
        item = next(
            candidate
            for candidate in run.lifecycle_evaluations
            if hasattr(candidate, field)
        )
        value = getattr(item, field)
        replacement = (
            MappingProxyType(dict(value))
            if isinstance(value, Mapping)
            else replace(value)
        )
        object.__setattr__(item, field, replacement)
    assert not _is_issued_procedure_run_plan(run)


def test_procedure_run_preflight_retains_evaluatorless_postconditions(
    tmp_path: Path,
) -> None:
    _, declarations, resolution, _, _ = _prepare_registry(tmp_path, "none")
    requirements = derive_attention_requirements(resolution)
    attention = plan_attention(requirements, {})
    operation_registry = build_operation_runner_registry(
        declarations,
        [
            OperationRunnerBinding(
                WRITE,
                cast(
                    OperationRunner,
                    lambda input_data: OperationFailure(WRITE, "write-failed"),
                ),
            )
        ],
    )

    run = prepare_procedure_run(
        attention, "content/write", {"path": "artifact.txt"}, operation_registry
    )

    assert run.requirements == run.executable_requirements
    assert any(
        isinstance(item.key, ProcedurePredicateKey)
        and item.key.phase is PredicatePhase.POSTCONDITION
        for item in run.executable_requirements
    )


def test_procedure_run_preflight_rejects_authority_and_input_defects(
    tmp_path: Path,
) -> None:
    _, _, _, _, attention = _mixed_plan(tmp_path / "primary")
    _, foreign_declarations, _, _, _ = _prepare_registry(tmp_path / "foreign", "none")
    runner = cast(
        OperationRunner,
        lambda input_data: OperationFailure(WRITE, "write-failed"),
    )
    foreign_registry = build_operation_runner_registry(
        foreign_declarations, [OperationRunnerBinding(WRITE, runner)]
    )
    valid_registry = build_operation_runner_registry(
        attention.resolution.registry, [OperationRunnerBinding(WRITE, runner)]
    )
    empty_registry = build_operation_runner_registry(attention.resolution.registry, [])

    forged_attention = object.__new__(AttentionPlan)
    object.__setattr__(forged_attention, "_issuer", object())
    with pytest.raises(ProcedureRunPlanningError) as bad_attention:
        prepare_procedure_run(
            forged_attention,
            "content/write",
            {"path": "artifact.txt"},
            valid_registry,
        )
    assert bad_attention.value.location == "$.attention"

    forged_registry = object.__new__(OperationRunnerRegistry)
    object.__setattr__(forged_registry, "_issuer", object())
    with pytest.raises(ProcedureRunPlanningError) as bad_registry:
        prepare_procedure_run(
            attention,
            "content/write",
            {"path": "artifact.txt"},
            forged_registry,
        )
    assert bad_registry.value.location == "$.operation-registry"

    with pytest.raises(ProcedureRunPlanningError) as cross_registry:
        prepare_procedure_run(
            attention,
            "content/write",
            {"path": "artifact.txt"},
            foreign_registry,
        )
    assert cross_registry.value.location == "$.operation-registry"

    with pytest.raises(ProcedureRunPlanningError) as missing_runner:
        prepare_procedure_run(
            attention, "content/write", {"path": "artifact.txt"}, empty_registry
        )
    assert missing_runner.value.location == "$.actions[0].operation"

    for parameters in ({}, {"path": "artifact.txt", "extra": True}):
        with pytest.raises(ProcedureRunPlanningError) as invalid_parameters:
            prepare_procedure_run(
                attention, "content/write", parameters, valid_registry
            )
        assert invalid_parameters.value.location.startswith("$.parameters")

    cyclic: dict[str, object] = {}
    cyclic["path"] = cyclic
    with pytest.raises(ProcedureRunPlanningError) as cyclic_parameters:
        prepare_procedure_run(attention, "content/write", cyclic, valid_registry)
    assert cyclic_parameters.value.location == "$.parameters"

    for identifier in ("registry/manual", "content/base"):
        with pytest.raises(ProcedureRunPlanningError) as wrong_procedure:
            prepare_procedure_run(
                attention,
                identifier,
                {"path": "artifact.txt"},
                valid_registry,
            )
        assert wrong_procedure.value.location == "$.procedure"


def test_mixed_plan_preserves_complete_context_order_and_authority(
    tmp_path: Path,
) -> None:
    root, requirements, fixtures, assurance, plan = _mixed_plan(tmp_path)

    assert _is_issued_attention_plan(plan)
    assert plan.requirements is requirements
    assert plan.resolution is requirements.resolution
    assert plan.resolution.trace is requirements.resolution.trace
    assert plan.checker_registry is requirements.checker_registry
    assert plan.detector_registry is requirements.detector_registry
    assert plan.fixture_index is fixtures
    assert plan.assurance is assurance
    assert all(
        isinstance(item, CompletionRequirement) for item in requirements.completion
    )
    assert tuple(item.key for item in requirements.completion) == (
        RuleCriterionKey("content/base", "manual-check"),
        RuleCriterionKey("content/base", "detector-check"),
        RuleCriterionKey("content/base", "checker-check"),
        ProcedurePredicateKey(
            "content/write", PredicatePhase.PRECONDITION, "manual-precondition"
        ),
        ProcedurePredicateKey(
            "content/write", PredicatePhase.PRECONDITION, "local-precondition"
        ),
        OperationPredicateKey(
            "content/write", "write-first", WRITE, "manual-operation"
        ),
        OperationPredicateKey("content/write", "write-first", WRITE, "local-operation"),
        OperationPredicateKey(
            "content/write", "write-second", WRITE, "manual-operation"
        ),
        OperationPredicateKey(
            "content/write", "write-second", WRITE, "local-operation"
        ),
        ProcedurePredicateKey(
            "content/write", PredicatePhase.INVARIANT, "detected-invariant"
        ),
        ProcedurePredicateKey(
            "content/write", PredicatePhase.POSTCONDITION, "checked-postcondition"
        ),
    )
    evaluator_less = (
        requirements.completion[4],
        requirements.completion[6],
        requirements.completion[8],
    )
    assert all(item.evaluator is None for item in evaluator_less)
    assert all(item.enforcement is None for item in evaluator_less)
    assert isinstance(evaluator_less[0].obligation, ProcedureObligationSnapshot)
    assert isinstance(evaluator_less[1].obligation, OperationObligationSnapshot)
    assert isinstance(evaluator_less[2].obligation, OperationObligationSnapshot)
    local_procedure = cast(ProcedureObligationSnapshot, evaluator_less[0].obligation)
    assert local_procedure.phase is PredicatePhase.PRECONDITION
    assert local_procedure.predicate.id == "local-precondition"
    assert local_procedure.purpose == "Writes one registry fixture artifact"
    assert local_procedure.parameters["required"] == ("path",)
    local_operations = tuple(
        cast(OperationObligationSnapshot, item.obligation)
        for item in evaluator_less[1:]
    )
    assert tuple(item.action.id for item in local_operations) == (
        "write-first",
        "write-second",
    )
    assert all(item.predicate.id == "local-operation" for item in local_operations)
    assert all(
        item.operation_inputs["required"] == ("path", "content")
        for item in local_operations
    )
    assert all(
        item.operation_method
        == "Write the bound content and inspect the resulting artifact."
        for item in local_operations
    )
    assert all(
        item.procedure_parameters["required"] == ("path",) for item in local_operations
    )
    assert all(
        item.operation_effects == ("filesystem/artifact",) for item in local_operations
    )
    assert all(item.failure_outcomes == ("write-failed",) for item in local_operations)
    assert all(
        item.recovery == "Preserve the prior artifact" for item in local_operations
    )
    class_keys = {
        EnforcementClass.DELIBERATIVE: tuple(
            item.key for item in requirements.deliberative
        ),
        EnforcementClass.ASSISTED: tuple(item.key for item in requirements.assisted),
        EnforcementClass.MECHANICAL: tuple(
            item.key for item in requirements.mechanical
        ),
    }
    for enforcement, keys in class_keys.items():
        assert keys == tuple(
            item.key
            for item in requirements.completion
            if item.enforcement is enforcement
        )
    completion_by_key = {item.key: item for item in requirements.completion}
    for projected in (
        *requirements.deliberative,
        *requirements.assisted,
        *requirements.mechanical,
    ):
        canonical = completion_by_key[projected.key]
        assert projected.obligation is canonical.obligation
        assert projected.evaluator is canonical.evaluator
        if isinstance(projected, RunnableAttentionRequirement):
            assert projected.enforcement is canonical.enforcement
    assert tuple(type(item) for item in plan.deliberative.entries) == (
        DeliberativeAttentionEntry,
        DeliberativeAttentionEntry,
        DeliberativeAttentionEntry,
        DeliberativeAttentionEntry,
    )
    assert tuple(item.obligation.key for item in plan.deliberative.entries) == (
        RuleCriterionKey("content/base", "manual-check"),
        ProcedurePredicateKey(
            "content/write", PredicatePhase.PRECONDITION, "manual-precondition"
        ),
        OperationPredicateKey(
            "content/write", "write-first", WRITE, "manual-operation"
        ),
        OperationPredicateKey(
            "content/write", "write-second", WRITE, "manual-operation"
        ),
    )
    operation = cast(
        OperationObligationSnapshot, plan.deliberative.entries[2].obligation
    )
    assert operation.procedure_parameters["required"] == ("path",)
    assert operation.action.bindings["path"].parameter == "path"  # type: ignore[union-attr]
    assert operation.operation_inputs["required"] == ("path", "content")
    second_operation = cast(
        OperationObligationSnapshot, plan.deliberative.entries[3].obligation
    )
    assert second_operation.action.id == "write-second"

    assert tuple(type(item) for item in plan.assisted.entries) == (
        AssistedAttentionEntry,
        AssistedAttentionEntry,
    )
    assert tuple(item.obligation.key for item in plan.assisted.entries) == (
        RuleCriterionKey("content/base", "detector-check"),
        ProcedurePredicateKey(
            "content/write", PredicatePhase.INVARIANT, "detected-invariant"
        ),
    )
    assert all(
        item.residual_question == "Does the candidate violate the obligation?"
        for item in plan.assisted.entries
    )
    assert tuple(type(item) for item in plan.mechanical.entries) == (
        MechanicalAttentionEntry,
        MechanicalAttentionEntry,
    )
    assert tuple(item.key for item in plan.mechanical.entries) == (
        RuleCriterionKey("content/base", "checker-check"),
        ProcedurePredicateKey(
            "content/write", PredicatePhase.POSTCONDITION, "checked-postcondition"
        ),
    )
    assert "accepted" in cast(
        Mapping[str, object], plan.mechanical.entries[0].evidence_schema["properties"]
    )
    assert plan.mechanical.entries[0].invocation.input_data["sources"] == (
        "candidate.yaml",
    )
    assert plan.assisted.entries[0].invocation.input_data["path"] == "artifact.txt"
    assert root.is_dir()


@pytest.mark.parametrize(
    ("mode", "counts"),
    [
        ("manual", (1, 0, 0)),
        ("mechanical", (0, 0, 1)),
        ("assisted", (0, 1, 0)),
        ("none", (0, 0, 0)),
    ],
)
def test_single_and_empty_class_boundaries(
    tmp_path: Path, mode: Mode, counts: tuple[int, int, int]
) -> None:
    _, declarations, resolution, checker_registry, detector_registry = (
        _prepare_registry(tmp_path, mode)
    )
    requirements = derive_attention_requirements(
        resolution,
        checker_registry=checker_registry,
        detector_registry=detector_registry,
    )
    assert (
        len(requirements.deliberative),
        len(requirements.assisted),
        len(requirements.mechanical),
    ) == counts
    assert len(requirements.completion) == sum(counts) + (1 if mode == "none" else 0)
    if mode == "none":
        only = requirements.completion[0]
        assert only.key == ProcedurePredicateKey(
            "content/write", PredicatePhase.POSTCONDITION, "written"
        )
        assert only.evaluator is None
        assert only.enforcement is None

    fixtures = assurance = None
    if checker_registry is not None:
        fixtures = _fixture_index(tmp_path, checker_registry)
        assurance = execute_known_failure_fixtures(
            declarations, fixtures, checker_registry
        )
    plan = plan_attention(
        requirements,
        _inputs(requirements),
        fixture_index=fixtures,
        assurance=assurance,
    )
    assert (
        len(plan.deliberative.entries),
        len(plan.assisted.entries),
        len(plan.mechanical.entries),
    ) == counts
    if mode == "manual":
        entry = plan.deliberative.entries[0]
        assert isinstance(entry.obligation, RuleObligationSnapshot)
        expected = (
            resolution.registry.families[MANUAL.id].versions[MANUAL.version].declaration
        )
        assert isinstance(expected, EvaluatorDeclaration)
        assert entry.evaluator is expected
        assert VersionedReference(entry.evaluator.id, entry.evaluator.version) == MANUAL
        assert entry.evaluator.evaluator_kind == "manual"
        assert entry.evaluator.coverage == "none"
        assert entry.evaluator.adjudication == "manual"
        assert entry.evaluator.timing == "post-artifact"
        assert entry.evaluator.input_revisions == ("declaration-v1",)
        assert entry.evaluator.evidence_schema["required"] == ("conclusion",)
        assert entry.evaluator.failure_behavior == "block"


def test_completion_requirement_rejects_inconsistent_public_values(
    tmp_path: Path,
) -> None:
    _, requirements, _, _, _ = _mixed_plan(tmp_path)
    canonical = requirements.completion[0]
    unrelated = requirements.completion[1]

    with pytest.raises(ValueError, match="must have enforcement"):
        CompletionRequirement(
            canonical.key,
            canonical.obligation,
            canonical.evaluator,
            None,
        )
    with pytest.raises(ValueError, match="differs from its snapshot"):
        CompletionRequirement(
            RuleCriterionKey("other", "criterion"),
            canonical.obligation,
            canonical.evaluator,
            canonical.enforcement,
        )
    with pytest.raises(ValueError, match="snapshot declares an evaluator"):
        CompletionRequirement(
            canonical.key,
            canonical.obligation,
            None,
            None,
        )
    with pytest.raises(ValueError, match="evaluator differs from its snapshot"):
        CompletionRequirement(
            canonical.key,
            canonical.obligation,
            unrelated.evaluator,
            unrelated.enforcement,
        )


def test_requirements_are_the_authoritative_input_discovery_surface(
    tmp_path: Path,
) -> None:
    _, requirements, fixtures, assurance, _ = _mixed_plan(tmp_path)
    supplied = _inputs(requirements)
    missing_key = requirements.assisted[0].key
    missing = dict(supplied)
    del missing[missing_key]
    with pytest.raises(AttentionPlanningError, match="missing evaluator input"):
        plan_attention(
            requirements, missing, fixture_index=fixtures, assurance=assurance
        )

    additional = dict(supplied)
    additional[RuleCriterionKey("stale", "criterion")] = EvaluatorInput(
        "declaration-v1", {}
    )
    with pytest.raises(AttentionPlanningError, match="unexpected evaluator input"):
        plan_attention(
            requirements, additional, fixture_index=fixtures, assurance=assurance
        )

    invalid = dict(supplied)
    invalid[requirements.assisted[0].key] = EvaluatorInput(
        "declaration-v1", {"path": "missing-content"}
    )
    with pytest.raises(AttentionPlanningError, match="operation contract"):
        plan_attention(
            requirements, invalid, fixture_index=fixtures, assurance=assurance
        )


def test_input_mapping_is_snapshotted_once_before_planning(tmp_path: Path) -> None:
    _, requirements, fixtures, assurance, _ = _mixed_plan(tmp_path)
    supplied = _SingleTraversalInputs(_inputs(requirements))

    plan = plan_attention(
        requirements,
        supplied,  # type: ignore[arg-type]
        fixture_index=fixtures,
        assurance=assurance,
    )

    assert supplied.traversals == 1
    assert len(plan.assisted.entries) == 2
    assert len(plan.mechanical.entries) == 2


def test_invalid_input_key_is_a_located_planning_error(tmp_path: Path) -> None:
    _, requirements, fixtures, assurance, _ = _mixed_plan(tmp_path)
    supplied: dict[object, object] = dict(_inputs(requirements))
    supplied["not-an-obligation-key"] = EvaluatorInput("declaration-v1", {})

    with pytest.raises(
        AttentionPlanningError, match="input key must identify"
    ) as captured:
        plan_attention(
            requirements,
            supplied,  # type: ignore[arg-type]
            fixture_index=fixtures,
            assurance=assurance,
        )

    assert captured.value.location.endswith("[4].key")


@pytest.mark.parametrize(
    ("key", "field"),
    [
        (
            ProcedurePredicateKey(
                "content/write", cast(PredicatePhase, "wrong"), "written"
            ),
            "phase",
        ),
        (
            OperationPredicateKey(
                "content/write",
                "write",
                VersionedReference("registry/write", 0),
                "authorized",
            ),
            "subject-operation.version",
        ),
        (
            RuleCriterionKey(cast(str, ["content/base"]), "manual-check"),
            "declaration",
        ),
        (
            RuleCriterionKey(
                cast(str, _UnhashableText("content/base")), "manual-check"
            ),
            "declaration",
        ),
    ],
)
def test_malformed_input_key_fields_are_located_before_hashing(
    tmp_path: Path, key: object, field: str
) -> None:
    _, requirements, fixtures, assurance, _ = _mixed_plan(tmp_path)

    with pytest.raises(AttentionPlanningError) as captured:
        plan_attention(
            requirements,
            _OnePairInputs(key, EvaluatorInput("declaration-v1", {})),  # type: ignore[arg-type]
            fixture_index=fixtures,
            assurance=assurance,
        )

    assert captured.value.location.endswith(field)


def test_input_mapping_traversal_failure_is_contained(tmp_path: Path) -> None:
    _, requirements, fixtures, assurance, _ = _mixed_plan(tmp_path)

    with pytest.raises(AttentionPlanningError, match="RuntimeError: traversal failed"):
        plan_attention(
            requirements,
            _FailingInputs(RuntimeError("traversal failed")),  # type: ignore[arg-type]
            fixture_index=fixtures,
            assurance=assurance,
        )


def test_hostile_input_mapping_failure_is_contained(tmp_path: Path) -> None:
    _, requirements, fixtures, assurance, _ = _mixed_plan(tmp_path)

    with pytest.raises(
        AttentionPlanningError,
        match="HostileMessageError; message formatting raised LookupError",
    ):
        plan_attention(
            requirements,
            _FailingInputs(_HostileMessageError()),  # type: ignore[arg-type]
            fixture_index=fixtures,
            assurance=assurance,
        )


def test_stale_fixture_blocks_plan_after_assurance_issuance(tmp_path: Path) -> None:
    _, requirements, fixtures, assurance, _ = _mixed_plan(tmp_path)
    fixture = fixtures.fixtures[KNOWN_FAILURE]
    source = next(digest.path for digest in fixture.digests if digest.role == "source")
    source.write_text("changed: true\n", encoding="utf-8")

    with pytest.raises(AttentionPlanningError, match="changed after") as captured:
        plan_attention(
            requirements,
            _inputs(requirements),
            fixture_index=fixtures,
            assurance=assurance,
        )
    assert captured.value.location == "$.assurance"


def test_catalog_and_requirements_share_every_effective_locator(tmp_path: Path) -> None:
    root, requirements, _, _, _ = _mixed_plan(tmp_path)
    catalog = build_declaration_catalog(
        requirements.resolution.registry, source_root=root
    )
    effective_keys = tuple(
        item.key
        for items in (
            requirements.deliberative,
            requirements.assisted,
            requirements.mechanical,
        )
        for item in items
    )
    effective_declarations = {
        key.declaration
        for key in effective_keys
        if isinstance(key, (RuleCriterionKey, ProcedurePredicateKey))
    }
    effective_operations = {
        key.subject_operation
        for key in effective_keys
        if isinstance(key, OperationPredicateKey)
    }
    catalog_coordinates: set[object] = set()
    coordinate: object
    for enforcement in EnforcementClass:
        for locator in catalog.filter_enforcement(enforcement):
            if isinstance(locator, RuleCriterionEnforcement):
                if locator.declaration not in effective_declarations:
                    continue
                coordinate = (locator.declaration, locator.criterion)
            elif isinstance(locator, ProcedurePredicateEnforcement):
                if locator.declaration not in effective_declarations:
                    continue
                coordinate = (
                    locator.declaration,
                    locator.phase,
                    locator.predicate,
                )
            elif isinstance(locator, OperationPredicateEnforcement):
                if locator.operation not in effective_operations:
                    continue
                coordinate = (locator.operation, locator.predicate)
            else:
                raise AssertionError(f"Unexpected enforcement locator: {locator!r}")
            catalog_coordinates.add(coordinate)

    effective_coordinates = {
        (
            (key.declaration, key.criterion)
            if isinstance(key, RuleCriterionKey)
            else (
                (key.declaration, key.phase, key.predicate)
                if isinstance(key, ProcedurePredicateKey)
                else (key.subject_operation, key.predicate)
            )
        )
        for key in effective_keys
    }
    assert effective_coordinates == catalog_coordinates


def test_private_aggregates_reject_forgery_copying_and_serialization(
    tmp_path: Path,
) -> None:
    _, requirements, _, _, plan = _mixed_plan(tmp_path)
    with pytest.raises(TypeError, match="issued by requirement derivation"):
        AttentionRequirements()
    with pytest.raises(TypeError, match="issued by attention planning"):
        AttentionPlan()
    for aggregate in (requirements, plan, requirements.resolution):
        with pytest.raises(TypeError, match="cannot be copied"):
            copy.copy(aggregate)
        with pytest.raises(TypeError, match="cannot be copied"):
            copy.deepcopy(aggregate)
        with pytest.raises(TypeError, match="cannot be serialized"):
            pickle.dumps(aggregate)

    reconstructed = object.__new__(AttentionRequirements)
    with pytest.raises(AttentionPlanningError, match="not issued"):
        plan_attention(reconstructed, {})


def test_requirements_authority_cannot_self_attest_equal_value_replacement(
    tmp_path: Path,
) -> None:
    _, requirements, _, _, plan = _mixed_plan(tmp_path)
    completion = list(requirements.completion)
    completion[0] = replace(completion[0])
    object.__setattr__(requirements, "completion", tuple(completion))
    object.__setattr__(
        requirements,
        "_state",
        _capture_requirements_authority_state(requirements),
    )

    assert not _is_issued_requirements(requirements)
    assert not _is_issued_attention_plan(plan)


def test_plan_authority_cannot_self_attest_equal_value_packet_replacement(
    tmp_path: Path,
) -> None:
    _, requirements, _, _, plan = _mixed_plan(tmp_path)
    entries = list(plan.assisted.entries)
    entries[0] = replace(entries[0])
    object.__setattr__(plan.assisted, "entries", tuple(entries))
    object.__setattr__(plan, "_state", _capture_plan_authority_state(plan))

    assert _is_issued_requirements(requirements)
    assert not _is_issued_attention_plan(plan)


def test_plan_authority_ignores_fixture_bytes_until_mechanical_execution(
    tmp_path: Path,
) -> None:
    _, _, fixtures, _, plan = _mixed_plan(tmp_path)
    fixture = next(iter(fixtures.fixtures.values()))
    source = next(digest.path for digest in fixture.digests if digest.role == "source")
    source.write_text("changed: true\n", encoding="utf-8")

    assert _is_issued_attention_plan(plan)


def test_plan_authority_rejects_fixture_descriptor_carrier_replacement(
    tmp_path: Path,
) -> None:
    _, _, fixtures, _, plan = _mixed_plan(tmp_path)
    fixture = next(iter(fixtures.fixtures.values()))
    replacement = Path(str(fixture.path))
    assert replacement == fixture.path and replacement is not fixture.path
    object.__setattr__(fixture, "path", replacement)

    assert not _is_issued_attention_plan(plan)


def test_plan_authority_ignores_stateful_runner_internal_state(tmp_path: Path) -> None:
    @dataclass
    class StatefulChecker:
        calls: int = 0

        def __call__(self, input_data):
            self.calls += 1
            return _checker_result_for_input(input_data)

    @dataclass
    class StatefulDetector:
        calls: int = 0

        def __call__(self, input_data):
            self.calls += 1
            return _detector_result()

    checker = StatefulChecker()
    detector = StatefulDetector()
    _, _, _, run = _precondition_run(
        tmp_path,
        checker_runner=cast(CheckerRunner, checker),
        detector_runner=cast(DetectorRunner, detector),
    )

    checker.calls += 1
    detector.calls += 1

    assert _is_issued_attention_plan(run.attention)


@pytest.mark.parametrize("aggregate", ["requirements", "plan"])
def test_attention_authority_rejects_token_replacement(
    tmp_path: Path, aggregate: str
) -> None:
    _, requirements, _, _, plan = _mixed_plan(tmp_path)
    target = requirements if aggregate == "requirements" else plan
    object.__setattr__(target, "_token", object())

    validator = (
        _is_issued_requirements
        if aggregate == "requirements"
        else _is_issued_attention_plan
    )
    assert not validator(target)


def test_irrelevant_runner_authority_is_rejected_for_empty_class(
    tmp_path: Path,
) -> None:
    _, _, resolution, _, _ = _prepare_registry(tmp_path / "manual", "manual")
    _, _, _, checker_registry, detector_registry = _prepare_registry(
        tmp_path / "mixed", "mixed"
    )
    assert checker_registry is not None and detector_registry is not None

    with pytest.raises(AttentionPlanningError, match="empty class"):
        derive_attention_requirements(resolution, checker_registry=checker_registry)
    with pytest.raises(AttentionPlanningError, match="empty class"):
        derive_attention_requirements(resolution, detector_registry=detector_registry)


def test_precondition_evaluation_plan_correlates_exact_run_and_requests(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    supplied = _provider_inputs(run)
    mutable_inputs: dict[ProcedurePredicateKey, dict[str, object]] = {
        key: dict(value.input_data) for key, value in supplied.items()
    }
    requests: dict[ProcedurePredicateKey, ProcedureEvaluatorInputRequest] = {}
    calls: dict[ProcedurePredicateKey, int] = {}
    providers: dict[ProcedurePredicateKey, ProcedureEvaluatorInputProvider] = {}
    for key, value in supplied.items():

        def provider(
            request: ProcedureEvaluatorInputRequest,
            /,
            *,
            provider_key: ProcedurePredicateKey = key,
            revision: str = value.input_revision,
        ) -> EvaluatorInput:
            calls[provider_key] = calls.get(provider_key, 0) + 1
            requests[provider_key] = request
            return EvaluatorInput(revision, mutable_inputs[provider_key])

        providers[key] = provider

    plan = plan_procedure_precondition_evaluations(run, providers)

    expected = tuple(
        item
        for item in run.requirements
        if item.evaluator is not None
        and type(item.key) is ProcedurePredicateKey
        and cast(ProcedurePredicateKey, item.key).phase is PredicatePhase.PRECONDITION
    )
    assert _is_issued_procedure_precondition_evaluation_plan(plan)
    assert plan.run is run
    assert plan.phase is PredicatePhase.PRECONDITION
    assert plan.occurrence == 0
    assert tuple(record.requirement for record in plan.records) == expected
    assert [record.requirement.enforcement for record in plan.records] == [
        EnforcementClass.DELIBERATIVE,
        EnforcementClass.ASSISTED,
        EnforcementClass.MECHANICAL,
    ]
    assert len(plan.manual) == len(plan.assisted) == len(plan.mechanical) == 1
    assert set(calls.values()) == {1}
    assert set(requests) == set(supplied)
    for requirement in expected:
        if requirement.enforcement is EnforcementClass.DELIBERATIVE:
            continue
        key = cast(ProcedurePredicateKey, requirement.key)
        request = requests[key]
        obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
        assert request.key == requirement.key
        assert request.key is not requirement.key
        assert request.procedure == run.procedure.id
        assert request.phase is PredicatePhase.PRECONDITION
        assert request.occurrence == 0
        assert request.parameters == run.parameters
        assert request.parameters is plan.parameters
        assert request.parameters is not run.parameters
        assert request.predicate == obligation.predicate
        assert request.predicate is not obligation.predicate

    for mutable_value in mutable_inputs.values():
        mutable_value.clear()
    assert _is_issued_procedure_precondition_evaluation_plan(plan)
    with pytest.raises(TypeError):
        plan.providers[next(iter(plan.providers))] = providers[  # type: ignore[index]
            next(iter(providers))
        ]


def test_precondition_evaluation_plan_rejects_provider_set_and_results(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    supplied = _provider_inputs(run)
    valid = {
        key: (lambda request, value=value: value) for key, value in supplied.items()
    }
    keys = tuple(supplied)

    with pytest.raises(ProcedureEvaluationPlanningError, match="missing provider"):
        plan_procedure_precondition_evaluations(run, {keys[0]: valid[keys[0]]})

    manual_key = cast(ProcedurePredicateKey, run.requirements[0].key)
    with pytest.raises(ProcedureEvaluationPlanningError, match="unexpected provider"):
        plan_procedure_precondition_evaluations(
            run, {**valid, manual_key: valid[keys[0]]}
        )

    incomplete = object.__new__(EvaluatorInput)
    bad_results: tuple[object, ...] = (
        object(),
        incomplete,
        EvaluatorInput(cast(str, _SpoofedRevision()), supplied[keys[0]].input_data),
        EvaluatorInput(cast(str, _HostileRevision()), supplied[keys[0]].input_data),
        EvaluatorInput("unknown-revision", supplied[keys[0]].input_data),
        EvaluatorInput(
            "declaration-v1", {"path": "different.txt", "content": "candidate"}
        ),
        EvaluatorInput("declaration-v1", {"path": "artifact.txt"}),
    )
    for result in bad_results:
        defective = dict(valid)
        defective[keys[0]] = lambda request, returned=result: returned  # type: ignore[assignment]
        with pytest.raises(ProcedureEvaluationPlanningError):
            plan_procedure_precondition_evaluations(run, defective)


def test_precondition_evaluation_plan_requires_canonical_provider_key_identity(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path / "target")
    _, _, _, foreign = _precondition_run(tmp_path / "foreign")
    supplied = _provider_inputs(run)
    foreign_keys = tuple(_provider_inputs(foreign))
    canonical_keys = tuple(supplied)

    foreign_providers = {
        foreign_key: (lambda request, value=supplied[canonical_key]: value)
        for canonical_key, foreign_key in zip(canonical_keys, foreign_keys)
    }
    with pytest.raises(ProcedureEvaluationPlanningError, match="canonical"):
        plan_procedure_precondition_evaluations(run, foreign_providers)

    reconstructed = tuple(
        ProcedurePredicateKey(key.declaration, key.phase, key.predicate)
        for key in canonical_keys
    )
    reconstructed_providers = {
        rebuilt: (lambda request, value=supplied[canonical]: value)
        for canonical, rebuilt in zip(canonical_keys, reconstructed)
    }
    with pytest.raises(ProcedureEvaluationPlanningError, match="canonical"):
        plan_procedure_precondition_evaluations(run, reconstructed_providers)

    reversed_providers = {
        key: (lambda request, value=supplied[key]: value)
        for key in reversed(canonical_keys)
    }
    assert _is_issued_procedure_precondition_evaluation_plan(
        plan_procedure_precondition_evaluations(run, reversed_providers)
    )

    incomplete = object.__new__(ProcedurePredicateKey)
    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            run,
            cast(
                Mapping[ProcedurePredicateKey, ProcedureEvaluatorInputProvider],
                _OnePairInputs(incomplete, reversed_providers[canonical_keys[0]]),
            ),
        )


def test_precondition_evaluation_plan_contains_packet_structure_defects(
    tmp_path: Path,
) -> None:
    packet_cases = (
        ("deliberative", DeliberativeAttentionEntry),
        ("assisted", AssistedAttentionEntry),
        ("mechanical", MechanicalAttentionEntry),
    )
    for case_index, (packet_name, entry_type) in enumerate(packet_cases):
        _, _, _, mutable_run = _precondition_run(tmp_path / f"mutable-{case_index}")
        mutable_inputs = _provider_inputs(mutable_run)
        mutable_packet = getattr(mutable_run.attention, packet_name)
        object.__setattr__(mutable_packet, "entries", list(mutable_packet.entries))
        with pytest.raises(
            ProcedureEvaluationPlanningError, match="issued by preflight"
        ):
            plan_procedure_precondition_evaluations(
                mutable_run,
                {
                    key: (lambda request, value=value: value)
                    for key, value in mutable_inputs.items()
                },
            )

        _, _, _, malformed_run = _precondition_run(tmp_path / f"malformed-{case_index}")
        malformed_inputs = _provider_inputs(malformed_run)
        malformed_packet = getattr(malformed_run.attention, packet_name)
        object.__setattr__(malformed_packet, "entries", (object(),))
        with pytest.raises(
            ProcedureEvaluationPlanningError, match="issued by preflight"
        ):
            plan_procedure_precondition_evaluations(
                malformed_run,
                {
                    key: (lambda request, value=value: value)
                    for key, value in malformed_inputs.items()
                },
            )

        _, _, _, incomplete_run = _precondition_run(
            tmp_path / f"incomplete-{case_index}"
        )
        incomplete_inputs = _provider_inputs(incomplete_run)
        incomplete_packet = getattr(incomplete_run.attention, packet_name)
        object.__setattr__(incomplete_packet, "entries", (object.__new__(entry_type),))
        with pytest.raises(
            ProcedureEvaluationPlanningError, match="issued by preflight"
        ):
            plan_procedure_precondition_evaluations(
                incomplete_run,
                {
                    key: (lambda request, value=value: value)
                    for key, value in incomplete_inputs.items()
                },
            )

        _, _, _, partial_run = _precondition_run(tmp_path / f"partial-{case_index}")
        partial_inputs = _provider_inputs(partial_run)
        partial_packet = getattr(partial_run.attention, packet_name)
        original = next(
            entry
            for entry in partial_packet.entries
            if type(
                entry.key
                if type(entry) is MechanicalAttentionEntry
                else entry.obligation.key
            )
            is ProcedurePredicateKey
        )
        partial: object = object.__new__(entry_type)
        if type(original) is MechanicalAttentionEntry:
            object.__setattr__(partial, "key", original.key)
        else:
            object.__setattr__(partial, "obligation", original.obligation)
        object.__setattr__(partial_packet, "entries", (partial,))
        with pytest.raises(
            ProcedureEvaluationPlanningError, match="issued by preflight"
        ):
            plan_procedure_precondition_evaluations(
                partial_run,
                {
                    key: (lambda request, value=value: value)
                    for key, value in partial_inputs.items()
                },
            )

        _, _, _, retained_run = _precondition_run(tmp_path / f"retained-{case_index}")
        retained_inputs = _provider_inputs(retained_run)
        retained_plan = plan_procedure_precondition_evaluations(
            retained_run,
            {
                key: (lambda request, value=value: value)
                for key, value in retained_inputs.items()
            },
        )
        retained_packet = getattr(retained_run.attention, packet_name)
        object.__setattr__(retained_packet, "entries", list(retained_packet.entries))
        assert not _is_issued_procedure_precondition_evaluation_plan(retained_plan)

        _, _, _, key_run = _precondition_run(tmp_path / f"key-{case_index}")
        key_inputs = _provider_inputs(key_run)
        key_packet = getattr(key_run.attention, packet_name)
        procedure_entry = next(
            entry
            for entry in key_packet.entries
            if type(
                entry.key
                if type(entry) is MechanicalAttentionEntry
                else entry.obligation.key
            )
            is ProcedurePredicateKey
        )
        incomplete_key = object.__new__(ProcedurePredicateKey)
        if type(procedure_entry) is MechanicalAttentionEntry:
            object.__setattr__(procedure_entry, "key", incomplete_key)
        else:
            original_key = procedure_entry.obligation.key
            canonical = next(
                item
                for item in key_run.attention.requirements.completion
                if item.key is original_key
            )
            object.__setattr__(procedure_entry.obligation, "key", incomplete_key)
            object.__setattr__(canonical, "key", incomplete_key)
        with pytest.raises(ProcedureEvaluationPlanningError):
            plan_procedure_precondition_evaluations(
                key_run,
                {
                    key: (lambda request, value=value: value)
                    for key, value in key_inputs.items()
                },
            )


def test_precondition_evaluation_plan_rejects_post_preflight_predicate_substitution(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    supplied = _provider_inputs(run)
    provider_calls = 0
    requirement = next(
        item
        for item in run.requirements
        if item.enforcement is EnforcementClass.ASSISTED
        and type(item.key) is ProcedurePredicateKey
        and item.key.phase is PredicatePhase.PRECONDITION
    )
    obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
    object.__setattr__(
        obligation.predicate,
        "expression",
        MappingProxyType({"facet": "scope.project", "operator": "exists"}),
    )

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    assert not _is_issued_procedure_run_plan(run)
    with pytest.raises(
        ProcedureEvaluationPlanningError,
        match="run plan was not issued by preflight",
    ):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert provider_calls == 0


def test_precondition_evaluation_plan_rejects_correlated_run_input_substitution(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    supplied = _provider_inputs(run)
    provider_calls = 0
    replacement_parameters = MappingProxyType({"path": "different.txt"})
    replacement_actions = tuple(
        PreparedProcedureAction(
            action.node,
            action.operation,
            action.contract,
            MappingProxyType({**dict(action.input_data), "path": "different.txt"}),
        )
        for action in run.actions
    )
    object.__setattr__(run, "parameters", replacement_parameters)
    object.__setattr__(run, "actions", replacement_actions)

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    assert not _is_issued_procedure_run_plan(run)
    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert provider_calls == 0


def test_precondition_evaluation_plan_rejects_packet_input_substitution(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    supplied = _provider_inputs(run)
    provider_calls = 0
    entry = next(
        item
        for item in run.attention.assisted.entries
        if type(item.obligation.key) is ProcedurePredicateKey
        and item.obligation.key.phase is PredicatePhase.PRECONDITION
    )
    invocation = entry.invocation
    replacement_input = MappingProxyType(
        {**dict(invocation.input_data), "content": "substituted"}
    )
    object.__setattr__(
        entry,
        "invocation",
        EvaluatorInvocation(
            invocation.evaluator,
            invocation.evaluator_input_operation,
            invocation.input_revision,
            replacement_input,
        ),
    )

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    assert not _is_issued_procedure_run_plan(run)
    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert provider_calls == 0


def test_procedure_run_preflight_contains_hostile_requirement_mapping(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)

    class ExplodingMapping(dict[str, object]):
        def items(self):
            raise RuntimeError("boom")

    requirement = next(
        item
        for item in run.requirements
        if type(item.key) is ProcedurePredicateKey
        and item.key.phase is PredicatePhase.PRECONDITION
    )
    obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
    object.__setattr__(
        obligation.predicate,
        "expression",
        MappingProxyType({"nested": ExplodingMapping()}),
    )

    with pytest.raises(ProcedureRunPlanningError) as error:
        _procedure_run(run.attention)

    assert error.value.location == "$.attention"
    assert "not issued by planning" in error.value.detail


def test_procedure_run_rejects_mutated_operation_method(tmp_path: Path) -> None:
    runner_calls = 0

    def runner(input_data):
        nonlocal runner_calls
        runner_calls += 1
        return OperationFailure(WRITE, "write-failed")

    _, requirements, _, _, attention = _mixed_plan(tmp_path)
    requirement = next(
        item
        for item in requirements.completion
        if type(item.key) is OperationPredicateKey
    )
    obligation = cast(OperationObligationSnapshot, requirement.obligation)
    assert obligation.operation_method is not None
    object.__setattr__(obligation, "operation_method", "Substituted method")

    assert not _is_issued_attention_plan(attention)
    with pytest.raises(ProcedureRunPlanningError) as error:
        _procedure_run(attention, cast(OperationRunner, runner))

    assert error.value.location == "$.attention"
    assert "not issued by planning" in error.value.detail
    assert runner_calls == 0


def test_precondition_evaluation_plan_rejects_same_output_binding_substitution(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    supplied = _provider_inputs(run)
    provider_calls = 0
    node = run.actions[0].node
    replacement_bindings = MappingProxyType(
        {
            **dict(node.bindings),
            "path": LiteralBinding("artifact.txt"),
        }
    )
    object.__setattr__(node, "bindings", replacement_bindings)

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    assert not _is_issued_procedure_run_plan(run)
    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert provider_calls == 0


def test_precondition_evaluation_plan_rejects_obligation_context_substitution(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    supplied = _provider_inputs(run)
    provider_calls = 0
    requirement = next(
        item
        for item in run.requirements
        if type(item.key) is ProcedurePredicateKey
        and item.key.phase is PredicatePhase.PRECONDITION
    )
    obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
    object.__setattr__(obligation, "purpose", "Substituted purpose")

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    assert not _is_issued_procedure_run_plan(run)
    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert provider_calls == 0


def test_procedure_run_preflight_contains_incomplete_packet_entry(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    object.__setattr__(
        run.attention.assisted,
        "entries",
        (object.__new__(AssistedAttentionEntry),),
    )

    with pytest.raises(ProcedureRunPlanningError) as error:
        _procedure_run(run.attention)

    assert error.value.location == "$.attention"
    assert "not issued by planning" in error.value.detail


def test_precondition_evaluation_plan_rejects_complete_run_semantic_substitutions(
    tmp_path: Path,
) -> None:
    for mode in (
        "procedure",
        "evaluator",
        "partition",
        "procedure-preconditions",
        "evaluator-backed-procedure-preconditions",
        "operation-contract",
    ):
        _, _, _, run = _precondition_run(tmp_path / mode)
        supplied = _provider_inputs(run)
        provider_calls = 0
        if mode == "procedure":
            object.__setattr__(run.procedure, "purpose", "Substituted purpose")
        elif mode == "evaluator":
            evaluator = next(
                item.evaluator
                for item in run.requirements
                if item.evaluator is not None
            )
            assert evaluator is not None
            object.__setattr__(evaluator, "title", "Substituted evaluator")
        elif mode == "partition":
            object.__setattr__(run, "executable_requirements", ())
        elif mode == "procedure-preconditions":
            object.__setattr__(
                run,
                "procedure_precondition_requirements",
                tuple(reversed(run.procedure_precondition_requirements)),
            )
        elif mode == "evaluator-backed-procedure-preconditions":
            object.__setattr__(
                run, "evaluator_backed_procedure_precondition_requirements", ()
            )
        else:
            object.__setattr__(
                run.actions[0].contract,
                "outputs",
                MappingProxyType({"type": "object"}),
            )

        def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
            nonlocal provider_calls
            provider_calls += 1
            return supplied[request.key]

        assert not _is_issued_procedure_run_plan(run)
        with pytest.raises(
            ProcedureEvaluationPlanningError, match="issued by preflight"
        ):
            plan_procedure_precondition_evaluations(
                run, {key: provider for key in supplied}
            )

        assert provider_calls == 0


def test_procedure_run_preflight_contains_incomplete_completion_requirement(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    completion = list(run.attention.requirements.completion)
    completion[0] = object.__new__(CompletionRequirement)
    object.__setattr__(run.attention.requirements, "completion", tuple(completion))

    with pytest.raises(ProcedureRunPlanningError) as error:
        _procedure_run(run.attention)

    assert error.value.location == "$.attention"
    assert "not issued by planning" in error.value.detail


def test_precondition_evaluation_plan_rechecks_packet_identity_after_semantic_reads(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    supplied = _provider_inputs(run)
    provider_calls = 0
    requirement = next(
        item
        for item in run.requirements
        if item.enforcement is EnforcementClass.ASSISTED
        and type(item.key) is ProcedurePredicateKey
        and item.key.phase is PredicatePhase.PRECONDITION
    )
    obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
    entry = next(
        item
        for item in run.attention.assisted.entries
        if item.obligation.key is requirement.key
    )
    original_expression = dict(obligation.predicate.expression)
    original_invocation = entry.invocation

    class MutatingBacking(dict[str, object]):
        def items(self):
            object.__setattr__(
                entry,
                "invocation",
                EvaluatorInvocation(
                    original_invocation.evaluator,
                    original_invocation.evaluator_input_operation,
                    original_invocation.input_revision,
                    MappingProxyType(
                        {
                            **dict(original_invocation.input_data),
                            "content": "substituted",
                        }
                    ),
                ),
            )
            return super().items()

    object.__setattr__(
        obligation.predicate,
        "expression",
        MappingProxyType(MutatingBacking(original_expression)),
    )

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert provider_calls == 0


def test_precondition_evaluation_plan_rejects_operation_registry_substitution(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    supplied = _provider_inputs(run)
    provider_calls = 0
    replacement = build_operation_runner_registry(
        run.attention.resolution.registry,
        [
            OperationRunnerBinding(
                WRITE,
                cast(
                    OperationRunner,
                    lambda input_data: OperationFailure(WRITE, "write-failed"),
                ),
            )
        ],
    )
    object.__setattr__(run, "operation_registry", replacement)

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    assert not _is_issued_procedure_run_plan(run)
    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert provider_calls == 0


def test_precondition_evaluation_plan_rechecks_scalars_after_semantic_reads(
    tmp_path: Path,
) -> None:
    _, _, _, source_run = _precondition_run(tmp_path)
    requirement = next(
        item
        for item in source_run.requirements
        if item.enforcement is EnforcementClass.ASSISTED
        and type(item.key) is ProcedurePredicateKey
        and item.key.phase is PredicatePhase.PRECONDITION
    )
    obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
    original_expression = dict(obligation.predicate.expression)

    class MutatingBacking(dict[str, object]):
        armed = False

        def items(self):
            if self.armed:
                object.__setattr__(obligation, "purpose", "Substituted purpose")
            return super().items()

    run = _procedure_run(source_run.attention)
    backing = MutatingBacking(original_expression)
    object.__setattr__(obligation.predicate, "expression", MappingProxyType(backing))
    supplied = _provider_inputs(run)
    provider_calls = 0
    backing.armed = True

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert provider_calls == 0


def test_precondition_evaluation_plan_rechecks_runner_after_mapping_reads(
    tmp_path: Path,
) -> None:
    _, _, _, source_run = _precondition_run(tmp_path)
    target_binding: OperationRunnerBinding | None = None
    original_document = dict(source_run.procedure.document)

    def replacement_runner(input_data: Mapping[str, JsonValue], /) -> OperationFailure:
        return OperationFailure(WRITE, "write-failed")

    class MutatingDocument(dict[str, object]):
        armed = False

        def items(self):
            if self.armed:
                assert target_binding is not None
                object.__setattr__(target_binding, "runner", replacement_runner)
            return super().items()

    document = MutatingDocument(original_document)
    object.__setattr__(source_run.procedure, "document", MappingProxyType(document))
    run = _procedure_run(source_run.attention)
    target_binding = next(iter(run.operation_registry.bindings.values()))
    supplied = _provider_inputs(run)
    provider_calls = 0
    document.armed = True

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert provider_calls == 0


def test_precondition_evaluation_plan_rechecks_maps_after_packet_side_effect(
    tmp_path: Path,
) -> None:
    _, _, _, source_run = _precondition_run(tmp_path)
    requirement = next(
        item
        for item in source_run.requirements
        if item.enforcement is EnforcementClass.ASSISTED
        and type(item.key) is ProcedurePredicateKey
        and item.key.phase is PredicatePhase.PRECONDITION
    )
    obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
    expression_backing = dict(obligation.predicate.expression)
    entry = next(
        item
        for item in source_run.attention.assisted.entries
        if item.obligation.key is requirement.key
    )
    invocation = entry.invocation

    class MutatingInput(dict[str, object]):
        armed = False

        def items(self):
            if self.armed:
                expression_backing.clear()
                expression_backing.update(
                    {"facet": "scope.project", "operator": "exists"}
                )
            return super().items()

    run = _procedure_run(source_run.attention)
    object.__setattr__(
        obligation.predicate,
        "expression",
        MappingProxyType(expression_backing),
    )
    invocation_input = MutatingInput(dict(invocation.input_data))
    object.__setattr__(invocation, "input_data", MappingProxyType(invocation_input))
    supplied = _provider_inputs(run)
    provider_calls = 0
    invocation_input.armed = True

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert provider_calls == 0


def test_precondition_evaluation_plan_rechecks_contract_scalar_after_schema_read(
    tmp_path: Path,
) -> None:
    _, _, _, source_run = _precondition_run(tmp_path)
    entry = next(
        item
        for item in source_run.attention.assisted.entries
        if type(item.obligation.key) is ProcedurePredicateKey
        and item.obligation.key.phase is PredicatePhase.PRECONDITION
    )
    reference = entry.invocation.evaluator_input_operation
    contract = (
        source_run.attention.resolution.registry.families[reference.id]
        .versions[reference.version]
        .declaration
    )
    assert type(contract) is OperationDeclaration

    class MutatingSchema(dict[str, object]):
        armed = False

        def items(self):
            if self.armed:
                object.__setattr__(contract, "recovery", "Substituted recovery")
            return super().items()

    schema = MutatingSchema(dict(contract.inputs))
    object.__setattr__(contract, "inputs", MappingProxyType(schema))
    run = _procedure_run(source_run.attention)
    supplied = _provider_inputs(run)
    provider_calls = 0
    schema.armed = True

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert provider_calls == 0


def test_precondition_evaluation_plan_contains_late_invocation_mutation(
    tmp_path: Path,
) -> None:
    _, _, _, source_run = _precondition_run(tmp_path)
    entry = next(
        item
        for item in source_run.attention.assisted.entries
        if type(item.obligation.key) is ProcedurePredicateKey
        and item.obligation.key.phase is PredicatePhase.PRECONDITION
    )
    invocation = entry.invocation
    invocation_backing = dict(invocation.input_data)

    class MutatingDocument(dict[str, object]):
        armed = False

        def items(self):
            if self.armed:
                invocation_backing["content"] = "late-substitution"
            return super().items()

    document = MutatingDocument(dict(source_run.procedure.document))
    run = _procedure_run(source_run.attention)
    object.__setattr__(invocation, "input_data", MappingProxyType(invocation_backing))
    object.__setattr__(source_run.procedure, "document", MappingProxyType(document))
    supplied = _provider_inputs(run)
    provider_calls = 0
    document.armed = True

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert provider_calls == 0


def test_precondition_evaluation_plan_rejects_detached_authority_substitution(
    tmp_path: Path,
) -> None:
    for mode in ("predicate", "invocation", "schema"):
        _, _, _, run = _precondition_run(tmp_path / mode)
        supplied = _provider_inputs(run)
        provider_calls = 0
        item = next(
            value
            for value in run._evaluation_inputs
            if value.invocation_input is not None
        )
        if mode == "predicate":
            object.__setattr__(
                item.predicate,
                "expression",
                MappingProxyType({"facet": "scope.project", "operator": "exists"}),
            )
        elif mode == "invocation":
            object.__setattr__(
                item,
                "invocation_input",
                MappingProxyType(
                    {**dict(item.invocation_input), "content": "substituted"}
                ),
            )
        else:
            object.__setattr__(
                item, "input_schema", MappingProxyType({"type": "object"})
            )

        def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
            nonlocal provider_calls
            provider_calls += 1
            return supplied[request.key]

        assert not _is_issued_procedure_run_plan(run)
        with pytest.raises(
            ProcedureEvaluationPlanningError, match="issued by preflight"
        ):
            plan_procedure_precondition_evaluations(
                run, {key: provider for key in supplied}
            )

        assert provider_calls == 0


def test_precondition_evaluation_plan_rejects_altered_run_correlations(
    tmp_path: Path,
) -> None:
    def providers_for(
        run: ProcedureRunPlan,
    ) -> dict[ProcedurePredicateKey, ProcedureEvaluatorInputProvider]:
        return {
            key: (lambda request, value=value: value)
            for key, value in _provider_inputs(run).items()
        }

    _, _, _, erased = _precondition_run(tmp_path / "erased")
    object.__setattr__(erased, "requirements", ())
    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(erased, providers_for(erased))

    _, _, _, reordered = _precondition_run(tmp_path / "reordered")
    object.__setattr__(
        reordered, "requirements", tuple(reversed(reordered.requirements))
    )
    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(reordered, providers_for(reordered))

    _, _, _, primary = _precondition_run(tmp_path / "primary")
    _, _, _, foreign = _precondition_run(tmp_path / "foreign")
    object.__setattr__(primary, "requirements", foreign.requirements)
    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(primary, providers_for(primary))

    _, _, _, wrong_procedure = _precondition_run(tmp_path / "wrong-procedure")
    object.__setattr__(wrong_procedure, "procedure", foreign.procedure)
    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(
            wrong_procedure, providers_for(wrong_procedure)
        )

    _, _, _, incomplete_key_run = _precondition_run(tmp_path / "incomplete-key")
    procedure_requirement = next(
        item
        for item in incomplete_key_run.attention.requirements.completion
        if type(item.key) is ProcedurePredicateKey
    )
    object.__setattr__(
        procedure_requirement, "key", object.__new__(ProcedurePredicateKey)
    )
    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            incomplete_key_run, providers_for(incomplete_key_run)
        )

    _, _, _, incomplete_run = _precondition_run(tmp_path / "incomplete-requirement")
    completion = list(incomplete_run.attention.requirements.completion)
    completion[0] = object.__new__(CompletionRequirement)
    object.__setattr__(
        incomplete_run.attention.requirements, "completion", tuple(completion)
    )
    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            incomplete_run, providers_for(incomplete_run)
        )


def test_precondition_evaluation_plan_requires_exact_evaluator_text_fields(
    tmp_path: Path,
) -> None:
    for index, value in enumerate((_SpoofedRevision(), _HostileRevision())):
        _, _, _, timing_run = _precondition_run(tmp_path / f"timing-{index}")
        timing_inputs = _provider_inputs(timing_run)
        evaluator = next(
            item.evaluator
            for item in timing_run.requirements
            if item.enforcement is EnforcementClass.ASSISTED
        )
        assert evaluator is not None
        object.__setattr__(evaluator, "timing", value)
        with pytest.raises(
            ProcedureEvaluationPlanningError, match="issued by preflight"
        ):
            plan_procedure_precondition_evaluations(
                timing_run,
                {
                    key: (lambda request, result=result: result)
                    for key, result in timing_inputs.items()
                },
            )

        _, _, _, residual_run = _precondition_run(tmp_path / f"residual-{index}")
        residual_inputs = _provider_inputs(residual_run)
        object.__setattr__(
            residual_run.attention.assisted.entries[0], "residual_question", value
        )
        with pytest.raises(
            ProcedureEvaluationPlanningError, match="issued by preflight"
        ):
            plan_procedure_precondition_evaluations(
                residual_run,
                {
                    key: (lambda request, result=result: result)
                    for key, result in residual_inputs.items()
                },
            )


def test_precondition_evaluation_plan_does_not_hash_procedure_id_before_baseline(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    original_id = run.procedure.id
    original_paths = run.attention.resolution.registry.paths
    hash_calls = 0
    provider_calls = 0

    class SelfCleaningIdentifier(str):
        def __hash__(self) -> int:
            nonlocal hash_calls
            hash_calls += 1
            object.__setattr__(run.procedure, "id", original_id)
            object.__setattr__(
                run.attention.resolution.registry,
                "paths",
                tuple(reversed(original_paths)),
            )
            return hash(original_id)

    object.__setattr__(run.procedure, "id", SelfCleaningIdentifier(original_id))
    supplied = _provider_inputs(run)

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert hash_calls == 0
    assert provider_calls == 0
    assert run.attention.resolution.registry.paths is original_paths


def test_precondition_evaluation_plan_requires_canonical_evaluator_authority(
    tmp_path: Path,
) -> None:
    def providers_for(
        run: ProcedureRunPlan,
    ) -> dict[ProcedurePredicateKey, ProcedureEvaluatorInputProvider]:
        return {
            key: (lambda request, value=value: value)
            for key, value in _provider_inputs(run).items()
        }

    for enforcement in (EnforcementClass.ASSISTED, EnforcementClass.MECHANICAL):
        label = enforcement.value
        _, _, _, copied_run = _precondition_run(tmp_path / f"copied-{label}")
        copied_requirement = next(
            item for item in copied_run.requirements if item.enforcement is enforcement
        )
        assert copied_requirement.evaluator is not None
        object.__setattr__(
            copied_requirement,
            "evaluator",
            copy.copy(copied_requirement.evaluator),
        )
        with pytest.raises(
            ProcedureEvaluationPlanningError, match="issued by preflight"
        ):
            plan_procedure_precondition_evaluations(
                copied_run, providers_for(copied_run)
            )

        _, _, _, target_run = _precondition_run(tmp_path / f"target-{label}")
        _, _, _, foreign_run = _precondition_run(tmp_path / f"foreign-{label}")
        target_requirement = next(
            item for item in target_run.requirements if item.enforcement is enforcement
        )
        foreign_evaluator = next(
            item.evaluator
            for item in foreign_run.requirements
            if item.enforcement is enforcement
        )
        object.__setattr__(target_requirement, "evaluator", foreign_evaluator)
        with pytest.raises(
            ProcedureEvaluationPlanningError, match="issued by preflight"
        ):
            plan_procedure_precondition_evaluations(
                target_run, providers_for(target_run)
            )

        _, _, _, reference_run = _precondition_run(tmp_path / f"reference-{label}")
        reference_requirement = next(
            item
            for item in reference_run.requirements
            if item.enforcement is enforcement
        )
        obligation = cast(ProcedureObligationSnapshot, reference_requirement.obligation)
        object.__setattr__(obligation.predicate, "evaluator", MANUAL)
        with pytest.raises(ProcedureEvaluationPlanningError):
            plan_procedure_precondition_evaluations(
                reference_run, providers_for(reference_run)
            )

        _, _, _, stale_run = _precondition_run(tmp_path / f"stale-{label}")
        stale_requirement = next(
            item for item in stale_run.requirements if item.enforcement is enforcement
        )
        replacement = (
            EnforcementClass.MECHANICAL
            if enforcement is EnforcementClass.ASSISTED
            else EnforcementClass.ASSISTED
        )
        object.__setattr__(stale_requirement, "enforcement", replacement)
        with pytest.raises(
            ProcedureEvaluationPlanningError, match="issued by preflight"
        ):
            plan_procedure_precondition_evaluations(stale_run, providers_for(stale_run))


def test_precondition_evaluation_plan_requires_exact_runner_registries(
    tmp_path: Path,
) -> None:
    def providers_for(
        run: ProcedureRunPlan,
    ) -> dict[ProcedurePredicateKey, ProcedureEvaluatorInputProvider]:
        return {
            key: (lambda request, value=value: value)
            for key, value in _provider_inputs(run).items()
        }

    _, _, _, cross_run = _precondition_run(tmp_path / "cross-target")
    _, _, _, foreign_run = _precondition_run(tmp_path / "cross-foreign")
    object.__setattr__(
        cross_run.attention,
        "detector_registry",
        foreign_run.attention.detector_registry,
    )
    object.__setattr__(
        cross_run.attention,
        "checker_registry",
        foreign_run.attention.checker_registry,
    )
    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(cross_run, providers_for(cross_run))

    _, _, _, detector_run = _precondition_run(tmp_path / "detector")
    detector_registry = build_detector_runner_registry(
        detector_run.attention.resolution.registry,
        [
            DetectorRunnerBinding(
                DETECTOR,
                WRITE,
                cast(DetectorRunner, lambda input_data: _detector_result()),
            )
        ],
    )
    object.__setattr__(detector_run.attention, "detector_registry", detector_registry)
    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(
            detector_run, providers_for(detector_run)
        )

    _, _, _, checker_run = _precondition_run(tmp_path / "checker")
    checker_registry = build_checker_runner_registry(
        checker_run.attention.resolution.registry,
        [
            CheckerRunnerBinding(
                CHECKER,
                CHECK_INPUT,
                cast(CheckerRunner, lambda input_data: _checker_result()),
            )
        ],
    )
    object.__setattr__(checker_run.attention, "checker_registry", checker_registry)
    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by planning"):
        plan_procedure_precondition_evaluations(checker_run, providers_for(checker_run))


def test_precondition_evaluation_plan_revalidates_run_parameters(
    tmp_path: Path,
) -> None:
    def providers_for(
        run: ProcedureRunPlan,
    ) -> dict[ProcedurePredicateKey, ProcedureEvaluatorInputProvider]:
        return {
            key: (lambda request, value=value: value)
            for key, value in _provider_inputs(run).items()
        }

    _, _, _, mutable = _precondition_run(tmp_path / "mutable")
    object.__setattr__(mutable, "parameters", {"path": "artifact.txt"})
    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(mutable, providers_for(mutable))

    _, _, _, invalid = _precondition_run(tmp_path / "invalid")
    object.__setattr__(invalid, "parameters", MappingProxyType({}))
    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(invalid, providers_for(invalid))

    _, _, _, disagreement = _precondition_run(tmp_path / "disagreement")
    object.__setattr__(
        disagreement,
        "parameters",
        MappingProxyType({"path": "different.txt"}),
    )
    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            disagreement, providers_for(disagreement)
        )

    _, _, _, changing = _precondition_run(tmp_path / "changing")
    backing = {"path": "artifact.txt"}
    object.__setattr__(changing, "parameters", MappingProxyType(backing))
    supplied = _provider_inputs(changing)
    first_key = next(iter(supplied))

    def mutating_provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        backing["path"] = "changed.txt"
        return supplied[request.key]

    providers = {
        key: (
            mutating_provider
            if key == first_key
            else (lambda request, value=value: value)
        )
        for key, value in supplied.items()
    }
    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(changing, providers)


def test_precondition_evaluation_plan_contains_provider_boundary_failures(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    supplied = _provider_inputs(run)
    keys = tuple(supplied)

    async def asynchronous(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        return supplied[keys[0]]

    class HostileSignature:
        @property
        def __signature__(self):
            raise RuntimeError("signature unavailable")

        def __call__(self, request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
            return supplied[keys[0]]

    for invalid in (object(), asynchronous, HostileSignature()):
        invalid_providers = {
            key: (invalid if key == keys[0] else (lambda request, value=value: value))
            for key, value in supplied.items()
        }
        with pytest.raises(ProcedureEvaluationPlanningError):
            plan_procedure_precondition_evaluations(
                run, invalid_providers  # type: ignore[arg-type]
            )

    def failing(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        raise _HostileMessageError()

    failing_providers: dict[ProcedurePredicateKey, ProcedureEvaluatorInputProvider] = {
        key: (failing if key == keys[0] else (lambda request, value=value: value))
        for key, value in supplied.items()
    }
    with pytest.raises(
        ProcedureEvaluationPlanningError,
        match="HostileMessageError; message formatting raised LookupError",
    ):
        plan_procedure_precondition_evaluations(run, failing_providers)


def test_precondition_evaluation_plan_inspects_provider_signatures_once(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    supplied = _provider_inputs(run)
    keys = tuple(supplied)
    original_trace = run.attention.resolution.trace

    class StatefulSignature:
        def __init__(self, *, mutate: bool) -> None:
            self.inspections = 0
            self.mutate = mutate

        @property
        def __signature__(self) -> inspect.Signature:
            self.inspections += 1
            if self.inspections > 1:
                if self.mutate:
                    object.__setattr__(
                        run.attention.resolution,
                        "trace",
                        tuple(reversed(original_trace)),
                    )
                raise RuntimeError("signature was inspected again")
            return inspect.signature(lambda request: supplied[keys[0]])

        def __call__(self, request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
            return supplied[request.key]

    for mutate in (False, True):
        provider = StatefulSignature(mutate=mutate)
        providers = {
            key: (provider if key == keys[0] else (lambda request, value=value: value))
            for key, value in supplied.items()
        }

        plan = plan_procedure_precondition_evaluations(run, providers)

        assert provider.inspections == 1
        assert run.attention.resolution.trace is original_trace
        assert _is_issued_procedure_precondition_evaluation_plan(plan)
        assert provider.inspections == 1


def test_precondition_evaluation_plan_rejects_initial_mutation_before_providers(
    tmp_path: Path,
) -> None:
    _, _, _, base_run = _precondition_run(tmp_path)
    holder: dict[str, ProcedureRunPlan] = {}

    class MutatingRunnerSignature:
        def __init__(self) -> None:
            self.inspections = 0

        @property
        def __signature__(self) -> inspect.Signature:
            self.inspections += 1
            if self.inspections == 2:
                run = holder["run"]
                object.__setattr__(
                    run.attention.resolution.registry,
                    "paths",
                    tuple(reversed(run.attention.resolution.registry.paths)),
                )
            return inspect.signature(lambda input_data: None)

        def __call__(self, input_data: Mapping[str, JsonValue]) -> OperationFailure:
            return OperationFailure(WRITE, "write-failed")

    runner = MutatingRunnerSignature()
    operation_registry = build_operation_runner_registry(
        base_run.attention.resolution.registry,
        [OperationRunnerBinding(WRITE, cast(OperationRunner, runner))],
    )
    run = prepare_procedure_run(
        base_run.attention,
        "content/write",
        {"path": "artifact.txt"},
        operation_registry,
    )
    holder["run"] = run
    supplied = _provider_inputs(run)
    provider_calls = 0

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError, match="graph changed"):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert runner.inspections == 2
    assert provider_calls == 0


def test_precondition_evaluation_plan_treats_callable_dataclasses_as_opaque(
    tmp_path: Path,
) -> None:
    _, _, _, base_run = _precondition_run(tmp_path)
    holder: dict[str, ProcedureRunPlan] = {}
    field_reads = 0

    @dataclass
    class CallableDataclassRunner:
        token: object

        def __getattribute__(self, name: str) -> object:
            nonlocal field_reads
            if name == "token":
                field_reads += 1
                if field_reads == 2:
                    run = holder["run"]
                    object.__setattr__(
                        run.attention.resolution.registry,
                        "paths",
                        (*run.attention.resolution.registry.paths, Path("late.yaml")),
                    )
            return object.__getattribute__(self, name)

        def __call__(self, input_data: Mapping[str, JsonValue]) -> OperationFailure:
            return OperationFailure(WRITE, "write-failed")

    runner = CallableDataclassRunner(object())
    operation_registry = build_operation_runner_registry(
        base_run.attention.resolution.registry,
        [OperationRunnerBinding(WRITE, cast(OperationRunner, runner))],
    )
    run = prepare_procedure_run(
        base_run.attention,
        "content/write",
        {"path": "artifact.txt"},
        operation_registry,
    )
    holder["run"] = run
    original_paths = run.attention.resolution.registry.paths
    supplied = _provider_inputs(run)
    provider_calls = 0

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    plan = plan_procedure_precondition_evaluations(
        run, {key: provider for key in supplied}
    )

    assert _is_issued_procedure_precondition_evaluation_plan(plan)
    assert field_reads == 0
    assert run.attention.resolution.registry.paths is original_paths
    assert provider_calls == len(supplied)


def test_precondition_evaluation_plan_does_not_probe_runner_metaclasses(
    tmp_path: Path,
) -> None:
    _, _, _, base_run = _precondition_run(tmp_path)
    holder: dict[str, ProcedureRunPlan] = {}
    dataclass_probes = 0

    class HostileRunnerMeta(type):
        def __getattribute__(cls, name: str) -> object:
            nonlocal dataclass_probes
            if name == "__dataclass_fields__":
                dataclass_probes += 1
                if dataclass_probes == 3:
                    run = holder["run"]
                    object.__setattr__(
                        run.attention.resolution.registry,
                        "paths",
                        (*run.attention.resolution.registry.paths, Path("late.yaml")),
                    )
            return super().__getattribute__(name)

    class Runner(metaclass=HostileRunnerMeta):
        def __call__(self, input_data: Mapping[str, JsonValue]) -> OperationFailure:
            return OperationFailure(WRITE, "write-failed")

    runner = Runner()
    operation_registry = build_operation_runner_registry(
        base_run.attention.resolution.registry,
        [OperationRunnerBinding(WRITE, cast(OperationRunner, runner))],
    )
    run = prepare_procedure_run(
        base_run.attention,
        "content/write",
        {"path": "artifact.txt"},
        operation_registry,
    )
    holder["run"] = run
    original_paths = run.attention.resolution.registry.paths
    supplied = _provider_inputs(run)
    provider_calls = 0

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    plan = plan_procedure_precondition_evaluations(
        run, {key: provider for key in supplied}
    )

    assert _is_issued_procedure_precondition_evaluation_plan(plan)
    assert dataclass_probes == 0
    assert run.attention.resolution.registry.paths is original_paths
    assert provider_calls == len(supplied)


def test_precondition_evaluation_plan_does_not_probe_unknown_metaclasses(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    dataclass_probes = 0
    provider_calls = 0

    class HostileValueMeta(type):
        def __getattribute__(cls, name: str) -> object:
            nonlocal dataclass_probes
            if name == "__dataclass_fields__":
                dataclass_probes += 1
                object.__setattr__(run.attention, "requirements", object())
            return super().__getattribute__(name)

    class HostileValue(metaclass=HostileValueMeta):
        pass

    paths = run.attention.resolution.registry.paths
    object.__setattr__(
        run.attention.resolution.registry,
        "paths",
        (HostileValue(), *paths[1:]),
    )
    supplied = _provider_inputs(run)

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError, match="registry path"):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert dataclass_probes == 0
    assert provider_calls == 0
    assert type(run.attention.requirements) is AttentionRequirements


def test_precondition_evaluation_plan_rejects_nested_hostile_mappings(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    provider_calls = 0
    mapping_reads = 0

    class HostileMapping(dict[str, object]):
        def items(self):
            nonlocal mapping_reads
            mapping_reads += 1
            object.__setattr__(
                run.attention.resolution.registry,
                "paths",
                (*run.attention.resolution.registry.paths, Path("late.yaml")),
            )
            return super().items()

    requirement = next(
        item
        for item in run.requirements
        if type(item.key) is ProcedurePredicateKey
        and item.key.phase is PredicatePhase.PRECONDITION
    )
    obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
    object.__setattr__(
        obligation.predicate,
        "expression",
        MappingProxyType({"nested": HostileMapping()}),
    )
    supplied = _provider_inputs(run)

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert mapping_reads == 0
    assert provider_calls == 0


def test_precondition_evaluation_plan_contains_mapping_proxy_backing_effects(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    requirement = next(
        item
        for item in run.requirements
        if type(item.key) is ProcedurePredicateKey
        and item.key.phase is PredicatePhase.PRECONDITION
    )
    obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
    original_expression = dict(obligation.predicate.expression)
    mapping_reads = 0
    provider_calls = 0

    class StatefulBacking(dict[str, object]):
        def items(self):
            nonlocal mapping_reads
            mapping_reads += 1
            object.__setattr__(
                run.attention.resolution.registry,
                "paths",
                tuple(reversed(run.attention.resolution.registry.paths)),
            )
            return super().items()

    object.__setattr__(
        obligation.predicate,
        "expression",
        MappingProxyType(StatefulBacking(original_expression)),
    )
    supplied = _provider_inputs(run)

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert mapping_reads == 0
    assert provider_calls == 0


def test_precondition_evaluation_plan_rejects_alternating_semantic_mappings(
    tmp_path: Path,
) -> None:
    class AlternatingBacking(dict[str, object]):
        def __init__(
            self,
            initial: Mapping[str, object],
            alternate: Mapping[str, object],
            alternate_call: int,
        ) -> None:
            super().__init__(initial)
            self.alternate = dict(alternate)
            self.alternate_call = alternate_call
            self.calls = 0

        def items(self):
            self.calls += 1
            if self.calls == self.alternate_call:
                return self.alternate.items()
            return super().items()

    for mode in ("predicate", "invocation", "schema"):
        _, _, _, run = _precondition_run(tmp_path / mode)
        supplied = _provider_inputs(run)
        provider_calls = 0
        if mode == "predicate":
            requirement = next(
                item
                for item in run.requirements
                if item.enforcement is EnforcementClass.ASSISTED
                and type(item.key) is ProcedurePredicateKey
                and item.key.phase is PredicatePhase.PRECONDITION
            )
            obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
            initial = dict(obligation.predicate.expression)
            alternate = {**initial, "operator": "absent"}
            backing = AlternatingBacking(initial, alternate, 2)
            object.__setattr__(
                obligation.predicate, "expression", MappingProxyType(backing)
            )
        elif mode == "invocation":
            entry = next(
                item
                for item in run.attention.assisted.entries
                if type(item.obligation.key) is ProcedurePredicateKey
                and item.obligation.key.phase is PredicatePhase.PRECONDITION
            )
            initial = dict(entry.invocation.input_data)
            alternate = {
                key: value for key, value in initial.items() if key != "content"
            }
            backing = AlternatingBacking(initial, alternate, 2)
            object.__setattr__(
                entry.invocation, "input_data", MappingProxyType(backing)
            )
        else:
            entry = next(
                item
                for item in run.attention.mechanical.entries
                if type(item.key) is ProcedurePredicateKey
                and item.key.phase is PredicatePhase.PRECONDITION
            )
            reference = entry.invocation.evaluator_input_operation
            family = run.attention.resolution.registry.families[reference.id]
            contract = family.versions[reference.version].declaration
            initial = dict(contract.inputs)
            backing = AlternatingBacking(initial, {}, 2)
            object.__setattr__(contract, "inputs", MappingProxyType(backing))

        def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
            nonlocal provider_calls
            provider_calls += 1
            return supplied[request.key]

        with pytest.raises(ProcedureEvaluationPlanningError):
            plan_procedure_precondition_evaluations(
                run, {key: provider for key in supplied}
            )

        if mode == "schema":
            assert backing.calls >= 1
        else:
            assert backing.calls == 0
        assert provider_calls == 0


def test_precondition_evaluation_plan_rejects_stable_invalid_specifications(
    tmp_path: Path,
) -> None:
    for mode in ("predicate", "schema"):
        _, _, _, run = _precondition_run(tmp_path / mode)
        supplied = _provider_inputs(run)
        provider_calls = 0
        if mode == "predicate":
            requirement = next(
                item
                for item in run.requirements
                if item.enforcement is EnforcementClass.ASSISTED
                and type(item.key) is ProcedurePredicateKey
                and item.key.phase is PredicatePhase.PRECONDITION
            )
            obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
            object.__setattr__(
                obligation.predicate,
                "expression",
                MappingProxyType({"bogus": 1}),
            )
        else:
            entry = next(
                item
                for item in run.attention.mechanical.entries
                if type(item.key) is ProcedurePredicateKey
                and item.key.phase is PredicatePhase.PRECONDITION
            )
            reference = entry.invocation.evaluator_input_operation
            family = run.attention.resolution.registry.families[reference.id]
            contract = family.versions[reference.version].declaration
            object.__setattr__(contract, "inputs", MappingProxyType({}))

        def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
            nonlocal provider_calls
            provider_calls += 1
            return supplied[request.key]

        with pytest.raises(ProcedureEvaluationPlanningError):
            plan_procedure_precondition_evaluations(
                run, {key: provider for key in supplied}
            )

        assert provider_calls == 0


def test_precondition_evaluation_plan_rejects_invalid_retained_facets(
    tmp_path: Path,
) -> None:
    expressions = (
        {"facet": "not.registered", "operator": "exists"},
        {"facet": "context.available", "operator": "equals", "value": "yes"},
    )
    for index, expression in enumerate(expressions):
        _, _, _, run = _precondition_run(tmp_path / str(index))
        supplied = _provider_inputs(run)
        provider_calls = 0
        requirement = next(
            item
            for item in run.requirements
            if item.enforcement is EnforcementClass.ASSISTED
            and type(item.key) is ProcedurePredicateKey
            and item.key.phase is PredicatePhase.PRECONDITION
        )
        obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
        object.__setattr__(
            obligation.predicate, "expression", MappingProxyType(expression)
        )

        def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
            nonlocal provider_calls
            provider_calls += 1
            return supplied[request.key]

        with pytest.raises(ProcedureEvaluationPlanningError):
            plan_procedure_precondition_evaluations(
                run, {key: provider for key in supplied}
            )

        assert provider_calls == 0


def test_precondition_evaluation_plan_rejects_correlated_facet_tampering(
    tmp_path: Path,
) -> None:
    for mode in ("insert", "schema"):
        _, _, _, run = _precondition_run(tmp_path / mode)
        supplied = _provider_inputs(run)
        provider_calls = 0
        requirement = next(
            item
            for item in run.requirements
            if item.enforcement is EnforcementClass.ASSISTED
            and type(item.key) is ProcedurePredicateKey
            and item.key.phase is PredicatePhase.PRECONDITION
        )
        obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
        facet_registry = run.attention.resolution.registry.facet_registry
        if mode == "insert":
            object.__setattr__(
                obligation.predicate,
                "expression",
                MappingProxyType({"facet": "not.registered", "operator": "exists"}),
            )
            object.__setattr__(
                facet_registry,
                "facets",
                MappingProxyType(
                    {
                        **dict(facet_registry.facets),
                        "not.registered": ContextFacet(
                            "not.registered", MappingProxyType({"type": "boolean"})
                        ),
                    }
                ),
            )
        else:
            object.__setattr__(
                obligation.predicate,
                "expression",
                MappingProxyType(
                    {
                        "facet": "context.available",
                        "operator": "equals",
                        "value": "yes",
                    }
                ),
            )
            facet = facet_registry.facets["context.available"]
            object.__setattr__(facet, "value_schema", MappingProxyType({}))

        def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
            nonlocal provider_calls
            provider_calls += 1
            return supplied[request.key]

        with pytest.raises(
            ProcedureEvaluationPlanningError, match="issued by preflight"
        ):
            plan_procedure_precondition_evaluations(
                run, {key: provider for key in supplied}
            )

        assert provider_calls == 0


def test_precondition_evaluation_plan_rejects_virtual_mappings_without_traversal(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    mapping_reads = 0
    provider_calls = 0

    class VirtualMapping:
        __module__ = "pathlib"

        def items(self):
            nonlocal mapping_reads
            mapping_reads += 1
            object.__setattr__(
                run.attention.resolution.registry,
                "paths",
                (*run.attention.resolution.registry.paths, Path("late.yaml")),
            )
            return ()

    Mapping.register(VirtualMapping)
    requirement = next(
        item
        for item in run.requirements
        if type(item.key) is ProcedurePredicateKey
        and item.key.phase is PredicatePhase.PRECONDITION
    )
    obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
    object.__setattr__(
        obligation.predicate,
        "expression",
        MappingProxyType({"nested": VirtualMapping()}),
    )
    supplied = _provider_inputs(run)

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert mapping_reads == 0
    assert provider_calls == 0


def test_precondition_evaluation_plan_rejects_hostile_json_sequences_and_keys(
    tmp_path: Path,
) -> None:
    class HostileList(list[object]):
        def __init__(self) -> None:
            super().__init__()
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            object.__setattr__(
                run.attention.resolution.registry,
                "paths",
                tuple(reversed(run.attention.resolution.registry.paths)),
            )
            return super().__iter__()

        def __call__(self) -> None:
            return None

    class HostileKey(str):
        def __new__(cls, value: str):
            instance = super().__new__(cls, value)
            instance.hashes = 0
            instance.armed = False
            return instance

        def __hash__(self) -> int:
            self.hashes += 1
            if self.armed:
                object.__setattr__(
                    run.attention.resolution.registry,
                    "paths",
                    tuple(reversed(run.attention.resolution.registry.paths)),
                )
            return super().__hash__()

        def __call__(self) -> None:
            return None

    for index, hostile in enumerate((HostileList(), HostileKey("hostile"))):
        _, _, _, run = _precondition_run(tmp_path / str(index))
        requirement = next(
            item
            for item in run.requirements
            if type(item.key) is ProcedurePredicateKey
            and item.key.phase is PredicatePhase.PRECONDITION
        )
        obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
        if isinstance(hostile, HostileKey):
            expression = MappingProxyType({hostile: "value"})
            hostile.armed = True
            initial_activity = hostile.hashes
        else:
            expression = MappingProxyType({"nested": hostile})
            initial_activity = hostile.iterations
        object.__setattr__(obligation.predicate, "expression", expression)
        supplied = _provider_inputs(run)
        provider_calls = 0

        def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
            nonlocal provider_calls
            provider_calls += 1
            return supplied[request.key]

        with pytest.raises(ProcedureEvaluationPlanningError):
            plan_procedure_precondition_evaluations(
                run, {key: provider for key in supplied}
            )

        final_activity = (
            hostile.hashes if isinstance(hostile, HostileKey) else hostile.iterations
        )
        assert final_activity >= initial_activity
        assert provider_calls == 0


def test_precondition_evaluation_plan_rejects_self_cleaning_invocation_input(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    entry = next(
        item
        for item in run.attention.mechanical.entries
        if type(item.key) is ProcedurePredicateKey
        and item.key.phase is PredicatePhase.PRECONDITION
    )
    invocation = entry.invocation
    original_input = invocation.input_data
    original_paths = run.attention.resolution.registry.paths
    provider_calls = 0

    class SelfCleaningList(list[object]):
        def __init__(self, values: object) -> None:
            super().__init__(cast(tuple[object, ...], values))
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            object.__setattr__(invocation, "input_data", original_input)
            object.__setattr__(
                run.attention.resolution.registry,
                "paths",
                tuple(reversed(original_paths)),
            )
            return super().__iter__()

    hostile_sources = SelfCleaningList(original_input["sources"])
    object.__setattr__(
        invocation,
        "input_data",
        MappingProxyType(
            {
                "sources": hostile_sources,
                "facet-registry": original_input["facet-registry"],
            }
        ),
    )
    supplied = _provider_inputs(run)

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal provider_calls
        provider_calls += 1
        return supplied[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )

    assert hostile_sources.iterations == 0
    assert provider_calls == 0


def test_precondition_evaluation_plan_revalidates_mechanical_assurance(
    tmp_path: Path,
) -> None:
    _, fixtures, _, run = _precondition_run(tmp_path)
    supplied = _provider_inputs(run)
    calls = 0

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal calls
        calls += 1
        return supplied[request.key]

    fixture = fixtures.fixtures[KNOWN_FAILURE]
    source = next(digest.path for digest in fixture.digests if digest.role == "source")
    source.write_text("changed: true\n", encoding="utf-8")

    with pytest.raises(ProcedureEvaluationPlanningError, match="changed after"):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )
    assert calls == 0


def test_precondition_evaluation_plan_revalidates_after_provider_side_effects(
    tmp_path: Path,
) -> None:
    _, fixtures, _, fixture_run = _precondition_run(tmp_path / "fixture")
    supplied = _provider_inputs(fixture_run)
    first_key = next(iter(supplied))
    fixture = fixtures.fixtures[KNOWN_FAILURE]
    source = next(digest.path for digest in fixture.digests if digest.role == "source")

    def stale_fixture(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        source.write_text("changed: true\n", encoding="utf-8")
        return supplied[request.key]

    fixture_providers = {
        key: (
            stale_fixture if key == first_key else (lambda request, value=value: value)
        )
        for key, value in supplied.items()
    }
    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(fixture_run, fixture_providers)

    _, _, _, packet_run = _precondition_run(tmp_path / "packet")
    packet_inputs = _provider_inputs(packet_run)
    packet_first = next(iter(packet_inputs))

    def mutate_packet(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        object.__setattr__(packet_run.attention.deliberative, "entries", ())
        return packet_inputs[request.key]

    packet_providers = {
        key: (
            mutate_packet
            if key == packet_first
            else (lambda request, value=value: value)
        )
        for key, value in packet_inputs.items()
    }
    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(packet_run, packet_providers)

    _, _, _, later_run = _precondition_run(tmp_path / "later")
    later_inputs = _provider_inputs(later_run)
    assisted_key = next(iter(later_inputs))
    mechanical_entry = next(
        entry
        for entry in later_run.attention.mechanical.entries
        if type(entry.key) is ProcedurePredicateKey
        and entry.key.phase is PredicatePhase.PRECONDITION
    )

    def remove_later_invocation(
        request: ProcedureEvaluatorInputRequest,
    ) -> EvaluatorInput:
        object.__delattr__(mechanical_entry, "invocation")
        return later_inputs[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            later_run,
            {
                key: (
                    remove_later_invocation
                    if key == assisted_key
                    else (lambda request, value=value: value)
                )
                for key, value in later_inputs.items()
            },
        )

    _, _, _, current_run = _precondition_run(tmp_path / "current")
    current_inputs = _provider_inputs(current_run)
    current_key = next(iter(current_inputs))
    current_requirement = next(
        item for item in current_run.requirements if item.key is current_key
    )

    def remove_current_authority(
        request: ProcedureEvaluatorInputRequest,
    ) -> EvaluatorInput:
        object.__delattr__(current_requirement, "evaluator")
        return current_inputs[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            current_run,
            {
                key: (
                    remove_current_authority
                    if key == current_key
                    else (lambda request, value=value: value)
                )
                for key, value in current_inputs.items()
            },
        )

    _, _, _, malformed_run = _precondition_run(tmp_path / "later-malformed")
    malformed_inputs = _provider_inputs(malformed_run)
    malformed_key = next(iter(malformed_inputs))
    mechanical_packet = malformed_run.attention.mechanical
    original_entries = mechanical_packet.entries
    mechanical_index = next(
        index
        for index, entry in enumerate(original_entries)
        if type(entry.key) is ProcedurePredicateKey
        and entry.key.phase is PredicatePhase.PRECONDITION
    )

    def replace_later_entry(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        partial = object.__new__(MechanicalAttentionEntry)
        object.__setattr__(partial, "key", original_entries[mechanical_index].key)
        changed = list(original_entries)
        changed[mechanical_index] = partial
        object.__setattr__(mechanical_packet, "entries", tuple(changed))
        return malformed_inputs[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            malformed_run,
            {
                key: (
                    replace_later_entry
                    if key == malformed_key
                    else (lambda request, value=value: value)
                )
                for key, value in malformed_inputs.items()
            },
        )


def test_precondition_evaluation_plan_retains_exact_registry_maps(
    tmp_path: Path,
) -> None:
    cases = (
        ("detector_registry", "bindings", dict),
        ("detector_registry", "input_contracts", MappingProxyType),
        ("checker_registry", "bindings", dict),
        ("checker_registry", "input_contracts", MappingProxyType),
        ("operation_registry", "bindings", dict),
        ("operation_registry", "contracts", MappingProxyType),
    )
    for index, (registry_name, field, wrapper) in enumerate(cases):
        _, _, _, run = _precondition_run(tmp_path / str(index))
        supplied = _provider_inputs(run)
        first_key = next(iter(supplied))
        registry = (
            run.operation_registry
            if registry_name == "operation_registry"
            else getattr(run.attention, registry_name)
        )
        original = getattr(registry, field)

        def mutate_registry(
            request: ProcedureEvaluatorInputRequest,
            /,
            *,
            target: object = registry,
            attribute: str = field,
            replacement: object = wrapper(dict(original)),
        ) -> EvaluatorInput:
            object.__setattr__(target, attribute, replacement)
            return supplied[request.key]

        with pytest.raises(ProcedureEvaluationPlanningError):
            plan_procedure_precondition_evaluations(
                run,
                {
                    key: (
                        mutate_registry
                        if key == first_key
                        else (lambda request, value=value: value)
                    )
                    for key, value in supplied.items()
                },
            )

    _, _, _, malformed_run = _precondition_run(tmp_path / "malformed")
    malformed_inputs = _provider_inputs(malformed_run)
    malformed_key = next(iter(malformed_inputs))

    def malformed_registry(
        request: ProcedureEvaluatorInputRequest,
    ) -> EvaluatorInput:
        detector = malformed_run.attention.detector_registry
        assert detector is not None
        object.__setattr__(detector, "bindings", object())
        return malformed_inputs[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            malformed_run,
            {
                key: (
                    malformed_registry
                    if key == malformed_key
                    else (lambda request, value=value: value)
                )
                for key, value in malformed_inputs.items()
            },
        )


def test_precondition_evaluation_plan_contains_provider_mapping_side_effects(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    supplied = _provider_inputs(run)
    providers = {
        key: (lambda request, value=value: value) for key, value in supplied.items()
    }
    registry = run.attention.resolution.registry

    class MutatingProviders(
        Mapping[ProcedurePredicateKey, ProcedureEvaluatorInputProvider]
    ):
        def __getitem__(
            self, key: ProcedurePredicateKey
        ) -> ProcedureEvaluatorInputProvider:
            return providers[key]

        def __iter__(self):
            return iter(providers)

        def __len__(self) -> int:
            return len(providers)

        def items(self):
            object.__setattr__(registry, "families", object())
            return providers.items()

    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(run, MutatingProviders())


def test_precondition_evaluation_plan_retains_declaration_registry_graph(
    tmp_path: Path,
) -> None:
    for index, field in enumerate(("records", "families")):
        _, _, _, run = _precondition_run(tmp_path / f"top-{index}")
        supplied = _provider_inputs(run)
        first_key = next(iter(supplied))
        registry = run.attention.resolution.registry
        replacement = MappingProxyType(dict(getattr(registry, field)))

        def replace_top_level(
            request: ProcedureEvaluatorInputRequest,
            /,
            *,
            attribute: str = field,
            value: object = replacement,
        ) -> EvaluatorInput:
            object.__setattr__(registry, attribute, value)
            return supplied[request.key]

        with pytest.raises(ProcedureEvaluationPlanningError):
            plan_procedure_precondition_evaluations(
                run,
                {
                    key: (
                        replace_top_level
                        if key == first_key
                        else (lambda request, value=value: value)
                    )
                    for key, value in supplied.items()
                },
            )

    _, _, _, nested_run = _precondition_run(tmp_path / "nested")
    nested_inputs = _provider_inputs(nested_run)
    nested_key = next(iter(nested_inputs))
    family = nested_run.attention.resolution.registry.families[DETECTOR.id]
    replacement_versions = MappingProxyType(dict(family.versions))

    def replace_versions(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        object.__setattr__(family, "versions", replacement_versions)
        return nested_inputs[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            nested_run,
            {
                key: (
                    replace_versions
                    if key == nested_key
                    else (lambda request, value=value: value)
                )
                for key, value in nested_inputs.items()
            },
        )


def test_precondition_evaluation_plan_rejects_provider_invocation_replacement(
    tmp_path: Path,
) -> None:
    for index, enforcement in enumerate(
        (EnforcementClass.ASSISTED, EnforcementClass.MECHANICAL)
    ):
        _, _, _, run = _precondition_run(tmp_path / str(index))
        supplied = _provider_inputs(run)
        requirement = next(
            item for item in run.requirements if item.enforcement is enforcement
        )
        key = cast(ProcedurePredicateKey, requirement.key)
        entry: AssistedAttentionEntry | MechanicalAttentionEntry
        replacement_input: Mapping[str, JsonValue]
        if enforcement is EnforcementClass.ASSISTED:
            entry = next(
                candidate
                for candidate in run.attention.assisted.entries
                if candidate.obligation.key is key
            )
            replacement_input = MappingProxyType(
                {"path": "replacement.txt", "content": "candidate"}
            )
        else:
            entry = next(
                candidate
                for candidate in run.attention.mechanical.entries
                if candidate.key is key
            )
            replacement_input = MappingProxyType(
                {"sources": ("replacement.yaml",), "facet-registry": "facets.yaml"}
            )
        original = entry.invocation

        def replace_invocation(
            request: ProcedureEvaluatorInputRequest,
        ) -> EvaluatorInput:
            object.__setattr__(
                entry,
                "invocation",
                EvaluatorInvocation(
                    original.evaluator,
                    original.evaluator_input_operation,
                    original.input_revision,
                    replacement_input,
                ),
            )
            return supplied[request.key]

        with pytest.raises(ProcedureEvaluationPlanningError):
            plan_procedure_precondition_evaluations(
                run,
                {
                    provider_key: (
                        replace_invocation
                        if provider_key is key
                        else (lambda request, value=value: value)
                    )
                    for provider_key, value in supplied.items()
                },
            )


def test_precondition_evaluation_plan_revalidates_during_result_traversal(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    supplied = _provider_inputs(run)
    key = next(iter(supplied))
    entry = next(
        candidate
        for candidate in run.attention.assisted.entries
        if candidate.obligation.key is key
    )
    invocation = entry.invocation
    replacement_input: Mapping[str, JsonValue] = MappingProxyType(
        {"path": "replacement.txt", "content": "candidate"}
    )

    class MutatingResult(Mapping[str, object]):
        def __getitem__(self, name: str) -> object:
            return replacement_input[name]

        def __iter__(self):
            return iter(replacement_input)

        def __len__(self) -> int:
            return len(replacement_input)

        def items(self):
            object.__setattr__(invocation, "input_data", replacement_input)
            return replacement_input.items()

    def mutating_result(
        request: ProcedureEvaluatorInputRequest,
    ) -> EvaluatorInput:
        return EvaluatorInput("declaration-v1", MutatingResult())

    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            run,
            {
                provider_key: (
                    mutating_result
                    if provider_key is key
                    else (lambda request, value=value: value)
                )
                for provider_key, value in supplied.items()
            },
        )

    _, _, _, registry_run = _precondition_run(tmp_path / "registry")
    registry_inputs = _provider_inputs(registry_run)
    registry_key = next(iter(registry_inputs))
    original_input = registry_inputs[registry_key].input_data
    registry = registry_run.attention.resolution.registry

    class RegistryMutatingResult(Mapping[str, object]):
        def __getitem__(self, name: str) -> object:
            return original_input[name]

        def __iter__(self):
            return iter(original_input)

        def __len__(self) -> int:
            return len(original_input)

        def items(self):
            object.__setattr__(registry, "families", object())
            return original_input.items()

    def mutate_registry_during_result(
        request: ProcedureEvaluatorInputRequest,
    ) -> EvaluatorInput:
        return EvaluatorInput("declaration-v1", RegistryMutatingResult())

    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            registry_run,
            {
                provider_key: (
                    mutate_registry_during_result
                    if provider_key == registry_key
                    else (lambda request, value=value: value)
                )
                for provider_key, value in registry_inputs.items()
            },
        )


def test_precondition_evaluation_request_detaches_key_and_predicate(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path / "detached")
    supplied = _provider_inputs(run)
    key = next(iter(supplied))
    requirement = next(item for item in run.requirements if item.key is key)
    obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
    original_expression = obligation.predicate.expression
    original_evaluator = obligation.predicate.evaluator
    assert original_evaluator is not None
    original_evaluator_id = original_evaluator.id

    def mutate_request(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        assert request.predicate.evaluator is not original_evaluator
        object.__setattr__(
            request.predicate,
            "expression",
            MappingProxyType({"facet": "scope.project", "operator": "exists"}),
        )
        assert request.predicate.evaluator is not None
        object.__setattr__(request.predicate.evaluator, "id", "detached/evaluator")
        object.__setattr__(request.key, "predicate", "detached-change")
        return supplied[key]

    providers = {
        provider_key: (
            mutate_request
            if provider_key is key
            else (lambda request, value=value: value)
        )
        for provider_key, value in supplied.items()
    }
    plan = plan_procedure_precondition_evaluations(run, providers)
    assert _is_issued_procedure_precondition_evaluation_plan(plan)
    assert obligation.predicate.expression is original_expression
    assert original_evaluator.id == original_evaluator_id
    assert key.predicate != "detached-change"

    _, _, _, canonical_run = _precondition_run(tmp_path / "canonical")
    canonical_inputs = _provider_inputs(canonical_run)
    canonical_key = next(iter(canonical_inputs))
    canonical_requirement = next(
        item for item in canonical_run.requirements if item.key is canonical_key
    )
    canonical_obligation = cast(
        ProcedureObligationSnapshot, canonical_requirement.obligation
    )

    def mutate_canonical(
        request: ProcedureEvaluatorInputRequest,
    ) -> EvaluatorInput:
        object.__setattr__(
            canonical_obligation.predicate,
            "expression",
            MappingProxyType({"facet": "scope.project", "operator": "exists"}),
        )
        return canonical_inputs[canonical_key]

    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            canonical_run,
            {
                provider_key: (
                    mutate_canonical
                    if provider_key is canonical_key
                    else (lambda request, value=value: value)
                )
                for provider_key, value in canonical_inputs.items()
            },
        )


def test_precondition_evaluation_plan_retains_exact_registry_binding_fields(
    tmp_path: Path,
) -> None:
    registry_cases = ("detector", "checker", "operation")
    for index, registry_kind in enumerate(registry_cases):
        _, _, _, run = _precondition_run(tmp_path / f"runner-{index}")
        supplied = _provider_inputs(run)
        first_key = next(iter(supplied))
        if registry_kind == "detector":
            registry = run.attention.detector_registry
            assert registry is not None
            binding = registry.bindings[DETECTOR]
        elif registry_kind == "checker":
            registry = run.attention.checker_registry
            assert registry is not None
            binding = registry.bindings[CHECKER]
        else:
            binding = run.operation_registry.bindings[WRITE]

        def replace_runner(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
            object.__setattr__(binding, "runner", object())
            return supplied[request.key]

        with pytest.raises(ProcedureEvaluationPlanningError):
            plan_procedure_precondition_evaluations(
                run,
                {
                    key: (
                        replace_runner
                        if key == first_key
                        else (lambda request, value=value: value)
                    )
                    for key, value in supplied.items()
                },
            )

    _, _, _, reference_run = _precondition_run(tmp_path / "reference")
    reference_inputs = _provider_inputs(reference_run)
    reference_key = next(iter(reference_inputs))
    detector = reference_run.attention.detector_registry
    assert detector is not None
    binding = detector.bindings[DETECTOR]

    def replace_reference(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        object.__setattr__(
            binding,
            "evaluator",
            VersionedReference(DETECTOR.id, DETECTOR.version),
        )
        return reference_inputs[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            reference_run,
            {
                key: (
                    replace_reference
                    if key == reference_key
                    else (lambda request, value=value: value)
                )
                for key, value in reference_inputs.items()
            },
        )


def test_precondition_evaluation_plan_rejects_tampered_attention_invocation(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    supplied = _provider_inputs(run)
    calls = 0

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal calls
        calls += 1
        return supplied[request.key]

    invocation = run.attention.assisted.entries[0].invocation
    object.__setattr__(invocation, "input_revision", "unadmitted")

    with pytest.raises(ProcedureEvaluationPlanningError, match="issued by preflight"):
        plan_procedure_precondition_evaluations(
            run, {key: provider for key in supplied}
        )
    assert calls == 0


def test_precondition_evaluation_plan_requires_immutable_retained_inputs(
    tmp_path: Path,
) -> None:
    _, _, _, pre_run = _precondition_run(tmp_path / "before")
    pre_inputs = _provider_inputs(pre_run)
    pre_invocation = pre_run.attention.assisted.entries[0].invocation
    object.__setattr__(pre_invocation, "input_data", dict(pre_invocation.input_data))
    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            pre_run,
            {
                key: (lambda request, value=value: value)
                for key, value in pre_inputs.items()
            },
        )

    _, _, _, during_run = _precondition_run(tmp_path / "during")
    during_inputs = _provider_inputs(during_run)
    first_key = next(iter(during_inputs))

    def mutating_provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        invocation = during_run.attention.assisted.entries[0].invocation
        object.__setattr__(invocation, "input_data", dict(invocation.input_data))
        return during_inputs[request.key]

    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            during_run,
            {
                key: (
                    mutating_provider
                    if key == first_key
                    else (lambda request, value=value: value)
                )
                for key, value in during_inputs.items()
            },
        )

    _, _, _, after_run = _precondition_run(tmp_path / "after")
    after_inputs = _provider_inputs(after_run)
    plan = plan_procedure_precondition_evaluations(
        after_run,
        {
            key: (lambda request, value=value: value)
            for key, value in after_inputs.items()
        },
    )
    after_invocation = after_run.attention.assisted.entries[0].invocation
    object.__setattr__(
        after_invocation, "input_data", dict(after_invocation.input_data)
    )
    assert not _is_issued_procedure_precondition_evaluation_plan(plan)


def test_precondition_evaluation_plan_contains_malformed_invocation_fields(
    tmp_path: Path,
) -> None:
    mutations = (
        ("input_revision", _HostileRevision()),
        ("evaluator", object()),
        ("evaluator_input_operation", object()),
    )
    for index, (field, value) in enumerate(mutations):
        _, _, _, run = _precondition_run(tmp_path / str(index))
        supplied = _provider_inputs(run)
        invocation = run.attention.assisted.entries[0].invocation
        object.__setattr__(invocation, field, value)
        with pytest.raises(ProcedureEvaluationPlanningError):
            plan_procedure_precondition_evaluations(
                run,
                {
                    key: (lambda request, result=result: result)
                    for key, result in supplied.items()
                },
            )

    _, _, _, incomplete_run = _precondition_run(tmp_path / "incomplete")
    supplied = _provider_inputs(incomplete_run)
    object.__setattr__(
        incomplete_run.attention.assisted.entries[0],
        "invocation",
        object.__new__(EvaluatorInvocation),
    )
    with pytest.raises(ProcedureEvaluationPlanningError):
        plan_procedure_precondition_evaluations(
            incomplete_run,
            {
                key: (lambda request, result=result: result)
                for key, result in supplied.items()
            },
        )


def test_precondition_evaluation_plan_handles_empty_and_wrong_timing(
    tmp_path: Path,
) -> None:
    _, declarations, resolution, _, _ = _prepare_registry(tmp_path / "empty", "none")
    attention = plan_attention(derive_attention_requirements(resolution), {})
    run = _procedure_run(attention)

    plan = plan_procedure_precondition_evaluations(run, {})

    assert plan.records == ()
    assert _is_issued_procedure_precondition_evaluation_plan(plan)

    _, _, _, _, late_attention = _mixed_plan(tmp_path / "late")
    with pytest.raises(ProcedureEvaluationPlanningError, match="must be pre-action"):
        plan_procedure_precondition_evaluations(_procedure_run(late_attention), {})


def test_precondition_evaluation_plan_retains_detached_provider_inputs(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    supplied = _provider_inputs(run)
    calls = 0

    def provider(request: ProcedureEvaluatorInputRequest) -> EvaluatorInput:
        nonlocal calls
        calls += 1
        return supplied[request.key]

    plan = plan_procedure_precondition_evaluations(
        run, {key: provider for key in supplied}
    )

    assert calls == len(supplied)
    for record in (*plan.assisted, *plan.mechanical):
        invocation = record.entry.invocation
        assert record.evaluator_input.input_revision == invocation.input_revision
        assert record.evaluator_input.input_data == invocation.input_data
        assert record.evaluator_input.input_data is not invocation.input_data
        assert type(record.evaluator_input.input_data) is MappingProxyType
    assert calls == len(supplied)
    assert _is_issued_procedure_precondition_evaluation_plan(plan)


def test_precondition_evaluation_plan_binds_retained_input_carriers(
    tmp_path: Path,
) -> None:
    def build(path: Path) -> ProcedurePreconditionEvaluationPlan:
        _, _, _, run = _precondition_run(path)
        supplied = _provider_inputs(run)
        return plan_procedure_precondition_evaluations(
            run,
            {
                key: (lambda request, value=value: value)
                for key, value in supplied.items()
            },
        )

    replaced = build(tmp_path / "replaced")
    replaced_record = replaced.assisted[0]
    retained = replaced_record.evaluator_input
    object.__setattr__(
        replaced_record,
        "evaluator_input",
        EvaluatorInput(retained.input_revision, retained.input_data),
    )
    assert not _is_issued_procedure_precondition_evaluation_plan(replaced)

    mutable = build(tmp_path / "mutable")
    mutable_input = mutable.mechanical[0].evaluator_input
    object.__setattr__(mutable_input, "input_data", dict(mutable_input.input_data))
    assert not _is_issued_procedure_precondition_evaluation_plan(mutable)

    changed = build(tmp_path / "changed")
    changed_input = changed.assisted[0].evaluator_input
    object.__setattr__(changed_input, "input_revision", "different-revision")
    assert not _is_issued_procedure_precondition_evaluation_plan(changed)


def _pre_action_authorities(
    tmp_path: Path,
    *,
    checker_runner: CheckerRunner = cast(CheckerRunner, _checker_result_for_input),
    detector_runner: DetectorRunner = cast(
        DetectorRunner, lambda input_data: _detector_result()
    ),
    observation_provider: ObservationProvider | None = None,
    duplicate_preconditions: bool = False,
    local_precondition_operator: str = "exists",
    later_requirements: bool = False,
    evaluator_backed_lifecycle: bool | str = False,
    lifecycle_location: str = "invariant",
    lifecycle_timing: str | None = None,
    two_actions: bool = False,
    operation_runner: OperationRunner = cast(
        OperationRunner, lambda input_data: OperationFailure(WRITE, "write-failed")
    ),
):
    """Build exact pre-action authorities and their external judgment inputs."""
    _, _, _, run = _precondition_run(
        tmp_path,
        checker_runner=checker_runner,
        detector_runner=detector_runner,
        duplicate_preconditions=duplicate_preconditions,
        local_precondition_operator=local_precondition_operator,
        later_requirements=later_requirements,
        evaluator_backed_lifecycle=evaluator_backed_lifecycle,
        lifecycle_location=lifecycle_location,
        lifecycle_timing=lifecycle_timing,
        two_actions=two_actions,
        operation_runner=operation_runner,
    )
    supplied = {
        key: value
        for key, value in _provider_inputs(run).items()
        if key.phase is PredicatePhase.PRECONDITION
    }
    evaluation_plan = plan_procedure_precondition_evaluations(
        run,
        {key: (lambda request, value=value: value) for key, value in supplied.items()},
    )
    declarations = run.attention.resolution.registry
    observation_registry = build_observation_provider_registry(
        declarations,
        declarations.facet_registry,
        observation_provider
        or cast(
            ObservationProvider,
            lambda request: {facet: True for facet in request.facets},
        ),
    )
    observation = observe_procedure_preconditions(run, observation_registry)
    manual = {
        cast(ProcedurePredicateKey, record.requirement.key): ManualJudgmentSubmission(
            cast(ProcedurePredicateKey, record.requirement.key),
            VersionedReference(
                record.entry.evaluator.id, record.entry.evaluator.version
            ),
            record.entry.evaluator.input_revisions[0],
            {"conclusion": "satisfied"},
        )
        for record in evaluation_plan.manual
    }
    residual: dict[ProcedurePredicateKey, ResidualJudgmentProvider] = {}
    for record in evaluation_plan.assisted:
        key = cast(ProcedurePredicateKey, record.requirement.key)

        def provider(
            request: ResidualJudgmentRequest,
            *,
            expected_key: ProcedurePredicateKey = key,
        ) -> ResidualJudgmentSubmission:
            invocation = next(
                item.entry.invocation
                for item in evaluation_plan.assisted
                if item.requirement.key is expected_key
            )
            assert request.requirement.key is expected_key
            return ResidualJudgmentSubmission(
                1,
                expected_key,
                invocation.evaluator,
                invocation.input_revision,
                EvaluationState.SATISFIED,
                "The detector evidence leaves no violating candidate.",
            )

        residual[key] = cast(ResidualJudgmentProvider, provider)
    return evaluation_plan, observation, manual, residual


def _pre_action_session_inputs(
    tmp_path: Path,
    **kwargs: object,
):
    """Build one ready session and its exact external judgment inputs."""
    plan, observation, manual, residual = _pre_action_authorities(tmp_path, **kwargs)
    return create_pre_action_evidence_session(plan, observation), manual, residual


def test_pre_action_evidence_session_issues_complete_canonical_clearance(
    tmp_path: Path,
) -> None:
    session, manual, residual = _pre_action_session_inputs(tmp_path)

    evidence = session.execute(manual=manual, residual_providers=residual)

    assert session.state is PreActionEvidenceSessionState.COMPLETED
    assert session.evidence is evidence
    assert evidence.cleared
    assert _is_issued_pre_action_evidence(evidence)
    assert tuple(record.requirement for record in evidence.records) == (
        evidence.plan.run.procedure_precondition_requirements
    )
    assert tuple(type(record) for record in evidence.records) == (
        ManualPreconditionEvidence,
        AssistedPreconditionEvidence,
        MechanicalPreconditionEvidence,
        ObservedPreconditionEvidence,
    )
    assert all(record.state is EvaluationState.SATISFIED for record in evidence.records)
    with pytest.raises(PreActionEvidenceError, match="completed"):
        session.execute(manual=manual, residual_providers=residual)


def test_pre_action_evidence_excludes_later_run_requirements(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(
        tmp_path,
        later_requirements=True,
    )
    supplied = _provider_inputs(run)
    evaluation_plan = plan_procedure_precondition_evaluations(
        run,
        {key: (lambda request, value=value: value) for key, value in supplied.items()},
    )
    observation_registry = build_observation_provider_registry(
        run.attention.resolution.registry,
        run.attention.resolution.registry.facet_registry,
        cast(
            ObservationProvider,
            lambda request: {facet: True for facet in request.facets},
        ),
    )
    observation = observe_procedure_preconditions(run, observation_registry)
    manual = {
        cast(ProcedurePredicateKey, record.requirement.key): ManualJudgmentSubmission(
            cast(ProcedurePredicateKey, record.requirement.key),
            VersionedReference(
                record.entry.evaluator.id,
                record.entry.evaluator.version,
            ),
            record.entry.evaluator.input_revisions[0],
            {"conclusion": "satisfied"},
        )
        for record in evaluation_plan.manual
    }
    residual = {
        cast(ProcedurePredicateKey, record.requirement.key): cast(
            ResidualJudgmentProvider,
            lambda request, item=record: ResidualJudgmentSubmission(
                1,
                cast(ProcedurePredicateKey, item.requirement.key),
                item.entry.invocation.evaluator,
                item.entry.invocation.input_revision,
                EvaluationState.SATISFIED,
                "The detector evidence leaves no violating candidate.",
            ),
        )
        for record in evaluation_plan.assisted
    }

    evidence = create_pre_action_evidence_session(evaluation_plan, observation).execute(
        manual=manual, residual_providers=residual
    )

    assert evidence.cleared
    assert all(
        record.requirement is requirement
        for record, requirement in zip(
            evidence.records, run.procedure_precondition_requirements
        )
    )
    assert len(evidence.records) == 4
    assert len(run.pre_action_requirements) > len(evidence.records)
    assert any(
        isinstance(item.key, OperationPredicateKey)
        for item in run.pre_action_requirements
    )
    assert any(
        isinstance(item.key, ProcedurePredicateKey)
        and item.key.phase is PredicatePhase.INVARIANT
        for item in run.pre_action_requirements
    )
    assert any(
        isinstance(item.key, ProcedurePredicateKey)
        and item.key.phase is PredicatePhase.POSTCONDITION
        for item in run.requirements
    )


def test_pre_action_evidence_rejects_key_errors_before_execution(
    tmp_path: Path,
) -> None:
    session, manual, residual = _pre_action_session_inputs(tmp_path)
    manual.clear()

    with pytest.raises(PreActionEvidenceError, match="exact required keys"):
        session.execute(manual=manual, residual_providers=residual)

    assert session.state is PreActionEvidenceSessionState.READY
    assert session.evidence is None


def test_pre_action_evidence_session_rejects_reentrant_execution(
    tmp_path: Path,
) -> None:
    session, manual, residual = _pre_action_session_inputs(tmp_path)
    key = next(iter(residual))
    original = residual[key]
    attempts = 0

    def reentrant(request: ResidualJudgmentRequest) -> ResidualJudgmentSubmission:
        nonlocal attempts
        attempts += 1
        with pytest.raises(PreActionEvidenceError):
            session.execute(manual=manual, residual_providers=residual)
        return original(request)

    residual[key] = cast(ResidualJudgmentProvider, reentrant)
    evidence = session.execute(manual=manual, residual_providers=residual)

    assert attempts == 1
    assert evidence.cleared
    assert session.state is PreActionEvidenceSessionState.COMPLETED


def test_invalid_residual_judgment_is_terminal_after_detector_execution(
    tmp_path: Path,
) -> None:
    session, manual, residual = _pre_action_session_inputs(tmp_path)
    key = next(iter(residual))

    residual[key] = cast(
        ResidualJudgmentProvider,
        lambda request: ResidualJudgmentSubmission(
            1,
            key,
            request.execution.evaluator,
            request.execution.input_revision,
            EvaluationState.SATISFIED,
            "",
        ),
    )
    with pytest.raises(PreActionEvidenceError, match="rationale"):
        session.execute(manual=manual, residual_providers=residual)

    assert session.state is PreActionEvidenceSessionState.FAILED_AFTER_EXECUTION
    with pytest.raises(PreActionEvidenceError, match="failed-after-execution"):
        session.execute(manual=manual, residual_providers=residual)


def test_pre_action_runner_failures_are_blocked_and_batch_continues(
    tmp_path: Path,
) -> None:
    detector_calls = 0
    checker_calls = 0

    def detector_runner(input_data: Mapping[str, JsonValue]) -> DetectorResult:
        nonlocal detector_calls
        detector_calls += 1
        raise RuntimeError("detector unavailable")

    def checker_runner(input_data: Mapping[str, JsonValue]) -> CheckerResult:
        nonlocal checker_calls
        sources = cast(tuple[str, ...], input_data["sources"])
        if any(source.endswith("invalid.yaml") for source in sources):
            return _checker_result()
        checker_calls += 1
        raise RuntimeError("checker unavailable")

    session, manual, residual = _pre_action_session_inputs(
        tmp_path,
        checker_runner=cast(CheckerRunner, checker_runner),
        detector_runner=cast(DetectorRunner, detector_runner),
    )
    residual_calls = 0
    assisted_key = next(iter(residual))

    def forbidden_residual(
        request: ResidualJudgmentRequest,
    ) -> ResidualJudgmentSubmission:
        nonlocal residual_calls
        residual_calls += 1
        raise AssertionError("residual judgment must not run after detector failure")

    residual[assisted_key] = cast(ResidualJudgmentProvider, forbidden_residual)
    evidence = session.execute(manual=manual, residual_providers=residual)

    assert detector_calls == 1
    assert checker_calls == 1
    assert residual_calls == 0
    assert session.state is PreActionEvidenceSessionState.COMPLETED
    assert not evidence.cleared
    assisted = next(
        record
        for record in evidence.records
        if type(record) is AssistedPreconditionEvidence
    )
    mechanical = next(
        record
        for record in evidence.records
        if type(record) is MechanicalPreconditionEvidence
    )
    assert assisted.state is EvaluationState.BLOCKED
    assert assisted.execution is None and assisted.judgment is None
    assert "detector unavailable" in cast(str, assisted.diagnostic)
    assert mechanical.state is EvaluationState.BLOCKED
    assert mechanical.result is None
    assert "checker unavailable" in cast(str, mechanical.diagnostic)
    assert _is_issued_pre_action_evidence(evidence)


def test_pre_action_evidence_requires_observation_from_the_same_run(
    tmp_path: Path,
) -> None:
    session, _, _ = _pre_action_session_inputs(tmp_path / "first")
    foreign, _, _ = _pre_action_session_inputs(tmp_path / "second")

    with pytest.raises(PreActionEvidenceError, match="another run"):
        create_pre_action_evidence_session(session.plan, foreign.observation)


def test_pre_action_evidence_accepts_issued_empty_observation(
    tmp_path: Path,
) -> None:
    _, declarations, resolution, _, _ = _prepare_registry(tmp_path, "none")
    attention = plan_attention(derive_attention_requirements(resolution), {})
    run = _procedure_run(attention)
    plan = plan_procedure_precondition_evaluations(run, {})

    def forbidden_observation(request: object) -> Mapping[str, object]:
        raise AssertionError("empty observation must not call its provider")

    registry = build_observation_provider_registry(
        declarations,
        declarations.facet_registry,
        cast(ObservationProvider, forbidden_observation),
    )
    observation = observe_procedure_preconditions(run, registry)
    session = create_pre_action_evidence_session(plan, observation)

    evidence = session.execute(manual={}, residual_providers={})

    assert evidence.records == ()
    assert evidence.cleared
    assert _is_issued_pre_action_evidence(evidence)


def test_residual_provider_cannot_mutate_issued_detector_execution(
    tmp_path: Path,
) -> None:
    session, manual, residual = _pre_action_session_inputs(tmp_path)
    key = next(iter(residual))
    original = residual[key]

    def mutating_provider(
        request: ResidualJudgmentRequest,
    ) -> ResidualJudgmentSubmission:
        judgment = original(request)
        object.__setattr__(
            request.execution,
            "evidence",
            MappingProxyType({"accepted": False}),
        )
        return judgment

    residual[key] = cast(ResidualJudgmentProvider, mutating_provider)

    with pytest.raises(PreActionEvidenceError, match="execution"):
        session.execute(manual=manual, residual_providers=residual)

    assert session.state is PreActionEvidenceSessionState.FAILED_AFTER_EXECUTION


def test_issued_pre_action_evidence_detects_result_carrier_mutation(
    tmp_path: Path,
) -> None:
    session, manual, residual = _pre_action_session_inputs(tmp_path)
    evidence = session.execute(manual=manual, residual_providers=residual)
    mechanical = next(
        record
        for record in evidence.records
        if type(record) is MechanicalPreconditionEvidence
    )
    assert mechanical.result is not None

    object.__setattr__(mechanical.result, "state", EvaluationState.VIOLATED)

    assert not _is_issued_pre_action_evidence(evidence)


def test_pre_action_session_authority_rejects_duplication_and_reset(
    tmp_path: Path,
) -> None:
    session, manual, residual = _pre_action_session_inputs(tmp_path)

    with pytest.raises(PreActionEvidenceError, match="already owns"):
        create_pre_action_evidence_session(session.plan, session.observation)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(session)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.deepcopy(session)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(session)
    forged = object.__new__(PreActionEvidenceSession)
    with pytest.raises(PreActionEvidenceError, match="not issued"):
        forged.execute(manual=manual, residual_providers=residual)

    session.execute(manual=manual, residual_providers=residual)
    with pytest.raises(AttributeError):
        session.state = PreActionEvidenceSessionState.READY  # type: ignore[misc]
    with pytest.raises(PreActionEvidenceError, match="completed"):
        session.execute(manual=manual, residual_providers=residual)

    token_session, token_manual, token_residual = _pre_action_session_inputs(
        tmp_path / "token"
    )
    assert not hasattr(token_session, "_control")
    object.__setattr__(token_session, "_token", object())
    with pytest.raises(PreActionEvidenceError, match="authority differs"):
        token_session.execute(manual=token_manual, residual_providers=token_residual)

    issuer_session, issuer_manual, issuer_residual = _pre_action_session_inputs(
        tmp_path / "session-issuer"
    )
    object.__setattr__(issuer_session, "_issuer", object())
    with pytest.raises(PreActionEvidenceError, match="not issued"):
        issuer_session.execute(manual=issuer_manual, residual_providers=issuer_residual)


def test_pre_action_session_cleans_up_every_base_exception(
    tmp_path: Path,
) -> None:
    session, manual, residual = _pre_action_session_inputs(tmp_path / "before")

    class InterruptingMapping(dict[ProcedurePredicateKey, ManualJudgmentSubmission]):
        def items(self):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        session.execute(manual=InterruptingMapping(manual), residual_providers=residual)
    assert session.state is PreActionEvidenceSessionState.READY
    assert session.execute(manual=manual, residual_providers=residual).cleared

    terminal, terminal_manual, terminal_residual = _pre_action_session_inputs(
        tmp_path / "after"
    )
    key = next(iter(terminal_residual))

    def interrupt(request: ResidualJudgmentRequest) -> ResidualJudgmentSubmission:
        raise SystemExit(3)

    terminal_residual[key] = cast(ResidualJudgmentProvider, interrupt)
    with pytest.raises(SystemExit):
        terminal.execute(manual=terminal_manual, residual_providers=terminal_residual)
    assert terminal.state is PreActionEvidenceSessionState.FAILED_AFTER_EXECUTION


def test_pre_action_session_cleans_up_transition_interruptions(
    tmp_path: Path,
) -> None:
    class ExitInterruptingLock:
        def __init__(self, delegate: object) -> None:
            self.delegate = delegate
            self.interrupted = False

        def __enter__(self):
            return self.delegate.__enter__()  # type: ignore[attr-defined]

        def __exit__(self, *args: object):
            result = self.delegate.__exit__(*args)  # type: ignore[attr-defined]
            if not self.interrupted:
                self.interrupted = True
                raise KeyboardInterrupt
            return result

    class InterruptingLock:
        def __init__(self, delegate: object, fail_on: int) -> None:
            self.delegate = delegate
            self.fail_on = fail_on
            self.entries = 0

        def __enter__(self):
            self.entries += 1
            if self.entries == self.fail_on:
                raise KeyboardInterrupt
            return self.delegate.__enter__()  # type: ignore[attr-defined]

        def __exit__(self, *args: object):
            return self.delegate.__exit__(*args)  # type: ignore[attr-defined]

    claim, claim_manual, claim_residual = _pre_action_session_inputs(
        tmp_path / "claim-transition"
    )
    claim_control = _SESSION_CONTROLS[claim]
    claim_control.lock = cast(
        object, ExitInterruptingLock(claim_control.lock)
    )  # type: ignore[assignment]
    with pytest.raises(KeyboardInterrupt):
        claim.execute(manual=claim_manual, residual_providers=claim_residual)
    assert claim.state is PreActionEvidenceSessionState.READY
    assert claim.execute(manual=claim_manual, residual_providers=claim_residual).cleared

    traced, traced_manual, traced_residual = _pre_action_session_inputs(
        tmp_path / "claim-bytecode"
    )
    source, start = inspect.getsourcelines(PreActionEvidenceSession.execute)
    active_line = start + next(
        index for index, line in enumerate(source) if "control.active = True" in line
    )

    def interrupt_before_active(frame: object, event: str, arg: object):
        if (
            event == "line"
            and frame.f_code is PreActionEvidenceSession.execute.__code__  # type: ignore[attr-defined]
            and frame.f_lineno == active_line  # type: ignore[attr-defined]
        ):
            sys.settrace(None)
            raise KeyboardInterrupt
        return interrupt_before_active

    sys.settrace(interrupt_before_active)
    try:
        with pytest.raises(KeyboardInterrupt):
            traced.execute(manual=traced_manual, residual_providers=traced_residual)
    finally:
        sys.settrace(None)
    assert traced.state is PreActionEvidenceSessionState.READY
    assert traced.execute(
        manual=traced_manual, residual_providers=traced_residual
    ).cleared

    before, before_manual, before_residual = _pre_action_session_inputs(
        tmp_path / "before-transition"
    )
    before_control = _SESSION_CONTROLS[before]
    before_control.lock = cast(
        object, InterruptingLock(before_control.lock, 2)
    )  # type: ignore[assignment]
    with pytest.raises(KeyboardInterrupt):
        before.execute(manual=before_manual, residual_providers=before_residual)
    assert before.state is PreActionEvidenceSessionState.READY

    after, after_manual, after_residual = _pre_action_session_inputs(
        tmp_path / "after-transition"
    )
    after_control = _SESSION_CONTROLS[after]
    after_control.lock = cast(
        object, InterruptingLock(after_control.lock, 3)
    )  # type: ignore[assignment]
    with pytest.raises(KeyboardInterrupt):
        after.execute(manual=after_manual, residual_providers=after_residual)
    assert after.state is PreActionEvidenceSessionState.FAILED_AFTER_EXECUTION
    assert after.evidence is None


def test_pre_action_inputs_require_canonical_keys_and_valid_manual_contracts(
    tmp_path: Path,
) -> None:
    copied, copied_manual, copied_residual = _pre_action_session_inputs(
        tmp_path / "copied"
    )
    canonical = next(iter(copied_residual))
    copied_key = ProcedurePredicateKey(
        canonical.declaration, canonical.phase, canonical.predicate
    )
    copied_provider = copied_residual.pop(canonical)
    copied_residual[copied_key] = copied_provider
    with pytest.raises(PreActionEvidenceError, match="exact required key"):
        copied.execute(manual=copied_manual, residual_providers=copied_residual)
    assert copied.state is PreActionEvidenceSessionState.READY

    malformed, malformed_manual, malformed_residual = _pre_action_session_inputs(
        tmp_path / "malformed"
    )
    manual_key = next(iter(malformed_manual))
    original = malformed_manual[manual_key]
    malformed_manual[manual_key] = ManualJudgmentSubmission(
        manual_key, original.evaluator, "unadmitted", {"conclusion": "satisfied"}
    )
    with pytest.raises(PreActionEvidenceError, match="not admitted"):
        malformed.execute(
            manual=malformed_manual, residual_providers=malformed_residual
        )
    assert malformed.state is PreActionEvidenceSessionState.READY


def test_aggregate_authority_rejects_detector_and_evaluator_corruption(
    tmp_path: Path,
) -> None:
    registry_session, manual, residual = _pre_action_session_inputs(
        tmp_path / "registry"
    )
    registry_evidence = registry_session.execute(
        manual=manual, residual_providers=residual
    )
    assisted = next(
        item
        for item in registry_evidence.records
        if type(item) is AssistedPreconditionEvidence
    )
    assert assisted.execution is not None
    object.__setattr__(
        assisted.execution,
        "registry",
        registry_session.plan.run.attention.checker_registry,
    )
    assert not _is_issued_pre_action_evidence(registry_evidence)

    issuer_session, issuer_manual, issuer_residual = _pre_action_session_inputs(
        tmp_path / "issuer"
    )
    issuer_evidence = issuer_session.execute(
        manual=issuer_manual, residual_providers=issuer_residual
    )
    issuer_assisted = next(
        item
        for item in issuer_evidence.records
        if type(item) is AssistedPreconditionEvidence
    )
    assert issuer_assisted.execution is not None
    object.__setattr__(issuer_assisted.execution, "_issuer", object())
    assert not _is_issued_pre_action_evidence(issuer_evidence)

    scalar_session, scalar_manual, scalar_residual = _pre_action_session_inputs(
        tmp_path / "scalar"
    )
    scalar_evidence = scalar_session.execute(
        manual=scalar_manual, residual_providers=scalar_residual
    )
    scalar_mechanical = next(
        item
        for item in scalar_evidence.records
        if type(item) is MechanicalPreconditionEvidence
    )
    assert scalar_mechanical.result is not None
    object.__setattr__(scalar_mechanical.result.evaluator, "id", "changed/checker")
    assert not _is_issued_pre_action_evidence(scalar_evidence)


def test_pre_action_missing_residual_and_malformed_manual_fail_before_running(
    tmp_path: Path,
) -> None:
    missing, missing_manual, _ = _pre_action_session_inputs(tmp_path / "missing")
    with pytest.raises(PreActionEvidenceError, match="exact required keys"):
        missing.execute(manual=missing_manual, residual_providers={})
    assert missing.state is PreActionEvidenceSessionState.READY

    cases = (
        ("missing-conclusion", {"review": "done"}, None),
        (
            "wrong-evaluator",
            {"conclusion": "satisfied"},
            VersionedReference("wrong/evaluator", 1),
        ),
    )
    for name, evidence, replacement in cases:
        session, manual, residual = _pre_action_session_inputs(tmp_path / name)
        key = next(iter(manual))
        original = manual[key]
        manual[key] = ManualJudgmentSubmission(
            key,
            replacement or original.evaluator,
            original.input_revision,
            evidence,
        )
        with pytest.raises(PreActionEvidenceError):
            session.execute(manual=manual, residual_providers=residual)
        assert session.state is PreActionEvidenceSessionState.READY


def test_invalid_evaluator_returns_become_blocked_records(
    tmp_path: Path,
) -> None:
    def invalid_detector(input_data: Mapping[str, JsonValue]) -> DetectorResult:
        return cast(DetectorResult, object())

    def invalid_checker(input_data: Mapping[str, JsonValue]) -> CheckerResult:
        sources = cast(tuple[str, ...], input_data["sources"])
        if any(source.endswith("invalid.yaml") for source in sources):
            return _checker_result()
        return cast(CheckerResult, object())

    session, manual, residual = _pre_action_session_inputs(
        tmp_path,
        checker_runner=cast(CheckerRunner, invalid_checker),
        detector_runner=cast(DetectorRunner, invalid_detector),
    )

    evidence = session.execute(manual=manual, residual_providers=residual)

    assert session.state is PreActionEvidenceSessionState.COMPLETED
    assert not evidence.cleared
    assert (
        sum(record.state is EvaluationState.BLOCKED for record in evidence.records) == 2
    )


def test_pre_action_non_satisfied_sources_prevent_clearance(
    tmp_path: Path,
) -> None:
    false_session, false_manual, false_residual = _pre_action_session_inputs(
        tmp_path / "observation",
        observation_provider=cast(
            ObservationProvider,
            lambda request: {},
        ),
    )
    false_evidence = false_session.execute(
        manual=false_manual, residual_providers=false_residual
    )
    assert not false_evidence.cleared
    assert any(
        type(record) is ObservedPreconditionEvidence
        and record.state is EvaluationState.VIOLATED
        for record in false_evidence.records
    )

    manual_session, manual, residual = _pre_action_session_inputs(tmp_path / "manual")
    key = next(iter(manual))
    original = manual[key]
    manual[key] = ManualJudgmentSubmission(
        key, original.evaluator, original.input_revision, {"conclusion": "blocked"}
    )
    manual_evidence = manual_session.execute(manual=manual, residual_providers=residual)
    assert not manual_evidence.cleared
    assert any(
        type(record) is ManualPreconditionEvidence
        and record.state is EvaluationState.BLOCKED
        for record in manual_evidence.records
    )

    residual_session, residual_manual, residual = _pre_action_session_inputs(
        tmp_path / "residual"
    )
    residual_key = next(iter(residual))
    residual[residual_key] = cast(
        ResidualJudgmentProvider,
        lambda request: ResidualJudgmentSubmission(
            1,
            residual_key,
            request.execution.evaluator,
            request.execution.input_revision,
            EvaluationState.VIOLATED,
            "A violating candidate remains.",
        ),
    )
    residual_evidence = residual_session.execute(
        manual=residual_manual, residual_providers=residual
    )
    assert not residual_evidence.cleared


def test_pre_action_total_state_mappings_retain_non_satisfied_results(
    tmp_path: Path,
) -> None:
    unknown_session, unknown_manual, unknown_residual = _pre_action_session_inputs(
        tmp_path / "unknown",
        observation_provider=cast(ObservationProvider, lambda request: {}),
        local_precondition_operator="equals",
    )
    unknown = unknown_session.execute(
        manual=unknown_manual, residual_providers=unknown_residual
    )
    unknown_record = next(
        item for item in unknown.records if type(item) is ObservedPreconditionEvidence
    )
    assert unknown_record.state is EvaluationState.BLOCKED
    assert not unknown.cleared

    violated_session, violated_manual, violated_residual = _pre_action_session_inputs(
        tmp_path / "manual-violated"
    )
    manual_key = next(iter(violated_manual))
    manual_submission = violated_manual[manual_key]
    violated_manual[manual_key] = ManualJudgmentSubmission(
        manual_key,
        manual_submission.evaluator,
        manual_submission.input_revision,
        {"conclusion": "violated"},
    )
    violated = violated_session.execute(
        manual=violated_manual, residual_providers=violated_residual
    )
    violated_record = next(
        item for item in violated.records if type(item) is ManualPreconditionEvidence
    )
    assert violated_record.state is EvaluationState.VIOLATED
    assert not violated.cleared

    blocked_session, blocked_manual, blocked_residual = _pre_action_session_inputs(
        tmp_path / "residual-blocked"
    )
    residual_key = next(iter(blocked_residual))
    blocked_residual[residual_key] = cast(
        ResidualJudgmentProvider,
        lambda request: ResidualJudgmentSubmission(
            1,
            residual_key,
            request.execution.evaluator,
            request.execution.input_revision,
            EvaluationState.BLOCKED,
            "The remaining evidence is inconclusive.",
        ),
    )
    blocked = blocked_session.execute(
        manual=blocked_manual, residual_providers=blocked_residual
    )
    blocked_record = next(
        item for item in blocked.records if type(item) is AssistedPreconditionEvidence
    )
    assert blocked_record.state is EvaluationState.BLOCKED
    assert blocked_record.diagnostic is None
    assert not blocked.cleared

    checker_session, checker_manual, checker_residual = _pre_action_session_inputs(
        tmp_path / "checker-violated",
        checker_runner=cast(CheckerRunner, lambda input_data: _checker_result()),
    )
    checker = checker_session.execute(
        manual=checker_manual, residual_providers=checker_residual
    )
    checker_record = next(
        item for item in checker.records if type(item) is MechanicalPreconditionEvidence
    )
    assert checker_record.state is EvaluationState.VIOLATED
    assert checker_record.result is not None
    assert checker_record.diagnostic is None
    assert not checker.cleared


def test_callback_authority_mutation_is_terminal(
    tmp_path: Path,
) -> None:
    session, manual, residual = _pre_action_session_inputs(tmp_path)
    key = next(iter(residual))
    original = residual[key]

    def mutate_observation(
        request: ResidualJudgmentRequest,
    ) -> ResidualJudgmentSubmission:
        result = original(request)
        object.__setattr__(session.observation, "occurrence", 1)
        return result

    residual[key] = cast(ResidualJudgmentProvider, mutate_observation)
    with pytest.raises(PreActionEvidenceError, match="observation"):
        session.execute(manual=manual, residual_providers=residual)
    assert session.state is PreActionEvidenceSessionState.FAILED_AFTER_EXECUTION


def test_submission_mapping_order_does_not_change_canonical_record_order(
    tmp_path: Path,
) -> None:
    session, manual, residual = _pre_action_session_inputs(
        tmp_path, duplicate_preconditions=True
    )
    reversed_manual = dict(reversed(tuple(manual.items())))
    reversed_residual = dict(reversed(tuple(residual.items())))

    evidence = session.execute(
        manual=reversed_manual, residual_providers=reversed_residual
    )

    assert tuple(record.requirement for record in evidence.records) == (
        session.plan.run.pre_action_requirements
    )
    assert evidence.cleared


def test_concurrent_factory_calls_claim_one_exact_plan(tmp_path: Path) -> None:
    plan, observation, _, _ = _pre_action_authorities(tmp_path)
    barrier = Barrier(3)

    def create() -> object:
        barrier.wait()
        try:
            return create_pre_action_evidence_session(plan, observation)
        except PreActionEvidenceError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (executor.submit(create), executor.submit(create))
        barrier.wait()
        results = tuple(future.result() for future in futures)

    assert sum(type(item) is PreActionEvidenceSession for item in results) == 1
    assert sum(type(item) is PreActionEvidenceError for item in results) == 1


def test_distinct_evaluation_plans_cannot_reexecute_one_run(tmp_path: Path) -> None:
    first_plan, observation, _, _ = _pre_action_authorities(tmp_path)
    create_pre_action_evidence_session(first_plan, observation)
    supplied = _provider_inputs(first_plan.run)
    second_plan = plan_procedure_precondition_evaluations(
        first_plan.run,
        {key: (lambda request, value=value: value) for key, value in supplied.items()},
    )

    with pytest.raises(PreActionEvidenceError, match="run already owns"):
        create_pre_action_evidence_session(second_plan, observation)


def test_concurrent_execute_calls_claim_one_transaction(tmp_path: Path) -> None:
    session, manual, residual = _pre_action_session_inputs(tmp_path)
    entered = Event()
    release = Event()

    class BlockingManual(dict[ProcedurePredicateKey, ManualJudgmentSubmission]):
        def items(self):
            entered.set()
            assert release.wait(timeout=5)
            return super().items()

    blocked_manual = BlockingManual(manual)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            session.execute,
            manual=blocked_manual,
            residual_providers=residual,
        )
        assert entered.wait(timeout=5)
        second = executor.submit(
            session.execute,
            manual=manual,
            residual_providers=residual,
        )
        with pytest.raises(PreActionEvidenceError):
            second.result()
        release.set()
        assert first.result().cleared


def test_session_control_is_collectible_but_live_plan_claim_remains(
    tmp_path: Path,
) -> None:
    plan, observation, manual, residual = _pre_action_authorities(tmp_path)
    abandoned = create_pre_action_evidence_session(plan, observation)
    abandoned_reference = weakref_ref(abandoned)
    del abandoned
    gc.collect()
    assert abandoned_reference() is None
    with pytest.raises(PreActionEvidenceError, match="already owns"):
        create_pre_action_evidence_session(plan, observation)

    terminal_plan, terminal_observation, terminal_manual, terminal_residual = (
        _pre_action_authorities(tmp_path / "terminal")
    )
    terminal = create_pre_action_evidence_session(terminal_plan, terminal_observation)
    assert terminal.execute(
        manual=terminal_manual, residual_providers=terminal_residual
    ).cleared
    terminal_reference = weakref_ref(terminal)
    del terminal
    gc.collect()
    assert terminal_reference() is None
    with pytest.raises(PreActionEvidenceError, match="already owns"):
        create_pre_action_evidence_session(terminal_plan, terminal_observation)


def test_precondition_evaluation_plan_rejects_forgery_copying_and_tampering(
    tmp_path: Path,
) -> None:
    _, _, _, run = _precondition_run(tmp_path)
    supplied = _provider_inputs(run)
    providers = {
        key: (lambda request, value=value: value) for key, value in supplied.items()
    }
    plan = plan_procedure_precondition_evaluations(run, providers)

    with pytest.raises(TypeError, match="issued by planning"):
        ProcedureEvaluatorInputRequest()
    with pytest.raises(TypeError, match="issued by planning"):
        ProcedurePreconditionEvaluationPlan()
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(plan)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.deepcopy(plan)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(plan)
    assert not _is_issued_procedure_precondition_evaluation_plan(
        object.__new__(ProcedurePreconditionEvaluationPlan)
    )

    object.__setattr__(plan, "records", tuple(reversed(plan.records)))
    assert not _is_issued_procedure_precondition_evaluation_plan(plan)

    clean_plan = plan_procedure_precondition_evaluations(run, providers)
    object.__setattr__(clean_plan, "providers", dict(clean_plan.providers))
    assert not _is_issued_procedure_precondition_evaluation_plan(clean_plan)

    coordinated = plan_procedure_precondition_evaluations(run, providers)
    invalid = {key: object() for key in coordinated.providers}
    object.__setattr__(coordinated, "providers", invalid)
    for assisted_record in coordinated.assisted:
        key = cast(ProcedurePredicateKey, assisted_record.requirement.key)
        object.__setattr__(assisted_record, "provider", invalid[key])
    for mechanical_record in coordinated.mechanical:
        key = cast(ProcedurePredicateKey, mechanical_record.requirement.key)
        object.__setattr__(mechanical_record, "provider", invalid[key])
    assert not _is_issued_procedure_precondition_evaluation_plan(coordinated)
