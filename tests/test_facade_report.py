"""Tests for concise structured-selection reports used by artifact facades."""

from __future__ import annotations

from pathlib import Path

from eutaxis.declarations import (
    acquire_external_declarations_from_path,
    resolve_external_cumulative_source_from_path,
    resolve_external_compilation_unit,
    resolved_artifact_selection,
)
from eutaxis.declarations.external_result import _retire_external_result_tree
from tests.test_external_acquisition import _write_contract
from tests.test_external_resolution import MANIFEST, RULE, _context
from tests.test_query_packet import RULE_SET


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
    assert source.source_revisions
    assert all(row.content_revision for row in source.source_revisions)
    assert b"**purpose**:" in source.content
    assert source.sha256.startswith("sha256:")


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
