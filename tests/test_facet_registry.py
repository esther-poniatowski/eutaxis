"""Conformance tests for typed context-facet registries."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from eutaxis.declarations import (
    DeclarationSchemaError,
    DeclarationSemanticError,
    FacetContextError,
    FacetRegistrySchemaError,
    FacetRegistrySemanticError,
    RuleDeclaration,
    TruthValue,
    evaluate_applicability,
    facet_registry_path,
    load_facet_registry,
    load_facet_validated_declaration,
)

FIXTURES = Path(__file__).parent / "fixtures"
DECLARATIONS = FIXTURES / "declarations"
FACET_FIXTURES = FIXTURES / "facets"


def _write_yaml(tmp_path: Path, name: str, document: object) -> Path:
    """Write one YAML test input without reordering its fields."""
    path = tmp_path / name
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _write_declaration_variant(
    tmp_path: Path,
    source_name: str,
    mutate: Callable[[dict[str, object]], None],
) -> Path:
    """Write one mutated declaration fixture."""
    document = yaml.safe_load((DECLARATIONS / "valid" / source_name).read_text())
    mutate(document)
    return _write_yaml(tmp_path, source_name, document)


def _replace_at(document: object, parts: tuple[str | int, ...], value: object) -> None:
    """Replace one test-document value at a known valid path."""
    current = document
    for part in parts[:-1]:
        current = current[part]  # type: ignore[index]
    current[parts[-1]] = value  # type: ignore[index]


def _line_containing(path: Path, text: str) -> int:
    """Return the one-based source line containing ``text``."""
    return next(
        index
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if text in line
    )


@pytest.fixture(scope="module")
def facets():
    """Load the complete test facet registry once per module."""
    return load_facet_registry(FACET_FIXTURES / "valid" / "context-facets.yaml")


def test_packaged_facet_registry_is_canonical_yaml() -> None:
    path = facet_registry_path()
    assert path.is_file()
    registry = load_facet_registry(path)
    assert registry.schema_version == 1
    assert registry.id == "eutaxis/context-facets"
    assert registry.facets["task.kind"].value_schema["enum"] == (
        "writing",
        "programming",
    )
    assert registry.facets["registry.valid"].value_schema == {"type": "boolean"}


def test_facet_registry_models_are_immutable(facets) -> None:
    with pytest.raises(TypeError):
        facets.facets["new"] = facets.facets["a"]  # type: ignore[index]
    with pytest.raises(TypeError):
        facets.facets["a"].value_schema["type"] = "string"  # type: ignore[index]


def test_context_validation_accepts_each_json_value_class(facets) -> None:
    context = facets.validate_context(
        {
            "a": True,
            "sample.integer": 1,
            "sample.number": 1.5,
            "sample.null": None,
            "sample.array": [1, 2],
            "sample.object": {"enabled": False},
            "request.mode": "review",
        }
    )
    assert context["sample.array"] == (1, 2)
    assert context["sample.object"] == {"enabled": False}


@pytest.mark.parametrize(
    ("context", "message"),
    [
        ({"unknown.facet": True}, "not registered"),
        ({"sample.integer": "one"}, "not of type 'integer'"),
        ({"sample.number": float("inf")}, "not a finite JSON value"),
        ({"sample.array": (1, 2)}, "not a finite JSON value"),
    ],
)
def test_context_validation_rejects_unknown_typed_and_non_json_values(
    facets, context: dict[str, object], message: str
) -> None:
    with pytest.raises(FacetContextError, match=message):
        facets.validate_context(context)


def test_context_validation_rejects_cycles(facets) -> None:
    cycle: list[object] = []
    cycle.append(cycle)
    with pytest.raises(FacetContextError, match="cyclic containers"):
        facets.validate_context({"sample.array": cycle})


def test_typed_evaluation_covers_numeric_structural_and_presence_semantics(
    facets,
) -> None:
    assert (
        evaluate_applicability(
            {"facet": "sample.number", "operator": "equals", "value": 1},
            {"sample.number": 1.0},
            facets,
        )
        is TruthValue.TRUE
    )
    assert (
        evaluate_applicability(
            {
                "facet": "sample.boolean-or-number",
                "operator": "equals",
                "value": 1,
            },
            {"sample.boolean-or-number": True},
            facets,
        )
        is TruthValue.FALSE
    )
    assert (
        evaluate_applicability(
            {
                "facet": "sample.object",
                "operator": "equals",
                "value": {"enabled": True},
            },
            {"sample.object": {"enabled": True}},
            facets,
        )
        is TruthValue.TRUE
    )
    assert (
        evaluate_applicability(
            {
                "facet": "sample.array",
                "operator": "in",
                "value": [[1, 2], [3]],
            },
            {"sample.array": [1, 2]},
            facets,
        )
        is TruthValue.TRUE
    )
    assert (
        evaluate_applicability(
            {"facet": "sample.null", "operator": "exists"},
            {"sample.null": None},
            facets,
        )
        is TruthValue.TRUE
    )


def test_typed_evaluation_preserves_strong_kleene_nested_logic(facets) -> None:
    predicate = {
        "not": {
            "any": [
                {"facet": "a", "operator": "equals", "value": True},
                {"facet": "b", "operator": "equals", "value": True},
            ]
        }
    }
    assert evaluate_applicability(predicate, {"a": False}, facets) is TruthValue.UNKNOWN
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
    assert evaluate_applicability(guarded, {}, facets) is TruthValue.FALSE


@pytest.mark.parametrize(
    "filename",
    [
        "rule.yaml",
        "rule-set.yaml",
        "procedure.yaml",
        "resolution-policy.yaml",
        "composition-manifest.yaml",
        "evaluator.yaml",
        "operation.yaml",
    ],
)
def test_every_declaration_kind_passes_the_typed_load_route(
    facets, filename: str
) -> None:
    load_facet_validated_declaration(DECLARATIONS / "valid" / filename, facets)


def test_known_failure_fixture_rejects_a_schema_invalid_facet_constant(facets) -> None:
    path = DECLARATIONS / "invalid" / "wrong-facet-value.yaml"
    with pytest.raises(DeclarationSemanticError) as captured:
        load_facet_validated_declaration(path, facets)
    assert captured.value.location == "$.applicability.value"
    assert captured.value.line == _line_containing(path, 'value: "yes"')
    assert "artifact.created" in str(captured.value)


@pytest.mark.parametrize(
    ("source_name", "parts", "expected_path"),
    [
        ("rule.yaml", ("applicability", "facet"), "$.applicability.facet"),
        (
            "rule-set.yaml",
            ("rules", 0, "applicability", "facet"),
            "$.rules[0].applicability.facet",
        ),
        (
            "rule-set.yaml",
            ("rules", 0, "norms", 0, "applies-when", "facet"),
            "$.rules[0].norms[0].applies-when.facet",
        ),
        (
            "rule-set.yaml",
            ("rules", 0, "exceptions", 0, "when", "facet"),
            "$.rules[0].exceptions[0].when.facet",
        ),
        (
            "procedure.yaml",
            ("postconditions", 0, "expression", "facet"),
            "$.postconditions[0].expression.facet",
        ),
        ("resolution-policy.yaml", ("when", "facet"), "$.when.facet"),
    ],
)
def test_unknown_facets_fail_at_every_nested_source_position(
    facets,
    tmp_path: Path,
    source_name: str,
    parts: tuple[str | int, ...],
    expected_path: str,
) -> None:
    def mutate(document: dict[str, object]) -> None:
        _replace_at(document, parts, "unknown.facet")

    path = _write_declaration_variant(tmp_path, source_name, mutate)
    with pytest.raises(DeclarationSemanticError) as captured:
        load_facet_validated_declaration(path, facets)
    assert captured.value.location == expected_path
    assert captured.value.line == _line_containing(path, "unknown.facet")


@pytest.mark.parametrize(
    ("source_name", "field", "predicate_class"),
    [
        ("procedure.yaml", "preconditions", "guard"),
        ("procedure.yaml", "invariants", "invariant"),
        ("procedure.yaml", "postconditions", "postcondition"),
        ("operation.yaml", "preconditions", "guard"),
    ],
)
def test_typed_load_visits_every_procedure_predicate_position(
    facets,
    tmp_path: Path,
    source_name: str,
    field: str,
    predicate_class: str,
) -> None:
    def mutate(document: dict[str, object]) -> None:
        predicate: dict[str, object] = {
            "id": f"test-{field}",
            "class": predicate_class,
            "expression": {"facet": "unknown.facet", "operator": "exists"},
        }
        if predicate_class == "invariant":
            predicate["observes"] = ["filesystem/artifact"]
        document[field] = [predicate]

    path = _write_declaration_variant(tmp_path, source_name, mutate)
    with pytest.raises(DeclarationSemanticError) as captured:
        load_facet_validated_declaration(path, facets)
    assert captured.value.location == f"$.{field}[0].expression.facet"
    assert captured.value.line == _line_containing(path, "unknown.facet")


def test_invalid_in_candidate_reports_its_index_and_line(
    facets, tmp_path: Path
) -> None:
    def mutate(document: dict[str, object]) -> None:
        document["applicability"] = {
            "facet": "sample.integer",
            "operator": "in",
            "value": [1, "bad", 2],
        }

    path = _write_declaration_variant(tmp_path, "rule.yaml", mutate)
    with pytest.raises(DeclarationSemanticError) as captured:
        load_facet_validated_declaration(path, facets)
    assert captured.value.location == "$.applicability.value[1]"
    assert captured.value.line == _line_containing(path, "- bad")


@pytest.mark.parametrize(
    ("filename", "error_type", "expected_path"),
    [
        ("duplicate-id.yaml", FacetRegistrySemanticError, "$.facets[1].id"),
        (
            "external-ref.yaml",
            FacetRegistrySemanticError,
            "$.facets[0].value-schema.$ref",
        ),
        (
            "invalid-schema.yaml",
            FacetRegistrySemanticError,
            "$.facets[0].value-schema.type",
        ),
    ],
)
def test_invalid_registry_fixtures_report_the_located_cause(
    filename: str, error_type: type[Exception], expected_path: str
) -> None:
    with pytest.raises(error_type) as captured:
        load_facet_registry(FACET_FIXTURES / "invalid" / filename)
    assert captured.value.location == expected_path  # type: ignore[attr-defined]
    assert captured.value.line is not None  # type: ignore[attr-defined]


def test_registry_schema_rejects_unknown_fields_at_their_source_line(
    tmp_path: Path,
) -> None:
    document = yaml.safe_load(
        (FACET_FIXTURES / "valid" / "context-facets.yaml").read_text()
    )
    document["description"] = "Not part of the registry contract"
    path = _write_yaml(tmp_path, "unknown-field.yaml", document)
    with pytest.raises(FacetRegistrySchemaError) as captured:
        load_facet_registry(path)
    assert captured.value.location == "$.description"
    assert captured.value.line == _line_containing(path, "description:")


@pytest.mark.parametrize(
    ("schema", "message"),
    [
        ({"$schema": "http://json-schema.org/draft-07/schema#"}, "must be"),
        ({"$id": "https://example.com/value.schema.json"}, "not admitted"),
        ({"$dynamicRef": "#node"}, "not admitted"),
        ({"$ref": "#/$defs/missing", "$defs": {}}, "does not resolve"),
    ],
)
def test_registry_rejects_non_self_contained_value_schemas(
    tmp_path: Path, schema: dict[str, object], message: str
) -> None:
    document = {
        "schema-version": 1,
        "id": "tests/invalid-reference",
        "owner": "eutaxis",
        "source-revision": "fixture-1",
        "facets": [{"id": "task.kind", "value-schema": schema}],
    }
    path = _write_yaml(tmp_path, "invalid-reference.yaml", document)
    with pytest.raises(FacetRegistrySemanticError, match=message):
        load_facet_registry(path)


def test_registry_accepts_resolved_local_json_pointers(tmp_path: Path) -> None:
    document = {
        "schema-version": 1,
        "id": "tests/local-reference",
        "owner": "eutaxis",
        "source-revision": "fixture-1",
        "facets": [
            {
                "id": "task.kind",
                "value-schema": {
                    "$defs": {"kind": {"type": "string"}},
                    "$ref": "#/$defs/kind",
                },
            }
        ],
    }
    registry = load_facet_registry(_write_yaml(tmp_path, "local-ref.yaml", document))
    assert registry.validate_context({"task.kind": "writing"}) == {
        "task.kind": "writing"
    }


@pytest.mark.parametrize(
    ("schema", "value"),
    [
        ({"const": {"$ref": "ordinary-data"}}, {"$ref": "ordinary-data"}),
        (
            {
                "type": "object",
                "properties": {"$id": {"type": "string"}},
                "required": ["$id"],
                "additionalProperties": False,
            },
            {"$id": "ordinary-property"},
        ),
    ],
)
def test_schema_traversal_does_not_treat_literal_data_or_property_names_as_keywords(
    tmp_path: Path, schema: dict[str, object], value: object
) -> None:
    document = {
        "schema-version": 1,
        "id": "tests/schema-positions",
        "owner": "eutaxis",
        "source-revision": "fixture-1",
        "facets": [{"id": "sample.object", "value-schema": schema}],
    }
    registry = load_facet_registry(_write_yaml(tmp_path, "positions.yaml", document))
    assert registry.validate_context({"sample.object": value})["sample.object"]


@pytest.mark.parametrize("conditional_keyword", ["then", "else"])
def test_registry_ignores_conditional_branches_without_if(
    tmp_path: Path, conditional_keyword: str
) -> None:
    schema = {
        "$defs": {
            "node": {conditional_keyword: {"$ref": "#/$defs/node"}},
        },
        "$ref": "#/$defs/node",
    }
    document = {
        "schema-version": 1,
        "id": "tests/inert-conditional",
        "owner": "eutaxis",
        "source-revision": "fixture-1",
        "facets": [{"id": "sample.value", "value-schema": schema}],
    }
    registry = load_facet_registry(_write_yaml(tmp_path, "inert.yaml", document))
    assert registry.validate_context({"sample.value": 1})["sample.value"] == 1


@pytest.mark.parametrize(
    "schema",
    [
        {
            "$defs": {"loop": {"$ref": "#/$defs/loop"}},
            "$ref": "#/$defs/loop",
        },
        {
            "$defs": {
                "a": {"$ref": "#/$defs/b"},
                "b": {"$ref": "#/$defs/a"},
            },
            "$ref": "#/$defs/a",
        },
        {
            "$defs": {
                "node": {"allOf": [{"$ref": "#/$defs/node"}]},
            },
            "$ref": "#/$defs/node",
        },
        {
            "$defs": {
                "a": {"allOf": [{"$ref": "#/$defs/b"}]},
                "b": {"anyOf": [{"$ref": "#/$defs/a"}]},
            },
            "$ref": "#/$defs/a",
        },
        {
            "$defs": {
                "node": {
                    "type": "object",
                    "properties": {"next": {"$ref": "#/$defs/node"}},
                },
            },
            "$ref": "#/$defs/node",
        },
        {
            "$defs": {
                "node": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/node"},
                },
            },
            "$ref": "#/$defs/node",
        },
        {
            "$defs": {
                "node": {
                    "if": {"type": "integer"},
                    "then": {"$ref": "#/$defs/node"},
                },
            },
            "$ref": "#/$defs/node",
        },
        {
            "$defs": {
                "node": {
                    "if": {"type": "integer"},
                    "else": {"$ref": "#/$defs/node"},
                },
            },
            "$ref": "#/$defs/node",
        },
    ],
)
def test_registry_rejects_direct_and_indirect_local_reference_cycles(
    tmp_path: Path, schema: dict[str, object]
) -> None:
    document = {
        "schema-version": 1,
        "id": "tests/reference-cycle",
        "owner": "eutaxis",
        "source-revision": "fixture-1",
        "facets": [{"id": "sample.object", "value-schema": schema}],
    }
    path = _write_yaml(tmp_path, "reference-cycle.yaml", document)
    with pytest.raises(
        FacetRegistrySemanticError, match="recursive \\$ref cycle"
    ) as captured:
        load_facet_registry(path)
    assert captured.value.location.endswith(".$ref")
    assert captured.value.line is not None


def test_registry_yaml_cycle_uses_the_registry_error_boundary(tmp_path: Path) -> None:
    path = tmp_path / "cyclic.yaml"
    path.write_text(
        "schema-version: 1\nid: tests/cycle\nowner: eutaxis\n"
        "source-revision: fixture-1\nfacets: &facets [*facets]\n",
        encoding="utf-8",
    )
    with pytest.raises(FacetRegistrySchemaError, match="cyclic YAML aliases"):
        load_facet_registry(path)


def test_registry_non_json_value_uses_the_registry_error_boundary(
    tmp_path: Path,
) -> None:
    path = tmp_path / "non-json.yaml"
    path.write_text(
        "schema-version: 1\nid: tests/non-json\nowner: eutaxis\n"
        "source-revision: .nan\nfacets: []\n",
        encoding="utf-8",
    )
    with pytest.raises(FacetRegistrySchemaError, match="not a JSON value"):
        load_facet_registry(path)


@pytest.mark.parametrize(
    ("applicability", "expected_path"),
    [
        (
            {"facet": "sample.integer", "operator": "in", "value": []},
            "$.applicability.value",
        ),
        (
            {"facet": "sample.integer", "operator": "exists", "value": 1},
            "$.applicability.value",
        ),
    ],
)
def test_operator_shape_errors_precede_facet_validation(
    facets,
    tmp_path: Path,
    applicability: dict[str, object],
    expected_path: str,
) -> None:
    def mutate(document: dict[str, object]) -> None:
        document["applicability"] = applicability

    path = _write_declaration_variant(tmp_path, "rule.yaml", mutate)
    with pytest.raises(DeclarationSchemaError) as captured:
        load_facet_validated_declaration(path, facets)
    assert captured.value.location == expected_path


def test_typed_load_returns_the_same_domain_model(facets) -> None:
    declaration = load_facet_validated_declaration(
        DECLARATIONS / "valid" / "rule.yaml", facets
    )
    assert isinstance(declaration, RuleDeclaration)
