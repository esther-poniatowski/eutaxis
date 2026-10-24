"""Conformance tests for canonical structured declarations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml

from eutaxis.declarations import (
    CompositionMechanism,
    CompositionManifestDeclaration,
    DeclarationSchemaError,
    DeclarationSemanticError,
    EvaluatorDeclaration,
    LiteralBinding,
    OperationDeclaration,
    ParameterBinding,
    ProcedureDeclaration,
    ResolutionPolicyDeclaration,
    RuleDeclaration,
    RuleSetDeclaration,
    TruthValue,
    declaration_schema,
    evaluate_applicability,
    load_declaration,
    load_facet_registry,
    schema_path,
)

FIXTURES = Path(__file__).parent / "fixtures" / "declarations"
FACETS = load_facet_registry(
    Path(__file__).parent / "fixtures" / "facets" / "valid" / "context-facets.yaml"
)


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


def _line_containing(path: Path, text: str) -> int:
    """Return the one-based source line containing ``text``."""
    return next(
        index
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if text in line
    )


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


def test_rule_set_is_a_selection_only_container(tmp_path: Path) -> None:
    path = _write_variant(
        tmp_path,
        "rule-set.yaml",
        lambda document: document.update(
            {"relations": [{"type": "requires", "target": "prose/exact-claims"}]}
        ),
    )

    with pytest.raises(DeclarationSchemaError) as captured:
        load_declaration(path)

    assert captured.value.location == "$.relations"


def test_procedure_model_preserves_every_contract_field() -> None:
    declaration = load_declaration(FIXTURES / "valid" / "procedure.yaml")
    assert isinstance(declaration, ProcedureDeclaration)
    assert declaration.parameters["type"] == "object"
    assert declaration.actions[0].operation.id == "eutaxis/write-artifact"
    assert declaration.actions[0].operation.version == 1
    path_binding = declaration.actions[0].bindings["path"]
    content_binding = declaration.actions[0].bindings["content"]
    assert isinstance(path_binding, ParameterBinding)
    assert path_binding.parameter == "path"
    assert isinstance(content_binding, LiteralBinding)
    assert content_binding.value == "Reviewed content"
    assert declaration.actions[0].on_success == "artifact-written"
    assert declaration.actions[0].on_failure == {"write-failed": "write-failed"}
    assert declaration.postconditions[0].predicate_class == "postcondition"
    assert declaration.effects == ("filesystem/artifact",)


def test_policy_manifest_evaluator_and_operation_models_are_complete() -> None:
    policy = load_declaration(FIXTURES / "valid" / "resolution-policy.yaml")
    manifest = load_declaration(FIXTURES / "valid" / "composition-manifest.yaml")
    evaluator = load_declaration(FIXTURES / "valid" / "evaluator.yaml")
    operation = load_declaration(FIXTURES / "valid" / "operation.yaml")

    assert isinstance(policy, ResolutionPolicyDeclaration)
    assert policy.when["facet"] == "scope.project"
    assert policy.strategy.retain == "project/format"
    assert isinstance(manifest, CompositionManifestDeclaration)
    assert manifest.mechanism is CompositionMechanism.CUMULATIVE
    assert manifest.sections[0].declarations == ("prose/core",)
    assert manifest.policies == ("eutaxis/prefer-project-format",)
    assert isinstance(evaluator, EvaluatorDeclaration)
    assert evaluator.timing == "post-artifact"
    assert evaluator.evidence_schema["type"] == "object"
    assert evaluator.failure_behavior == "block"
    assert isinstance(operation, OperationDeclaration)
    assert operation.inputs["type"] == "object"
    assert operation.outputs["type"] == "object"
    assert operation.effects == ("filesystem/artifact",)
    assert operation.failure_outcomes == ("write-failed",)


def test_composition_mechanism_is_an_exact_closed_enum() -> None:
    assert {mechanism.value for mechanism in CompositionMechanism} == {
        "cumulative",
        "separate-directory",
        "single-slot",
    }


@pytest.mark.parametrize("mechanism", tuple(CompositionMechanism))
def test_composition_manifest_preserves_each_typed_mechanism(
    tmp_path: Path, mechanism: CompositionMechanism
) -> None:
    def mutate(document: dict[str, object]) -> None:
        document["mechanism"] = mechanism.value

    declaration = load_declaration(
        _write_variant(tmp_path, "composition-manifest.yaml", mutate)
    )

    assert isinstance(declaration, CompositionManifestDeclaration)
    assert declaration.mechanism is mechanism


@pytest.mark.parametrize(
    ("value", "expected_location"),
    [(None, "$"), ("implicit-from-target", "$.mechanism")],
)
def test_composition_manifest_requires_a_known_mechanism(
    tmp_path: Path, value: str | None, expected_location: str
) -> None:
    def mutate(document: dict[str, object]) -> None:
        if value is None:
            del document["mechanism"]
        else:
            document["mechanism"] = value

    path = _write_variant(tmp_path, "composition-manifest.yaml", mutate)

    with pytest.raises(DeclarationSchemaError) as captured:
        load_declaration(path)

    assert captured.value.location == expected_location


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
    assert evaluate_applicability(guarded, {}, FACETS) is TruthValue.FALSE
    assert (
        evaluate_applicability(
            {"facet": "source.available", "operator": "equals", "value": True},
            {},
            FACETS,
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
    assert evaluate_applicability(predicate, {"a": False}, FACETS) is TruthValue.UNKNOWN


def test_applicability_comparison_is_type_sensitive() -> None:
    equals_one = {
        "facet": "sample.boolean-or-number",
        "operator": "equals",
        "value": 1,
    }
    in_one = {
        "facet": "sample.boolean-or-number",
        "operator": "in",
        "value": [1],
    }
    context = {"sample.boolean-or-number": True}
    assert evaluate_applicability(equals_one, context, FACETS) is TruthValue.FALSE
    assert evaluate_applicability(in_one, context, FACETS) is TruthValue.FALSE


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
            FACETS,
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
        "duplicate-effects.yaml",
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


def test_multiple_unknown_fields_report_the_first_source_field(tmp_path: Path) -> None:
    def mutate(document: dict[str, object]) -> None:
        document["description"] = "First unknown field"
        document["summary"] = "Second unknown field"

    path = _write_variant(tmp_path, "procedure.yaml", mutate)
    with pytest.raises(DeclarationSchemaError) as captured:
        load_declaration(path)
    assert captured.value.location == "$.description"
    assert captured.value.line == _line_containing(path, "description:")


@pytest.mark.parametrize("unknown_name", ["can't-field", "a'b\"c-field"])
def test_quoted_unknown_field_reports_its_full_path_and_source_line(
    tmp_path: Path, unknown_name: str
) -> None:
    marker = f"Unknown field {unknown_name}"

    def mutate(document: dict[str, object]) -> None:
        document[unknown_name] = marker

    path = _write_variant(tmp_path, "procedure.yaml", mutate)
    with pytest.raises(DeclarationSchemaError) as captured:
        load_declaration(path)
    assert captured.value.location == f"$.{unknown_name}"
    assert captured.value.line == _line_containing(path, marker)


def test_evaluator_diagnostic_follows_the_matching_discriminator_branch() -> None:
    path = FIXTURES / "invalid" / "manual-total.yaml"
    with pytest.raises(DeclarationSchemaError) as captured:
        load_declaration(path)
    assert captured.value.location in {"$.coverage", "$.adjudication"}
    assert "evaluator-kind" not in str(captured.value)


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


def test_invariant_observations_and_named_failure_routes_are_preserved(
    tmp_path: Path,
) -> None:
    def mutate(document: dict[str, object]) -> None:
        document["invariants"] = [
            {
                "id": "preserve-index",
                "class": "invariant",
                "expression": {
                    "facet": "index.valid",
                    "operator": "equals",
                    "value": True,
                },
                "observes": ["filesystem/index"],
            }
        ]
        actions = document["actions"]
        assert isinstance(actions, list)
        actions[0]["on-failure"] = {
            "write-failed": "write-failed",
            "permission-denied": "write-failed",
        }

    declaration = load_declaration(_write_variant(tmp_path, "procedure.yaml", mutate))
    assert isinstance(declaration, ProcedureDeclaration)
    assert declaration.invariants[0].observes == ("filesystem/index",)
    assert declaration.actions[0].on_failure == {
        "write-failed": "write-failed",
        "permission-denied": "write-failed",
    }


def _first_action(document: dict[str, object]) -> dict[str, object]:
    """Return the first mutable action from a procedure fixture document."""
    actions = document["actions"]
    assert isinstance(actions, list)
    action = actions[0]
    assert isinstance(action, dict)
    return action


def _bindings(document: dict[str, object]) -> dict[str, object]:
    """Return the first action's mutable input bindings."""
    bindings = _first_action(document)["with"]
    assert isinstance(bindings, dict)
    return bindings


