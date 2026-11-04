"""Revision 2 catalog tests for authenticated external acquisition results."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import cast

import pytest

import eutaxis.declarations.catalog as catalog_module
import eutaxis.declarations.external_result as result_module
from eutaxis.declarations import (
    AcquisitionKind,
    AcquisitionSourceCoordinate,
    DeclarationCatalogError,
    EnforcementClass,
    ExternalAcquisitionResult,
    StaticCatalogQuery,
    build_declaration_catalog,
    catalog_json_bytes,
    load_persisted_catalog_index,
)
from eutaxis.declarations.acquisition_contract import GitLock
from eutaxis.declarations.external_result import _issued_external_result_state
from tests.test_external_acquisition import _build_git_workspace, _write_contract

V1_GOLDEN = Path(__file__).parent / "fixtures" / "catalog" / "static-index.json"
V2_GOLDEN = Path(__file__).parent / "fixtures" / "catalog" / "static-index-v2.json"


def _acquire(
    workspace: Path,
    *,
    kind: AcquisitionKind = AcquisitionKind.WORKSPACE,
    root: str = ".",
    git: GitLock | None = None,
) -> ExternalAcquisitionResult:
    manifest_path, lock_path = _write_contract(workspace, kind=kind, root=root, git=git)
    return result_module.acquire_external_declarations_from_path(
        str(workspace), manifest_path, lock_path
    )


def _document(result: ExternalAcquisitionResult) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(catalog_json_bytes(build_declaration_catalog(result))),
    )


def _rich_revision_2_document() -> dict[str, object]:
    """Convert the reviewed revision 1 fixture without changing its rows."""
    document = cast(dict[str, object], json.loads(V1_GOLDEN.read_bytes()))
    document["index-revision"] = 2
    document["facet-content-revision"] = "sha256:" + "0" * 64
    for source in cast(list[dict[str, object]], document["sources"]):
        source["namespace"] = "alpha"
        source["sha256"] = "sha256:" + cast(str, source["sha256"])
    for row in (
        *cast(list[dict[str, object]], document["declarations"]),
        *cast(list[dict[str, object]], document["contracts"]),
    ):
        cast(dict[str, object], row["source"])["namespace"] = "alpha"
    return document


def test_public_builder_emits_revision_2_from_issued_result(tmp_path: Path) -> None:
    result = _acquire(tmp_path)
    catalog = build_declaration_catalog(result)
    document = _document(result)

    assert catalog.revision == 2
    assert catalog.facet_content_revision == result.facet_registry.content_revision
    assert document["index-revision"] == 2
    assert document["facet-content-revision"] == result.facet_registry.content_revision
    assert document["sources"] == [
        {
            "namespace": coordinate.namespace,
            "path": coordinate.path,
            "sha256": coordinate.sha256,
        }
        for coordinate in sorted(
            result.source_coordinates,
            key=lambda item: (item.namespace, item.path),
        )
    ]
    rows = cast(list[dict[str, object]], document["declarations"]) + cast(
        list[dict[str, object]], document["contracts"]
    )
    source_keys = {
        (row["namespace"], row["path"])
        for row in cast(list[dict[str, object]], document["sources"])
    }
    assert {
        (
            cast(dict[str, object], row["source"])["namespace"],
            cast(dict[str, object], row["source"])["path"],
        )
        for row in rows
    } == source_keys
    assert all("sha256" not in cast(dict[str, object], row["source"]) for row in rows)

    loaded = load_persisted_catalog_index(catalog_json_bytes(catalog))
    assert loaded.revision == 2
    assert loaded.facet_content_revision == catalog.facet_content_revision
    assert tuple((item.namespace, item.path) for item in loaded.sources) == tuple(
        (item.namespace, item.path) for item in catalog.sources
    )
    assert catalog_json_bytes(catalog) == V2_GOLDEN.read_bytes()
    assert not hasattr(catalog, "source_map")
    assert not hasattr(catalog, "authority")
    assert not hasattr(catalog, "authority_state")
    assert not hasattr(catalog, "projection_state")


def test_builder_rejects_raw_registry_and_source_root(tmp_path: Path) -> None:
    result = _acquire(tmp_path)
    registry = _issued_external_result_state(result).external_registry_state.registry
    with pytest.raises(Exception, match="not issued here"):
        build_declaration_catalog(registry)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="source_root"):
        build_declaration_catalog(result, source_root=tmp_path)  # type: ignore[call-arg]


def test_complete_catalog_is_transport_independent(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    vendored_root = tmp_path / "vendored"
    git_root = tmp_path / "git"
    workspace_root.mkdir()
    vendored_root.mkdir()
    git_root.mkdir()

    workspace = _acquire(workspace_root)
    vendored = _acquire(
        vendored_root,
        kind=AcquisitionKind.VENDORED,
        root="vendor/oikos",
    )
    git_workspace, git_locks = _build_git_workspace(
        git_root, (("oikos", "vendor/oikos", True),)
    )
    git_result = _acquire(
        git_workspace,
        kind=AcquisitionKind.GIT_SUBMODULE,
        root="vendor/oikos",
        git=git_locks["oikos"],
    )

    payloads = {
        catalog_json_bytes(build_declaration_catalog(item))
        for item in (workspace, vendored, git_result)
    }
    assert len(payloads) == 1
    assert (
        len(
            {
                item.lock.sources[0].acquisition_revision
                for item in (workspace, vendored, git_result)
            }
        )
        == 3
    )


def test_revision_1_golden_remains_readable_without_invented_namespace() -> None:
    loaded = load_persisted_catalog_index(V1_GOLDEN.read_bytes())

    assert loaded.revision == 1
    assert loaded.facet_content_revision is None
    assert all(source.namespace is None for source in loaded.sources)
    assert all(row.source.namespace is None for row in loaded.declarations.values())
    with pytest.raises(DeclarationCatalogError, match="not issued here"):
        catalog_json_bytes(cast(object, loaded))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda document: document.pop("facet-content-revision"),
        lambda document: document.update({"facet-content-revision": "0" * 64}),
        lambda document: document.update(
            {"facet-content-revision": "sha256:" + "0" * 64 + "\n"}
        ),
        lambda document: cast(list[dict[str, object]], document["sources"])[0].pop(
            "namespace"
        ),
        lambda document: cast(list[dict[str, object]], document["sources"])[0].update(
            {"sha256": "0" * 64}
        ),
        lambda document: cast(
            dict[str, object],
            cast(list[dict[str, object]], document["declarations"])[0]["source"],
        ).update({"transport": "workspace"}),
    ],
)
def test_revision_2_schema_rejects_missing_or_transport_fields(
    tmp_path: Path,
    mutation,
) -> None:
    document = _document(_acquire(tmp_path))
    mutation(document)

    with pytest.raises(DeclarationCatalogError, match="Invalid catalog index"):
        load_persisted_catalog_index(json.dumps(document).encode())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("namespace", ""),
        ("namespace", "-owner"),
        ("namespace", "owner-"),
        ("namespace", "Owner"),
        ("namespace", "owner_name"),
        ("namespace", "owner\n"),
        ("path", "/absolute.yaml"),
        ("path", "a\\b.yaml"),
        ("path", "a/../b.yaml"),
        ("path", "a/./b.yaml"),
        ("path", "a//b.yaml"),
        ("path", "a/\ud800.yaml"),
        ("sha256", "0" * 64),
        ("sha256", "sha256:" + "A" * 64),
        ("sha256", "sha256:" + "0" * 63),
        ("sha256", "sha256:" + "0" * 64 + "\n"),
    ],
)
def test_revision_2_rejects_each_source_coordinate_grammar(
    tmp_path: Path, field: str, value: str
) -> None:
    document = _document(_acquire(tmp_path))
    cast(list[dict[str, object]], document["sources"])[0][field] = value

    with pytest.raises(DeclarationCatalogError):
        load_persisted_catalog_index(json.dumps(document).encode())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("document-path", [True]),
        ("document-path", [-1]),
        ("line", 0),
        ("line", -1),
        ("line", True),
        ("column", 0),
        ("column", -1),
        ("column", True),
    ],
)
def test_revision_2_rejects_malformed_record_positions(
    tmp_path: Path, field: str, value: object
) -> None:
    document = _document(_acquire(tmp_path))
    source = cast(
        dict[str, object],
        cast(list[dict[str, object]], document["declarations"])[0]["source"],
    )
    source[field] = value

    with pytest.raises(DeclarationCatalogError, match="Invalid catalog index"):
        load_persisted_catalog_index(json.dumps(document).encode())


def test_revision_2_rejects_duplicate_unknown_or_orphan_source_pairs(
    tmp_path: Path,
) -> None:
    document = _document(_acquire(tmp_path))
    sources = cast(list[dict[str, object]], document["sources"])
    sources.append(dict(sources[0]))
    with pytest.raises(DeclarationCatalogError, match="duplicate source coordinate"):
        load_persisted_catalog_index(json.dumps(document).encode())

    document = _document(_acquire(tmp_path / "unknown"))
    row_source = cast(
        dict[str, object],
        cast(list[dict[str, object]], document["declarations"])[0]["source"],
    )
    row_source["namespace"] = "unknown"
    with pytest.raises(DeclarationCatalogError, match="unknown source path"):
        load_persisted_catalog_index(json.dumps(document).encode())

    document = _document(_acquire(tmp_path / "orphan"))
    cast(list[dict[str, object]], document["sources"]).append(
        {
            "namespace": "orphan",
            "path": "rules.yaml",
            "sha256": "sha256:" + "0" * 64,
        }
    )
    with pytest.raises(DeclarationCatalogError, match="orphan source path"):
        load_persisted_catalog_index(json.dumps(document).encode())


def test_revision_2_rejects_cross_collection_coordinate_collision(
    tmp_path: Path,
) -> None:
    document = _document(_acquire(tmp_path))
    declaration_source = cast(
        dict[str, object],
        cast(list[dict[str, object]], document["declarations"])[0]["source"],
    )
    contract_source = cast(
        dict[str, object],
        cast(list[dict[str, object]], document["contracts"])[0]["source"],
    )
    declaration_source.update(contract_source)

    with pytest.raises(DeclarationCatalogError, match="duplicate source coordinate"):
        load_persisted_catalog_index(json.dumps(document).encode())


def test_same_path_in_two_namespaces_is_valid_and_sorted(tmp_path: Path) -> None:
    from tests.test_external_acquisition import _write_multi_contract

    manifest_path, lock_path = _write_multi_contract(
        tmp_path,
        specs=(
            ("zeta", AcquisitionKind.WORKSPACE, "."),
            ("alpha", AcquisitionKind.VENDORED, "vendor/alpha"),
        ),
        extension_order=("zeta", "alpha"),
    )
    result = result_module.acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    document = _document(result)
    pairs = [
        (cast(str, row["namespace"]), cast(str, row["path"]))
        for row in cast(list[dict[str, object]], document["sources"])
    ]

    assert pairs == sorted(pairs)
    assert ("alpha", "declarations/process-core.yaml") in pairs
    assert ("zeta", "declarations/process-core.yaml") in pairs


def test_embedded_rule_cannot_cross_namespace_at_the_same_path() -> None:
    document = _rich_revision_2_document()
    declarations = cast(list[dict[str, object]], document["declarations"])
    embedded = next(row for row in declarations if row["containing-rule-set"])
    embedded_source = cast(dict[str, object], embedded["source"])
    original_source = next(
        row
        for row in cast(list[dict[str, object]], document["sources"])
        if row["path"] == embedded_source["path"]
    )
    cast(list[dict[str, object]], document["sources"]).append(
        {**original_source, "namespace": "beta"}
    )
    embedded_source["namespace"] = "beta"

    with pytest.raises(DeclarationCatalogError, match="must share a source"):
        load_persisted_catalog_index(json.dumps(document).encode())


def test_ordinary_projection_failure_preserves_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _acquire(tmp_path)

    def fail(_state, _result):
        raise RuntimeError("projection failed")

    monkeypatch.setattr(catalog_module, "_build_external_catalog", fail)
    with pytest.raises(RuntimeError, match="projection failed"):
        build_declaration_catalog(result)
    assert result.source_coordinates


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_catalog_authority_issue_interruption_retires_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: type[BaseException],
) -> None:
    result = _acquire(tmp_path)
    issue = catalog_module._CATALOG_AUTHORITIES.issue
    published = []

    def interrupt(catalog, state):
        issue(catalog, state)
        published.append(catalog)
        raise failure("catalog issue interrupted")

    monkeypatch.setattr(catalog_module._CATALOG_AUTHORITIES, "issue", interrupt)
    with pytest.raises(failure, match="catalog issue interrupted"):
        build_declaration_catalog(result)
    assert len(published) == 1
    assert catalog_module._CATALOG_AUTHORITIES.state(published[0]) is None
    assert result.source_coordinates


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_catalog_post_publication_authentication_interruption_retires_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: type[BaseException],
) -> None:
    result = _acquire(tmp_path)
    authenticate = catalog_module._authenticate_catalog_state
    published = []
    issue = catalog_module._CATALOG_AUTHORITIES.issue

    def capture(catalog, state):
        published.append(catalog)
        return issue(catalog, state)

    def interrupt(_catalog):
        raise failure("catalog authentication interrupted")

    monkeypatch.setattr(catalog_module._CATALOG_AUTHORITIES, "issue", capture)
    monkeypatch.setattr(catalog_module, "_authenticate_catalog_state", interrupt)
    with pytest.raises(failure, match="catalog authentication interrupted"):
        build_declaration_catalog(result)
    assert len(published) == 1
    assert catalog_module._CATALOG_AUTHORITIES.state(published[0]) is None
    monkeypatch.setattr(catalog_module, "_authenticate_catalog_state", authenticate)
    assert result.source_coordinates


def test_result_authentication_failure_retires_catalog_authority(
    tmp_path: Path,
) -> None:
    result = _acquire(tmp_path)
    catalog = build_declaration_catalog(result)
    object.__setattr__(result.source_coordinates[-1], "path", "forged.yaml")

    with pytest.raises(Exception, match="coordinate state changed"):
        catalog.get(next(iter(catalog.declarations)))
    assert catalog_module._CATALOG_AUTHORITIES.state(catalog) is None


@pytest.mark.parametrize("field", ["facet", "sources", "declarations"])
def test_serializer_rejects_post_build_catalog_mutation(
    tmp_path: Path, field: str
) -> None:
    catalog = build_declaration_catalog(_acquire(tmp_path))
    original = {
        "facet": catalog.facet_content_revision,
        "sources": catalog.sources,
        "declarations": catalog.declarations,
    }[field]
    if field == "facet":
        object.__setattr__(catalog, "facet_content_revision", "sha256:" + "0" * 64)
    elif field == "sources":
        object.__setattr__(catalog, "sources", tuple(reversed(catalog.sources)))
    else:
        object.__setattr__(
            catalog,
            "declarations",
            MappingProxyType(dict(reversed(tuple(catalog.declarations.items())))),
        )

    with pytest.raises(DeclarationCatalogError, match="projection state changed"):
        catalog_json_bytes(catalog)
    assert catalog_module._CATALOG_AUTHORITIES.state(catalog) is None
    object.__setattr__(
        catalog,
        {
            "facet": "facet_content_revision",
            "sources": "sources",
            "declarations": "declarations",
        }[field],
        original,
    )
    with pytest.raises(DeclarationCatalogError, match="not issued here"):
        catalog_json_bytes(catalog)


def test_replaced_catalog_cannot_splice_another_result_authority(
    tmp_path: Path,
) -> None:
    first = build_declaration_catalog(_acquire(tmp_path / "first"))
    second = build_declaration_catalog(_acquire(tmp_path / "second"))
    forged = replace(first, sources=second.sources)

    with pytest.raises(DeclarationCatalogError, match="not issued here"):
        catalog_json_bytes(forged)


@pytest.mark.parametrize(
    "operation",
    [
        lambda catalog: catalog.get(next(iter(catalog.declarations))),
        lambda catalog: catalog.get_contract(
            (key := next(iter(catalog.contracts))).kind, key.id, key.version
        ),
        lambda catalog: catalog.filter_static(StaticCatalogQuery()),
        lambda catalog: catalog.filter_enforcement(EnforcementClass.DELIBERATIVE),
    ],
)
def test_every_public_query_authenticates_projection(tmp_path: Path, operation) -> None:
    catalog = build_declaration_catalog(_acquire(tmp_path))
    object.__setattr__(catalog, "conflicts", (*catalog.conflicts, ("a", "b")))

    with pytest.raises(DeclarationCatalogError, match="projection state changed"):
        operation(catalog)


def test_query_rejects_nested_registered_record_mutation(tmp_path: Path) -> None:
    catalog = build_declaration_catalog(_acquire(tmp_path))
    record = next(iter(catalog.declarations.values()))
    object.__setattr__(record.declaration, "status", "retired")

    with pytest.raises(Exception, match="state changed"):
        catalog.get(record.declaration.id)


def test_query_success_path_mutation_fails_final_authentication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = build_declaration_catalog(_acquire(tmp_path))
    match = catalog_module.matches_static_query
    changed = False

    def mutate(*args, **kwargs):
        nonlocal changed
        result = match(*args, **kwargs)
        if not changed:
            changed = True
            object.__setattr__(catalog, "conflicts", (("a", "b"),))
        return result

    monkeypatch.setattr(catalog_module, "matches_static_query", mutate)
    with pytest.raises(DeclarationCatalogError, match="projection state changed"):
        catalog.filter_static(StaticCatalogQuery())


def test_query_failure_and_authentication_failure_preserve_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = build_declaration_catalog(_acquire(tmp_path))

    def fail(*_args, **_kwargs):
        object.__setattr__(catalog, "conflicts", (("a", "b"),))
        raise RuntimeError("query failed first")

    monkeypatch.setattr(catalog_module, "matches_static_query", fail)
    with pytest.raises(
        DeclarationCatalogError, match="projection state changed"
    ) as captured:
        catalog.filter_static(StaticCatalogQuery())
    assert isinstance(captured.value.__cause__, RuntimeError)
    assert str(captured.value.__cause__) == "query failed first"


def test_private_source_correlation_substitution_is_rejected(tmp_path: Path) -> None:
    catalog = build_declaration_catalog(_acquire(tmp_path))
    state = catalog_module._issued_catalog_state(catalog)
    catalog_module._CATALOG_AUTHORITIES.issue(
        catalog,
        state._replace(source_map=tuple(item for item in state.source_map)),
    )

    with pytest.raises(DeclarationCatalogError, match="source correlation changed"):
        catalog_json_bytes(catalog)
    assert catalog_module._CATALOG_AUTHORITIES.state(catalog) is None


def test_serialization_success_path_mutation_fails_final_authentication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = build_declaration_catalog(_acquire(tmp_path))
    project = catalog_module._entry_payload
    changed = False

    def mutate(*args, **kwargs):
        nonlocal changed
        payload = project(*args, **kwargs)
        if not changed:
            changed = True
            object.__setattr__(catalog, "conflicts", (("a", "b"),))
        return payload

    monkeypatch.setattr(catalog_module, "_entry_payload", mutate)
    with pytest.raises(DeclarationCatalogError, match="projection state changed"):
        catalog_json_bytes(catalog)


def test_serialization_failure_and_authentication_failure_preserve_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = build_declaration_catalog(_acquire(tmp_path))

    def fail(*_args, **_kwargs):
        object.__setattr__(catalog, "conflicts", (("a", "b"),))
        raise RuntimeError("serialization failed first")

    monkeypatch.setattr(catalog_module, "_entry_payload", fail)
    with pytest.raises(
        DeclarationCatalogError, match="projection state changed"
    ) as captured:
        catalog_json_bytes(catalog)
    assert isinstance(captured.value.__cause__, RuntimeError)
    assert str(captured.value.__cause__) == "serialization failed first"


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_serialization_failure_without_mutation_preserves_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: type[BaseException],
) -> None:
    catalog = build_declaration_catalog(_acquire(tmp_path))
    original = catalog_module._entry_payload

    def fail(*_args, **_kwargs):
        raise failure("serialization stopped")

    monkeypatch.setattr(catalog_module, "_entry_payload", fail)
    with pytest.raises(failure, match="serialization stopped"):
        catalog_json_bytes(catalog)
    monkeypatch.setattr(catalog_module, "_entry_payload", original)
    assert catalog_json_bytes(catalog)


def test_projection_failure_and_authentication_failure_preserve_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _acquire(tmp_path)

    def fail(_state, _result):
        object.__setattr__(result.source_coordinates[-1], "path", "forged.yaml")
        raise RuntimeError("projection failed first")

    monkeypatch.setattr(catalog_module, "_build_external_catalog", fail)
    with pytest.raises(Exception, match="coordinate state changed") as captured:
        build_declaration_catalog(result)
    assert isinstance(captured.value.__cause__, RuntimeError)
    assert str(captured.value.__cause__) == "projection failed first"


def test_success_path_mutation_fails_final_authentication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _acquire(tmp_path)
    build = catalog_module._build_external_catalog

    def mutate(state, value):
        catalog = build(state, value)
        object.__setattr__(result.source_coordinates[-1], "path", "forged.yaml")
        return catalog

    monkeypatch.setattr(catalog_module, "_build_external_catalog", mutate)
    with pytest.raises(Exception, match="coordinate state changed"):
        build_declaration_catalog(result)


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_final_authentication_failure_retires_result_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: type[BaseException],
) -> None:
    result = _acquire(tmp_path)
    authenticate = result_module._authenticate_external_result_state
    calls = 0

    def fail_after_build(value):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise failure("final authentication failed")
        return authenticate(value)

    monkeypatch.setattr(
        result_module, "_authenticate_external_result_state", fail_after_build
    )
    with pytest.raises(failure, match="final authentication failed"):
        build_declaration_catalog(result)
    with pytest.raises(Exception, match="not issued here"):
        _issued_external_result_state(result)


def test_coordinate_substitution_is_rejected_before_projection(tmp_path: Path) -> None:
    result = _acquire(tmp_path)
    state = _issued_external_result_state(result)
    coordinate = state.source_coordinates[-1]
    forged = AcquisitionSourceCoordinate(
        coordinate.namespace, "forged.yaml", coordinate.sha256
    )
    result_module._RESULT_AUTHORITIES.issue(
        result,
        state._replace(source_coordinates=(*state.source_coordinates[:-1], forged)),
    )

    with pytest.raises(Exception, match="source coordinate state changed"):
        build_declaration_catalog(result)
