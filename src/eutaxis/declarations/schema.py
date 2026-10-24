"""Load and apply the packaged normative declaration schema."""

from __future__ import annotations

import json
from collections.abc import Iterable
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Mapping, NoReturn, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import (  # type: ignore[import-untyped]
    ValidationError,
    best_match,
)

from .. import data_path
from .embedded_schema import (
    EmbeddedSchemaContractError,
    validate_self_contained_schema,
)
from .exceptions import DeclarationSchemaError, FacetRegistrySchemaError
from .source import (
    DocumentPath,
    SourceMap,
    format_document_path,
    nearest_location,
)

SCHEMA_FILENAME = "declaration-v1.schema.json"
DECLARATION_KINDS = frozenset(
    {
        "rule-set",
        "rule",
        "procedure",
        "resolution-policy",
        "composition-manifest",
        "evaluator",
        "operation",
    }
)


def schema_path() -> Path:
    """Return the packaged path of declaration schema version 1."""
    return data_path() / "schemas" / SCHEMA_FILENAME


@lru_cache(maxsize=1)
def _declaration_schema() -> dict[str, object]:
    """Load and meta-validate the private schema used by validators."""
    schema = cast(
        dict[str, object], json.loads(schema_path().read_text(encoding="utf-8"))
    )
    Draft202012Validator.check_schema(schema)
    return schema


def declaration_schema() -> dict[str, object]:
    """Return an isolated copy of declaration schema version 1."""
    return deepcopy(_declaration_schema())


@lru_cache(maxsize=7)
def _validator_for_kind(kind: str) -> Draft202012Validator:
    """Return a discriminator-specific validator retaining shared definitions."""
    root = _declaration_schema()
    schema = {
        "$schema": root["$schema"],
        "$defs": root["$defs"],
        "$ref": f"#/$defs/{kind}",
    }
    return Draft202012Validator(schema)


@lru_cache(maxsize=1)
def _facet_registry_validator() -> Draft202012Validator:
    """Return the validator for the separate context-facet registry source."""
    root = _declaration_schema()
    schema = {
        "$schema": root["$schema"],
        "$defs": root["$defs"],
        "$ref": "#/$defs/facet-registry",
    }
    return Draft202012Validator(schema)


def validate_document(
    document: object,
    *,
    path: Path,
    locations: SourceMap | None = None,
) -> Mapping[str, object]:
    """Validate ``document`` and return its mapping representation.

    Raises
    ------
    DeclarationSchemaError
        If the document violates the normative JSON Schema.
    """
    source_map = locations or {}
    if not isinstance(document, dict):
        _raise_schema_error(path, (), "declaration must be a mapping", source_map)
    kind = document.get("kind")
    if not isinstance(kind, str) or kind not in DECLARATION_KINDS:
        _raise_schema_error(
            path,
            ("kind",),
            f"kind must be one of {sorted(DECLARATION_KINDS)!r}",
            source_map,
        )

    error = _actionable_schema_error(_validator_for_kind(kind).iter_errors(document))
    if error is not None:
        parts = _schema_error_parts(error, source_map)
        _raise_schema_error(path, parts, error.message, source_map)
    return cast(Mapping[str, object], document)


def validate_facet_registry_document(
    document: object,
    *,
    path: Path,
    locations: SourceMap | None = None,
) -> Mapping[str, object]:
    """Validate one canonical context-facet registry document.

    Raises
    ------
    FacetRegistrySchemaError
        If the document violates the normative registry schema.
    """
    source_map = locations or {}
    error = _actionable_schema_error(_facet_registry_validator().iter_errors(document))
    if error is not None:
        parts = _schema_error_parts(error, source_map)
        _raise_facet_registry_error(path, parts, error.message, source_map)
    return cast(Mapping[str, object], document)


