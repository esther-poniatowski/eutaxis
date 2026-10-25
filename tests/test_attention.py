"""Adversarial tests for effective attention requirements and packet issuance."""

from __future__ import annotations

import copy
import pickle
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, cast

import pytest
import yaml

from eutaxis.declarations import (
    AssistedAttentionEntry,
    AttentionPlan,
    AttentionPlanningError,
    AttentionRequirements,
    CheckerResult,
    CheckerRunner,
    CheckerRunnerBinding,
    CompletionRequirement,
    DeliberativeAttentionEntry,
    DetectorResult,
    DetectorRunner,
    DetectorRunnerBinding,
    EnforcementClass,
    EvaluationState,
    EvaluatorDeclaration,
    EvaluatorInput,
    MechanicalAttentionEntry,
    OperationObligationSnapshot,
    OperationPredicateEnforcement,
    OperationPredicateKey,
    PredicatePhase,
    ProcedureObligationSnapshot,
    ProcedurePredicateEnforcement,
    ProcedurePredicateKey,
    RuleCriterionEnforcement,
    RuleCriterionKey,
    RuleObligationSnapshot,
    RunnableAttentionRequirement,
    VersionedReference,
    build_checker_runner_registry,
    build_declaration_catalog,
    build_detector_runner_registry,
    derive_attention_requirements,
    execute_known_failure_fixtures,
    load_declaration_registry,
    load_evaluator_fixture_index,
    load_facet_registry,
    plan_attention,
    resolve_compilation_unit,
)
from eutaxis.declarations.attention import _is_issued_attention_plan
from eutaxis.declarations.models import JsonValue

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY_FIXTURES = FIXTURES / "registry" / "valid"
FACETS = FIXTURES / "facets" / "valid" / "context-facets.yaml"
CHECKER = VersionedReference("registry/checker", 1)
DETECTOR = VersionedReference("registry/detector", 1)
MANUAL = VersionedReference("registry/manual", 1)
CHECK_INPUT = VersionedReference("registry/check-input", 1)
WRITE = VersionedReference("registry/write", 1)
KNOWN_FAILURE = "registry/checker/known-failure"
Mode = Literal["mixed", "manual", "mechanical", "assisted", "none"]


class _HostileMessageError(RuntimeError):
    """Refuse string conversion to test contained public-boundary failures."""

    def __str__(self) -> str:
        raise LookupError("message unavailable")


class _UnhashableText(str):
    """Retain string behavior while refusing the schema primitive's hash."""

    __hash__ = None  # type: ignore[assignment]


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


def _detector_result() -> DetectorResult:
    """Return one schema-valid detector carrier for registry construction."""
    return DetectorResult(
        evaluator=DETECTOR,
        input_revision="declaration-v1",
        evidence={"accepted": True},
    )


def _prepare_registry(tmp_path: Path, mode: Mode):
    """Build one registry whose effective obligations match ``mode``."""
    root = tmp_path / "registry"
    shutil.copytree(REGISTRY_FIXTURES, root)

    manual = _read(root, "evaluator.yaml")
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
        actions[:] = [first_action, second_action]
        procedure["entry"] = "write-first"
        operation["preconditions"] = [
            _predicate("manual-operation", "authorization", MANUAL),
            _predicate("local-operation", "authorization", None),
        ]
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
    elif mode == "mixed":
        section["declarations"] = ["content/package", "content/write"]
    else:
        section["declarations"] = ["content/package"]
    manifest["policies"] = []
    _write(root, "manifest.yaml", manifest)

    declarations = load_declaration_registry(
        tuple(sorted(root.glob("*.yaml"))), load_facet_registry(FACETS)
    )
    resolution = resolve_compilation_unit(declarations, "registry/manifest", _context())
    checker_registry = None
    if mode in {"mixed", "mechanical"}:
        checker_registry = build_checker_runner_registry(
            declarations,
            [
                CheckerRunnerBinding(
                    CHECKER,
                    CHECK_INPUT,
                    cast(CheckerRunner, lambda input_data: _checker_result()),
                )
            ],
        )
    detector_registry = None
    if mode in {"mixed", "assisted"}:
        detector_registry = build_detector_runner_registry(
            declarations,
            [
                DetectorRunnerBinding(
                    DETECTOR,
                    WRITE,
                    cast(DetectorRunner, lambda input_data: _detector_result()),
                )
            ],
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
