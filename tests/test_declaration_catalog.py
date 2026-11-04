"""Tests for the portable static declaration catalog."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import cast

import pytest
import yaml

from eutaxis.declarations import (
    DeclarationCatalogError,
    DeclarationKind,
    DeclarationRegistry,
    ExactContractKey,
    load_declaration_registry,
    load_facet_registry,
)
from eutaxis.declarations.catalog import (
    _build_declaration_catalog_from_registry as build_declaration_catalog,
    _legacy_catalog_json_bytes as catalog_json_bytes,
)

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY_FIXTURES = FIXTURES / "registry" / "valid"
FACET_FIXTURE = FIXTURES / "facets" / "valid" / "context-facets.yaml"
GOLDEN_INDEX = FIXTURES / "catalog" / "static-index.json"


def _paths(root: Path) -> tuple[Path, ...]:
    return tuple(sorted(root.glob("*.yaml")))


def _registry(root: Path = REGISTRY_FIXTURES) -> DeclarationRegistry:
    return load_declaration_registry(
        reversed(_paths(root)), load_facet_registry(FACET_FIXTURE)
    )


def _catalog(root: Path = REGISTRY_FIXTURES):
    return build_declaration_catalog(_registry(root), source_root=root)


def _copy_corpus(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copytree(REGISTRY_FIXTURES, target)
    return target


def _index(catalog) -> dict[str, object]:
    return cast(dict[str, object], json.loads(catalog_json_bytes(catalog)))


def _entries(index: dict[str, object], field: str) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], index[field])


def test_catalog_reuses_registered_records_and_has_exact_lookup_semantics() -> None:
    registry = _registry()
    catalog = build_declaration_catalog(registry, source_root=REGISTRY_FIXTURES)

    assert catalog.get("content/base") is registry.records["content/base"]
    assert catalog.get("missing") is None
    assert (
        catalog.get_contract(DeclarationKind.EVALUATOR, "registry/manual", 1)
        is registry.families["registry/manual"].versions[1]
    )
    assert (
        catalog.get_contract(DeclarationKind.OPERATION, "registry/write", 1)
        is registry.families["registry/write"].versions[1]
    )
    assert catalog.get_contract(DeclarationKind.EVALUATOR, "registry/write", 1) is None
    assert catalog.get_contract(DeclarationKind.OPERATION, "registry/write", 2) is None
    with pytest.raises(ValueError, match="not an exact contract kind"):
        catalog.get_contract(DeclarationKind.RULE, "content/base", 1)
    with pytest.raises(TypeError):
        cast(dict[str, object], catalog.declarations)["new"] = registry.records[
            "content/base"
        ]
    with pytest.raises(TypeError):
        cast(dict[ExactContractKey, object], catalog.contracts)[
            ExactContractKey(DeclarationKind.EVALUATOR, "new", 1)
        ] = registry.families["registry/manual"].versions[1]


def test_catalog_json_is_deterministic_under_registry_iteration_changes() -> None:
    registry = _registry()
    shuffled = DeclarationRegistry(
        paths=tuple(reversed(registry.paths)),
        records=MappingProxyType(dict(reversed(tuple(registry.records.items())))),
        families=MappingProxyType(dict(reversed(tuple(registry.families.items())))),
        conflicts=frozenset(reversed(tuple(registry.conflicts))),
        facet_registry=registry.facet_registry,
    )

    first = catalog_json_bytes(
        build_declaration_catalog(registry, source_root=REGISTRY_FIXTURES)
    )
    second = catalog_json_bytes(
        build_declaration_catalog(shuffled, source_root=REGISTRY_FIXTURES)
    )

    assert first == second
    assert first.endswith(b"\n")
    assert not first.endswith(b"\n\n")


def test_catalog_serializer_rejects_unissued_reordered_copy() -> None:
    catalog = _catalog()
    reordered = replace(
        catalog,
        sources=tuple(reversed(catalog.sources)),
        declarations=MappingProxyType(
            dict(reversed(tuple(catalog.declarations.items())))
        ),
        contracts=MappingProxyType(dict(reversed(tuple(catalog.contracts.items())))),
        conflicts=tuple(
            reversed(tuple(tuple(reversed(pair)) for pair in catalog.conflicts))
        ),
    )

    with pytest.raises(DeclarationCatalogError, match="not issued here"):
        catalog_json_bytes(reordered)
    assert catalog_json_bytes(catalog) == catalog_json_bytes(catalog)


def test_catalog_json_is_relocatable_and_preserves_unicode(tmp_path: Path) -> None:
    first_root = _copy_corpus(tmp_path, "first")
    second_root = _copy_corpus(tmp_path, "second")
    for root in (first_root, second_root):
        path = root / "alternate-rule.yaml"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["source-revision"] = "révision-π"
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    first = catalog_json_bytes(_catalog(first_root))
    second = catalog_json_bytes(_catalog(second_root))

    assert first == second
    assert "révision-π".encode() in first
    assert str(tmp_path).encode() not in first


def test_catalog_rejects_sources_outside_the_explicit_root(tmp_path: Path) -> None:
    with pytest.raises(DeclarationCatalogError, match="outside source root"):
        build_declaration_catalog(_registry(), source_root=tmp_path)


def test_catalog_rejects_a_source_file_as_the_root() -> None:
    with pytest.raises(DeclarationCatalogError, match="is not a directory"):
        build_declaration_catalog(
            _registry(), source_root=REGISTRY_FIXTURES / "alternate-rule.yaml"
        )


def test_empty_catalog_serializes_under_the_shared_index_schema() -> None:
    registry = DeclarationRegistry(
        paths=(),
        records=MappingProxyType({}),
        families=MappingProxyType({}),
        conflicts=frozenset(),
        facet_registry=_registry().facet_registry,
    )
    catalog = build_declaration_catalog(registry, source_root=REGISTRY_FIXTURES)

    assert json.loads(catalog_json_bytes(catalog)) == {
        "conflicts": [],
        "contracts": [],
        "declarations": [],
        "index-revision": 1,
        "sources": [],
    }


def test_catalog_uses_the_source_snapshot_captured_during_loading(
    tmp_path: Path,
) -> None:
    root = _copy_corpus(tmp_path, "registry")
    registry = _registry(root)
    before = catalog_json_bytes(build_declaration_catalog(registry, source_root=root))
    path = root / "alternate-rule.yaml"
    captured_hash = next(
        source.sha256
        for source in build_declaration_catalog(registry, source_root=root).sources
        if source.path == "alternate-rule.yaml"
    )
    assert captured_hash == hashlib.sha256(path.read_bytes()).hexdigest()

    path.write_text(path.read_text(encoding="utf-8") + "# changed later\n")
    after = catalog_json_bytes(build_declaration_catalog(registry, source_root=root))

    assert after == before
    assert captured_hash != hashlib.sha256(path.read_bytes()).hexdigest()


def test_catalog_index_has_portable_structured_provenance_and_order() -> None:
    catalog = _catalog()
    index = _index(catalog)
    declarations = _entries(index, "declarations")
    contracts = _entries(index, "contracts")
    sources = cast(list[dict[str, str]], index["sources"])

    assert list(index) == [
        "conflicts",
        "contracts",
        "declarations",
        "index-revision",
        "sources",
    ]
    declaration_ids = [cast(str, entry["id"]) for entry in declarations]
    assert declaration_ids == sorted(declaration_ids)
    contract_order = [
        (
            cast(str, entry["kind"]),
            cast(str, entry["id"]),
            cast(int, entry["version"]),
        )
        for entry in contracts
    ]
    assert contract_order == sorted(contract_order)
    assert [source["path"] for source in sources] == sorted(
        source["path"] for source in sources
    )
    assert index["conflicts"] == [["content/alternate", "content/refined"]]
    policy = [
        entry for entry in declarations if entry["id"] == "registry/prefer-refined"
    ]
    assert len(policy) == 1
    policy_query = cast(dict[str, object], policy[0]["query"])
    assert policy_query["conflicts"] == index["conflicts"][0]

    package = [entry for entry in declarations if entry["id"] == "content/package"]
    nested = [entry for entry in declarations if entry["id"] == "content/base"]
    assert len(package) == len(nested) == 1
    assert cast(dict[str, object], package[0]["source"])["document-path"] == []
    nested_source = cast(dict[str, object], nested[0]["source"])
    assert nested_source["document-path"] == ["rules", 0]
    assert nested[0]["containing-rule-set"] == "content/package"
    assert isinstance(nested_source["line"], int)
    assert isinstance(nested_source["column"], int)
    assert all(not Path(source["path"]).is_absolute() for source in sources)

    entry_keys = {
        "applicability",
        "containing-rule-set",
        "id",
        "kind",
        "owner",
        "query",
        "relations",
        "schema-version",
        "source",
        "source-revision",
        "status",
    }
    assert all(set(entry) == entry_keys for entry in declarations)
    assert all(set(entry) == entry_keys | {"version"} for entry in contracts)
    serialized = catalog_json_bytes(catalog)
    for excluded in (
        b"generated-at",
        b'"effective"',
        b'"selected"',
        b'"waived"',
        b'"overridden"',
        b"markdown",
    ):
        assert excluded not in serialized


def test_catalog_json_matches_the_reviewed_golden_index() -> None:
    assert catalog_json_bytes(_catalog()) == GOLDEN_INDEX.read_bytes()
