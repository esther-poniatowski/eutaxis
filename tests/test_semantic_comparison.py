"""Exercise complete semantic comparison of authenticated declaration corpora."""

from __future__ import annotations

from pathlib import Path

import pytest

import eutaxis.declarations.external_result as external_result_module
import eutaxis.declarations.semantic_comparison as comparison_module
from eutaxis.declarations import (
    SemanticChangeKind,
    SemanticObjectKey,
    SemanticObjectKind,
    acquire_external_declarations_from_path,
    compare_external_declarations,
)
from eutaxis.declarations.exceptions import AcquisitionContractError
from eutaxis.declarations.external_result import ExternalAcquisitionResult
from tests.test_external_acquisition import (
    _declaration_source,
    _facet_source,
    _write_contract,
)


def _acquire(
    workspace: Path,
    *,
    declaration_bytes: bytes | None = None,
    declaration_files: tuple[tuple[str, bytes], ...] | None = None,
    facet_bytes: bytes | None = None,
) -> ExternalAcquisitionResult:
    manifest_path, lock_path = _write_contract(
        workspace,
        declaration_bytes=declaration_bytes,
        declaration_files=declaration_files,
        facet_bytes=facet_bytes,
    )
    return acquire_external_declarations_from_path(
        str(workspace),
        manifest_path,
        lock_path,
    )


def test_ignores_source_revision_and_transport_location(tmp_path: Path) -> None:
    """Treat source revisions and workspace paths as non-semantic metadata."""
    baseline_source = _declaration_source("oikos")
    candidate_source = baseline_source.replace(b"fixture-1", b"fixture-2")
    baseline = _acquire(tmp_path / "baseline", declaration_bytes=baseline_source)
    candidate = _acquire(tmp_path / "candidate", declaration_bytes=candidate_source)

    comparison = compare_external_declarations(baseline, candidate)

    assert comparison.equivalent
    assert not comparison.differences


def test_reports_exact_nested_semantic_path(tmp_path: Path) -> None:
    """Locate one changed typed field without widening its path."""
    baseline_source = _declaration_source("oikos")
    candidate_source = baseline_source.replace(
        b"modality: must",
        b"modality: must-not",
    )
    baseline = _acquire(tmp_path / "baseline", declaration_bytes=baseline_source)
    candidate = _acquire(tmp_path / "candidate", declaration_bytes=candidate_source)

    comparison = compare_external_declarations(baseline, candidate)

    difference = comparison.differences[0]
    assert not comparison.equivalent
    assert difference.key == SemanticObjectKey(
        SemanticObjectKind.DECLARATION,
        "oikos/reader-purpose",
    )
    assert difference.change is SemanticChangeKind.MODIFIED
    assert difference.paths == (("norms", 0, "modality"),)


def test_distinguishes_boolean_from_numeric_json_value(tmp_path: Path) -> None:
    """Preserve the JSON boolean and number type distinction."""
    unconstrained_facet = _facet_source("oikos").replace(
        b"{type: boolean}",
        b"{}",
    )
    baseline = _acquire(
        tmp_path / "baseline",
        facet_bytes=unconstrained_facet,
    )
    candidate = _acquire(
        tmp_path / "candidate",
        declaration_bytes=_declaration_source("oikos").replace(
            b"value: true",
            b"value: 1",
        ),
        facet_bytes=unconstrained_facet,
    )

    comparison = compare_external_declarations(baseline, candidate)

    difference = next(
        item
        for item in comparison.differences
        if item.key.id == "oikos/reader-purpose"
    )
    assert difference.paths == (
        ("applicability", "value"),
        ("norms", 0, "applicability", "value"),
    )


def test_orders_removed_before_added_declarations(tmp_path: Path) -> None:
    """Report membership changes in stable semantic-key order."""
    baseline = _acquire(tmp_path / "baseline")
    candidate = _acquire(
        tmp_path / "candidate",
        declaration_bytes=_declaration_source("oikos").replace(
            b"oikos/reader-purpose",
            b"oikos/alternate-purpose",
        ),
    )

    comparison = compare_external_declarations(baseline, candidate)

    assert [difference.key.id for difference in comparison.differences] == [
        "oikos/alternate-purpose",
        "oikos/reader-purpose",
    ]
    assert [difference.change for difference in comparison.differences] == [
        SemanticChangeKind.ADDED,
        SemanticChangeKind.REMOVED,
    ]
    assert all(difference.paths == ((),) for difference in comparison.differences)


def test_compares_local_facet_value_schema(tmp_path: Path) -> None:
    """Include consumer-defined facet semantics in the comparison."""
    baseline = _acquire(tmp_path / "baseline")
    candidate_facet = _facet_source("oikos").replace(
        b"{type: boolean}",
        b"{type: string}",
    )
    candidate_declaration = _declaration_source("oikos").replace(
        b"operator: equals, value: true",
        b"operator: equals, value: enabled",
    )
    candidate = _acquire(
        tmp_path / "candidate",
        declaration_bytes=candidate_declaration,
        facet_bytes=candidate_facet,
    )

    comparison = compare_external_declarations(baseline, candidate)

    facet_difference = next(
        difference
        for difference in comparison.differences
        if difference.key.object_kind is SemanticObjectKind.FACET
        and difference.key.id == "oikos.enabled"
    )
    assert facet_difference.paths == (("value_schema", "type"),)


