"""Validate and execute self-contained embedded JSON Schemas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, TypeAlias, TypeGuard
from urllib.parse import quote, unquote

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import (  # type: ignore[import-untyped]
    SchemaError,
    ValidationError,
    best_match,
)
from referencing import Registry, Resource  # type: ignore[import-untyped]
from referencing.jsonschema import DRAFT202012  # type: ignore[import-untyped]

SchemaPath: TypeAlias = tuple[str | int, ...]

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_RESOURCE_URI = "urn:eutaxis:embedded-schema"
_SINGLE_SCHEMA_KEYWORDS = (
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
)
_SCHEMA_ARRAY_KEYWORDS = ("allOf", "anyOf", "oneOf", "prefixItems")
_SCHEMA_MAP_KEYWORDS = (
    "$defs",
    "dependentSchemas",
    "patternProperties",
    "properties",
)
_CONTROL_KEYWORDS = ("$schema", "$id", "$ref", "$dynamicRef", "$recursiveRef")


@dataclass(frozen=True)
class EmbeddedSchemaContractError(ValueError):
    """One source-relative defect in an embedded schema definition."""

    path: SchemaPath
    message: str

    def __str__(self) -> str:
        return self.message


def validate_self_contained_schema(schema: object) -> None:
    """Require one self-contained Draft 2020-12 schema resource.

    The definition scan covers inactive schemas as well as evaluated schemas.
    Only reachable local-reference cycles are rejected.
    """
    try:
        Draft202012Validator.check_schema(_plain_json_containers(schema))
    except SchemaError as exc:
        raise EmbeddedSchemaContractError(
            tuple(exc.path), f"invalid embedded JSON Schema: {exc.message}"
        ) from exc
    if not isinstance(schema, Mapping):
        return

    schema_nodes = _schema_nodes(schema)
    schema_node_ids = {id(node) for _, node in schema_nodes}
    evaluation_edges: dict[int, list[tuple[int, SchemaPath | None]]] = {}
    for node_path, node in schema_nodes:
        node_edges = evaluation_edges.setdefault(id(node), [])
        for child in _evaluation_children(node):
            node_edges.append((id(child), None))
        for keyword in _CONTROL_KEYWORDS:
            if keyword not in node:
                continue
            value = node[keyword]
            location = node_path + (keyword,)
            if keyword == "$schema" and value != JSON_SCHEMA_DIALECT:
                raise EmbeddedSchemaContractError(
                    location,
                    f"$schema must be {JSON_SCHEMA_DIALECT!r}",
                )
            if keyword in {"$id", "$dynamicRef", "$recursiveRef"}:
                raise EmbeddedSchemaContractError(
                    location,
                    f"{keyword} is not admitted in embedded schemas",
                )
            if keyword != "$ref":
                continue
            if not isinstance(value, str) or not value.startswith("#/"):
                raise EmbeddedSchemaContractError(
                    location,
                    "$ref must be a local JSON Pointer beginning with '#/'",
                )
            target = _resolve_json_pointer(schema, value)
            if target is None:
                raise EmbeddedSchemaContractError(
                    location,
                    f"$ref does not resolve inside this schema: {value!r}",
                )
            if not isinstance(target, (Mapping, bool)) or (
                isinstance(target, Mapping) and id(target) not in schema_node_ids
            ):
                raise EmbeddedSchemaContractError(
                    location,
                    f"$ref target is not a schema: {value!r}",
                )
            if isinstance(target, Mapping):
                node_edges.append((id(target), location))
    _reject_reference_cycles(id(schema), evaluation_edges)


def validate_json_instance(
    schema: Mapping[str, object], instance: object
) -> ValidationError | None:
    """Return the most relevant error for an instance under a schema root."""
    validator = _local_reference_validator(schema, _RESOURCE_URI)
    return best_match(validator.iter_errors(_plain_json_containers(instance)))


def validate_json_subschema(
    schema: Mapping[str, object],
    subschema_path: SchemaPath,
    instance: object,
) -> ValidationError | None:
    """Validate an instance against a subschema with the complete root in scope."""
    pointer = "/".join(_pointer_token(part) for part in subschema_path)
    reference = f"{_RESOURCE_URI}#/{quote(pointer, safe='/~')}"
    validator = _local_reference_validator(schema, reference)
    return best_match(validator.iter_errors(_plain_json_containers(instance)))


def normalize_json_subschema(
    schema: Mapping[str, object], subschema_path: SchemaPath
) -> object:
    """Return one schema fragment with its local-reference closure expanded.

    Only values in JSON Schema positions are traversed as schemas. Annotation
    values that happen to contain a ``$ref`` key remain ordinary JSON data.
    """
    if subschema_path:
        pointer = "/".join(_pointer_token(part) for part in subschema_path)
        selected = _resolve_json_pointer(schema, f"#/{pointer}")
    else:
        selected = schema
    if not isinstance(selected, (Mapping, bool)):
        raise ValueError(
            f"subschema path does not identify a schema: {subschema_path!r}"
        )
    return _normalize_schema_node(schema, selected, set())


def _local_reference_validator(
    schema: Mapping[str, object], reference: str
) -> Draft202012Validator:
    """Build a validator whose references cannot retrieve external resources."""
    resource = Resource.from_contents(schema, default_specification=DRAFT202012)
    registry = Registry().with_resource(_RESOURCE_URI, resource)
    return Draft202012Validator({"$ref": reference}, registry=registry)


def _plain_json_containers(value: object) -> object:
    """Copy immutable JSON containers into meta-schema-compatible containers."""
    if isinstance(value, Mapping):
        return {key: _plain_json_containers(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json_containers(item) for item in value]
    return value


def _normalize_schema_node(
    root: Mapping[str, object],
    node: Mapping[str, object] | bool,
    active: set[int],
) -> object:
    """Expand local references while preserving exact schema structure."""
    if isinstance(node, bool):
        return node
    node_id = id(node)
    if node_id in active:
        raise ValueError("cannot normalize a recursive schema reference")
    active.add(node_id)
    try:
        normalized: dict[str, object] = {}
        for keyword, value in node.items():
            if keyword == "$ref":
                if not isinstance(value, str):
                    raise ValueError("validated $ref is not a string")
                target = _resolve_json_pointer(root, value)
                if not isinstance(target, (Mapping, bool)):
                    raise ValueError(
                        f"validated $ref does not identify a schema: {value!r}"
                    )
                normalized[keyword] = _normalize_schema_node(root, target, active)
            elif keyword in _SINGLE_SCHEMA_KEYWORDS and isinstance(
                value, (Mapping, bool)
            ):
                normalized[keyword] = _normalize_schema_node(root, value, active)
            elif keyword in _SCHEMA_ARRAY_KEYWORDS and _is_schema_sequence(value):
                normalized[keyword] = [
                    (
                        _normalize_schema_node(root, item, active)
                        if isinstance(item, (Mapping, bool))
                        else _plain_json_containers(item)
                    )
                    for item in value
                ]
            elif keyword in _SCHEMA_MAP_KEYWORDS and isinstance(value, Mapping):
                normalized[keyword] = {
                    name: (
                        _normalize_schema_node(root, item, active)
                        if isinstance(item, (Mapping, bool))
                        else _plain_json_containers(item)
                    )
                    for name, item in value.items()
                }
            else:
                normalized[keyword] = _plain_json_containers(value)
        return normalized
    finally:
        active.remove(node_id)


def _schema_nodes(
    schema: Mapping[str, object], path: SchemaPath = ()
) -> tuple[tuple[SchemaPath, Mapping[str, object]], ...]:
    """Return only mappings that Draft 2020-12 treats as schemas."""
    found = [(path, schema)]
    for keyword in _SINGLE_SCHEMA_KEYWORDS:
        child = schema.get(keyword)
        if isinstance(child, Mapping):
            found.extend(_schema_nodes(child, path + (keyword,)))
    for keyword in _SCHEMA_ARRAY_KEYWORDS:
        children = schema.get(keyword)
        if _is_schema_sequence(children):
            for index, child in enumerate(children):
                if isinstance(child, Mapping):
                    found.extend(_schema_nodes(child, path + (keyword, index)))
    for keyword in _SCHEMA_MAP_KEYWORDS:
        children = schema.get(keyword)
        if isinstance(children, Mapping):
            for name, child in children.items():
                if isinstance(child, Mapping):
                    found.extend(_schema_nodes(child, path + (keyword, str(name))))
    return tuple(found)


def _evaluation_children(
    schema: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    """Return subschemas reachable without entering definitions through syntax."""
    found: list[Mapping[str, object]] = []
    single_keywords = set(_SINGLE_SCHEMA_KEYWORDS).intersection(schema)
    if "if" not in schema:
        single_keywords -= {"then", "else"}
    for keyword in _SINGLE_SCHEMA_KEYWORDS:
        if keyword not in single_keywords:
            continue
        child = schema[keyword]
        if isinstance(child, Mapping):
            found.append(child)
    for keyword in _SCHEMA_ARRAY_KEYWORDS:
        children = schema.get(keyword)
        if _is_schema_sequence(children):
            found.extend(child for child in children if isinstance(child, Mapping))
    for keyword in _SCHEMA_MAP_KEYWORDS:
        if keyword == "$defs":
            continue
        children = schema.get(keyword)
        if isinstance(children, Mapping):
            found.extend(
                child for child in children.values() if isinstance(child, Mapping)
            )
    return tuple(found)


def _reject_reference_cycles(
    root: int,
    edges: Mapping[int, list[tuple[int, SchemaPath | None]]],
) -> None:
    """Reject cycles reachable through evaluation and local-reference edges."""
    states: dict[int, int] = {}
    active_nodes: list[int] = []
    incoming_references: list[SchemaPath | None] = []

    def visit(node: int, incoming_reference: SchemaPath | None) -> None:
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
                raise EmbeddedSchemaContractError(
                    returning_reference,
                    "recursive $ref cycle is not admitted",
                )
            if states.get(target, 0) == 0:
                visit(target, reference_path)
        active_nodes.pop()
        incoming_references.pop()
        states[node] = 2

    visit(root, None)


def _resolve_json_pointer(root: Mapping[str, object], reference: str) -> object | None:
    """Resolve a local JSON Pointer against its complete schema resource."""
    current: object = root
    for token in unquote(reference[2:]).split("/"):
        decoded = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if decoded not in current:
                return None
            current = current[decoded]
        elif _is_schema_sequence(current) and decoded.isdecimal():
            index = int(decoded)
            if index >= len(current):
                return None
            current = current[index]
        else:
            return None
    return current


def _is_schema_sequence(
    value: object,
) -> TypeGuard[list[object] | tuple[object, ...]]:
    """Recognize mutable and frozen JSON arrays, excluding scalar strings."""
    return isinstance(value, (list, tuple))


def _pointer_token(part: str | int) -> str:
    """Encode one document-path part as a JSON Pointer token."""
    return str(part).replace("~", "~0").replace("/", "~1")
