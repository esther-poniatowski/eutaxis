"""Load and apply the packaged normative declaration schema."""

from __future__ import annotations

import json
import re
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
from referencing import Registry, Resource

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
BASE_SCHEMA_FILENAME = "declaration-v1.base.schema.json"
FACET_SCHEMA_FILENAME = "context-facets-v1.schema.json"
FACET_BASE_SCHEMA_FILENAME = "context-facets-v1.base.schema.json"


def _contract_metadata(bound_filename: str) -> tuple[str, int, str]:
    """Read one logical binding and its base resource from packaged schemas."""
    bound_path = data_path() / "schemas" / bound_filename
    bound = json.loads(bound_path.read_text(encoding="utf-8"))
    try:
        logical_id = bound["properties"]["_schema"]["const"]
    except (KeyError, TypeError) as error:
        raise RuntimeError(f"invalid bound schema metadata in {bound_path}") from error
    if not isinstance(logical_id, str):
        raise RuntimeError(f"invalid bound schema metadata in {bound_path}")
    match = re.fullmatch(r"[a-z][a-z0-9-]*:[a-z][a-z0-9-]*@([1-9][0-9]*)", logical_id)
    if match is None:
        raise RuntimeError(f"invalid logical schema identifier {logical_id!r}")

    references: set[str] = set()

    def collect_references(value: object) -> None:
        if isinstance(value, dict):
            reference = value.get("$ref")
            if isinstance(reference, str) and ".base.schema.json" in reference:
                references.add(reference.partition("#")[0])
            for child in value.values():
                collect_references(child)
        elif isinstance(value, list):
            for child in value:
                collect_references(child)

    collect_references(bound)
    if len(references) != 1:
        raise RuntimeError(
            f"bound schema must reference one base resource in {bound_path}"
        )
    base_resource_id = references.pop()
    base_filename = Path(base_resource_id).name
    base_path = data_path() / "schemas" / base_filename
    base = json.loads(base_path.read_text(encoding="utf-8"))
    if base.get("$id") != base_resource_id:
        raise RuntimeError(
            f"bound schema base reference {base_resource_id!r} does not match "
            f"the packaged resource in {base_path}"
        )
    return logical_id, int(match.group(1)), base_resource_id


(
    DECLARATION_SCHEMA_ID,
    DECLARATION_SCHEMA_VERSION,
    DECLARATION_BASE_RESOURCE_ID,
) = _contract_metadata(SCHEMA_FILENAME)
FACET_SCHEMA_ID, FACET_SCHEMA_VERSION, FACET_BASE_RESOURCE_ID = _contract_metadata(
    FACET_SCHEMA_FILENAME
)
DECLARATION_KINDS = frozenset(
    {
        "rule-set",
        "rule",
        "procedure",
        "resolution-policy",
        "composition-manifest",
        "evaluator",
        "operation",
        "decision",
    }
)


def schema_path() -> Path:
    """Return the packaged path of declaration schema version 1."""
    return data_path() / "schemas" / SCHEMA_FILENAME


def base_schema_path() -> Path:
    """Return the packaged path of the unbound declaration base schema."""
    return data_path() / "schemas" / BASE_SCHEMA_FILENAME


def facet_schema_path() -> Path:
    """Return the packaged path of the bound context-facet contract."""
    return data_path() / "schemas" / FACET_SCHEMA_FILENAME


def facet_base_schema_path() -> Path:
    """Return the packaged path of the unbound context-facet base schema."""
    return data_path() / "schemas" / FACET_BASE_SCHEMA_FILENAME


@lru_cache(maxsize=1)
def _declaration_schema() -> dict[str, object]:
    """Load and meta-validate the private schema used by validators."""
    schema = cast(
        dict[str, object], json.loads(schema_path().read_text(encoding="utf-8"))
    )
    Draft202012Validator.check_schema(schema)
    return schema


def _load_schema(path: Path) -> dict[str, object]:
    """Load and meta-validate one packaged Draft 2020-12 schema."""
    schema = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    Draft202012Validator.check_schema(schema)
    return schema


@lru_cache(maxsize=1)
def _declaration_base_schema() -> dict[str, object]:
    """Load the unbound declaration base schema."""
    return _load_schema(base_schema_path())


@lru_cache(maxsize=1)
def _facet_schema() -> dict[str, object]:
    """Load the bound context-facet registry contract."""
    return _load_schema(facet_schema_path())


@lru_cache(maxsize=1)
def _facet_base_schema() -> dict[str, object]:
    """Load the unbound context-facet registry base schema."""
    return _load_schema(facet_base_schema_path())


@lru_cache(maxsize=1)
def _schema_registry() -> Registry[object]:
    """Return the offline resource registry shared by source validators."""
    schemas = (
        _declaration_base_schema(),
        _declaration_schema(),
        _facet_base_schema(),
        _facet_schema(),
    )
    return Registry().with_resources(
        (cast(str, schema["$id"]), Resource.from_contents(schema)) for schema in schemas
    )


