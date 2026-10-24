"""Tests for complete immutable applicability predicate-tree traces."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Mapping, cast

import pytest

from eutaxis.declarations import (
    AtomicApplicabilityTrace,
    BooleanApplicabilityTrace,
    FacetContextError,
    FacetRegistry,
    TruthValue,
    evaluate_applicability,
    evaluate_applicability_with_trace,
    load_facet_registry,
)

FACETS = load_facet_registry(
    Path(__file__).parent / "fixtures" / "facets" / "valid" / "context-facets.yaml"
)
CONTEXT = {"a": True}
ATOMS = {
    TruthValue.TRUE: {"facet": "a", "operator": "equals", "value": True},
    TruthValue.FALSE: {"facet": "a", "operator": "equals", "value": False},
    TruthValue.UNKNOWN: {"facet": "b", "operator": "equals", "value": True},
}


@pytest.mark.parametrize("operator", ["all", "any"])
@pytest.mark.parametrize("left", tuple(TruthValue))
@pytest.mark.parametrize("right", tuple(TruthValue))
def test_boolean_trace_covers_the_complete_two_child_truth_tables(
    operator: str, left: TruthValue, right: TruthValue
) -> None:
    predicate = {operator: [ATOMS[left], ATOMS[right]]}
    expected = _boolean_result(operator, left, right)

    trace = evaluate_applicability_with_trace(predicate, CONTEXT, FACETS)

    assert isinstance(trace, BooleanApplicabilityTrace)
    assert trace.result is expected
    assert tuple(child.result for child in trace.children) == (left, right)
    assert evaluate_applicability(predicate, CONTEXT, FACETS) is expected


@pytest.mark.parametrize(
    ("child_result", "expected"),
    [
        (TruthValue.TRUE, TruthValue.FALSE),
        (TruthValue.FALSE, TruthValue.TRUE),
        (TruthValue.UNKNOWN, TruthValue.UNKNOWN),
    ],
)
def test_not_trace_covers_all_three_truth_values(
    child_result: TruthValue, expected: TruthValue
) -> None:
    predicate = {"not": ATOMS[child_result]}

    trace = evaluate_applicability_with_trace(predicate, CONTEXT, FACETS)

    assert isinstance(trace, BooleanApplicabilityTrace)
    assert trace.result is expected
    assert trace.children[0].result is child_result
    assert evaluate_applicability(predicate, CONTEXT, FACETS) is expected


@pytest.mark.parametrize(
    ("predicate", "context", "expected"),
    [
        (
            {"facet": "sample.null", "operator": "exists"},
            {},
            TruthValue.FALSE,
        ),
        (
            {"facet": "sample.null", "operator": "exists"},
            {"sample.null": None},
            TruthValue.TRUE,
        ),
        (
            {"facet": "a", "operator": "exists"},
            {"a": True},
            TruthValue.TRUE,
        ),
        (
            {"facet": "a", "operator": "equals", "value": True},
            {"a": True},
            TruthValue.TRUE,
        ),
        (
            {"facet": "a", "operator": "equals", "value": False},
            {"a": True},
            TruthValue.FALSE,
        ),
        (
            {"facet": "a", "operator": "equals", "value": True},
            {},
            TruthValue.UNKNOWN,
        ),
        (
            {"facet": "request.mode", "operator": "in", "value": ["a", "b"]},
            {"request.mode": "a"},
            TruthValue.TRUE,
        ),
        (
            {"facet": "request.mode", "operator": "in", "value": ["a", "b"]},
            {"request.mode": "c"},
            TruthValue.FALSE,
        ),
        (
            {"facet": "request.mode", "operator": "in", "value": ["a", "b"]},
            {},
            TruthValue.UNKNOWN,
        ),
    ],
)
def test_atomic_trace_covers_presence_comparison_and_membership(
    predicate: dict[str, object], context: dict[str, object], expected: TruthValue
) -> None:
    trace = evaluate_applicability_with_trace(predicate, context, FACETS)

    assert isinstance(trace, AtomicApplicabilityTrace)
    assert trace.result is expected
    assert evaluate_applicability(predicate, context, FACETS) is expected


def test_missing_and_present_null_are_distinct_trace_facts() -> None:
    predicate = {"facet": "sample.null", "operator": "exists"}

    missing = evaluate_applicability_with_trace(predicate, {}, FACETS)
    present = evaluate_applicability_with_trace(
        predicate, {"sample.null": None}, FACETS
    )

    assert isinstance(missing, AtomicApplicabilityTrace)
    assert isinstance(present, AtomicApplicabilityTrace)
    assert (missing.observed_present, missing.observed) == (False, None)
    assert (present.observed_present, present.observed) == (True, None)


def test_atomic_trace_expected_value_conventions_are_explicit() -> None:
    exists = evaluate_applicability_with_trace(
        {"facet": "sample.null", "operator": "exists"},
        {"sample.null": None},
        FACETS,
    )
    equals_null = evaluate_applicability_with_trace(
        {"facet": "sample.null", "operator": "equals", "value": None},
        {"sample.null": None},
        FACETS,
    )
    membership = evaluate_applicability_with_trace(
        {"facet": "request.mode", "operator": "in", "value": ["a", "b"]},
        {"request.mode": "a"},
        FACETS,
    )

    assert isinstance(exists, AtomicApplicabilityTrace)
    assert isinstance(equals_null, AtomicApplicabilityTrace)
    assert isinstance(membership, AtomicApplicabilityTrace)
    assert (exists.observed_present, exists.observed, exists.expected) == (
        True,
        None,
        None,
    )
    assert (equals_null.observed_present, equals_null.observed) == (True, None)
    assert equals_null.expected is None
    assert membership.expected == ("a", "b")


@pytest.mark.parametrize(
    ("predicate", "context", "expected"),
    [
        (
            {
                "facet": "request.payload",
                "operator": "equals",
                "value": {"a": 1, "b": 2},
            },
            {"request.payload": {"b": 2, "a": 1}},
            TruthValue.TRUE,
        ),
        (
            {"facet": "sample.array", "operator": "equals", "value": [1, 2]},
            {"sample.array": [2, 1]},
            TruthValue.FALSE,
        ),
        (
            {
                "facet": "sample.boolean-or-number",
                "operator": "equals",
                "value": 1,
            },
            {"sample.boolean-or-number": True},
            TruthValue.FALSE,
        ),
        (
            {"facet": "sample.number", "operator": "equals", "value": 1},
            {"sample.number": 1.0},
            TruthValue.TRUE,
        ),
    ],
)
def test_trace_uses_the_shared_json_equality_semantics(
    predicate: dict[str, object], context: dict[str, object], expected: TruthValue
) -> None:
    trace = evaluate_applicability_with_trace(predicate, context, FACETS)

    assert trace.result is expected
    assert evaluate_applicability(predicate, context, FACETS) is expected


def test_nested_trace_preserves_each_normalized_path_and_child_order() -> None:
    predicate = {
        "not": {
            "any": [
                {"facet": "a", "operator": "equals", "value": True},
                {"facet": "b", "operator": "equals", "value": True},
            ]
        }
    }

    root = evaluate_applicability_with_trace(predicate, CONTEXT, FACETS)

    assert isinstance(root, BooleanApplicabilityTrace)
    any_trace = root.children[0]
    assert isinstance(any_trace, BooleanApplicabilityTrace)
    assert root.predicate_path == ()
    assert any_trace.predicate_path == ("not",)
    assert tuple(child.predicate_path for child in any_trace.children) == (
        ("not", "any", 0),
        ("not", "any", 1),
    )
    assert tuple(
        child.facet
        for child in any_trace.children
        if isinstance(child, AtomicApplicabilityTrace)
    ) == (
        "a",
        "b",
    )


class _CountingFacets:
    """Count validation calls while delegating to a real registry."""

    def __init__(self) -> None:
        self.calls = 0

    def validate_context(self, context: Mapping[str, object]) -> Mapping[str, object]:
        """Validate one context and record the call."""
        self.calls += 1
        return FACETS.validate_context(context)


@pytest.mark.parametrize("traced", [False, True])
def test_each_public_evaluation_validates_context_once(traced: bool) -> None:
    facets = _CountingFacets()
    registry = cast(FacetRegistry, facets)

    if traced:
        evaluate_applicability_with_trace(ATOMS[TruthValue.TRUE], CONTEXT, registry)
    else:
        evaluate_applicability(ATOMS[TruthValue.TRUE], CONTEXT, registry)

    assert facets.calls == 1


@pytest.mark.parametrize(
    ("predicate", "context"),
    [
        ({"all": []}, {}),
        ({"all": [True]}, {}),
        ({"not": True}, {}),
        ({"facet": 1, "operator": "equals", "value": 1}, {}),
        ({"facet": "a", "operator": "unsupported"}, {}),
        ({"facet": "a", "operator": "in", "value": 1}, {"a": True}),
    ],
)
def test_scalar_and_traced_apis_raise_identical_predicate_errors(
    predicate: dict[str, object], context: dict[str, object]
) -> None:
    with pytest.raises(ValueError) as scalar_error:
        evaluate_applicability(predicate, context, FACETS)
    with pytest.raises(ValueError) as traced_error:
        evaluate_applicability_with_trace(predicate, context, FACETS)

    assert type(scalar_error.value) is type(traced_error.value)
    assert str(scalar_error.value) == str(traced_error.value)


@pytest.mark.parametrize(
    "predicate",
    [
        {"facet": "a", "operator": "unsupported"},
        {"facet": "a", "operator": "in", "value": 1},
    ],
)
def test_malformed_atomic_structure_fails_when_the_facet_is_absent(
    predicate: dict[str, object],
) -> None:
    with pytest.raises(ValueError) as scalar_error:
        evaluate_applicability(predicate, {}, FACETS)
    with pytest.raises(ValueError) as traced_error:
        evaluate_applicability_with_trace(predicate, {}, FACETS)

    assert str(scalar_error.value) == str(traced_error.value)


def test_non_json_equals_operand_fails_when_the_facet_is_absent() -> None:
    cycle: list[object] = []
    cycle.append(cycle)
    predicate = {"facet": "a", "operator": "equals", "value": cycle}

    with pytest.raises(TypeError, match="cyclic containers") as scalar_error:
        evaluate_applicability(predicate, {}, FACETS)
    with pytest.raises(TypeError, match="cyclic containers") as traced_error:
        evaluate_applicability_with_trace(predicate, {}, FACETS)

    assert str(scalar_error.value) == str(traced_error.value)


@pytest.mark.parametrize("traced", [False, True])
def test_context_validation_precedes_predicate_traversal(traced: bool) -> None:
    malformed: dict[str, object] = {"all": []}
    invalid_context = {"unregistered": True}

    with pytest.raises(FacetContextError, match="facet is not registered"):
        if traced:
            evaluate_applicability_with_trace(malformed, invalid_context, FACETS)
        else:
            evaluate_applicability(malformed, invalid_context, FACETS)


def test_trace_copies_values_and_retains_only_referenced_context() -> None:
    expected = {"enabled": True}
    observed = {"enabled": True}
    predicate = {
        "facet": "sample.object",
        "operator": "equals",
        "value": expected,
    }
    context = {"sample.object": observed, "request.mode": "private"}

    trace = evaluate_applicability_with_trace(predicate, context, FACETS)
    expected["enabled"] = False
    observed["enabled"] = False

    assert isinstance(trace, AtomicApplicabilityTrace)
    assert trace.expected == {"enabled": True}
    assert trace.observed == {"enabled": True}
    assert trace.facet == "sample.object"
    assert "private" not in repr(trace)
    with pytest.raises(TypeError):
        cast(dict[str, object], trace.expected)["enabled"] = False
    with pytest.raises(TypeError):
        cast(dict[str, object], trace.observed)["enabled"] = False
    with pytest.raises(FrozenInstanceError):
        trace.result = TruthValue.FALSE  # type: ignore[misc]

    expected_list = [1, 2]
    observed_list = [1, 2]
    list_trace = evaluate_applicability_with_trace(
        {"facet": "sample.array", "operator": "equals", "value": expected_list},
        {"sample.array": observed_list},
        FACETS,
    )
    expected_list.append(3)
    observed_list.append(3)
    assert isinstance(list_trace, AtomicApplicabilityTrace)
    assert list_trace.expected == (1, 2)
    assert list_trace.observed == (1, 2)


def test_public_trace_constructors_reject_fabricated_evidence() -> None:
    with pytest.raises(TypeError, match="issued by applicability evaluation"):
        AtomicApplicabilityTrace(
            (),
            "exists",
            "a",
            TruthValue.TRUE,
            False,
            "contradictory",
            {"mutable": []},
        )
    with pytest.raises(TypeError, match="issued by applicability evaluation"):
        BooleanApplicabilityTrace((), "not", TruthValue.TRUE, ())


def _boolean_result(operator: str, left: TruthValue, right: TruthValue) -> TruthValue:
    """Return the expected strong-Kleene result for two truth values."""
    values = (left, right)
    if operator == "all":
        if TruthValue.FALSE in values:
            return TruthValue.FALSE
        if all(value is TruthValue.TRUE for value in values):
            return TruthValue.TRUE
        return TruthValue.UNKNOWN
    if TruthValue.TRUE in values:
        return TruthValue.TRUE
    if all(value is TruthValue.FALSE for value in values):
        return TruthValue.FALSE
    return TruthValue.UNKNOWN