def _set_plain_binding(document: dict[str, object]) -> None:
    _bindings(document)["path"] = "path"


def _set_both_binding_tags(document: dict[str, object]) -> None:
    _bindings(document)["path"] = {"parameter": "path", "literal": "other"}


def _set_neither_binding_tag(document: dict[str, object]) -> None:
    _bindings(document)["path"] = {}


def _set_missing_invariant_observations(document: dict[str, object]) -> None:
    document["invariants"] = [
        {
            "id": "unscoped-invariant",
            "class": "invariant",
            "expression": {"facet": "index.valid", "operator": "exists"},
        }
    ]


def _set_observations_on_guard(document: dict[str, object]) -> None:
    document["preconditions"] = [
        {
            "id": "guard-with-observations",
            "class": "guard",
            "expression": {"facet": "index.valid", "operator": "exists"},
            "observes": ["filesystem/index"],
        }
    ]


def _set_empty_failure_routes(document: dict[str, object]) -> None:
    _first_action(document)["on-failure"] = {}


@pytest.mark.parametrize(
    ("mutate", "expected_path"),
    [
        (_set_plain_binding, "$.actions[0].with.path"),
        (_set_both_binding_tags, "$.actions[0].with.path"),
        (_set_neither_binding_tag, "$.actions[0].with.path"),
        (_set_missing_invariant_observations, "$.invariants[0]"),
        (_set_observations_on_guard, "$.preconditions[0].observes"),
        (_set_empty_failure_routes, "$.actions[0].on-failure"),
    ],
)
def test_invalid_procedure_contracts_report_the_nested_cause(
    tmp_path: Path,
    mutate: Callable[[dict[str, object]], None],
    expected_path: str,
) -> None:
    path = _write_variant(tmp_path, "procedure.yaml", mutate)
    with pytest.raises(DeclarationSchemaError) as captured:
        load_declaration(path)
    assert captured.value.location == expected_path
    assert captured.value.line is not None
    if expected_path.endswith(".observes"):
        assert captured.value.line == _line_containing(path, "observes:")