def declaration_schema() -> dict[str, object]:
    """Return an isolated copy of declaration schema version 1."""
    return deepcopy(_declaration_schema())


@lru_cache(maxsize=8)
def _validator_for_kind(kind: str) -> Draft202012Validator:
    """Return a discriminator-specific validator retaining shared definitions."""
    root = deepcopy(_declaration_schema())
    all_of: list[dict[str, object]] = [
        {"$ref": f"{DECLARATION_BASE_RESOURCE_ID}#/$defs/{kind}"}
    ]
    if kind == "rule-set":
        alternatives = cast(list[dict[str, object]], root["oneOf"])
        rule_set_layers = cast(list[dict[str, object]], alternatives[0]["allOf"])
        all_of.append(rule_set_layers[1])
    schema = {
        "$schema": root["$schema"],
        "type": root["type"],
        "required": root["required"],
        "properties": root["properties"],
        "allOf": all_of,
        "$defs": root["$defs"],
        "unevaluatedProperties": root["unevaluatedProperties"],
    }
    return Draft202012Validator(schema, registry=_schema_registry())


@lru_cache(maxsize=1)
def _facet_registry_validator() -> Draft202012Validator:
    """Return the validator for the separate context-facet registry source."""
    return Draft202012Validator(_facet_schema(), registry=_schema_registry())


@lru_cache(maxsize=2)
def _validator_for_definition(name: str) -> Draft202012Validator:
    """Return one validator for a retained normative declaration fragment."""
    if name not in {"applicability", "closed-object-schema"}:
        raise ValueError(f"unsupported declaration definition: {name!r}")
    root = _declaration_base_schema()
    return Draft202012Validator(
        {
            "$schema": root["$schema"],
            "$defs": root["$defs"],
            "$ref": f"#/$defs/{name}",
        }
    )


def validate_declaration_definition(
    name: str, instance: object
) -> ValidationError | None:
    """Return the most relevant violation of one retained source contract."""
    return _actionable_schema_error(
        _validator_for_definition(name).iter_errors(_plain_instance(instance))
    )


def _plain_instance(value: object) -> object:
    """Convert one frozen JSON value into containers recognized by jsonschema."""
    if isinstance(value, Mapping):
        return {key: _plain_instance(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_instance(item) for item in value]
    return value


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
    _require_first_schema_key(
        document,
        path=path,
        locations=source_map,
        expected=DECLARATION_SCHEMA_ID,
        facet_registry=False,
    )
    kind = document.get("kind")
    if not isinstance(kind, str) or kind not in DECLARATION_KINDS:
        _raise_schema_error(
            path,
            ("kind",),
            f"kind must be one of {sorted(DECLARATION_KINDS)!r}",
            source_map,
        )
    if kind == "rule-set":
        rules = document.get("rules")
        if isinstance(rules, list):
            for index, rule in enumerate(rules):
                if isinstance(rule, dict):
                    _require_first_schema_key(
                        rule,
                        path=path,
                        locations=source_map,
                        expected=DECLARATION_SCHEMA_ID,
                        facet_registry=False,
                        root=("rules", index),
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
    if isinstance(document, dict):
        _require_first_schema_key(
            document,
            path=path,
            locations=source_map,
            expected=FACET_SCHEMA_ID,
            facet_registry=True,
        )
    error = _actionable_schema_error(_facet_registry_validator().iter_errors(document))
    if error is not None:
        parts = _schema_error_parts(error, source_map)
        _raise_facet_registry_error(path, parts, error.message, source_map)
    return cast(Mapping[str, object], document)


def _require_first_schema_key(
    document: Mapping[str, object],
    *,
    path: Path,
    locations: SourceMap,
    expected: str,
    facet_registry: bool,
    root: DocumentPath = (),
) -> None:
    """Require the portable contract binding as the first authored key."""
    first = next(iter(document), None)
    if first == "_schema" and document.get("_schema") == expected:
        return
    message = f"_schema must be the first key and equal {expected!r}"
    parts = root + (("_schema",) if "_schema" in document else ())
    if facet_registry:
        _raise_facet_registry_error(path, parts, message, locations)
    _raise_schema_error(path, parts, message, locations)


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
    admitted = _declared_properties(error.schema, _declaration_base_schema())
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
    """Resolve a local pointer or one reference to a packaged base schema."""
    if reference.startswith(f"{DECLARATION_BASE_RESOURCE_ID}#/"):
        root = _declaration_base_schema()
        reference = reference.removeprefix(DECLARATION_BASE_RESOURCE_ID)
    facet_base_id = cast(str, _facet_base_schema()["$id"])
    if reference.startswith(f"{facet_base_id}#/"):
        root = _facet_base_schema()
        reference = reference.removeprefix(facet_base_id)
    if reference == DECLARATION_BASE_RESOURCE_ID:
        return _declaration_base_schema()
    if reference == facet_base_id:
        return _facet_base_schema()
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
