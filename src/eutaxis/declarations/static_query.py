"""Define exact, non-semantic predicates for static catalog fields."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from .models import (
    DeclarationKind,
    JsonValue,
    RuleAxis,
    freeze_json,
    json_values_equal,
)


class StaticField(StrEnum):
    """Fields that a static catalog can compare without semantic inference."""

    OWNER = "owner"
    KIND = "kind"
    AXIS = "axis"
    FAILURE_MODE = "failure-mode"
    REQUIRED_VISIBILITY = "required-visibility"
    APPLICABILITY = "applicability"


@dataclass(frozen=True)
class StaticPredicate:
    """One exact comparison against a field stored in a catalog row."""

    field: StaticField
    value: object

    def __post_init__(self) -> None:
        """Normalize enum values and reject values outside the field domain."""
        if not isinstance(self.field, StaticField):
            raise TypeError("field must be a StaticField")
        value: object = self.value
        if self.field is StaticField.KIND and isinstance(value, DeclarationKind):
            value = value.value
        if self.field is StaticField.AXIS and isinstance(value, RuleAxis):
            value = value.value
        frozen = freeze_json(value)
        _validate_value(self.field, frozen)
        object.__setattr__(self, "value", frozen)


@dataclass(frozen=True)
class StaticCatalogQuery:
    """An immutable conjunction of distinct exact field predicates."""

    predicates: tuple[StaticPredicate, ...] = ()

    def __post_init__(self) -> None:
        """Copy the predicate sequence and reject duplicate fields."""
        predicates = tuple(self.predicates)
        if any(not isinstance(predicate, StaticPredicate) for predicate in predicates):
            raise TypeError("predicates must contain only StaticPredicate values")
        fields = [predicate.field for predicate in predicates]
        if len(fields) != len(set(fields)):
            raise ValueError("static query fields must be unique")
        object.__setattr__(self, "predicates", predicates)


def matches_static_query(
    query: StaticCatalogQuery,
    *,
    owner: str,
    kind: DeclarationKind,
    applicability: Mapping[str, JsonValue],
    query_fields: Mapping[str, object],
) -> bool:
    """Return whether stored fields satisfy every exact query predicate."""
    for predicate in query.predicates:
        if predicate.field is StaticField.OWNER:
            candidate: object = owner
        elif predicate.field is StaticField.KIND:
            candidate = kind.value
        elif predicate.field is StaticField.APPLICABILITY:
            candidate = applicability
        else:
            if predicate.field.value not in query_fields:
                return False
            candidate = query_fields[predicate.field.value]
        if not json_values_equal(candidate, predicate.value):
            return False
    return True


def _validate_value(field: StaticField, value: JsonValue) -> None:
    """Validate one normalized predicate value against its field domain."""
    if field is StaticField.OWNER:
        if (
            not isinstance(value, str)
            or not value
            or any(char.isspace() for char in value)
        ):
            raise ValueError("owner must be a nonempty string without whitespace")
        return
    if field is StaticField.KIND:
        if not isinstance(value, str) or value not in {
            kind.value for kind in DeclarationKind
        }:
            raise ValueError("kind must name a declaration kind")
        return
    if field is StaticField.AXIS:
        if not isinstance(value, str) or value not in {axis.value for axis in RuleAxis}:
            raise ValueError("axis must name a rule axis")
        return
    if field is StaticField.FAILURE_MODE:
        if not isinstance(value, str) or value not in {"silent", "visible"}:
            raise ValueError("failure-mode must be 'silent' or 'visible'")
        return
    if field is StaticField.REQUIRED_VISIBILITY:
        if value is not None and (
            not isinstance(value, str) or value not in {"pre-invocation", "pre-action"}
        ):
            raise ValueError(
                "required-visibility must be null, 'pre-invocation', or 'pre-action'"
            )
        return
    if not isinstance(value, Mapping):
        raise ValueError("applicability must be a JSON object")
