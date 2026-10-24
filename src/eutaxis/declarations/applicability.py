"""Evaluate bounded declaration applicability predicates."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from .facets import FacetRegistry
from .models import json_values_equal


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
    predicate: Mapping[str, object],
    context: Mapping[str, object],
    facets: FacetRegistry,
) -> TruthValue:
    """Validate ``context`` and evaluate one normalized predicate.

    Missing facets yield ``unknown`` for comparisons and ``false`` for
    ``exists``. Boolean nodes follow strong-Kleene truth tables.
    """
    return _evaluate_applicability(predicate, facets.validate_context(context))


def _evaluate_applicability(
    predicate: Mapping[str, object], context: Mapping[str, object]
) -> TruthValue:
    """Evaluate one predicate under an already validated context."""
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
        value = _evaluate_applicability(child, context)
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
            if json_values_equal(context[facet], predicate.get("value"))
            else TruthValue.FALSE
        )
    if operator == "in":
        candidates = predicate.get("value")
        if not isinstance(candidates, (list, tuple)):
            raise ValueError("applicability 'in' requires a sequence value")
        return (
            TruthValue.TRUE
            if any(json_values_equal(context[facet], item) for item in candidates)
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
    return tuple(_evaluate_applicability(child, context) for child in predicates)