def test_missing_success_transition_reports_the_action() -> None:
    path = FIXTURES / "invalid" / "missing-success-transition.yaml"
    with pytest.raises(DeclarationSchemaError) as captured:
        load_declaration(path)
    assert captured.value.location == "$.actions[0]"
    assert captured.value.line is not None


def test_literal_null_and_nested_literals_remain_distinguishable_and_immutable(
    tmp_path: Path,
) -> None:
    def mutate(document: dict[str, object]) -> None:
        bindings = _bindings(document)
        bindings["path"] = {"literal": None}
        bindings["content"] = {"literal": {"parts": ["reviewed"]}}

    declaration = load_declaration(_write_variant(tmp_path, "procedure.yaml", mutate))
    assert isinstance(declaration, ProcedureDeclaration)
    null_binding = declaration.actions[0].bindings["path"]
    nested_binding = declaration.actions[0].bindings["content"]
    assert isinstance(null_binding, LiteralBinding)
    assert null_binding.value is None
    assert isinstance(nested_binding, LiteralBinding)
    assert nested_binding.value == {"parts": ("reviewed",)}
    assert isinstance(nested_binding.value, Mapping)
    with pytest.raises(TypeError):
        nested_binding.value["parts"] = ()  # type: ignore[index]


def test_procedure_binding_and_failure_maps_are_immutable() -> None:
    declaration = load_declaration(FIXTURES / "valid" / "procedure.yaml")
    assert isinstance(declaration, ProcedureDeclaration)
    with pytest.raises(TypeError):
        declaration.actions[0].bindings["path"] = ParameterBinding(  # type: ignore[index]
            "content"
        )
    with pytest.raises(TypeError):
        declaration.actions[0].on_failure["write-failed"] = "other"  # type: ignore[index]