def test_rule_set_does_not_duplicate_nested_rule_change(tmp_path: Path) -> None:
    """Compare an embedded rule once under its independently addressable ID."""
    baseline_source = _rule_set_source("must")
    candidate_source = _rule_set_source("must-not")
    source_path = "declarations/rule-set.yaml"
    baseline = _acquire(
        tmp_path / "baseline",
        declaration_files=((source_path, baseline_source),),
    )
    candidate = _acquire(
        tmp_path / "candidate",
        declaration_files=((source_path, candidate_source),),
    )

    comparison = compare_external_declarations(baseline, candidate)

    external_differences = [
        difference
        for difference in comparison.differences
        if difference.key.id.startswith("oikos/")
    ]
    assert [(difference.key.id, difference.paths) for difference in external_differences] == [
        ("oikos/exact-claims", (("norms", 0, "modality"),)),
    ]


def test_versions_are_distinct_semantic_objects(tmp_path: Path) -> None:
    """Key exact contracts by both declaration ID and version."""
    source_path = "declarations/evaluator.yaml"
    baseline = _acquire(
        tmp_path / "baseline",
        declaration_files=((source_path, _evaluator_source(1)),),
    )
    candidate = _acquire(
        tmp_path / "candidate",
        declaration_files=((source_path, _evaluator_source(2)),),
    )

    comparison = compare_external_declarations(baseline, candidate)

    exact_differences = [
        difference
        for difference in comparison.differences
        if difference.key.id == "oikos/manual"
    ]
    assert [difference.key.version for difference in exact_differences] == [1, 2]
    assert [difference.change for difference in exact_differences] == [
        SemanticChangeKind.REMOVED,
        SemanticChangeKind.ADDED,
    ]


def test_revalidates_authority_after_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return no comparison after either input loses its issued authority."""
    # This white-box test must cross both private boundaries to invalidate the
    # exact authority between the comparator's projection and final check.
    baseline = _acquire(tmp_path / "baseline")
    candidate = _acquire(tmp_path / "candidate")
    original = comparison_module._semantic_objects  # pylint: disable=protected-access
    calls = 0

    def retire_after_projection(state):
        nonlocal calls
        projection = original(state)
        calls += 1
        if calls == 2:
            external_result_module._retire_external_result_tree(  # pylint: disable=protected-access
                baseline
            )
        return projection

    monkeypatch.setattr(
        comparison_module,
        "_semantic_objects",
        retire_after_projection,
    )

    with pytest.raises(AcquisitionContractError, match="not issued here"):
        compare_external_declarations(baseline, candidate)


def test_rejects_unissued_result(tmp_path: Path) -> None:
    """Require both comparison inputs to cross the acquisition boundary."""
    baseline = _acquire(tmp_path / "baseline")
    forged = object.__new__(ExternalAcquisitionResult)

    with pytest.raises(AcquisitionContractError, match="not issued here"):
        compare_external_declarations(baseline, forged)


def _rule_set_source(modality: str) -> bytes:
    return f"""\
_schema: eutaxis:declaration@1
id: oikos/core
kind: rule-set
owner: oikos
status: active
source-revision: fixture-1
applicability: {{facet: oikos.enabled, operator: equals, value: true}}
relations: []
purpose: Group the rules used by the fixture
rules:
  - _schema: eutaxis:declaration@1
    id: oikos/exact-claims
    kind: rule
    owner: oikos
    status: active
    source-revision: fixture-1
    applicability: {{facet: oikos.enabled, operator: equals, value: true}}
    relations: []
    axis: reasoning-target
    failure-mode: visible
    norms:
      - id: support-claim
        modality: {modality}
        subject: agent
        action: {{verb: support, object: every claim}}
    criteria:
      - id: claims-have-evidence
        norms: [support-claim]
        evaluator: {{id: eutaxis/manual-judgment, version: 1}}
        statement: Every claim identifies its evidence
""".encode()


def _evaluator_source(version: int) -> bytes:
    return f"""\
_schema: eutaxis:declaration@1
id: oikos/manual
kind: evaluator
owner: oikos
status: active
source-revision: fixture-1
applicability: {{facet: oikos.enabled, operator: equals, value: true}}
relations: []
version: {version}
evaluator-kind: manual
coverage: none
adjudication: manual
timing: post-artifact
input-revisions: [declaration-v1]
evidence-schema:
  type: object
  properties:
    conclusion: {{enum: [satisfied, violated, blocked]}}
  required: [conclusion]
  additionalProperties: false
failure-behavior: block
""".encode()
