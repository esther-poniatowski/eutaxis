"""Tests for concise structured-selection reports used by artifact facades."""

from __future__ import annotations

from pathlib import Path

from eutaxis.declarations import (
    ResolvedArtifactSelection,
    ResolvedCumulativeSource,
    acquire_external_declarations_from_path,
    resolve_external_cumulative_source_from_path,
    resolve_external_compilation_unit,
    resolved_artifact_selection,
)
from eutaxis.declarations.external_result import _retire_external_result_tree
from tests.test_external_acquisition import _write_contract
from tests.test_external_resolution import MANIFEST, RULE, _context
from tests.test_query_packet import RULE_SET
from tests.test_markdown_projection import (
    FACETS,
    MANIFEST as PROCEDURE_MANIFEST,
    OPERATION,
    PROCEDURE,
    RULE as ACTIVE_RULE,
    RULE_SET as ACTIVE_RULE_SET,
    RULE_SET_MANIFEST,
)


def _contract(tmp_path: Path) -> tuple[str, str]:
    return _write_contract(
        tmp_path,
        namespace="resolution",
        declaration_files=(
            ("declarations/rule.yaml", RULE),
            ("declarations/manifest.yaml", MANIFEST),
        ),
    )


def test_projects_only_ordered_effective_records(tmp_path: Path) -> None:
    manifest_path, lock_path = _contract(tmp_path)
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    try:
        resolution = resolve_external_compilation_unit(
            acquisition,
            "resolution/manifest",
            _context(),
        )

        report = resolved_artifact_selection(resolution)
    finally:
        _retire_external_result_tree(acquisition)

    assert report.manifest == "resolution/manifest"
    assert report.mechanism == "cumulative"
    assert report.scope == "project"
    assert report.target == "AGENTS.md"
    assert report.records == ("resolution/purpose",)


def test_path_facade_acquires_resolves_and_returns_detached_report(
    tmp_path: Path,
) -> None:
    manifest_path, lock_path = _contract(tmp_path)

    source = resolve_external_cumulative_source_from_path(
        str(tmp_path),
        manifest_path,
        lock_path,
        "resolution/manifest",
        _context(),
    )

    assert source.selection.records == ("resolution/purpose",)
    assert source.contributors == ("resolution/purpose",)
    assert source.source_revisions
    assert all(row.content_revision for row in source.source_revisions)
    assert b"**purpose**:" in source.content
    assert source.sha256.startswith("sha256:")


def test_cumulative_source_preserves_previous_constructor_shape() -> None:
    selection = ResolvedArtifactSelection(
        "resolution/manifest",
        "cumulative",
        "project",
        "AGENTS.md",
        ("resolution/purpose",),
    )

    source = ResolvedCumulativeSource(selection, (), b"content", "sha256:digest")

    assert source.contributors == ()


def test_cumulative_contributors_include_embedded_operation_contract(
    tmp_path: Path,
) -> None:
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="projection",
        declaration_files=(
            ("declarations/rule.yaml", ACTIVE_RULE),
            ("declarations/operation.yaml", OPERATION),
            ("declarations/procedure.yaml", PROCEDURE),
            ("declarations/manifest.yaml", PROCEDURE_MANIFEST),
        ),
        facet_bytes=FACETS,
    )

    source = resolve_external_cumulative_source_from_path(
        str(tmp_path),
        manifest_path,
        lock_path,
        "projection/manifest",
        {
            "context.available": True,
            "projection.enabled": True,
            "projection.optional": False,
            "projection.stable": True,
            "projection.done": False,
        },
    )

    assert source.contributors == (
        "projection/all-modalities",
        "projection/branching-procedure",
        "projection/transform",
    )
    assert "**`projection/transform@1`.**" in source.text


def test_cumulative_contributors_include_rendered_rule_set_frame(
    tmp_path: Path,
) -> None:
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="projection",
        declaration_files=(
            ("declarations/rule-set.yaml", ACTIVE_RULE_SET),
            ("declarations/manifest.yaml", RULE_SET_MANIFEST),
        ),
        facet_bytes=FACETS,
    )

    source = resolve_external_cumulative_source_from_path(
        str(tmp_path),
        manifest_path,
        lock_path,
        "projection/rule-set-manifest",
        {
            "context.available": True,
            "projection.enabled": True,
            "projection.optional": False,
            "projection.stable": True,
            "projection.done": False,
        },
    )

    assert source.selection.records == ("projection/framed-rule",)
    assert source.contributors == (
        "projection/strategic-rules",
        "projection/framed-rule",
    )
    assert "# Strategic rules" in source.text


def test_reports_valid_empty_component_set_explicitly(tmp_path: Path) -> None:
    manifest = b"""\
_schema: eutaxis:declaration@1
id: packet/empty-manifest
kind: composition-manifest
owner: packet
status: active
source-revision: manifest-revision
applicability: {facet: packet.enabled, operator: equals, value: true}
relations: []
mechanism: cumulative
scope: project
target: EMPTY.md
sections:
  - id: core
    declarations: [packet/package]
policies: []
"""
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="packet",
        declaration_files=(
            ("declarations/package.yaml", RULE_SET),
            ("declarations/manifest.yaml", manifest),
        ),
    )

    source = resolve_external_cumulative_source_from_path(
        str(tmp_path),
        manifest_path,
        lock_path,
        "packet/empty-manifest",
        {"context.available": True, "packet.enabled": True},
    )

    assert source.selection.records == ()
    assert source.contributors == ()