def test_empty_mutation_footprints_are_explicitly_admitted(tmp_path: Path) -> None:
    def clear_operation_effects(document: dict[str, object]) -> None:
        document["effects"] = []

    def clear_procedure_effects(document: dict[str, object]) -> None:
        document["effects"] = []

    operation = load_declaration(
        _write_variant(
            tmp_path, "operation.yaml", clear_operation_effects, name="op.yaml"
        )
    )
    procedure = load_declaration(
        _write_variant(
            tmp_path, "procedure.yaml", clear_procedure_effects, name="procedure.yaml"
        )
    )
    assert isinstance(operation, OperationDeclaration)
    assert isinstance(procedure, ProcedureDeclaration)
    assert operation.effects == ()
    assert procedure.effects == ()


@pytest.mark.parametrize("source_name", ["operation.yaml", "procedure.yaml"])
def test_duplicate_mutation_footprints_report_the_effects_field(
    tmp_path: Path, source_name: str
) -> None:
    def duplicate_effect(document: dict[str, object]) -> None:
        document["effects"] = ["filesystem/artifact", "filesystem/artifact"]

    path = _write_variant(tmp_path, source_name, duplicate_effect)
    with pytest.raises(DeclarationSchemaError) as captured:
        load_declaration(path)
    assert captured.value.location == "$.effects"
    assert captured.value.line is not None


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ("unknown", "unknown states"),
        ("artifact-written", "routes failure directly"),
    ],
)
def test_named_failure_routes_must_target_failure_paths(
    tmp_path: Path, target: str, message: str
) -> None:
    def mutate(document: dict[str, object]) -> None:
        _first_action(document)["on-failure"] = {"write-failed": target}

    path = _write_variant(tmp_path, "procedure.yaml", mutate)
    with pytest.raises(DeclarationSemanticError, match=message):
        load_declaration(path)


def test_required_input_must_have_a_property_schema(tmp_path: Path) -> None:
    def mutate(document: dict[str, object]) -> None:
        inputs = document["inputs"]
        assert isinstance(inputs, dict)
        inputs["required"] = ["undeclared"]

    path = _write_variant(tmp_path, "operation.yaml", mutate)
    with pytest.raises(DeclarationSemanticError, match="has no declared schema"):
        load_declaration(path)


def test_parameter_binding_must_reference_a_declared_parameter(tmp_path: Path) -> None:
    def mutate(document: dict[str, object]) -> None:
        _bindings(document)["path"] = {"parameter": "undeclared"}

    path = _write_variant(tmp_path, "procedure.yaml", mutate)
    with pytest.raises(DeclarationSemanticError, match="unknown procedure parameter"):
        load_declaration(path)


@pytest.mark.parametrize(
    ("source_name", "field"),
    [
        ("procedure.yaml", "parameters"),
        ("operation.yaml", "inputs"),
        ("procedure.yaml", "bindings"),
    ],
)
@pytest.mark.parametrize("name", ["", "bad name"])
def test_contract_property_names_use_identifier_syntax(
    tmp_path: Path, source_name: str, field: str, name: str
) -> None:
    def mutate(document: dict[str, object]) -> None:
        if field == "bindings":
            _bindings(document)[name] = {"literal": "value"}
            return
        contract = document[field]
        assert isinstance(contract, dict)
        contract["properties"] = {name: {"type": "string"}}
        contract["required"] = [name]

    path = _write_variant(tmp_path, source_name, mutate)
    with pytest.raises(DeclarationSchemaError):
        load_declaration(path)


@pytest.mark.parametrize(
    ("source_name", "field", "expected_path"),
    [
        ("procedure.yaml", "parameters", "$.parameters.properties.bad name"),
        ("operation.yaml", "inputs", "$.inputs.properties.bad name"),
        ("procedure.yaml", "bindings", "$.actions[0].with.bad name"),
    ],
)
def test_invalid_contract_key_reports_its_own_path_and_line(
    tmp_path: Path, source_name: str, field: str, expected_path: str
) -> None:
    def mutate(document: dict[str, object]) -> None:
        if field == "bindings":
            _bindings(document)["bad name"] = {"literal": "value"}
            return
        contract = document[field]
        assert isinstance(contract, dict)
        properties = contract["properties"]
        assert isinstance(properties, dict)
        properties["bad name"] = {"type": "string"}

    path = _write_variant(tmp_path, source_name, mutate)
    with pytest.raises(DeclarationSchemaError) as captured:
        load_declaration(path)
    assert captured.value.location == expected_path
    assert captured.value.line == _line_containing(path, "bad name")
