"""Load context-facet registries and validate typed applicability inputs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, NoReturn, cast

from .. import data_path
from .embedded_schema import (
    EmbeddedSchemaContractError,
    validate_json_instance,
    validate_self_contained_schema,
)
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
    load_yaml_bytes,
    load_yaml_document,
    nearest_location,
)

FACET_REGISTRY_FILENAME = "context-facets-v1.yaml"


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
            try:
                validate_self_contained_schema(facet.value_schema)
            except EmbeddedSchemaContractError as exc:
                raise FacetContextError(
                    facet_id, f"registered schema is invalid: {exc.message}"
                ) from exc
            error = validate_json_instance(facet.value_schema, value)
            if error is not None:
                raise FacetContextError(facet_id, error.message)
            validated[facet_id] = freeze_json(value)
        return MappingProxyType(validated)


@dataclass(frozen=True)
class ApplicabilityFacetViolation:
    """Describe one retained applicability value rejected by its facet registry."""

    path: DocumentPath
    message: str


def validate_applicability_expression(
    predicate: Mapping[str, object], registry: FacetRegistry
) -> ApplicabilityFacetViolation | None:
    """Validate one structurally valid applicability tree against ``registry``."""
    for boolean_operator in ("all", "any"):
        if boolean_operator in predicate:
            for index, child in enumerate(
                cast(tuple[object, ...], predicate[boolean_operator])
            ):
                violation = validate_applicability_expression(
                    cast(Mapping[str, object], child), registry
                )
                if violation is not None:
                    return ApplicabilityFacetViolation(
                        (boolean_operator, index, *violation.path), violation.message
                    )
            return None
    if "not" in predicate:
        violation = validate_applicability_expression(
            cast(Mapping[str, object], predicate["not"]), registry
        )
        if violation is None:
            return None
        return ApplicabilityFacetViolation(("not", *violation.path), violation.message)

    facet_id = cast(str, predicate["facet"])
    facet = registry.facets.get(facet_id)
    if facet is None:
        return ApplicabilityFacetViolation(
            ("facet",), f"facet {facet_id!r} is not registered in {registry.id!r}"
        )
    operator = predicate["operator"]
    if operator == "exists":
        return None
    values = (
        (predicate["value"],)
        if operator == "equals"
        else cast(tuple[object, ...], predicate["value"])
    )
    for index, value in enumerate(values):
        error = validate_json_instance(facet.value_schema, value)
        if error is not None:
            prefix: DocumentPath = (
                ("value",) if operator == "equals" else ("value", index)
            )
            return ApplicabilityFacetViolation(
                (*prefix, *error.absolute_path),
                f"value for facet {facet.id!r} is invalid: {error.message}",
            )
    return None


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
    document, locations, _source_sha256 = load_yaml_document(
        path, error_type=FacetRegistrySchemaError
    )
    return _facet_registry_from_document(document, path=path, locations=locations)


def load_facet_registry_bytes(source: bytes, *, path: Path) -> FacetRegistry:
    """Load one facet registry from already-retained exact bytes."""
    document, locations, _source_sha256 = load_yaml_bytes(
        source,
        path=path,
        error_type=FacetRegistrySchemaError,
    )
    return _facet_registry_from_document(document, path=path, locations=locations)


def _facet_registry_from_document(
    document: object,
    *,
    path: Path,
    locations: SourceMap,
) -> FacetRegistry:
    """Validate and detach one parsed facet-registry document."""
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
    violation = validate_applicability_expression(predicate, registry)
    if violation is not None:
        _raise_declaration_semantic(
            path,
            (*parts, *violation.path),
            violation.message,
            locations,
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
    error = validate_json_instance(facet.value_schema, value)
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
        validate_self_contained_schema(schema)
    except EmbeddedSchemaContractError as exc:
        _raise_registry_semantic(
            path,
            parts + exc.path,
            exc.message,
            locations,
        )


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
