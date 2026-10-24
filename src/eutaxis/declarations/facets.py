"""Load context-facet registries and validate typed applicability inputs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, NoReturn, cast
from urllib.parse import unquote

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError, best_match  # type: ignore[import-untyped]

from .. import data_path
from .exceptions import (
    DeclarationSemanticError,
    FacetContextError,
    FacetRegistrySchemaError,
    FacetRegistrySemanticError,
)
from .models import JsonValue, freeze_json
from .schema import validate_facet_registry_document
from .source import (
    DocumentPath,
    SourceMap,
    format_document_path,
    load_yaml_document,
    nearest_location,
)

FACET_REGISTRY_FILENAME = "context-facets-v1.yaml"
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_SINGLE_SCHEMA_KEYWORDS = frozenset(
    {
        "additionalProperties",
        "contains",
        "contentSchema",
        "else",
        "if",
        "items",
        "not",
        "propertyNames",
        "then",
        "unevaluatedItems",
        "unevaluatedProperties",
    }
)
_SCHEMA_ARRAY_KEYWORDS = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
_SCHEMA_MAP_KEYWORDS = frozenset(
    {"$defs", "dependentSchemas", "patternProperties", "properties"}
)
_CONTROL_KEYWORDS = frozenset(
    {"$schema", "$id", "$ref", "$dynamicRef", "$recursiveRef"}
)


@dataclass(frozen=True)
class ContextFacet:
    """One named context value and its self-contained JSON Schema."""

    id: str
    value_schema: Mapping[str, JsonValue]


@dataclass(frozen=True)
class FacetRegistry:
    """One authoritative set of typed context facets for a validation run."""

    schema_version: int
    id: str
    owner: str
    source_revision: str
    facets: Mapping[str, ContextFacet]

    def validate_context(
        self, context: Mapping[str, object]
    ) -> Mapping[str, JsonValue]:
        """Validate and freeze one runtime context.

        Raises
        ------
        FacetContextError
            If a key is unknown or a present value violates its facet schema.
        """
        validated: dict[str, JsonValue] = {}
        for facet_id, value in context.items():
            if not isinstance(facet_id, str):
                raise FacetContextError(str(facet_id), "context keys must be strings")
            facet = self.facets.get(facet_id)
            if facet is None:
                raise FacetContextError(facet_id, "facet is not registered")
            _require_json_context_value(facet_id, value)
            error = best_match(
                Draft202012Validator(facet.value_schema).iter_errors(value)
            )
            if error is not None:
                raise FacetContextError(facet_id, error.message)
            validated[facet_id] = freeze_json(value)
        return MappingProxyType(validated)


def facet_registry_path() -> Path:
    """Return the packaged path of the reference context-facet registry."""
    return data_path() / "registries" / FACET_REGISTRY_FILENAME


def load_facet_registry(path: Path) -> FacetRegistry:
    """Load and validate one canonical YAML context-facet registry.

    Raises
    ------
    FacetRegistrySchemaError
        If the YAML or registry structure is invalid.
    FacetRegistrySemanticError
        If facet identifiers repeat or a value schema is invalid or non-local.
    """
    document, locations = load_yaml_document(path, error_type=FacetRegistrySchemaError)
    validated = validate_facet_registry_document(
        document, path=path, locations=locations
    )
    facets: dict[str, ContextFacet] = {}
    for index, value in enumerate(cast(list[object], validated["facets"])):
        item = _mapping(value)
        facet_id = str(item["id"])
        if facet_id in facets:
            _raise_registry_semantic(
                path,
                ("facets", index, "id"),
                f"duplicate facet id {facet_id!r}",
                locations,
            )
        schema_parts = ("facets", index, "value-schema")
        value_schema = _mapping(item["value-schema"])
        _validate_value_schema(
            value_schema,
            path=path,
            parts=schema_parts,
            locations=locations,
        )
        facets[facet_id] = ContextFacet(
            id=facet_id,
            value_schema=cast(Mapping[str, JsonValue], freeze_json(value_schema)),
        )
    return FacetRegistry(
        schema_version=cast(int, validated["schema-version"]),
        id=str(validated["id"]),
        owner=str(validated["owner"]),
        source_revision=str(validated["source-revision"]),
        facets=MappingProxyType(facets),
    )


def validate_declaration_facets(
    document: Mapping[str, object],
    registry: FacetRegistry,
    *,
    path: Path,
    locations: SourceMap,
) -> None:
    """Validate every schema-owned applicability position in a declaration."""
    _validate_applicability(
        _mapping(document["applicability"]),
        registry,
        path=path,
        parts=("applicability",),
        locations=locations,
    )
    kind = document["kind"]
    if kind == "rule":
        _validate_rule_facets(
            document, registry, path=path, parts=(), locations=locations
        )
    elif kind == "rule-set":
        for index, rule in enumerate(cast(list[object], document["rules"])):
            rule_parts = ("rules", index)
            rule_mapping = _mapping(rule)
            _validate_applicability(
                _mapping(rule_mapping["applicability"]),
                registry,
                path=path,
                parts=rule_parts + ("applicability",),
                locations=locations,
            )
            _validate_rule_facets(
                rule_mapping,
                registry,
                path=path,
                parts=rule_parts,
                locations=locations,
            )
    elif kind in {"procedure", "operation"}:
        fields = (
            ("preconditions", "invariants", "postconditions")
            if kind == "procedure"
            else ("preconditions",)
        )
        for field in fields:
            for index, predicate in enumerate(cast(list[object], document[field])):
                _validate_applicability(
                    _mapping(_mapping(predicate)["expression"]),
                    registry,
                    path=path,
                    parts=(field, index, "expression"),
                    locations=locations,
                )
    elif kind == "resolution-policy":
        _validate_applicability(
            _mapping(document["when"]),
            registry,
            path=path,
            parts=("when",),
            locations=locations,
        )


def _validate_rule_facets(
    rule: Mapping[str, object],
    registry: FacetRegistry,
    *,
    path: Path,
    parts: DocumentPath,
    locations: SourceMap,
) -> None:
    """Validate norm and exception predicates owned by one rule."""
    for index, norm in enumerate(cast(list[object], rule["norms"])):
        norm_mapping = _mapping(norm)
        if "applies-when" in norm_mapping:
            _validate_applicability(
                _mapping(norm_mapping["applies-when"]),
                registry,
                path=path,
                parts=parts + ("norms", index, "applies-when"),
                locations=locations,
            )
    for index, exception in enumerate(cast(list[object], rule.get("exceptions", []))):
        _validate_applicability(
            _mapping(_mapping(exception)["when"]),
            registry,
            path=path,
            parts=parts + ("exceptions", index, "when"),
            locations=locations,
        )


def _validate_applicability(
    predicate: Mapping[str, object],
    registry: FacetRegistry,
    *,
    path: Path,
    parts: DocumentPath,
    locations: SourceMap,
) -> None:
    """Validate one applicability tree without traversing arbitrary mappings."""
    for boolean_operator in ("all", "any"):
        if boolean_operator in predicate:
            for index, child in enumerate(
                cast(list[object], predicate[boolean_operator])
            ):
                _validate_applicability(
                    _mapping(child),
                    registry,
                    path=path,
                    parts=parts + (boolean_operator, index),
                    locations=locations,
                )
            return
    if "not" in predicate:
        _validate_applicability(
            _mapping(predicate["not"]),
            registry,
            path=path,
            parts=parts + ("not",),
            locations=locations,
        )
        return

    facet_id = str(predicate["facet"])
    facet = registry.facets.get(facet_id)
    if facet is None:
        _raise_declaration_semantic(
            path,
            parts + ("facet",),
            f"facet {facet_id!r} is not registered in {registry.id!r}",
            locations,
        )
    operator = predicate["operator"]
    if operator == "exists":
        return
    if operator == "equals":
        _validate_declared_value(
            predicate["value"],
            facet,
            path=path,
            parts=parts + ("value",),
            locations=locations,
        )
        return
    for index, candidate in enumerate(cast(list[object], predicate["value"])):
        _validate_declared_value(
            candidate,
            facet,
            path=path,
            parts=parts + ("value", index),
            locations=locations,
        )


def _validate_declared_value(
    value: object,
    facet: ContextFacet,
    *,
    path: Path,
    parts: DocumentPath,
    locations: SourceMap,
) -> None:
    """Validate one declared comparison value against its registered facet."""
    error = best_match(Draft202012Validator(facet.value_schema).iter_errors(value))
    if error is None:
        return
    _raise_declaration_semantic(
        path,
        parts + tuple(error.absolute_path),
        f"value for facet {facet.id!r} is invalid: {error.message}",
        locations,
    )


def _validate_value_schema(
    schema: Mapping[str, object],
    *,
    path: Path,
    parts: DocumentPath,
    locations: SourceMap,
) -> None:
    """Require one self-contained Draft 2020-12 facet value schema."""
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        _raise_registry_semantic(
            path,
            parts + tuple(exc.path),
            f"invalid facet value schema: {exc.message}",
            locations,
        )
    schema_nodes = _schema_nodes(schema)
    schema_node_ids = {id(node) for _, node in schema_nodes}
    evaluation_edges: dict[int, list[tuple[int, DocumentPath | None]]] = {}
    for node_parts, node in schema_nodes:
        node_edges = evaluation_edges.setdefault(id(node), [])
        for child in _evaluation_children(node):
            node_edges.append((id(child), None))
        for keyword in _CONTROL_KEYWORDS.intersection(node):
            value = node[keyword]
            location = parts + node_parts + (keyword,)
            if keyword == "$schema" and value != JSON_SCHEMA_DIALECT:
                _raise_registry_semantic(
                    path,
                    location,
                    f"$schema must be {JSON_SCHEMA_DIALECT!r}",
                    locations,
                )
            if keyword in {"$id", "$dynamicRef", "$recursiveRef"}:
                _raise_registry_semantic(
                    path,
                    location,
                    f"{keyword} is not admitted in facet value schemas",
                    locations,
                )
            if keyword != "$ref":
                continue
            if not isinstance(value, str) or not value.startswith("#/"):
                _raise_registry_semantic(
                    path,
                    location,
                    "$ref must be a local JSON Pointer beginning with '#/'",
                    locations,
                )
            target = _resolve_json_pointer(schema, value)
            if target is None:
                _raise_registry_semantic(
                    path,
                    location,
                    f"$ref does not resolve inside this value schema: {value!r}",
                    locations,
                )
            if not isinstance(target, (Mapping, bool)) or (
                isinstance(target, Mapping) and id(target) not in schema_node_ids
            ):
                _raise_registry_semantic(
                    path,
                    location,
                    f"$ref target is not a schema: {value!r}",
                    locations,
                )
            if isinstance(target, Mapping):
                node_edges.append((id(target), location))
    _reject_reference_cycles(
        id(schema),
        evaluation_edges,
        path=path,
        locations=locations,
    )


def _schema_nodes(
    schema: Mapping[str, object], parts: DocumentPath = ()
) -> tuple[tuple[DocumentPath, Mapping[str, object]], ...]:
    """Return only mappings that Draft 2020-12 treats as schemas."""
    found = [(parts, schema)]
    for keyword in _SINGLE_SCHEMA_KEYWORDS.intersection(schema):
        child = schema[keyword]
        if isinstance(child, Mapping):
            found.extend(_schema_nodes(child, parts + (keyword,)))
    for keyword in _SCHEMA_ARRAY_KEYWORDS.intersection(schema):
        children = schema[keyword]
        if isinstance(children, list):
            for index, child in enumerate(children):
                if isinstance(child, Mapping):
                    found.extend(_schema_nodes(child, parts + (keyword, index)))
    for keyword in _SCHEMA_MAP_KEYWORDS.intersection(schema):
        children = schema[keyword]
        if isinstance(children, Mapping):
            for name, child in children.items():
                if isinstance(child, Mapping):
                    found.extend(_schema_nodes(child, parts + (keyword, str(name))))
    return tuple(found)


def _evaluation_children(
    schema: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    """Return subschemas that evaluation can reach without following ``$defs``."""
    found: list[Mapping[str, object]] = []
    single_keywords = _SINGLE_SCHEMA_KEYWORDS.intersection(schema)
    if "if" not in schema:
        single_keywords -= {"then", "else"}
    for keyword in single_keywords:
        child = schema[keyword]
        if isinstance(child, Mapping):
            found.append(child)
    for keyword in _SCHEMA_ARRAY_KEYWORDS.intersection(schema):
        children = schema[keyword]
        if isinstance(children, list):
            found.extend(child for child in children if isinstance(child, Mapping))
    for keyword in (_SCHEMA_MAP_KEYWORDS - {"$defs"}).intersection(schema):
        children = schema[keyword]
        if isinstance(children, Mapping):
            found.extend(
                child for child in children.values() if isinstance(child, Mapping)
            )
    return tuple(found)


def _reject_reference_cycles(
    root: int,
    edges: Mapping[int, list[tuple[int, DocumentPath | None]]],
    *,
    path: Path,
    locations: SourceMap,
) -> None:
    """Reject cycles reachable through schema evaluation and local references."""
    states: dict[int, int] = {}
    active_nodes: list[int] = []
    incoming_references: list[DocumentPath | None] = []

    def visit(node: int, incoming_reference: DocumentPath | None) -> None:
        states[node] = 1
        active_nodes.append(node)
        incoming_references.append(incoming_reference)
        for target, reference_path in edges.get(node, []):
            if states.get(target) == 1:
                cycle_start = active_nodes.index(target)
                returning_reference = next(
                    (
                        candidate
                        for candidate in reversed(
                            incoming_references[cycle_start + 1 :] + [reference_path]
                        )
                        if candidate is not None
                    ),
                    None,
                )
                if returning_reference is None:
                    raise RuntimeError("schema cycle contains no local reference")
                _raise_registry_semantic(
                    path,
                    returning_reference,
                    "recursive $ref cycle is not admitted",
                    locations,
                )
            if states.get(target, 0) == 0:
                visit(target, reference_path)
        active_nodes.pop()
        incoming_references.pop()
        states[node] = 2

    visit(root, None)


def _resolve_json_pointer(root: Mapping[str, object], reference: str) -> object | None:
    """Resolve a local JSON Pointer against its facet value schema."""
    current: object = root
    for token in unquote(reference[2:]).split("/"):
        decoded = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if decoded not in current:
                return None
            current = current[decoded]
        elif isinstance(current, list) and decoded.isdecimal():
            index = int(decoded)
            if index >= len(current):
                return None
            current = current[index]
        else:
            return None
    return current


def _require_json_context_value(
    facet_id: str, value: object, active: set[int] | None = None
) -> None:
    """Reject runtime values outside the finite JSON data model."""
    if active is None:
        active = set()
    if isinstance(value, Mapping):
        identity = _enter_context_container(facet_id, value, active)
        try:
            for key, child in value.items():
                if not isinstance(key, str):
                    raise FacetContextError(facet_id, "object keys must be strings")
                _require_json_context_value(facet_id, child, active)
        finally:
            active.remove(identity)
        return
    if isinstance(value, list):
        identity = _enter_context_container(facet_id, value, active)
        try:
            for child in value:
                _require_json_context_value(facet_id, child, active)
        finally:
            active.remove(identity)
        return
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    raise FacetContextError(
        facet_id, f"{type(value).__name__} is not a finite JSON value"
    )


def _enter_context_container(facet_id: str, value: object, active: set[int]) -> int:
    """Enter one context container and reject recursive object graphs."""
    identity = id(value)
    if identity in active:
        raise FacetContextError(facet_id, "cyclic containers are not JSON values")
    active.add(identity)
    return identity


def _mapping(value: object) -> Mapping[str, object]:
    """Narrow a mapping already guaranteed by schema validation."""
    return cast(Mapping[str, object], value)


def _raise_registry_semantic(
    path: Path,
    parts: DocumentPath,
    message: str,
    locations: SourceMap,
) -> NoReturn:
    """Raise a registry-semantic error at its closest source position."""
    source = nearest_location(locations, parts)
    raise FacetRegistrySemanticError(
        path,
        format_document_path(parts),
        message,
        line=source.line if source else None,
        column=source.column if source else None,
    )


def _raise_declaration_semantic(
    path: Path,
    parts: DocumentPath,
    message: str,
    locations: SourceMap,
) -> NoReturn:
    """Raise a facet-related declaration error at its source position."""
    source = nearest_location(locations, parts)
    raise DeclarationSemanticError(
        path,
        format_document_path(parts),
        message,
        line=source.line if source else None,
        column=source.column if source else None,
    )
