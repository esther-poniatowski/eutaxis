"""End-to-end tests for the packaged version 1 declaration contract."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, cast

import pytest

from eutaxis import data_path
from eutaxis.declarations import (
    DECLARATION_REGISTRY_EVALUATOR,
    DECLARATION_REGISTRY_INPUT_REVISION,
    LOAD_DECLARATION_REGISTRY_OPERATION,
    CheckerExecutionError,
    CheckerResult,
    CheckerRunnerBinding,
    EvaluationState,
    EvaluatorDeclaration,
    OperationDeclaration,
    OperationFailure,
    OperationSuccess,
    ParameterBinding,
    ProcedureDeclaration,
    RuleDeclaration,
    build_checker_runner_registry,
    build_operation_runner_registry,
    declaration_registry_checker_binding,
    execute_checker,
    execute_known_failure_fixtures,
    execute_operation,
    facet_registry_path,
    load_declaration_registry,
    load_evaluator_fixture_index,
    load_facet_registry,
    load_declaration_registry_operation_binding,
)
from eutaxis.declarations.models import JsonValue

DECLARATION_ROOT = data_path() / "declarations" / "v1"
FIXTURE_ROOT = data_path() / "evaluator-fixtures" / "v1"


def _declaration_paths() -> tuple[Path, ...]:
    """Return the complete packaged version 1 declaration corpus."""
    return tuple(sorted(DECLARATION_ROOT.glob("*.yaml")))


def _registry_and_runners():
    """Load the packaged registry and its one code-owned checker binding."""
    declarations = load_declaration_registry(
        _declaration_paths(), load_facet_registry(facet_registry_path())
    )
    runners = build_checker_runner_registry(
        declarations, [declaration_registry_checker_binding()]
    )
    return declarations, runners


def test_packaged_records_form_the_exact_closed_registry() -> None:
    declarations, runners = _registry_and_runners()

    assert {path.name for path in declarations.paths} == {
        "declaration-corpus-contract.yaml",
        "declaration-registry.yaml",
        "load-declaration-registry.yaml",
        "manual-judgment.yaml",
        "validate-declaration-registry.yaml",
    }
    assert set(declarations.records) == {
        "eutaxis/declaration-corpus-contract",
        "eutaxis/validate-declaration-registry",
    }
    assert set(declarations.families) == {
        "eutaxis/declaration-registry",
        "eutaxis/load-declaration-registry",
        "eutaxis/manual-judgment",
    }
    assert set(runners.bindings) == {DECLARATION_REGISTRY_EVALUATOR}


def test_packaged_valid_corpus_returns_satisfied_closed_evidence() -> None:
    declarations, runners = _registry_and_runners()

    result = execute_checker(
        runners,
        DECLARATION_REGISTRY_EVALUATOR,
        input_revision=DECLARATION_REGISTRY_INPUT_REVISION,
        input_data={
            "sources": [str(path) for path in _declaration_paths()],
            "facet-registry": str(facet_registry_path()),
        },
        expected_state=EvaluationState.SATISFIED,
    )

    assert result.evidence == {
        "outcome": "valid",
        "record-count": 5,
        "family-count": 3,
        "conflict-count": 0,
    }
    assert len(declarations.records) == 2


def test_packaged_operation_executes_and_projects_declared_outputs() -> None:
    declarations, _ = _registry_and_runners()
    operations = build_operation_runner_registry(
        declarations, [load_declaration_registry_operation_binding()]
    )

    result = execute_operation(
        operations,
        LOAD_DECLARATION_REGISTRY_OPERATION,
        input_data={
            "sources": [str(path) for path in _declaration_paths()],
            "facet-registry": str(facet_registry_path()),
        },
    )

    assert isinstance(result, OperationSuccess)
    assert result.outputs == {
        "registry.valid": True,
        "record-count": 5,
        "family-count": 3,
        "conflict-count": 0,
    }


def test_packaged_operation_maps_source_defect_to_declared_failure() -> None:
    declarations, _ = _registry_and_runners()
    operations = build_operation_runner_registry(
        declarations, [load_declaration_registry_operation_binding()]
    )

    result = execute_operation(
        operations,
        LOAD_DECLARATION_REGISTRY_OPERATION,
        input_data={
            "sources": [str(Path("missing.yaml"))],
            "facet-registry": str(facet_registry_path()),
        },
    )

    assert result == OperationFailure(
        operation=LOAD_DECLARATION_REGISTRY_OPERATION,
        outcome="invalid-registry",
    )


def test_packaged_known_failure_returns_located_registry_violation() -> None:
    declarations, runners = _registry_and_runners()
    fixture_paths = tuple(sorted(FIXTURE_ROOT.glob("*.yaml")))
    fixtures = load_evaluator_fixture_index(
        fixture_paths,
        root=FIXTURE_ROOT,
        input_contracts=runners.input_contracts,
    )

    results = execute_known_failure_fixtures(declarations, fixtures, runners)

    fixture_id = "eutaxis/declaration-registry/unresolved-exact-reference"
    binding_fixture_id = "eutaxis/declaration-registry/wrong-schema-binding"
    assert set(results) == {fixture_id, binding_fixture_id}
    result = results[fixture_id]
    assert result.state is EvaluationState.VIOLATED
    assert result.evidence["outcome"] == "invalid"
    assert result.evidence["error-class"] == "declaration-registry"
    assert result.evidence["location"] == "$.criteria[0].evaluator.id"
    assert str(result.evidence["source"]).endswith(
        "resources/unresolved-exact-reference.yaml"
    )
    assert cast(int, result.evidence["line"]) > 0
    assert cast(int, result.evidence["column"]) > 0
    binding_result = results[binding_fixture_id]
    assert binding_result.state is EvaluationState.VIOLATED
    assert binding_result.evidence["error-class"] == "declaration-schema"
    assert binding_result.evidence["location"] == "$._schema"


def test_packaged_procedure_and_operation_match_without_effects() -> None:
    declarations, _ = _registry_and_runners()
    procedure = cast(
        ProcedureDeclaration,
        declarations.records["eutaxis/validate-declaration-registry"].declaration,
    )
    operation = cast(
        OperationDeclaration,
        declarations.families[LOAD_DECLARATION_REGISTRY_OPERATION.id]
        .versions[LOAD_DECLARATION_REGISTRY_OPERATION.version]
        .declaration,
    )

    expected_inputs = {
        "type": "object",
        "required": ("sources", "facet-registry"),
        "properties": {
            "sources": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1},
            },
            "facet-registry": {"type": "string", "minLength": 1},
        },
        "additionalProperties": False,
    }
    assert procedure.parameters == expected_inputs
    assert operation.inputs == expected_inputs
    assert procedure.entry == "load-registry"
    assert procedure.preconditions == ()
    assert procedure.invariants == ()
    assert procedure.effects == operation.effects == ()
    assert len(procedure.actions) == 1
    action = procedure.actions[0]
    assert action.operation == LOAD_DECLARATION_REGISTRY_OPERATION
    assert action.bindings == {
        "sources": ParameterBinding("sources"),
        "facet-registry": ParameterBinding("facet-registry"),
    }
    assert action.on_success == "valid-registry"
    assert action.on_failure == {"invalid-registry": "invalid-registry"}
    assert procedure.failures == ("invalid-registry",)
    assert operation.failure_outcomes == ("invalid-registry",)
    assert operation.outputs == {
        "type": "object",
        "required": (
            "registry.valid",
            "record-count",
            "family-count",
            "conflict-count",
        ),
        "properties": {
            "registry.valid": {"const": True},
            "record-count": {"type": "integer", "minimum": 0},
            "family-count": {"type": "integer", "minimum": 0},
            "conflict-count": {"type": "integer", "minimum": 0},
        },
        "additionalProperties": False,
    }
    assert len(procedure.postconditions) == 1
    postcondition = procedure.postconditions[0]
    assert postcondition.id == "valid-registry"
    assert postcondition.predicate_class == "postcondition"
    assert postcondition.expression == {
        "facet": "registry.valid",
        "operator": "equals",
        "value": True,
    }


def test_packaged_rule_assigns_mechanical_and_manual_criteria() -> None:
    declarations, _ = _registry_and_runners()
    rule = cast(
        RuleDeclaration,
        declarations.records["eutaxis/declaration-corpus-contract"].declaration,
    )

    assert [norm.id for norm in rule.norms] == ["establish-valid-corpus"]
    assert [criterion.id for criterion in rule.criteria] == [
        "static-contracts-valid",
        "semantic-contracts-faithful",
    ]
    assert rule.criteria[0].evaluator == DECLARATION_REGISTRY_EVALUATOR
    assert rule.criteria[1].evaluator.id == "eutaxis/manual-judgment"
    assert rule.criteria[1].evaluator.version == 1

    manual = cast(
        EvaluatorDeclaration,
        declarations.families["eutaxis/manual-judgment"].versions[1].declaration,
    )
    assert manual.evidence_schema == {
        "type": "object",
        "required": ("reviewer", "criterion", "observation", "conclusion"),
        "properties": {
            "reviewer": {"type": "string", "minLength": 1},
            "criterion": {"type": "string", "minLength": 1},
            "observation": {"type": "string", "minLength": 1},
            "conclusion": {"enum": ("satisfied", "violated", "blocked")},
        },
        "additionalProperties": False,
    }


def test_packaged_checker_schema_accepts_blocked_and_rejects_invalid_evidence() -> None:
    declarations, _ = _registry_and_runners()

    def blocked_runner(input_data: Mapping[str, JsonValue], /) -> CheckerResult:
        return CheckerResult(
            evaluator=DECLARATION_REGISTRY_EVALUATOR,
            input_revision=DECLARATION_REGISTRY_INPUT_REVISION,
            state=EvaluationState.BLOCKED,
            evidence={
                "outcome": "blocked",
                "internal-exception-class": "RuntimeError",
                "message": "planted internal failure",
            },
        )

    blocked_registry = build_checker_runner_registry(
        declarations,
        [
            CheckerRunnerBinding(
                evaluator=DECLARATION_REGISTRY_EVALUATOR,
                operation=LOAD_DECLARATION_REGISTRY_OPERATION,
                runner=blocked_runner,
            )
        ],
    )
    result = execute_checker(
        blocked_registry,
        DECLARATION_REGISTRY_EVALUATOR,
        input_revision=DECLARATION_REGISTRY_INPUT_REVISION,
        input_data={"sources": ["source.yaml"], "facet-registry": "facets.yaml"},
        expected_state=EvaluationState.BLOCKED,
    )
    assert result.evidence["outcome"] == "blocked"

    def invalid_runner(input_data: Mapping[str, JsonValue], /) -> CheckerResult:
        return CheckerResult(
            evaluator=DECLARATION_REGISTRY_EVALUATOR,
            input_revision=DECLARATION_REGISTRY_INPUT_REVISION,
            state=EvaluationState.BLOCKED,
            evidence={
                "outcome": "blocked",
                "internal-exception-class": "RuntimeError",
            },
        )

    invalid_registry = build_checker_runner_registry(
        declarations,
        [
            CheckerRunnerBinding(
                evaluator=DECLARATION_REGISTRY_EVALUATOR,
                operation=LOAD_DECLARATION_REGISTRY_OPERATION,
                runner=invalid_runner,
            )
        ],
    )
    with pytest.raises(CheckerExecutionError) as captured:
        execute_checker(
            invalid_registry,
            DECLARATION_REGISTRY_EVALUATOR,
            input_revision=DECLARATION_REGISTRY_INPUT_REVISION,
            input_data={
                "sources": ["source.yaml"],
                "facet-registry": "facets.yaml",
            },
            expected_state=EvaluationState.BLOCKED,
        )
    assert captured.value.location == "$.result.evidence"
