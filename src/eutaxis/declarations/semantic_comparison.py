"""Compare the complete typed semantics of two acquired declaration corpora."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum, StrEnum
from types import MappingProxyType
from typing import cast

from .external_result import (
    ExternalAcquisitionResult,
    _ExternalAcquisitionResultState,
    _issued_external_result_state,
)
from .models import (
    AnyDeclaration,
    JsonValue,
    RuleSetDeclaration,
    json_values_equal,
)
from .registry import DeclarationRegistry

SemanticPath = tuple[str | int, ...]


class SemanticObjectKind(StrEnum):
    """Kinds of semantic object compared across acquired corpora."""

    DECLARATION = "declaration"
    FACET = "facet"


class SemanticChangeKind(StrEnum):
    """Relations between one baseline object and one candidate object."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


@dataclass(frozen=True)
class SemanticObjectKey:
    """Identify one declaration, exact contract, or context facet."""

    object_kind: SemanticObjectKind
    id: str
    version: int | None = None


@dataclass(frozen=True)
class SemanticDifference:
    """Retain one complete object difference and its changed field paths."""

    key: SemanticObjectKey
    change: SemanticChangeKind
    paths: tuple[SemanticPath, ...]
    baseline: Mapping[str, JsonValue] | None
    candidate: Mapping[str, JsonValue] | None


@dataclass(frozen=True)
class SemanticComparison:
    """Retain the deterministic semantic differences between two corpora."""

    differences: tuple[SemanticDifference, ...]

    @property
    def equivalent(self) -> bool:
        """Return whether the corpora have identical typed semantics."""
        return not self.differences


def compare_external_declarations(
    baseline: ExternalAcquisitionResult,
    candidate: ExternalAcquisitionResult,
) -> SemanticComparison:
    """Compare two issued corpora without treating transport as semantics."""
    baseline_state = _issued_external_result_state(baseline)
    candidate_state = _issued_external_result_state(candidate)
    baseline_objects = _semantic_objects(baseline_state)
    candidate_objects = _semantic_objects(candidate_state)
    differences: list[SemanticDifference] = []
    for key in sorted(
        baseline_objects.keys() | candidate_objects.keys(),
        key=_key_order,
    ):
        baseline_value = baseline_objects.get(key)
        candidate_value = candidate_objects.get(key)
        if baseline_value is None:
            differences.append(
                SemanticDifference(
                    key=key,
                    change=SemanticChangeKind.ADDED,
                    paths=((),),
                    baseline=None,
                    candidate=candidate_value,
                )
            )
        elif candidate_value is None:
            differences.append(
                SemanticDifference(
                    key=key,
                    change=SemanticChangeKind.REMOVED,
                    paths=((),),
                    baseline=baseline_value,
                    candidate=None,
                )
            )
        else:
            changed_paths = _changed_paths(baseline_value, candidate_value)
            if changed_paths:
                differences.append(
                    SemanticDifference(
                        key=key,
                        change=SemanticChangeKind.MODIFIED,
                        paths=changed_paths,
                        baseline=baseline_value,
                        candidate=candidate_value,
                    )
                )

    _require_unchanged_authority(baseline, baseline_state)
    _require_unchanged_authority(candidate, candidate_state)
    return SemanticComparison(tuple(differences))


def _semantic_objects(
    state: _ExternalAcquisitionResultState,
) -> Mapping[SemanticObjectKey, Mapping[str, JsonValue]]:
    """Project all semantic objects from one authenticated acquisition state."""
    registry = state.external_registry_state.registry
    objects = _declaration_objects(registry)
    facets = state.stage_state.composite
    for identifier, facet in facets.facets.items():
        authority = facets.authority_for(identifier)
        key = SemanticObjectKey(SemanticObjectKind.FACET, identifier)
        objects[key] = _freeze_mapping(
            {
                "schema_version": authority.schema_version,
                "registry": authority.id,
                "owner": authority.owner,
                "value_schema": facet.value_schema,
            }
        )
    return MappingProxyType(objects)


