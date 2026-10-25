"""Tests for contextual semantic resolution and its evidence boundary."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from eutaxis.declarations import (
    CompositionError,
    FacetContextError,
    ResolutionError,
    ResolutionErrorCode,
    ResolutionEvent,
    ResolutionEventKind,
    ResolutionResult,
    ResolutionTrace,
    ResolvedCompilationUnit,
    ResolvedRuleProjection,
    TruthValue,
    load_declaration_registry,
    load_facet_registry,
    plan_cumulative_composition,
    resolve_compilation_unit,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "resolution" / "valid"
FACET_PATH = (
    Path(__file__).parent / "fixtures" / "facets" / "valid" / "context-facets.yaml"
)


def _context(**overrides: object) -> dict[str, object]:
    context: dict[str, object] = {
        "artifact.created": True,
        "artifact.written": True,
        "context.available": True,
        "filesystem.writable": True,
        "scope.project": True,
        "source.available": True,
        "target.codex": True,
    }
    context.update(overrides)
    return context


def _registry(root: Path = FIXTURE_ROOT, *, reverse: bool = False):
    paths = sorted(root.glob("*.yaml"), reverse=reverse)
    return load_declaration_registry(tuple(paths), load_facet_registry(FACET_PATH))


def _mutable_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "resolution"
    shutil.copytree(FIXTURE_ROOT, root)
    return root


def _document(root: Path, name: str) -> dict[str, object]:
    return yaml.safe_load((root / name).read_text(encoding="utf-8"))


def _write_document(root: Path, name: str, document: dict[str, object]) -> None:
    (root / name).write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )


def _resolve(root: Path = FIXTURE_ROOT, **context: object):
    return resolve_compilation_unit(
        _registry(root), "resolution/manifest", _context(**context)
    )


def test_resolution_is_deterministic_and_composition_ready() -> None:
    first = resolve_compilation_unit(_registry(), "resolution/manifest", _context())
    second = resolve_compilation_unit(
        _registry(reverse=True), "resolution/manifest", _context()
    )

    assert first == second
    assert tuple(component.declaration for component in first.unit.components) == (
        "resolution/base",
        "resolution/refined",
        "resolution/write-artifact",
    )
    assert first.unit.components[0].rank == 1
    assert tuple(
        (edge.prerequisite, edge.dependant) for edge in first.unit.dependencies
    ) == (
        ("resolution/base", "resolution/refined"),
        ("resolution/base", "resolution/write-artifact"),
    )
    assert tuple(
        (projection.declaration, projection.norms, projection.criteria)
        for projection in first.unit.rule_projections
    ) == (
        ("resolution/base", ("preserve",), ("preservation",)),
        ("resolution/refined", ("refine",), ("refined-check",)),
    )
    assert first.trace.facet_registry == "tests/context-facets"
    assert first.trace.facet_source_revision == "fixture-1"
    assert [event.ordinal for event in first.trace.events] == list(
        range(len(first.trace.events))
    )
    assert first.trace.events[-1].kind is ResolutionEventKind.UNIT_ISSUED
    assert plan_cumulative_composition(_registry(), first.unit).manifest == (
        "resolution/manifest"
    )


def test_rule_set_is_expanded_but_never_becomes_effective() -> None:
    result = _resolve()

    assert "resolution/package" not in {
        component.declaration for component in result.unit.components
    }
    expansion = next(
        event
        for event in result.trace.events
        if event.kind is ResolutionEventKind.RULE_SET_MEMBER_EXPANDED
    )
    assert expansion.declaration == "resolution/base"
    assert expansion.anchor is not None and expansion.anchor.rank == 0
    assert result.unit.components[0].rank == 1


def test_composer_rejects_a_projection_for_an_effective_procedure() -> None:
    result = _resolve()
    unit = object.__new__(ResolvedCompilationUnit)
    object.__setattr__(unit, "manifest", result.unit.manifest)
    object.__setattr__(unit, "components", result.unit.components)
    object.__setattr__(unit, "dependencies", result.unit.dependencies)
    object.__setattr__(
        unit,
        "rule_projections",
        (
            *result.unit.rule_projections,
            ResolvedRuleProjection("resolution/write-artifact", (), ()),
        ),
    )

    with pytest.raises(CompositionError) as captured:
        plan_cumulative_composition(_registry(), unit)

    assert captured.value.location == "$.rule_projections[2].declaration"
    assert "procedure" in str(captured.value)


@pytest.mark.parametrize(
    ("manifest", "code", "has_trace"),
    [
        ("resolution/missing", ResolutionErrorCode.UNKNOWN_MANIFEST, False),
        ("resolution/base", ResolutionErrorCode.MANIFEST_WRONG_KIND, False),
    ],
)
def test_manifest_lookup_failures_precede_trace_creation(
    manifest: str, code: ResolutionErrorCode, has_trace: bool
) -> None:
    with pytest.raises(ResolutionError) as captured:
        resolve_compilation_unit(_registry(), manifest, _context())

    assert captured.value.code is code
    assert (captured.value.trace is not None) is has_trace


@pytest.mark.parametrize(
    ("target", "code", "truth"),
    [
        (False, ResolutionErrorCode.MANIFEST_INAPPLICABLE, TruthValue.FALSE),
        (
            None,
            ResolutionErrorCode.MANIFEST_APPLICABILITY_INDETERMINATE,
            TruthValue.UNKNOWN,
        ),
    ],
)
def test_manifest_predicate_failures_carry_exact_evidence(
    target: bool | None, code: ResolutionErrorCode, truth: TruthValue
) -> None:
    context = _context()
    if target is None:
        del context["target.codex"]
    else:
        context["target.codex"] = target

    with pytest.raises(ResolutionError) as captured:
        resolve_compilation_unit(_registry(), "resolution/manifest", context)

    error = captured.value
    assert error.code is code
    assert error.truth is truth
    assert error.applicability is not None
    assert error.trace is not None
    assert tuple(event.kind for event in error.trace.events) == (
        ResolutionEventKind.MANIFEST_EVALUATED,
    )
    assert error.source is not None
    assert error.source.document_path == ("applicability",)


def test_context_validation_precedes_event_issuance() -> None:
    with pytest.raises(FacetContextError):
        resolve_compilation_unit(
            _registry(),
            "resolution/manifest",
            {**_context(), "unknown.facet": True},
        )


@pytest.mark.parametrize(
    ("availability", "truth"),
    [(False, TruthValue.FALSE), (None, TruthValue.UNKNOWN)],
)
def test_inapplicable_direct_candidate_is_omitted(
    tmp_path: Path, availability: bool | None, truth: TruthValue
) -> None:
    root = _mutable_fixture(tmp_path)
    manifest = _document(root, "manifest.yaml")
    manifest["sections"][0]["declarations"] = ["resolution/alternate"]  # type: ignore[index]
    manifest["policies"] = []
    alternate = _document(root, "alternate-rule.yaml")
    alternate["applicability"] = {
        "facet": "context.available",
        "operator": "equals",
        "value": True,
    }
    _write_document(root, "manifest.yaml", manifest)
    _write_document(root, "alternate-rule.yaml", alternate)
    context = _context()
    if availability is None:
        del context["context.available"]
    else:
        context["context.available"] = availability

    result = resolve_compilation_unit(_registry(root), "resolution/manifest", context)

    assert result.unit.components == ()
    evaluations = [
        event
        for event in result.trace.events
        if event.kind is ResolutionEventKind.DECLARATION_EVALUATED
    ]
    assert evaluations
    assert {event.truth for event in evaluations} == {truth}


@pytest.mark.parametrize(
    ("availability", "code", "truth"),
    [
        (False, ResolutionErrorCode.DEPENDENCY_INAPPLICABLE, TruthValue.FALSE),
        (
            None,
            ResolutionErrorCode.DEPENDENCY_APPLICABILITY_INDETERMINATE,
            TruthValue.UNKNOWN,
        ),
    ],
)
def test_dependency_predicate_failure_is_not_omitted(
    tmp_path: Path,
    availability: bool | None,
    code: ResolutionErrorCode,
    truth: TruthValue,
) -> None:
    root = _mutable_fixture(tmp_path)
    manifest = _document(root, "manifest.yaml")
    manifest["sections"][0]["declarations"] = ["resolution/write-artifact"]  # type: ignore[index]
    _write_document(root, "manifest.yaml", manifest)
    package = _document(root, "rule-set.yaml")
    package["rules"][0]["applicability"] = {  # type: ignore[index]
        "facet": "context.available",
        "operator": "equals",
        "value": True,
    }
    _write_document(root, "rule-set.yaml", package)
    context = _context()
    if availability is None:
        del context["context.available"]
    else:
        context["context.available"] = availability

    with pytest.raises(ResolutionError) as captured:
        resolve_compilation_unit(_registry(root), "resolution/manifest", context)

    assert captured.value.code is code
    assert captured.value.truth is truth
    assert captured.value.source is not None
    assert captured.value.source.document_path == ("relations", 0, "target")


def test_false_norm_and_matching_waiver_produce_an_empty_projection() -> None:
    result = _resolve(FIXTURE_ROOT, **{"source.available": False})
    projection = next(
        item
        for item in result.unit.rule_projections
        if item.declaration == "resolution/base"
    )

    assert projection.norms == ()
    assert projection.criteria == ()
    assert any(
        event.kind is ResolutionEventKind.CRITERION_INACTIVE
        and event.criterion == "preservation"
        for event in result.trace.events
    )


def test_matching_waiver_removes_an_initially_effective_norm(
    tmp_path: Path,
) -> None:
    root = _mutable_fixture(tmp_path)
    package = _document(root, "rule-set.yaml")
    exception = package["rules"][0]["exceptions"][0]  # type: ignore[index]
    exception["when"] = {  # type: ignore[index]
        "facet": "artifact.created",
        "operator": "equals",
        "value": True,
    }
    _write_document(root, "rule-set.yaml", package)

    result = _resolve(root)
    projection = next(
        item
        for item in result.unit.rule_projections
        if item.declaration == "resolution/base"
    )
    norm_event = next(
        event
        for event in result.trace.events
        if event.kind is ResolutionEventKind.NORM_EVALUATED and event.norm == "preserve"
    )
    exception_event = next(
        event
        for event in result.trace.events
        if event.kind is ResolutionEventKind.EXCEPTION_EVALUATED
        and event.exception == "unavailable-source"
    )
    removed = next(
        event
        for event in result.trace.events
        if event.kind is ResolutionEventKind.NORM_REMOVED and event.norm == "preserve"
    )
    inactive = next(
        event
        for event in result.trace.events
        if event.kind is ResolutionEventKind.CRITERION_INACTIVE
        and event.criterion == "preservation"
    )

    assert norm_event.truth is TruthValue.TRUE
    assert exception_event.truth is TruthValue.TRUE
    assert projection.norms == ()
    assert projection.criteria == ()
    assert removed.source.document_path == (
        "rules",
        0,
        "exceptions",
        0,
        "affects",
        0,
    )
    assert removed.causes == tuple(
        sorted((norm_event.ordinal, exception_event.ordinal))
    )
    assert inactive.source.document_path == ("rules", 0, "criteria", 0)
    assert inactive.causes == (norm_event.ordinal,)


def test_matching_substitution_retains_only_the_authored_replacement(
    tmp_path: Path,
) -> None:
    root = _mutable_fixture(tmp_path)
    package = _document(root, "rule-set.yaml")
    rule = package["rules"][0]  # type: ignore[index]
    rule["norms"].append(  # type: ignore[index]
        {
            "id": "secondary",
            "modality": "must",
            "subject": "agent",
            "action": {"verb": "check", "object": "the secondary contract"},
        }
    )
    rule["exceptions"][0] = {  # type: ignore[index]
        "id": "replace-preserve",
        "when": {
            "facet": "artifact.created",
            "operator": "equals",
            "value": True,
        },
        "disposition": "substitute",
        "affects": ["preserve"],
        "substitutes": ["secondary"],
    }
    rule["criteria"].append(  # type: ignore[index]
        {
            "id": "secondary-check",
            "norms": ["secondary"],
            "evaluator": {"id": "resolution/manual", "version": 1},
            "statement": "The secondary contract is checked",
        }
    )
    _write_document(root, "rule-set.yaml", package)

    result = _resolve(root)
    projection = next(
        item
        for item in result.unit.rule_projections
        if item.declaration == "resolution/base"
    )
    norm_events = {
        event.norm: event
        for event in result.trace.events
        if event.kind is ResolutionEventKind.NORM_EVALUATED
        and event.declaration == "resolution/base"
    }
    exception_event = next(
        event
        for event in result.trace.events
        if event.kind is ResolutionEventKind.EXCEPTION_EVALUATED
        and event.exception == "replace-preserve"
    )
    removed = next(
        event
        for event in result.trace.events
        if event.kind is ResolutionEventKind.NORM_REMOVED and event.norm == "preserve"
    )
    substituted = next(
        event
        for event in result.trace.events
        if event.kind is ResolutionEventKind.NORM_SUBSTITUTED
        and event.norm == "secondary"
    )
    effective = next(
        event
        for event in result.trace.events
        if event.kind is ResolutionEventKind.NORM_EFFECTIVE
        and event.norm == "secondary"
    )
    criterion_events = {
        event.criterion: event
        for event in result.trace.events
        if event.kind
        in {
            ResolutionEventKind.CRITERION_EFFECTIVE,
            ResolutionEventKind.CRITERION_INACTIVE,
        }
        and event.declaration == "resolution/base"
    }

    assert {event.truth for event in norm_events.values()} == {TruthValue.TRUE}
    assert exception_event.truth is TruthValue.TRUE
    assert projection.norms == ("secondary",)
    assert projection.criteria == ("secondary-check",)
    assert removed.source.document_path == (
        "rules",
        0,
        "exceptions",
        0,
        "affects",
        0,
    )
    assert removed.causes == tuple(
        sorted((norm_events["preserve"].ordinal, exception_event.ordinal))
    )
    assert substituted.source.document_path == (
        "rules",
        0,
        "exceptions",
        0,
        "substitutes",
        0,
    )
    assert substituted.causes == tuple(
        sorted((norm_events["secondary"].ordinal, exception_event.ordinal))
    )
    assert effective.source.document_path == ("rules", 0, "norms", 1)
    assert effective.causes == tuple(
        sorted((norm_events["secondary"].ordinal, substituted.ordinal))
    )
    assert criterion_events["preservation"].kind is (
        ResolutionEventKind.CRITERION_INACTIVE
    )
    assert criterion_events["secondary-check"].kind is (
        ResolutionEventKind.CRITERION_EFFECTIVE
    )
    assert criterion_events["secondary-check"].causes == (effective.ordinal,)


def test_unresolved_conflict_fails_at_the_declared_incompatibility(
    tmp_path: Path,
) -> None:
    root = _mutable_fixture(tmp_path)
    manifest = _document(root, "manifest.yaml")
    manifest["policies"] = []
    _write_document(root, "manifest.yaml", manifest)

    with pytest.raises(ResolutionError) as captured:
        _resolve(root)

    assert captured.value.code is ResolutionErrorCode.UNRESOLVED_CONFLICT
    assert captured.value.source is not None
    assert captured.value.source.path.name == "refined-rule.yaml"
    assert captured.value.source.document_path == ("relations", 1, "target")


def test_indeterminate_policy_is_distinct_from_no_matching_policy() -> None:
    context = _context()
    del context["scope.project"]

    with pytest.raises(ResolutionError) as captured:
        resolve_compilation_unit(_registry(), "resolution/manifest", context)

    assert captured.value.code is ResolutionErrorCode.CONFLICT_POLICY_INDETERMINATE
    assert captured.value.truth is TruthValue.UNKNOWN
    assert captured.value.applicability is not None


@pytest.mark.parametrize("strategy_kind", ["substitute", "combine"])
def test_policy_results_enter_the_next_resolution_round(
    tmp_path: Path, strategy_kind: str
) -> None:
    root = _mutable_fixture(tmp_path)
    replacement = _document(root, "alternate-rule.yaml")
    replacement["id"] = "resolution/replacement"
    replacement["relations"] = [{"type": "requires", "target": "resolution/base"}]
    _write_document(root, "replacement-rule.yaml", replacement)
    policy = _document(root, "policy.yaml")
    if strategy_kind == "substitute":
        policy["strategy"] = {
            "kind": "substitute",
            "replace": "resolution/alternate",
            "with": "resolution/replacement",
        }
    else:
        policy["strategy"] = {
            "kind": "combine",
            "result": "resolution/replacement",
        }
    _write_document(root, "policy.yaml", policy)

    result = _resolve(root)
    effective = {component.declaration for component in result.unit.components}

    assert "resolution/replacement" in effective
    assert "resolution/alternate" not in effective
    if strategy_kind == "combine":
        assert "resolution/refined" not in effective
    else:
        assert "resolution/refined" in effective
    assert (
        "resolution/base",
        "resolution/replacement",
    ) in {(edge.prerequisite, edge.dependant) for edge in result.unit.dependencies}
    assert any(
        event.kind is ResolutionEventKind.POLICY_RESULT_DISCOVERED
        and event.declaration == "resolution/replacement"
        for event in result.trace.events
    )


@pytest.mark.parametrize(
    ("availability", "code", "truth"),
    [
        (
            False,
            ResolutionErrorCode.POLICY_SUBSTITUTE_INAPPLICABLE,
            TruthValue.FALSE,
        ),
        (
            None,
            ResolutionErrorCode.POLICY_SUBSTITUTE_INDETERMINATE,
            TruthValue.UNKNOWN,
        ),
    ],
)
def test_substitute_result_requires_true_applicability(
    tmp_path: Path,
    availability: bool | None,
    code: ResolutionErrorCode,
    truth: TruthValue,
) -> None:
    root = _mutable_fixture(tmp_path)
    replacement = _document(root, "alternate-rule.yaml")
    replacement["id"] = "resolution/replacement"
    replacement["applicability"] = {
        "facet": "source.available",
        "operator": "equals",
        "value": True,
    }
    _write_document(root, "replacement-rule.yaml", replacement)
    policy = _document(root, "policy.yaml")
    policy["strategy"] = {
        "kind": "substitute",
        "replace": "resolution/alternate",
        "with": "resolution/replacement",
    }
    _write_document(root, "policy.yaml", policy)
    context = _context()
    if availability is None:
        del context["source.available"]
    else:
        context["source.available"] = availability

    with pytest.raises(ResolutionError) as captured:
        resolve_compilation_unit(_registry(root), "resolution/manifest", context)

    assert captured.value.code is code
    assert captured.value.truth is truth


def test_overlapping_batch_rejects_ambiguous_alias_before_state_changes(
    tmp_path: Path,
) -> None:
    root = _mutable_fixture(tmp_path)
    alternate = _document(root, "alternate-rule.yaml")
    alternate["relations"] = [
        {"type": "incompatible-with", "target": "resolution/third"}
    ]
    _write_document(root, "alternate-rule.yaml", alternate)
    for name in ("third", "replacement-one", "replacement-two"):
        rule = _document(root, "alternate-rule.yaml")
        rule["id"] = f"resolution/{name}"
        rule["relations"] = []
        _write_document(root, f"{name}.yaml", rule)
    first_policy = _document(root, "policy.yaml")
    first_policy["strategy"] = {
        "kind": "substitute",
        "replace": "resolution/alternate",
        "with": "resolution/replacement-one",
    }
    _write_document(root, "policy.yaml", first_policy)
    second_policy = _document(root, "policy.yaml")
    second_policy["id"] = "resolution/replace-again"
    second_policy["conflicts"] = ["resolution/alternate", "resolution/third"]
    second_policy["strategy"] = {
        "kind": "substitute",
        "replace": "resolution/alternate",
        "with": "resolution/replacement-two",
    }
    _write_document(root, "second-policy.yaml", second_policy)
    manifest = _document(root, "manifest.yaml")
    manifest["sections"][0]["declarations"].append(  # type: ignore[index, attr-defined]
        "resolution/third"
    )
    manifest["policies"].append("resolution/replace-again")  # type: ignore[attr-defined]
    _write_document(root, "manifest.yaml", manifest)

    with pytest.raises(ResolutionError) as captured:
        _resolve(root)

    assert captured.value.code is ResolutionErrorCode.AMBIGUOUS_POLICY_ALIAS
    assert captured.value.source is not None
    assert captured.value.source.path.name == "second-policy.yaml"
    assert captured.value.source.document_path == ("strategy", "with")
    assert captured.value.trace is not None
    assert not any(
        event.kind
        in {
            ResolutionEventKind.CONFLICT_RESOLVED,
            ResolutionEventKind.DECLARATION_EXCLUDED,
            ResolutionEventKind.ALIAS_CREATED,
        }
        for event in captured.value.trace.events
    )


def test_current_batch_exclusion_blocks_a_policy_result(tmp_path: Path) -> None:
    root = _mutable_fixture(tmp_path)
    replacement = _document(root, "alternate-rule.yaml")
    replacement["id"] = "resolution/replacement"
    replacement["relations"] = [
        {"type": "incompatible-with", "target": "resolution/third"}
    ]
    _write_document(root, "replacement-rule.yaml", replacement)
    third = _document(root, "alternate-rule.yaml")
    third["id"] = "resolution/third"
    third["relations"] = []
    _write_document(root, "third-rule.yaml", third)
    first_policy = _document(root, "policy.yaml")
    first_policy["strategy"] = {
        "kind": "substitute",
        "replace": "resolution/alternate",
        "with": "resolution/replacement",
    }
    _write_document(root, "policy.yaml", first_policy)
    second_policy = _document(root, "policy.yaml")
    second_policy["id"] = "resolution/prefer-third"
    second_policy["conflicts"] = ["resolution/replacement", "resolution/third"]
    second_policy["strategy"] = {
        "kind": "retain",
        "retain": "resolution/third",
    }
    _write_document(root, "second-policy.yaml", second_policy)
    manifest = _document(root, "manifest.yaml")
    manifest["sections"][0]["declarations"].extend(  # type: ignore[index]
        ["resolution/replacement", "resolution/third"]
    )
    manifest["policies"].append("resolution/prefer-third")  # type: ignore[attr-defined]
    _write_document(root, "manifest.yaml", manifest)

    with pytest.raises(ResolutionError) as captured:
        _resolve(root)

    assert captured.value.code is ResolutionErrorCode.POLICY_RESULT_EXCLUDED
    assert captured.value.trace is not None
    assert not any(
        event.kind is ResolutionEventKind.CONFLICT_RESOLVED
        for event in captured.value.trace.events
    )


def test_direct_policy_alias_rewrites_a_retained_dependency(tmp_path: Path) -> None:
    root = _mutable_fixture(tmp_path)
    replacement = _document(root, "alternate-rule.yaml")
    replacement["id"] = "resolution/replacement"
    replacement["relations"] = []
    _write_document(root, "replacement-rule.yaml", replacement)
    dependant = _document(root, "alternate-rule.yaml")
    dependant["id"] = "resolution/dependant"
    dependant["relations"] = [{"type": "requires", "target": "resolution/alternate"}]
    _write_document(root, "dependant-rule.yaml", dependant)
    policy = _document(root, "policy.yaml")
    policy["strategy"] = {
        "kind": "substitute",
        "replace": "resolution/alternate",
        "with": "resolution/replacement",
    }
    _write_document(root, "policy.yaml", policy)
    manifest = _document(root, "manifest.yaml")
    manifest["sections"][0]["declarations"].append(  # type: ignore[index]
        "resolution/dependant"
    )
    _write_document(root, "manifest.yaml", manifest)

    result = _resolve(root)

    assert (
        "resolution/replacement",
        "resolution/dependant",
    ) in {(edge.prerequisite, edge.dependant) for edge in result.unit.dependencies}
    assert not any(
        edge.prerequisite == "resolution/alternate" for edge in result.unit.dependencies
    )


def test_prerequisite_retention_is_conservative_after_dependant_exclusion(
    tmp_path: Path,
) -> None:
    root = _mutable_fixture(tmp_path)
    replacement = _document(root, "alternate-rule.yaml")
    replacement["id"] = "resolution/replacement"
    replacement["relations"] = []
    _write_document(root, "replacement-rule.yaml", replacement)
    policy = _document(root, "policy.yaml")
    policy["strategy"] = {
        "kind": "combine",
        "result": "resolution/replacement",
    }
    _write_document(root, "policy.yaml", policy)
    manifest = _document(root, "manifest.yaml")
    manifest["sections"][0]["declarations"] = [  # type: ignore[index]
        "resolution/refined",
        "resolution/alternate",
    ]
    _write_document(root, "manifest.yaml", manifest)

    result = _resolve(root)

    assert tuple(component.declaration for component in result.unit.components) == (
        "resolution/base",
        "resolution/replacement",
    )
    assert result.unit.dependencies == ()
    assert result.unit.components[0].rank == 0


def test_partial_criterion_applicability_fails_in_final_projection(
    tmp_path: Path,
) -> None:
    root = _mutable_fixture(tmp_path)
    package = _document(root, "rule-set.yaml")
    rule = package["rules"][0]  # type: ignore[index]
    rule["norms"].append(  # type: ignore[index]
        {
            "id": "secondary",
            "modality": "must",
            "subject": "agent",
            "action": {"verb": "check", "object": "the secondary contract"},
            "applies-when": {
                "facet": "artifact.written",
                "operator": "equals",
                "value": True,
            },
        }
    )
    rule["criteria"][0]["norms"] = ["preserve", "secondary"]  # type: ignore[index]
    _write_document(root, "rule-set.yaml", package)
    context = _context()
    del context["artifact.written"]

    with pytest.raises(ResolutionError) as captured:
        resolve_compilation_unit(_registry(root), "resolution/manifest", context)

    assert captured.value.code is ResolutionErrorCode.PARTIAL_CRITERION_APPLICABILITY
    assert captured.value.source is not None
    assert captured.value.source.document_path == (
        "rules",
        0,
        "criteria",
        0,
    )


@pytest.mark.parametrize(
    ("availability", "code", "truth"),
    [
        (
            False,
            ResolutionErrorCode.EXCEPTION_SUBSTITUTE_INAPPLICABLE,
            TruthValue.FALSE,
        ),
        (
            None,
            ResolutionErrorCode.EXCEPTION_SUBSTITUTE_INDETERMINATE,
            TruthValue.UNKNOWN,
        ),
    ],
)
def test_exception_substitute_requires_true_norm_applicability(
    tmp_path: Path,
    availability: bool | None,
    code: ResolutionErrorCode,
    truth: TruthValue,
) -> None:
    root = _mutable_fixture(tmp_path)
    package = _document(root, "rule-set.yaml")
    rule = package["rules"][0]  # type: ignore[index]
    rule["norms"].append(  # type: ignore[index]
        {
            "id": "secondary",
            "modality": "must",
            "subject": "agent",
            "action": {"verb": "check", "object": "the secondary contract"},
            "applies-when": {
                "facet": "source.available",
                "operator": "equals",
                "value": True,
            },
        }
    )
    rule["exceptions"][0] = {  # type: ignore[index]
        "id": "replace-preserve",
        "when": {
            "facet": "artifact.created",
            "operator": "equals",
            "value": True,
        },
        "disposition": "substitute",
        "affects": ["preserve"],
        "substitutes": ["secondary"],
    }
    _write_document(root, "rule-set.yaml", package)
    context = _context()
    if availability is None:
        del context["source.available"]
    else:
        context["source.available"] = availability

    with pytest.raises(ResolutionError) as captured:
        resolve_compilation_unit(_registry(root), "resolution/manifest", context)

    assert captured.value.code is code
    assert captured.value.truth is truth


def test_certified_aggregate_constructors_remain_private() -> None:
    for aggregate, arguments in (
        (ResolvedCompilationUnit, ("resolution/manifest", (), (), ())),
        (ResolutionTrace, ("resolution/manifest", "facets", "revision", ())),
        (ResolutionEvent, ()),
        (ResolutionResult, ()),
    ):
        with pytest.raises(TypeError, match="issued"):
            aggregate(*arguments)

    with pytest.raises(TypeError, match="issued"):
        replace(_resolve().unit, dependencies=())
