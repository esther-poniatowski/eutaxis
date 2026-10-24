"""Evaluate bounded declaration applicability predicates."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class TruthValue(StrEnum):
    """Values of the strong-Kleene applicability logic."""

    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


def conjoin_applicability(
    parent: Mapping[str, object], child: Mapping[str, object]
) -> Mapping[str, object]:
    """Narrow ``parent`` structurally with the local ``child`` predicate."""
    return MappingProxyType({"all": (parent, child)})


def evaluate_applicability(
    predicate: Mapping[str, object], context: Mapping[str, object]
) -> TruthValue:
    """Evaluate a normalized applicability predicate under ``context``.

    Missing facets yield ``unknown`` for comparisons and ``false`` for
    ``exists``. Boolean nodes follow strong-Kleene truth tables.
    """
    if "all" in predicate:
        values = _children(predicate["all"], context)
        if TruthValue.FALSE in values:
            return TruthValue.FALSE
        if all(value is TruthValue.TRUE for value in values):
            return TruthValue.TRUE
        return TruthValue.UNKNOWN
    if "any" in predicate:
        values = _children(predicate["any"], context)
        if TruthValue.TRUE in values:
            return TruthValue.TRUE
        if all(value is TruthValue.FALSE for value in values):
            return TruthValue.FALSE
        return TruthValue.UNKNOWN
    if "not" in predicate:
        child = predicate["not"]
        if not isinstance(child, Mapping):
            raise ValueError("applicability 'not' must contain a predicate")
        value = evaluate_applicability(child, context)
        if value is TruthValue.UNKNOWN:
            return value
        return TruthValue.FALSE if value is TruthValue.TRUE else TruthValue.TRUE

    facet = predicate.get("facet")
    operator = predicate.get("operator")
    if not isinstance(facet, str) or not isinstance(operator, str):
        raise ValueError("atomic applicability requires facet and operator")
    if operator == "exists":
        return TruthValue.TRUE if facet in context else TruthValue.FALSE
    if facet not in context:
        return TruthValue.UNKNOWN
    if operator == "equals":
        return (
            TruthValue.TRUE
            if _json_equal(context[facet], predicate.get("value"))
            else TruthValue.FALSE
        )
    if operator == "in":
        candidates = predicate.get("value")
        if not isinstance(candidates, (list, tuple)):
            raise ValueError("applicability 'in' requires a sequence value")
        return (
            TruthValue.TRUE
            if any(_json_equal(context[facet], item) for item in candidates)
            else TruthValue.FALSE
        )
    raise ValueError(f"unsupported applicability operator: {operator!r}")


def _children(value: object, context: Mapping[str, object]) -> tuple[TruthValue, ...]:
    """Evaluate the non-empty child sequence of a boolean node."""
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("applicability boolean node requires children")
    predicates: list[Mapping[str, object]] = []
    for child in value:
        if not isinstance(child, Mapping):
            raise ValueError("applicability child must be a predicate")
        predicates.append(child)
    return tuple(evaluate_applicability(child, context) for child in predicates)


def _json_equal(left: object, right: object) -> bool:
    """Compare JSON values without Python's Boolean-number coercion."""
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return left.keys() == right.keys() and all(
            _json_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            _json_equal(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    if type(left) is not type(right):
        return False
    return left == right
