"""Evaluate bounded declaration applicability predicates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Literal, Mapping, TypeAlias

from .facets import FacetRegistry
from .models import JsonValue, freeze_json, json_values_equal


class TruthValue(StrEnum):
    """Values of the strong-Kleene applicability logic."""

    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


PredicatePath: TypeAlias = tuple[str | int, ...]


@dataclass(frozen=True, init=False)
class AtomicApplicabilityTrace:
    """One evaluated atomic predicate in a normalized predicate tree."""

    predicate_path: PredicatePath
    operator: Literal["exists", "equals", "in"]
    facet: str
    result: TruthValue
    observed_present: bool
    observed: JsonValue
    expected: JsonValue

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Reject construction outside applicability evaluation."""
        raise TypeError(
            "AtomicApplicabilityTrace instances must be issued by applicability evaluation"
        )


@dataclass(frozen=True, init=False)
class BooleanApplicabilityTrace:
    """One evaluated Boolean node and its ordered child traces."""

    predicate_path: PredicatePath
    operator: Literal["all", "any", "not"]
    result: TruthValue
    children: tuple["ApplicabilityTrace", ...]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Reject construction outside applicability evaluation."""
        raise TypeError(
            "BooleanApplicabilityTrace instances must be issued by applicability evaluation"
        )


ApplicabilityTrace: TypeAlias = AtomicApplicabilityTrace | BooleanApplicabilityTrace


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

    Before applying missing-facet semantics, both evaluator interfaces reject
    an unsupported operator, a non-sequence ``in`` operand, or a comparison
    operand that is not JSON. Canonical source loading owns complete predicate
    schema validation.
    """
    return evaluate_applicability_with_trace(predicate, context, facets).result


def evaluate_applicability_with_trace(
    predicate: Mapping[str, object],
    context: Mapping[str, object],
    facets: FacetRegistry,
) -> ApplicabilityTrace:
    """Evaluate one predicate and retain its complete predicate-tree trace.

    The trace retains values for referenced facets. Callers must apply a
    disclosure policy before logging or serializing it.

    Before applying missing-facet semantics, both evaluator interfaces reject
    an unsupported operator, a non-sequence ``in`` operand, or a comparison
    operand that is not JSON. Canonical source loading owns complete predicate
    schema validation.
    """
    validated_context = facets.validate_context(context)
    return _evaluate_applicability(predicate, validated_context, ())


def _evaluate_applicability(
    predicate: Mapping[str, object],
    context: Mapping[str, JsonValue],
    path: PredicatePath,
) -> ApplicabilityTrace:
    """Evaluate one predicate under an already validated context."""
    if "all" in predicate:
        children = _children(predicate["all"], context, path, "all")
        values = tuple(child.result for child in children)
        if TruthValue.FALSE in values:
            result = TruthValue.FALSE
        elif all(value is TruthValue.TRUE for value in values):
            result = TruthValue.TRUE
        else:
            result = TruthValue.UNKNOWN
        return _issue_boolean_trace(path, "all", result, children)
    if "any" in predicate:
        children = _children(predicate["any"], context, path, "any")
        values = tuple(child.result for child in children)
        if TruthValue.TRUE in values:
            result = TruthValue.TRUE
        elif all(value is TruthValue.FALSE for value in values):
            result = TruthValue.FALSE
        else:
            result = TruthValue.UNKNOWN
        return _issue_boolean_trace(path, "any", result, children)
    if "not" in predicate:
        child = predicate["not"]
        if not isinstance(child, Mapping):
            raise ValueError("applicability 'not' must contain a predicate")
        child_trace = _evaluate_applicability(child, context, path + ("not",))
        if child_trace.result is TruthValue.UNKNOWN:
            result = TruthValue.UNKNOWN
        elif child_trace.result is TruthValue.TRUE:
            result = TruthValue.FALSE
        else:
            result = TruthValue.TRUE
        return _issue_boolean_trace(path, "not", result, (child_trace,))

    facet = predicate.get("facet")
    operator = predicate.get("operator")
    if not isinstance(facet, str) or not isinstance(operator, str):
        raise ValueError("atomic applicability requires facet and operator")
    if operator not in {"exists", "equals", "in"}:
        raise ValueError(f"unsupported applicability operator: {operator!r}")
    observed_present = facet in context
    observed = context[facet] if observed_present else None
    if operator == "exists":
        result = TruthValue.TRUE if observed_present else TruthValue.FALSE
        return _issue_atomic_trace(
            path, "exists", facet, result, observed_present, observed, None
        )
    if operator == "equals":
        expected = freeze_json(predicate.get("value"))
        result = (
            TruthValue.TRUE
            if observed_present and json_values_equal(observed, expected)
            else TruthValue.FALSE
        )
        if not observed_present:
            result = TruthValue.UNKNOWN
        return _issue_atomic_trace(
            path, "equals", facet, result, observed_present, observed, expected
        )
    candidates = predicate.get("value")
    if not isinstance(candidates, (list, tuple)):
        raise ValueError("applicability 'in' requires a sequence value")
    expected = freeze_json(candidates)
    assert isinstance(expected, tuple)
    result = (
        TruthValue.TRUE
        if observed_present
        and any(json_values_equal(observed, item) for item in expected)
        else TruthValue.FALSE
    )
    if not observed_present:
        result = TruthValue.UNKNOWN
    return _issue_atomic_trace(
        path, "in", facet, result, observed_present, observed, expected
    )


def _issue_atomic_trace(
    path: PredicatePath,
    operator: Literal["exists", "equals", "in"],
    facet: str,
    result: TruthValue,
    observed_present: bool,
    observed: JsonValue,
    expected: JsonValue,
) -> AtomicApplicabilityTrace:
    """Issue one evaluator-owned atomic trace node."""
    trace = object.__new__(AtomicApplicabilityTrace)
    object.__setattr__(trace, "predicate_path", path)
    object.__setattr__(trace, "operator", operator)
    object.__setattr__(trace, "facet", facet)
    object.__setattr__(trace, "result", result)
    object.__setattr__(trace, "observed_present", observed_present)
    object.__setattr__(trace, "observed", observed)
    object.__setattr__(trace, "expected", expected)
    return trace


def _issue_boolean_trace(
    path: PredicatePath,
    operator: Literal["all", "any", "not"],
    result: TruthValue,
    children: tuple[ApplicabilityTrace, ...],
) -> BooleanApplicabilityTrace:
    """Issue one evaluator-owned Boolean trace node."""
    trace = object.__new__(BooleanApplicabilityTrace)
    object.__setattr__(trace, "predicate_path", path)
    object.__setattr__(trace, "operator", operator)
    object.__setattr__(trace, "result", result)
    object.__setattr__(trace, "children", children)
    return trace


def _children(
    value: object,
    context: Mapping[str, JsonValue],
    path: PredicatePath,
    operator: Literal["all", "any"],
) -> tuple[ApplicabilityTrace, ...]:
    """Evaluate the ordered non-empty children of one Boolean node."""
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("applicability boolean node requires children")
    predicates: list[Mapping[str, object]] = []
    for child in value:
        if not isinstance(child, Mapping):
            raise ValueError("applicability child must be a predicate")
        predicates.append(child)
    return tuple(
        _evaluate_applicability(child, context, path + (operator, index))
        for index, child in enumerate(predicates)
    )