def _declaration_objects(
    registry: DeclarationRegistry,
) -> dict[SemanticObjectKey, Mapping[str, JsonValue]]:
    """Project every unversioned declaration and exact contract."""
    objects: dict[SemanticObjectKey, Mapping[str, JsonValue]] = {}
    for identifier, record in registry.records.items():
        key = SemanticObjectKey(SemanticObjectKind.DECLARATION, identifier)
        objects[key] = _declaration_semantics(record.declaration)
    for identifier, family in registry.families.items():
        for version, record in family.versions.items():
            key = SemanticObjectKey(
                SemanticObjectKind.DECLARATION,
                identifier,
                version,
            )
            objects[key] = _declaration_semantics(record.declaration)
    return objects


def _declaration_semantics(
    declaration: AnyDeclaration,
) -> Mapping[str, JsonValue]:
    """Project one declaration while excluding source and transport metadata."""
    result: dict[str, JsonValue] = {}
    for field in fields(declaration):
        if field.name in {"document", "source_revision"}:
            continue
        value = getattr(declaration, field.name)
        if isinstance(declaration, RuleSetDeclaration) and field.name == "rules":
            result["rules"] = tuple(rule.id for rule in declaration.rules)
            continue
        result[field.name] = _semantic_value(value)
    return MappingProxyType(result)


def _semantic_value(value: object) -> JsonValue:
    """Convert one typed model value to a stable immutable JSON value."""
    if isinstance(value, Enum):
        return cast(str, value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return MappingProxyType(
            {
                field.name: _semantic_value(getattr(value, field.name))
                for field in fields(value)
            }
        )
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _semantic_value(value[key])
                for key in sorted(value, key=str)
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(_semantic_value(item) for item in value)
    if value is None or type(value) in {bool, int, float, str}:
        return cast(bool | int | float | str | None, value)
    raise TypeError(f"Unsupported semantic value: {type(value).__name__}")


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, JsonValue]:
    """Freeze one string-keyed semantic mapping in lexical key order."""
    return MappingProxyType(
        {key: _semantic_value(value[key]) for key in sorted(value)}
    )


def _changed_paths(
    baseline: JsonValue,
    candidate: JsonValue,
    path: SemanticPath = (),
) -> tuple[SemanticPath, ...]:
    """Return the minimal deterministic paths whose values differ."""
    if isinstance(baseline, Mapping) and isinstance(candidate, Mapping):
        changed: list[SemanticPath] = []
        for key in sorted(baseline.keys() | candidate.keys()):
            if key not in baseline or key not in candidate:
                changed.append((*path, key))
            else:
                changed.extend(
                    _changed_paths(baseline[key], candidate[key], (*path, key))
                )
        return tuple(changed)
    if isinstance(baseline, tuple) and isinstance(candidate, tuple):
        changed = []
        common = min(len(baseline), len(candidate))
        for index in range(common):
            changed.extend(
                _changed_paths(
                    baseline[index],
                    candidate[index],
                    (*path, index),
                )
            )
        changed.extend(
            (*path, index)
            for index in range(common, max(len(baseline), len(candidate)))
        )
        return tuple(changed)
    return () if json_values_equal(baseline, candidate) else (path,)


def _key_order(key: SemanticObjectKey) -> tuple[str, str, int, int]:
    """Return the canonical order for mixed semantic object keys."""
    return (
        key.object_kind.value,
        key.id,
        0 if key.version is None else 1,
        0 if key.version is None else key.version,
    )


def _require_unchanged_authority(
    result: ExternalAcquisitionResult,
    state: _ExternalAcquisitionResultState,
) -> None:
    """Reject a result whose authenticated state changed during comparison."""
    if _issued_external_result_state(result) is not state:
        raise AssertionError("external acquisition state changed during comparison")
