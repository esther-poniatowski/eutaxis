"""Tests for concise structured-selection reports used by artifact facades."""

from __future__ import annotations

from pathlib import Path

import pytest

import eutaxis.declarations.facade_report as facade_module
import eutaxis.declarations.external_result as external_result_module
from eutaxis.declarations import (
    ExternalCumulativeSourceRequest,
    ResolvedArtifactSelection,
    ResolvedCumulativeSource,
    acquire_external_declarations_from_path,
    build_declaration_catalog,
    resolve_external_cumulative_source,
    resolve_external_cumulative_sources,
    resolve_external_cumulative_source_from_path,
    resolve_external_compilation_unit,
    resolved_artifact_selection,
)
from eutaxis.declarations.external_result import _retire_external_result_tree
from eutaxis.declarations.exceptions import AcquisitionContractError
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


def _two_manifest_contract(tmp_path: Path) -> tuple[str, str]:
    second_manifest = MANIFEST.replace(
        b"id: resolution/manifest",
        b"id: resolution/second-manifest",
    ).replace(b"target: AGENTS.md", b"target: SECOND.md")
    return _write_contract(
        tmp_path,
        namespace="resolution",
        declaration_files=(
            ("declarations/rule.yaml", RULE),
            ("declarations/manifest.yaml", MANIFEST),
            ("declarations/second-manifest.yaml", second_manifest),
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


def test_caller_owned_facade_returns_detached_equivalent_report(
    tmp_path: Path,
) -> None:
    manifest_path, lock_path = _contract(tmp_path)
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    catalog = build_declaration_catalog(acquisition)
    source = resolve_external_cumulative_source(
        acquisition,
        "resolution/manifest",
        _context(),
    )
    _retire_external_result_tree(acquisition)

    expected = resolve_external_cumulative_source_from_path(
        str(tmp_path),
        manifest_path,
        lock_path,
        "resolution/manifest",
        _context(),
    )

    assert source == expected
    assert source.text == expected.text
    with pytest.raises(Exception, match="not issued"):
        catalog.get("resolution/purpose")


def test_cumulative_source_batch_preserves_order_and_equivalence(
    tmp_path: Path,
) -> None:
    manifest_path, lock_path = _two_manifest_contract(tmp_path)
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    requests = (
        ExternalCumulativeSourceRequest("resolution/second-manifest", _context()),
        ExternalCumulativeSourceRequest("resolution/manifest", _context()),
    )
    try:
        actual = resolve_external_cumulative_sources(acquisition, requests)
        expected = tuple(
            resolve_external_cumulative_source(
                acquisition,
                request.composition_manifest,
                request.context,
            )
            for request in requests
        )
    finally:
        _retire_external_result_tree(acquisition)

    assert actual == expected
    assert tuple(item.selection.manifest for item in actual) == (
        "resolution/second-manifest",
        "resolution/manifest",
    )


def test_cumulative_source_batch_authenticates_acquisition_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, lock_path = _two_manifest_contract(tmp_path)
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    original = external_result_module._authenticate_external_result_state
    call_count = 0

    def authenticate(value: object):
        nonlocal call_count
        call_count += 1
        return original(value)

    monkeypatch.setattr(
        external_result_module,
        "_authenticate_external_result_state",
        authenticate,
    )
    try:
        resolve_external_cumulative_sources(
            acquisition,
            (
                ExternalCumulativeSourceRequest(
                    "resolution/manifest", _context()
                ),
                ExternalCumulativeSourceRequest(
                    "resolution/second-manifest", _context()
                ),
            ),
        )
    finally:
        _retire_external_result_tree(acquisition)

    assert call_count == 2


def test_cumulative_source_batch_snapshots_nested_contexts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, lock_path = _contract(tmp_path)
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    nested = {"nested": {"value": 1}}
    sentinel = object()

    def resolve(_acquisition, _manifest, context):
        nested["nested"]["value"] = 2
        assert context["nested"]["value"] == 1
        return sentinel

    monkeypatch.setattr(facade_module, "resolve_external_cumulative_source", resolve)
    try:
        actual = resolve_external_cumulative_sources(
            acquisition,
            (ExternalCumulativeSourceRequest("resolution/manifest", nested),),
        )
    finally:
        _retire_external_result_tree(acquisition)

    assert actual == (sentinel,)


def test_cumulative_source_batch_rejects_success_with_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, lock_path = _contract(tmp_path)
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )

    def resolve(_acquisition, _manifest, _context):
        object.__setattr__(acquisition.source_coordinates[-1], "path", "forged.yaml")
        return object()

    monkeypatch.setattr(facade_module, "resolve_external_cumulative_source", resolve)

    with pytest.raises(AcquisitionContractError, match="coordinate state changed"):
        resolve_external_cumulative_sources(
            acquisition,
            (ExternalCumulativeSourceRequest("resolution/manifest", _context()),),
        )


def test_cumulative_source_batch_prioritizes_hostile_iterator_mutation(
    tmp_path: Path,
) -> None:
    manifest_path, lock_path = _contract(tmp_path)
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )

    class HostileRequests:
        def __iter__(self):
            object.__setattr__(
                acquisition.source_coordinates[-1], "path", "forged.yaml"
            )
            raise RuntimeError("request iteration failed")

    with pytest.raises(
        AcquisitionContractError,
        match="coordinate state changed",
    ) as captured:
        resolve_external_cumulative_sources(acquisition, HostileRequests())

    assert isinstance(captured.value.__cause__, RuntimeError)
    assert str(captured.value.__cause__) == "request iteration failed"


def test_caller_owned_facade_preserves_clean_body_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, lock_path = _contract(tmp_path)
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )

    def fail(_resolution):
        raise RuntimeError("resolution failed")

    monkeypatch.setattr(facade_module, "plan_external_cumulative_composition", fail)
    try:
        with pytest.raises(RuntimeError, match="resolution failed"):
            resolve_external_cumulative_source(
                acquisition,
                "resolution/manifest",
                _context(),
            )
        assert acquisition.source_coordinates
    finally:
        _retire_external_result_tree(acquisition)


def test_caller_owned_facade_rejects_success_with_nested_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, lock_path = _contract(tmp_path)
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    construct = facade_module.ResolvedCumulativeSource

    def mutate(*args, **kwargs):
        source = construct(*args, **kwargs)
        object.__setattr__(acquisition.source_coordinates[-1], "path", "forged.yaml")
        return source

    monkeypatch.setattr(facade_module, "ResolvedCumulativeSource", mutate)

    with pytest.raises(AcquisitionContractError, match="coordinate state changed"):
        resolve_external_cumulative_source(
            acquisition,
            "resolution/manifest",
            _context(),
        )


def test_caller_owned_facade_prioritizes_mutation_over_body_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, lock_path = _contract(tmp_path)
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )

    def mutate_and_fail(_resolution):
        object.__setattr__(acquisition.source_coordinates[-1], "path", "forged.yaml")
        raise RuntimeError("resolution failed")

    monkeypatch.setattr(
        facade_module,
        "plan_external_cumulative_composition",
        mutate_and_fail,
    )

    with pytest.raises(
        AcquisitionContractError, match="coordinate state changed"
    ) as captured:
        resolve_external_cumulative_source(
            acquisition,
            "resolution/manifest",
            _context(),
        )

    assert isinstance(captured.value.__cause__, RuntimeError)
    assert str(captured.value.__cause__) == "resolution failed"


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