def _schema_error_parts(error: ValidationError, locations: SourceMap) -> DocumentPath:
    """Return the most specific document path exposed by a schema error."""
    parts = tuple(error.absolute_path)
    schema_parts = tuple(error.absolute_schema_path)
    if "propertyNames" in schema_parts and isinstance(error.instance, str):
        parts += (error.instance,)
    if error.validator == "not" and isinstance(error.instance, dict):
        forbidden = error.schema.get("not", {}).get("required", [])
        if len(forbidden) == 1 and forbidden[0] in error.instance:
            parts += (forbidden[0],)
    unexpected = _unexpected_property(error, parts, locations)
    if unexpected is not None:
        parts += (unexpected,)
    return parts


def _actionable_schema_error(
    errors: Iterable[ValidationError],
) -> ValidationError | None:
    """Select the deepest concrete cause over composition wrapper errors."""
    candidates = list(errors)
    concrete = [
        error for error in candidates if error.validator != "unevaluatedProperties"
    ]
    selected = best_match(concrete or candidates)
    while (
        selected is not None
        and selected.context
        and selected.validator == "oneOf"
        and isinstance(selected.instance, Mapping)
        and "operator" in selected.instance
    ):
        selected = best_match(selected.context)
    return selected


def _unexpected_property(
    error: ValidationError,
    parts: DocumentPath,
    locations: SourceMap,
) -> str | None:
    """Return the first unexpected property in source order, when present."""
    if error.validator not in {"additionalProperties", "unevaluatedProperties"}:
        return None
    if not isinstance(error.instance, Mapping):
        return None
    admitted = _declared_properties(error.schema, _declaration_schema())
    names = [
        name
        for name in error.instance
        if isinstance(name, str) and name not in admitted
    ]
    if not names:
        return None

    def source_order(name: str) -> tuple[int, int, str]:
        location = locations.get(parts + (name,))
        if location is None:
            return (2**31, 2**31, name)
        return (location.line, location.column, name)

    return min(names, key=source_order)


def _declared_properties(
    schema: object,
    root: Mapping[str, object],
    seen_references: frozenset[str] = frozenset(),
) -> set[str]:
    """Return properties declared by one object schema and its compositions."""
    if not isinstance(schema, Mapping):
        return set()

    declared: set[str] = set()
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        declared.update(key for key in properties if isinstance(key, str))

    reference = schema.get("$ref")
    if isinstance(reference, str) and reference not in seen_references:
        referenced = _resolve_local_reference(reference, root)
        declared.update(
            _declared_properties(
                referenced,
                root,
                seen_references | frozenset({reference}),
            )
        )

    compositions = schema.get("allOf")
    if isinstance(compositions, list):
        for component in compositions:
            declared.update(_declared_properties(component, root, seen_references))
    return declared


def _resolve_local_reference(
    reference: str, root: Mapping[str, object]
) -> object | None:
    """Resolve a local JSON Pointer without interpreting external references."""
    if not reference.startswith("#/"):
        return None
    current: object = root
    for token in reference[2:].split("/"):
        if not isinstance(current, Mapping):
            return None
        decoded = token.replace("~1", "/").replace("~0", "~")
        if decoded not in current:
            return None
        current = current[decoded]
    return current


def validate_embedded_schema(
    schema: object,
    *,
    path: Path,
    document_path: DocumentPath,
    locations: SourceMap,
) -> None:
    """Validate one self-contained embedded Draft 2020-12 schema."""
    try:
        validate_self_contained_schema(schema)
    except EmbeddedSchemaContractError as exc:
        _raise_schema_error(path, document_path + exc.path, exc.message, locations)


def _raise_schema_error(
    path: Path,
    parts: DocumentPath,
    message: str,
    locations: SourceMap,
) -> NoReturn:
    """Raise a schema error at the closest known source position."""
    source = nearest_location(locations, parts)
    raise DeclarationSchemaError(
        path,
        format_document_path(parts),
        message,
        line=source.line if source else None,
        column=source.column if source else None,
    )


def _raise_facet_registry_error(
    path: Path,
    parts: DocumentPath,
    message: str,
    locations: SourceMap,
) -> NoReturn:
    """Raise a registry-schema error at the closest known source position."""
    source = nearest_location(locations, parts)
    raise FacetRegistrySchemaError(
        path,
        format_document_path(parts),
        message,
        line=source.line if source else None,
        column=source.column if source else None,
    )
