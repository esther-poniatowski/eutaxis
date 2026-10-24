"""Conformance tests for canonical structured declarations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml

from eutaxis.declarations import (
    CompositionManifestDeclaration,
    DeclarationSchemaError,
    DeclarationSemanticError,
    EvaluatorDeclaration,
    OperationDeclaration,
    ProcedureDeclaration,
    ResolutionPolicyDeclaration,
    RuleDeclaration,
    RuleSetDeclaration,
    TruthValue,
    declaration_schema,
    evaluate_applicability,
    load_declaration,
    schema_path,
)

FIXTURES = Path(__file__).parent / "fixtures" / "declarations"


def _write_variant(
    tmp_path: Path,
    source_name: str,
    mutate: Callable[[dict[str, object]], None],
    *,
    name: str = "variant.yaml",
) -> Path:
    """Write one mutated valid fixture for a boundary regression test."""
    document = yaml.safe_load((FIXTURES / "valid" / source_name).read_text())
    mutate(document)
    path = tmp_path / name
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("filename", "expected_type"),
    [
        ("rule.yaml", RuleDeclaration),
        ("rule-set.yaml", RuleSetDeclaration),
        ("procedure.yaml", ProcedureDeclaration),
        ("resolution-policy.yaml", ResolutionPolicyDeclaration),
        ("composition-manifest.yaml", CompositionManifestDeclaration),
        ("evaluator.yaml", EvaluatorDeclaration),
        ("operation.yaml", OperationDeclaration),
    ],
)
def test_valid_declaration_fixtures_load(
    filename: str, expected_type: type[object]
) -> None:
    declaration = load_declaration(FIXTURES / "valid" / filename)
    assert isinstance(declaration, expected_type)
    assert declaration.schema_version == 1
    assert declaration.owner == "eutaxis"


def test_schema_is_packaged_and_meta_validated() -> None:
    assert schema_path().is_file()
    schema = declaration_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert isinstance(schema["oneOf"], list)
    assert len(schema["oneOf"]) == 7


def test_schema_accessor_returns_an_isolated_copy() -> None:
    schema = declaration_schema()
    schema["title"] = "mutated by caller"
    assert declaration_schema()["title"] == "Eutaxis declaration version 1"


def test_rule_set_contains_typed_rules() -> None:
    declaration = load_declaration(FIXTURES / "valid" / "rule-set.yaml")
    assert isinstance(declaration, RuleSetDeclaration)
    assert declaration.rules[0].id == "prose/exact-claims"
    rule = declaration.rules[0]
    assert rule.criteria[0].norms == ("support-claim",)
    assert rule.criteria[0].evaluator.id == "eutaxis/manual-judgment"
    assert rule.criteria[0].evaluator.version == 1
    assert tuple(rule.applicability) == ("all",)
    assert tuple(rule.norms[0].applicability) == ("all",)
    assert rule.norms[0].guidance is not None
    assert rule.exceptions[0].affects == ("support-claim",)
    assert tuple(rule.exceptions[0].when) == ("all",)


def test_procedure_model_preserves_every_contract_field() -> None:
    declaration = load_declaration(FIXTURES / "valid" / "procedure.yaml")
    assert isinstance(declaration, ProcedureDeclaration)
    assert declaration.parameters["type"] == "object"
    assert declaration.actions[0].operation.id == "eutaxis/write-artifact"
    assert declaration.actions[0].operation.version == 1
    assert declaration.actions[0].bindings["path"] == "request.path"
    assert declaration.actions[0].on_success == "artifact-written"
    assert declaration.postconditions[0].predicate_class == "postcondition"
    assert declaration.effects[0].state == "filesystem/artifact"


def test_policy_manifest_evaluator_and_operation_models_are_complete() -> None:
    policy = load_declaration(FIXTURES / "valid" / "resolution-policy.yaml")
    manifest = load_declaration(FIXTURES / "valid" / "composition-manifest.yaml")
    evaluator = load_declaration(FIXTURES / "valid" / "evaluator.yaml")
    operation = load_declaration(FIXTURES / "valid" / "operation.yaml")

    assert isinstance(policy, ResolutionPolicyDeclaration)
    assert policy.when["facet"] == "scope.project"
    assert policy.strategy.retain == "project/format"
    assert isinstance(manifest, CompositionManifestDeclaration)
    assert manifest.sections[0].declarations == ("prose/core",)
    assert manifest.policies == ("eutaxis/prefer-project-format",)
    assert isinstance(evaluator, EvaluatorDeclaration)
    assert evaluator.timing == "post-artifact"
    assert evaluator.evidence_schema["type"] == "object"
    assert evaluator.failure_behavior == "block"
    assert isinstance(operation, OperationDeclaration)
    assert operation.inputs["type"] == "object"
    assert operation.outputs["type"] == "object"
    assert operation.effects[0].disposition == "allowed"
    assert operation.failure_outcomes == ("write-failed",)


def test_strong_kleene_applicability_guards_missing_facets() -> None:
    guarded = {
        "all": [
            {"facet": "source.available", "operator": "exists"},
            {
                "facet": "source.available",
                "operator": "equals",
                "value": True,
            },
        ]
    }
    assert evaluate_applicability(guarded, {}) is TruthValue.FALSE
    assert (
        evaluate_applicability(
            {"facet": "source.available", "operator": "equals", "value": True},
            {},
        )
        is TruthValue.UNKNOWN
    )


def test_strong_kleene_any_and_not_preserve_unknown() -> None:
    predicate = {
        "not": {
            "any": [
                {"facet": "a", "operator": "equals", "value": True},
                {"facet": "b", "operator": "equals", "value": True},
            ]
        }
    }
    assert evaluate_applicability(predicate, {"a": False}) is TruthValue.UNKNOWN


def test_applicability_comparison_is_type_sensitive() -> None:
    equals_one = {"facet": "value", "operator": "equals", "value": 1}
    in_one = {"facet": "value", "operator": "in", "value": [1]}
    assert evaluate_applicability(equals_one, {"value": True}) is TruthValue.FALSE
    assert evaluate_applicability(in_one, {"value": True}) is TruthValue.FALSE


def test_loaded_structured_applicability_matches_ordinary_json_context(
    tmp_path: Path,
) -> None:
    def mutate(document: dict[str, object]) -> None:
        document["applicability"] = {
            "facet": "request.payload",
            "operator": "equals",
            "value": {"items": [1, 2]},
        }

    declaration = load_declaration(_write_variant(tmp_path, "rule.yaml", mutate))
    assert (
        evaluate_applicability(
            declaration.applicability,
            {"request.payload": {"items": [1, 2]}},
        )
        is TruthValue.TRUE
    )


def test_normalized_documents_are_immutable() -> None:
    declaration = load_declaration(FIXTURES / "valid" / "rule.yaml")
    assert isinstance(declaration, RuleDeclaration)
    with pytest.raises(TypeError):
        declaration.document["owner"] = "other"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        declaration.norms[0].subject = "other"  # type: ignore[misc]


@pytest.mark.parametrize(
    "filename",
    [
        "unknown-field.yaml",
        "manual-total.yaml",
        "duplicate-key.yaml",
        "non-json-value.yaml",
        "invalid-embedded-schema.yaml",
        "missing-success-transition.yaml",
    ],
)
def test_schema_invalid_fixtures_fail(filename: str) -> None:
    with pytest.raises(DeclarationSchemaError, match="Invalid declaration"):
        load_declaration(FIXTURES / "invalid" / filename)


def test_unknown_norm_reference_fails_semantic_validation() -> None:
    with pytest.raises(DeclarationSemanticError, match="unknown norms"):
        load_declaration(FIXTURES / "invalid" / "unknown-norm.yaml")


def test_procedure_cycle_fails_semantic_validation() -> None:
    with pytest.raises(DeclarationSemanticError, match="contains a cycle"):
        load_declaration(FIXTURES / "invalid" / "procedure-cycle.yaml")


@pytest.mark.parametrize(
    ("filename", "message"),
    [
        ("unknown-decision-criterion.yaml", "unknown decision criterion"),
        ("rule-set-id-collision.yaml", "duplicate id"),
        ("wrong-predicate-class.yaml", "is not admitted"),
        ("contradictory-effects.yaml", "has both"),
        ("retain-outside-conflict.yaml", "not a member"),
        ("misrouted-outcome.yaml", "routes success"),
    ],
)
def test_semantically_invalid_fixtures_fail(filename: str, message: str) -> None:
    with pytest.raises(DeclarationSemanticError, match=message):
        load_declaration(FIXTURES / "invalid" / filename)


def test_schema_error_reports_source_location() -> None:
    path = FIXTURES / "invalid" / "unknown-field.yaml"
    with pytest.raises(DeclarationSchemaError) as captured:
        load_declaration(path)
    assert str(path) in str(captured.value)
    assert "at $.description" in str(captured.value)
    assert "line 14" in str(captured.value)


def test_duplicate_key_error_reports_both_source_locations() -> None:
    path = FIXTURES / "invalid" / "duplicate-key.yaml"
    with pytest.raises(DeclarationSchemaError) as captured:
        load_declaration(path)
    message = str(captured.value)
    assert "line 4" in message
    assert "line 5" in message


def test_cyclic_yaml_alias_fails_at_the_schema_boundary(tmp_path: Path) -> None:
    path = tmp_path / "cyclic-alias.yaml"
    path.write_text("value: &recursive [*recursive]\n", encoding="utf-8")
    with pytest.raises(DeclarationSchemaError, match="cyclic YAML aliases"):
        load_declaration(path)


@pytest.mark.parametrize("identifier", [" leading", "embedded space", "trailing\n"])
def test_identifiers_reject_whitespace(tmp_path: Path, identifier: str) -> None:
    def mutate(document: dict[str, object]) -> None:
        document["id"] = identifier

    path = _write_variant(tmp_path, "rule.yaml", mutate)
    with pytest.raises(DeclarationSchemaError):
        load_declaration(path)


@pytest.mark.parametrize(
    ("evaluator_kind", "coverage", "adjudication"),
    [
        ("detector", "total", "authoritative"),
        ("checker", "none", "manual"),
    ],
)
def test_evaluator_class_must_be_derivable(
    tmp_path: Path,
    evaluator_kind: str,
    coverage: str,
    adjudication: str,
) -> None:
    def mutate(document: dict[str, object]) -> None:
        document["evaluator-kind"] = evaluator_kind
        document["coverage"] = coverage
        document["adjudication"] = adjudication

    path = _write_variant(tmp_path, "evaluator.yaml", mutate)
    with pytest.raises(DeclarationSchemaError):
        load_declaration(path)


@pytest.mark.parametrize(
    ("evaluator_kind", "coverage", "adjudication"),
    [
        ("checker", "total", "authoritative"),
        ("detector", "partial", "candidate"),
    ],
)
def test_machine_evaluator_contracts_are_admitted(
    tmp_path: Path,
    evaluator_kind: str,
    coverage: str,
    adjudication: str,
) -> None:
    def mutate(document: dict[str, object]) -> None:
        document["evaluator-kind"] = evaluator_kind
        document["coverage"] = coverage
        document["adjudication"] = adjudication
        if evaluator_kind == "checker":
            document["known-failure-fixtures"] = ["tests/known-failure"]

    declaration = load_declaration(_write_variant(tmp_path, "evaluator.yaml", mutate))
    assert isinstance(declaration, EvaluatorDeclaration)
    assert declaration.evaluator_kind == evaluator_kind


def test_checker_requires_named_known_failure_fixture(tmp_path: Path) -> None:
    def mutate(document: dict[str, object]) -> None:
        document["evaluator-kind"] = "checker"
        document["coverage"] = "total"
        document["adjudication"] = "authoritative"
        document["known-failure-fixtures"] = [""]

    path = _write_variant(tmp_path, "evaluator.yaml", mutate)
    with pytest.raises(DeclarationSchemaError):
        load_declaration(path)


def test_overlapping_rule_exceptions_fail(tmp_path: Path) -> None:
    def mutate(document: dict[str, object]) -> None:
        document["exceptions"] = [
            {
                "id": "first",
                "when": {"facet": "request.mode", "operator": "exists"},
                "disposition": "waive",
                "affects": ["state-purpose"],
            },
            {
                "id": "second",
                "when": {"facet": "request.mode", "operator": "exists"},
                "disposition": "waive",
                "affects": ["state-purpose"],
            },
        ]

    path = _write_variant(tmp_path, "rule.yaml", mutate)
    with pytest.raises(DeclarationSemanticError, match="affected by both"):
        load_declaration(path)


def test_chained_rule_exception_substitutions_fail(tmp_path: Path) -> None:
    def mutate(document: dict[str, object]) -> None:
        norms = document["norms"]
        assert isinstance(norms, list)
        norms.extend(
            [
                {
                    "id": "alternate-purpose",
                    "modality": "must",
                    "subject": "agent",
                    "action": {"verb": "state", "object": "an alternate purpose"},
                },
                {
                    "id": "final-purpose",
                    "modality": "must",
                    "subject": "agent",
                    "action": {"verb": "state", "object": "a final purpose"},
                },
            ]
        )
        document["exceptions"] = [
            {
                "id": "first",
                "when": {"facet": "request.mode", "operator": "exists"},
                "disposition": "substitute",
                "affects": ["state-purpose"],
                "substitutes": ["alternate-purpose"],
            },
            {
                "id": "second",
                "when": {"facet": "request.mode", "operator": "exists"},
                "disposition": "substitute",
                "affects": ["alternate-purpose"],
                "substitutes": ["final-purpose"],
            },
        ]

    path = _write_variant(tmp_path, "rule.yaml", mutate)
    with pytest.raises(DeclarationSemanticError, match="one-step substitutions"):
        load_declaration(path)


def test_decision_criterion_must_evaluate_its_norm(tmp_path: Path) -> None:
    def mutate(document: dict[str, object]) -> None:
        norms = document["norms"]
        assert isinstance(norms, list)
        norms.append(
            {
                "id": "recommended-purpose",
                "modality": "should",
                "subject": "agent",
                "action": {"verb": "state", "object": "a recommended purpose"},
                "decision-criterion": "purpose-is-explicit",
            }
        )

    path = _write_variant(tmp_path, "rule.yaml", mutate)
    with pytest.raises(DeclarationSemanticError, match="does not evaluate norm"):
        load_declaration(path)


@pytest.mark.parametrize(
    "strategy",
    [
        {
            "kind": "substitute",
            "replace": "shared/format",
            "with": "shared/format",
        },
        {"kind": "combine", "result": "shared/format"},
    ],
)
def test_resolution_policy_rejects_degenerate_outcomes(
    tmp_path: Path, strategy: dict[str, str]
) -> None:
    def mutate(document: dict[str, object]) -> None:
        document["strategy"] = strategy

    path = _write_variant(tmp_path, "resolution-policy.yaml", mutate)
    with pytest.raises(DeclarationSemanticError):
        load_declaration(path)


def test_semantic_error_reports_document_and_source_location() -> None:
    path = FIXTURES / "invalid" / "unknown-decision-criterion.yaml"
    with pytest.raises(DeclarationSemanticError) as captured:
        load_declaration(path)
    assert "$.norms[0].decision-criterion" in str(captured.value)
    assert captured.value.line is not None


def test_duplicate_identifier_reports_the_second_id_field() -> None:
    path = FIXTURES / "invalid" / "rule-set-id-collision.yaml"
    with pytest.raises(DeclarationSemanticError) as captured:
        load_declaration(path)
    assert "$.rules[0].id" in str(captured.value)
