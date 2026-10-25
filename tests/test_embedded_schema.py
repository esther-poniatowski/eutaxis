"""Contract tests for self-contained embedded JSON Schemas."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Mapping
from urllib import request

import pytest
import yaml

from eutaxis.declarations import (
    ContextFacet,
    DeclarationSchemaError,
    FacetContextError,
    FacetRegistry,
    TruthValue,
    evaluate_applicability,
    load_declaration,
)
from eutaxis.declarations.embedded_schema import (
    normalize_json_subschema,
    validate_json_subschema,
    validate_self_contained_schema,
)
from eutaxis.declarations.models import JsonValue, freeze_json, json_values_equal

DECLARATIONS = Path(__file__).parent / "fixtures" / "declarations" / "valid"


def _write_variant(
    tmp_path: Path,
    source_name: str,
    parts: tuple[str, ...],
    value: object,
) -> Path:
    """Write one declaration with a replaced embedded schema."""
    document = yaml.safe_load((DECLARATIONS / source_name).read_text(encoding="utf-8"))
    current = document
    for part in parts[:-1]:
        current = current[part]
    current[parts[-1]] = value
    path = tmp_path / source_name
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("source_name", "parts", "schema", "expected_location"),
    [
        (
            "procedure.yaml",
            ("parameters", "properties", "path"),
            {"$ref": "https://example.com/path.schema.json"},
            "$.parameters.properties.path.$ref",
        ),
        (
            "evaluator.yaml",
            ("evidence-schema",),
            {
                "$defs": {},
                "$ref": "#/$defs/missing",
                "type": "object",
                "required": ["conclusion"],
                "properties": {
                    "conclusion": {"enum": ["satisfied", "violated", "blocked"]}
                },
            },
            "$.evidence-schema.$ref",
        ),
        (
            "operation.yaml",
            ("inputs", "properties", "path"),
            {"$ref": "#/properties/path"},
            "$.inputs.properties.path.$ref",
        ),
        (
            "operation.yaml",
            ("outputs",),
            {"$dynamicRef": "#node"},
            "$.outputs.$dynamicRef",
        ),
    ],
)
def test_every_declaration_schema_consumer_rejects_unsafe_references(
    tmp_path: Path,
    source_name: str,
    parts: tuple[str, ...],
    schema: dict[str, object],
    expected_location: str,
) -> None:
    path = _write_variant(tmp_path, source_name, parts, schema)
    with pytest.raises(DeclarationSchemaError) as captured:
        load_declaration(path)
    assert captured.value.location == expected_location
    assert captured.value.line is not None


def test_subschema_validation_retains_the_complete_root_resource() -> None:
    schema = {
        "$defs": {"positive": {"type": "integer", "minimum": 1}},
        "type": "object",
        "properties": {"a/b": {"$ref": "#/$defs/positive"}},
        "additionalProperties": False,
    }
    validate_self_contained_schema(schema)
    error = validate_json_subschema(schema, ("properties", "a/b"), 0)
    assert error is not None
    assert error.message == "0 is less than the minimum of 1"
    assert validate_json_subschema(schema, ("properties", "a/b"), 2) is None


def test_subschema_validation_preserves_nested_paths_for_frozen_values() -> None:
    schema = {
        "type": "object",
        "properties": {
            "item": {
                "type": "object",
                "properties": {"count": {"type": "integer"}},
                "required": ["count"],
                "additionalProperties": False,
            }
        },
        "required": ["item"],
        "additionalProperties": False,
    }
    instance = freeze_json({"count": "seven"})

    error = validate_json_subschema(schema, ("properties", "item"), instance)

    assert error is not None
    assert tuple(error.absolute_path) == ("count",)


def test_subschema_normalization_expands_transitive_escaped_references() -> None:
    schema = {
        "$defs": {
            "a/b": {"$ref": "#/$defs/c~0d", "minimum": 1},
            "c~d": {"type": "integer"},
        },
        "type": "object",
        "properties": {
            "selected": {
                "$ref": "#/$defs/a~1b",
                "description": "kept sibling",
                "examples": [{"$ref": "annotation data"}],
            }
        },
        "additionalProperties": False,
    }
    validate_self_contained_schema(schema)

    normalized = normalize_json_subschema(schema, ("properties", "selected"))

    assert normalized == {
        "$ref": {"$ref": {"type": "integer"}, "minimum": 1},
        "description": "kept sibling",
        "examples": [{"$ref": "annotation data"}],
    }


def test_subschema_normalization_depends_on_each_complete_root() -> None:
    left = {
        "type": "object",
        "properties": {
            "selected": {"$ref": "#/properties/shared"},
            "shared": {"type": "integer"},
        },
        "additionalProperties": False,
    }
    equal = {
        "type": "object",
        "properties": {
            "selected": {"$ref": "#/properties/shared"},
            "shared": {"type": "integer"},
        },
        "additionalProperties": False,
    }
    different = {
        "type": "object",
        "properties": {
            "selected": {"$ref": "#/properties/shared"},
            "shared": {"type": "string"},
        },
        "additionalProperties": False,
    }

    normalized = normalize_json_subschema(left, ("properties", "selected"))

    assert json_values_equal(
        normalized,
        normalize_json_subschema(equal, ("properties", "selected")),
    )
    assert not json_values_equal(
        normalized,
        normalize_json_subschema(different, ("properties", "selected")),
    )


def test_unreachable_recursive_definition_remains_admitted() -> None:
    schema = {
        "$defs": {"unused": {"$ref": "#/$defs/unused"}},
        "type": "string",
    }
    validate_self_contained_schema(schema)


def test_runtime_facet_validation_cannot_retrieve_external_schemas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retrievals: list[str] = []

    def record_retrieval(url: str, *args: object, **kwargs: object) -> None:
        retrievals.append(url)
        raise AssertionError("runtime facet validation attempted network retrieval")

    monkeypatch.setattr(request, "urlopen", record_retrieval)
    facets = FacetRegistry(
        schema_version=1,
        id="test/facets",
        owner="test",
        source_revision="test",
        facets={
            "unsafe": ContextFacet(
                id="unsafe",
                value_schema=MappingProxyType(
                    {
                        "allOf": (
                            MappingProxyType(
                                {"$ref": "https://example.com/schema.json"}
                            ),
                        )
                    }
                ),
            )
        },
    )

    with pytest.raises(FacetContextError, match="registered schema is invalid"):
        facets.validate_context({"unsafe": "value"})
    assert retrievals == []


@pytest.mark.parametrize(
    "schema",
    [
        MappingProxyType({"allOf": (MappingProxyType({"$dynamicRef": "#node"}),)}),
        MappingProxyType(
            {
                "$defs": MappingProxyType(
                    {
                        "node": MappingProxyType(
                            {"allOf": (MappingProxyType({"$ref": "#/$defs/node"}),)}
                        )
                    }
                ),
                "$ref": "#/$defs/node",
            }
        ),
    ],
)
def test_runtime_facet_validation_rejects_invalid_immutable_nested_schemas(
    schema: Mapping[str, JsonValue],
) -> None:
    facets = FacetRegistry(
        schema_version=1,
        id="test/facets",
        owner="test",
        source_revision="test",
        facets={"unsafe": ContextFacet(id="unsafe", value_schema=schema)},
    )

    with pytest.raises(FacetContextError, match="registered schema is invalid"):
        facets.validate_context({"unsafe": "value"})


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ({"a": 1, "b": [2]}, {"b": [2.0], "a": 1.0}, True),
        ([True], [1], False),
        ({"a": [True]}, {"a": [1]}, False),
        ([1, 2], [2, 1], False),
        (1, 1.0, True),
        (10**400, 10**400, True),
        (10**400, 10**401, False),
        (10**400, 1.0, False),
    ],
)
def test_json_structural_equality(left: object, right: object, expected: bool) -> None:
    assert json_values_equal(freeze_json(left), freeze_json(right)) is expected


@pytest.mark.parametrize(
    ("declared", "expected"),
    [(10**400, TruthValue.TRUE), (10**401, TruthValue.FALSE), (1.0, TruthValue.FALSE)],
)
def test_applicability_compares_large_integers_without_float_conversion(
    declared: int | float, expected: TruthValue
) -> None:
    facets = FacetRegistry(
        schema_version=1,
        id="test/facets",
        owner="test",
        source_revision="test",
        facets={"large": ContextFacet(id="large", value_schema={"type": "integer"})},
    )
    predicate = {"facet": "large", "operator": "equals", "value": declared}

    assert evaluate_applicability(predicate, {"large": 10**400}, facets) is expected
