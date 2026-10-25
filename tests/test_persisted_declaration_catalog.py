"""Tests for the validated persisted static-catalog projection."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import Callable, cast

import pytest

from eutaxis.declarations import (
    CatalogSource,
    DeclarationCatalogError,
    DeclarationKind,
    ExactContractKey,
    PersistedCatalogEntry,
    StaticCatalogQuery,
    StaticField,
    StaticPredicate,
    build_declaration_catalog,
    catalog_index_schema,
    catalog_json_bytes,
    load_declaration_registry,
    load_facet_registry,
    load_persisted_catalog_index,
)

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY_FIXTURES = FIXTURES / "registry" / "valid"
FACET_FIXTURE = FIXTURES / "facets" / "valid" / "context-facets.yaml"
GOLDEN_INDEX = FIXTURES / "catalog" / "static-index.json"


def _live_catalog():
    registry = load_declaration_registry(
        sorted(REGISTRY_FIXTURES.glob("*.yaml")), load_facet_registry(FACET_FIXTURE)
    )
    return build_declaration_catalog(registry, source_root=REGISTRY_FIXTURES)


def _document() -> dict[str, object]:
    return cast(dict[str, object], json.loads(GOLDEN_INDEX.read_bytes()))


def _bytes(document: object, *, pretty: bool = False) -> bytes:
    return json.dumps(
        document,
        indent=2 if pretty else None,
        ensure_ascii=False,
        allow_nan=True,
    ).encode("utf-8")


def _load_document(document: object):
    return load_persisted_catalog_index(_bytes(document))


def _declarations(document: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], document["declarations"])


def _contracts(document: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], document["contracts"])


def _evaluator_query(document: dict[str, object]) -> dict[str, object]:
    row = next(item for item in _contracts(document) if item["kind"] == "evaluator")
    return cast(dict[str, object], row["query"])


def _sources(document: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], document["sources"])


def _entry(document: dict[str, object], identifier: str) -> dict[str, object]:
    return next(row for row in _declarations(document) if row["id"] == identifier)


def _persisted_keys(rows: tuple[PersistedCatalogEntry, ...]) -> tuple[object, ...]:
    return tuple(
        (
            row.id
            if row.version is None
            else ExactContractKey(row.kind, row.id, row.version)
        )
        for row in rows
    )


def _live_keys(rows: tuple[object, ...]) -> tuple[object, ...]:
    keys: list[object] = []
    for row in rows:
        declaration = row.declaration  # type: ignore[attr-defined]
        version = getattr(declaration, "version", None)
        keys.append(
            declaration.id
            if version is None
            else ExactContractKey(declaration.kind, declaration.id, version)
        )
    return tuple(keys)


def test_packaged_schema_is_isolated_and_accepts_emitted_golden() -> None:
    first = catalog_index_schema()
    second = catalog_index_schema()
    first["title"] = "mutated"

    assert second["title"] == "Eutaxis static catalog index revision 1"
    loaded = load_persisted_catalog_index(
        catalog_json_bytes(_live_catalog()), source=GOLDEN_INDEX
    )
    assert loaded.revision == 1


def test_emitter_validates_its_payload_against_the_packaged_schema() -> None:
    catalog = _live_catalog()
    invalid = replace(
        catalog,
        sources=(
            CatalogSource(catalog.sources[0].path, "not-a-sha256"),
            *catalog.sources[1:],
        ),
    )

    with pytest.raises(DeclarationCatalogError, match=r"sources\[0\].sha256"):
        catalog_json_bytes(invalid)


def test_persisted_lookup_and_nested_values_are_immutable() -> None:
    index = load_persisted_catalog_index(GOLDEN_INDEX.read_bytes())

    assert index.get("content/base") is index.declarations["content/base"]
    assert index.get("missing") is None
    assert (
        index.get_contract(DeclarationKind.EVALUATOR, "registry/manual", 1)
        is index.contracts[
            ExactContractKey(DeclarationKind.EVALUATOR, "registry/manual", 1)
        ]
    )
    assert index.get_contract(DeclarationKind.OPERATION, "registry/write", 2) is None
    with pytest.raises(ValueError, match="not an exact contract kind"):
        index.get_contract(DeclarationKind.RULE, "content/base", 1)
    with pytest.raises(TypeError):
        cast(dict[str, object], index.declarations)["new"] = index.declarations[
            "content/base"
        ]
    with pytest.raises(TypeError):
        cast(dict[str, object], index.get("content/base").applicability)["new"] = 1  # type: ignore[union-attr]
    assert isinstance(index.get("content/base").source.document_path, tuple)  # type: ignore[union-attr]


def test_noncanonical_json_loads_into_canonical_collection_order() -> None:
    document = _document()
    for field in ("sources", "declarations", "contracts", "conflicts"):
        cast(list[object], document[field]).reverse()

    index = load_persisted_catalog_index(_bytes(document, pretty=True))

    assert tuple(index.declarations) == tuple(sorted(index.declarations))
    contract_keys = tuple(index.contracts)
    assert contract_keys == tuple(
        sorted(contract_keys, key=lambda key: (key.kind.value, key.id, key.version))
    )
    assert tuple(source.path for source in index.sources) == tuple(
        sorted(source.path for source in index.sources)
    )

    reordered_public = replace(
        index,
        declarations=MappingProxyType(
            dict(reversed(tuple(index.declarations.items())))
        ),
        contracts=MappingProxyType(dict(reversed(tuple(index.contracts.items())))),
    )
    assert _persisted_keys(reordered_public.filter_static(StaticCatalogQuery())) == (
        _persisted_keys(index.filter_static(StaticCatalogQuery()))
    )


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b'{"index-revision":1,"index-revision":1}', "duplicate JSON object key"),
        (
            b'{"index-revision":1,"sources":[],"declarations":[],"contracts":[],"conflicts":[],"x":{"a":1,"a":2}}',
            "duplicate JSON object key",
        ),
        (b"\xef\xbb\xbf{}", "byte-order mark"),
        (b"\xff", "invalid UTF-8"),
        (b'{"index-revision":NaN}', "non-JSON numeric constant"),
        (b"{}", "unsupported index revision None"),
        (b'{"index-revision":2}', "unsupported index revision 2"),
    ],
)
def test_loader_rejects_invalid_json_boundaries(data: bytes, message: str) -> None:
    with pytest.raises(DeclarationCatalogError, match=message):
        load_persisted_catalog_index(data)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda document: document.update({"unknown": True}),
        lambda document: _sources(document)[0].update({"sha256": "ABC"}),
        lambda document: cast(
            dict[str, object], _declarations(document)[0]["source"]
        ).update({"line": 0}),
        lambda document: cast(
            dict[str, object], _declarations(document)[0]["query"]
        ).update({"unknown": True}),
        lambda document: _declarations(document)[0].update({"version": 1}),
        lambda document: _contracts(document)[0].pop("version"),
    ],
)
def test_schema_rejects_unknown_or_malformed_fields(
    mutation: Callable[[dict[str, object]], object],
) -> None:
    document = _document()
    mutation(document)

    with pytest.raises(DeclarationCatalogError, match="Invalid catalog index"):
        _load_document(document)


def test_schema_rejects_unknown_query_fields_for_every_kind() -> None:
    template = _document()
    rows = (*_declarations(template), *_contracts(template))

    for row in rows:
        document = _document()
        candidates = (*_declarations(document), *_contracts(document))
        target = next(
            candidate
            for candidate in candidates
            if candidate["id"] == row["id"]
            and candidate.get("version") == row.get("version")
        )
        cast(dict[str, object], target["query"])["unknown"] = True
        with pytest.raises(DeclarationCatalogError, match="unknown"):
            _load_document(document)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda query: query.update(
            {
                "evaluator-kind": "detector",
                "coverage": "partial",
                "adjudication": "candidate",
            }
        ),
        lambda query: query.update(
            {
                "evaluator-kind": "checker",
                "coverage": "total",
                "adjudication": "authoritative",
                "residual-question": "A checker has no residual question.",
            }
        ),
        lambda query: query.update(
            {"residual-question": "A manual evaluator owns no detector residual."}
        ),
        lambda query: query.update(
            {
                "evaluator-kind": "detector",
                "coverage": "total",
                "adjudication": "authoritative",
                "residual-question": "Does the candidate remain?",
            }
        ),
        lambda query: query.update(
            {
                "evaluator-kind": "checker",
                "coverage": "none",
                "adjudication": "manual",
            }
        ),
        lambda query: query.update(
            {
                "coverage": "partial",
                "adjudication": "candidate",
            }
        ),
    ],
)
def test_persisted_evaluator_projection_preserves_class_invariants(
    mutate: Callable[[dict[str, object]], object],
) -> None:
    document = _document()
    mutate(_evaluator_query(document))

    with pytest.raises(DeclarationCatalogError, match="Invalid catalog index"):
        _load_document(document)


@pytest.mark.parametrize("failure_behavior", ["candidate", "record"])
def test_persisted_detector_requires_blocking_failure_behavior(
    failure_behavior: str,
) -> None:
    document = _document()
    query = _evaluator_query(document)
    query.update(
        {
            "evaluator-kind": "detector",
            "coverage": "partial",
            "adjudication": "candidate",
            "residual-question": "Does the candidate remain?",
            "failure-behavior": failure_behavior,
        }
    )

    with pytest.raises(DeclarationCatalogError, match="Invalid catalog index"):
        _load_document(document)


@pytest.mark.parametrize(
    "value",
    [
        "/absolute.yaml",
        "a\\b.yaml",
        "a/../b.yaml",
        "a/./b.yaml",
        "a//b.yaml",
        "a\x00b.yaml",
    ],
)
def test_loader_rejects_nonportable_source_paths(value: str) -> None:
    document = _document()
    old = cast(str, _sources(document)[0]["path"])
    _sources(document)[0]["path"] = value
    for row in (*_declarations(document), *_contracts(document)):
        source = cast(dict[str, object], row["source"])
        if source["path"] == old:
            source["path"] = value

    with pytest.raises(DeclarationCatalogError, match="not portable and normalized"):
        _load_document(document)


def test_loader_rejects_duplicate_sources_ids_and_exact_keys() -> None:
    mutations: tuple[Callable[[dict[str, object]], None], ...] = (
        lambda document: _sources(document).append(dict(_sources(document)[0])),
        lambda document: _declarations(document).append(
            dict(_declarations(document)[0])
        ),
        lambda document: _contracts(document).append(dict(_contracts(document)[0])),
    )
    for mutation in mutations:
        document = _document()
        mutation(document)
        with pytest.raises(DeclarationCatalogError, match="duplicate"):
            _load_document(document)


def test_loader_rejects_contract_family_drift_and_cross_space_collisions() -> None:
    document = _document()
    second_version = json.loads(json.dumps(_contracts(document)[0]))
    second_version["version"] = 2
    second_version["owner"] = "changed-owner"
    _contracts(document).append(second_version)
    with pytest.raises(DeclarationCatalogError, match="changes kind or owner"):
        _load_document(document)

    document = _document()
    evaluator = _contracts(document)[0]
    operation_version = json.loads(json.dumps(_contracts(document)[1]))
    operation_version["id"] = evaluator["id"]
    operation_version["owner"] = evaluator["owner"]
    operation_version["version"] = 2
    _contracts(document).append(operation_version)
    with pytest.raises(DeclarationCatalogError, match="changes kind or owner"):
        _load_document(document)

    document = _document()
    _contracts(document)[0]["id"] = "content/base"
    with pytest.raises(DeclarationCatalogError, match="both index spaces"):
        _load_document(document)


def test_loader_rejects_missing_and_orphan_sources() -> None:
    document = _document()
    _sources(document).append({"path": "orphan.yaml", "sha256": "0" * 64})
    with pytest.raises(DeclarationCatalogError, match="orphan source path"):
        _load_document(document)

    document = _document()
    cast(dict[str, object], _declarations(document)[0]["source"])[
        "path"
    ] = "missing.yaml"
    with pytest.raises(DeclarationCatalogError, match="unknown source path"):
        _load_document(document)


def test_loader_rejects_bad_relations_containers_and_conflict_links() -> None:
    document = _document()
    _entry(document, "content/refined")["relations"] = [
        {"type": "requires", "target": "missing"}
    ]
    with pytest.raises(DeclarationCatalogError, match="not indexed content"):
        _load_document(document)

    document = _document()
    _entry(document, "content/base")["containing-rule-set"] = "content/alternate"
    with pytest.raises(DeclarationCatalogError, match="not an indexed rule set"):
        _load_document(document)

    document = _document()
    policy = _entry(document, "registry/prefer-refined")
    cast(dict[str, object], policy["query"])["conflicts"] = [
        "content/refined",
        "content/alternate",
    ]
    with pytest.raises(
        DeclarationCatalogError, match="not a normalized indexed conflict"
    ):
        _load_document(document)

    document = _document()
    _entry(document, "content/refined")["relations"] = []
    with pytest.raises(
        DeclarationCatalogError, match="lacks an incompatibility assertion"
    ):
        _load_document(document)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda document: cast(
                list[object], _entry(document, "content/refined")["relations"]
            ).append({"type": "requires", "target": "content/refined"}),
            "cannot relate to itself",
        ),
        (
            lambda document: cast(
                list[object], _entry(document, "content/refined")["relations"]
            ).append({"type": "requires", "target": "content/base"}),
            "duplicate relation",
        ),
        (
            lambda document: _entry(document, "registry/prefer-refined").update(
                {"relations": [{"type": "requires", "target": "content/base"}]}
            ),
            "only content rows may relate",
        ),
        (
            lambda document: cast(list[object], document["conflicts"]).append(
                ["content/alternate", "content/refined"]
            ),
            "duplicate conflict pair",
        ),
        (
            lambda document: document.update(
                {"conflicts": [["content/refined", "content/alternate"]]}
            ),
            "conflict pair is not normalized",
        ),
    ],
)
def test_loader_rejects_each_relation_and_conflict_invariant(
    mutation: Callable[[dict[str, object]], object], message: str
) -> None:
    document = _document()
    mutation(document)

    with pytest.raises(DeclarationCatalogError, match=message):
        _load_document(document)


def test_loader_rejects_reciprocal_incompatibility_assertions() -> None:
    document = _document()
    _entry(document, "content/alternate")["relations"] = [
        {"type": "incompatible-with", "target": "content/refined"}
    ]

    with pytest.raises(DeclarationCatalogError, match="duplicate incompatibility pair"):
        _load_document(document)


@pytest.mark.parametrize(
    ("relations", "message"),
    [
        (
            {"content/base": [{"type": "requires", "target": "content/refined"}]},
            "dependency relation closes a cycle",
        ),
        (
            {
                "content/alternate": [
                    {"type": "supersedes", "target": "content/refined"}
                ],
                "content/refined": [
                    {"type": "supersedes", "target": "content/alternate"}
                ],
            },
            "supersedes relation closes a cycle",
        ),
    ],
)
def test_loader_rejects_persisted_relation_cycles(
    relations: dict[str, list[dict[str, str]]], message: str
) -> None:
    document = _document()
    for identifier, additions in relations.items():
        cast(list[object], _entry(document, identifier)["relations"]).extend(additions)

    with pytest.raises(DeclarationCatalogError, match=message):
        _load_document(document)


def test_loader_rejects_duplicate_source_coordinates() -> None:
    document = _document()
    alternate_source = cast(
        dict[str, object], _entry(document, "content/alternate")["source"]
    )
    refined_source = cast(
        dict[str, object], _entry(document, "content/refined")["source"]
    )
    alternate_source.update(refined_source)

    with pytest.raises(DeclarationCatalogError, match="duplicate source coordinate"):
        _load_document(document)


def test_loader_rejects_cross_source_or_malformed_containment() -> None:
    document = _document()
    base = _entry(document, "content/base")
    cast(dict[str, object], base["source"])["path"] = "alternate-rule.yaml"
    with pytest.raises(DeclarationCatalogError, match="must share a source"):
        _load_document(document)

    document = _document()
    cast(dict[str, object], _entry(document, "content/base")["source"])[
        "document-path"
    ] = ["members", 0]
    with pytest.raises(
        DeclarationCatalogError, match="embedded rule must use the path"
    ):
        _load_document(document)

    document = _document()
    cast(dict[str, object], _entry(document, "content/alternate")["source"])[
        "document-path"
    ] = ["rules", 0]
    with pytest.raises(DeclarationCatalogError, match="top-level row"):
        _load_document(document)


def test_static_filter_parity_for_each_field_and_conjunctions() -> None:
    live = _live_catalog()
    persisted = load_persisted_catalog_index(catalog_json_bytes(live))
    applicability = persisted.get("content/alternate").applicability  # type: ignore[union-attr]
    queries = (
        StaticCatalogQuery((StaticPredicate(StaticField.OWNER, "registry"),)),
        StaticCatalogQuery(
            (StaticPredicate(StaticField.KIND, DeclarationKind.EVALUATOR),)
        ),
        StaticCatalogQuery((StaticPredicate(StaticField.AXIS, "reasoning-target"),)),
        StaticCatalogQuery((StaticPredicate(StaticField.FAILURE_MODE, "visible"),)),
        StaticCatalogQuery((StaticPredicate(StaticField.REQUIRED_VISIBILITY, None),)),
        StaticCatalogQuery(
            (StaticPredicate(StaticField.APPLICABILITY, applicability),)
        ),
        StaticCatalogQuery(
            (
                StaticPredicate(StaticField.OWNER, "registry"),
                StaticPredicate(StaticField.KIND, DeclarationKind.RULE),
            )
        ),
        StaticCatalogQuery(
            (
                StaticPredicate(StaticField.AXIS, "reasoning-target"),
                StaticPredicate(StaticField.FAILURE_MODE, "visible"),
            )
        ),
    )
    for query in queries:
        assert _persisted_keys(persisted.filter_static(query)) == _live_keys(
            cast(tuple[object, ...], live.filter_static(query))
        )

    no_predicate = persisted.filter_static(StaticCatalogQuery())
    null_visibility = persisted.filter_static(
        StaticCatalogQuery((StaticPredicate(StaticField.REQUIRED_VISIBILITY, None),))
    )
    assert len(null_visibility) < len(no_predicate)


def test_applicability_filter_uses_structural_json_equality() -> None:
    index = load_persisted_catalog_index(GOLDEN_INDEX.read_bytes())
    base = index.get("content/base")
    assert base is not None
    reordered = {
        "all": [
            {"operator": "equals", "value": True, "facet": "artifact.created"},
            {"operator": "exists", "facet": "context.available"},
        ]
    }
    reversed_array = {"all": list(reversed(reordered["all"]))}

    matching = index.filter_static(
        StaticCatalogQuery((StaticPredicate(StaticField.APPLICABILITY, reordered),))
    )
    nonmatching = index.filter_static(
        StaticCatalogQuery(
            (StaticPredicate(StaticField.APPLICABILITY, reversed_array),)
        )
    )
    numeric = {
        "all": [
            {"operator": "equals", "value": 1, "facet": "artifact.created"},
            {"operator": "exists", "facet": "context.available"},
        ]
    }
    bool_vs_number = index.filter_static(
        StaticCatalogQuery((StaticPredicate(StaticField.APPLICABILITY, numeric),))
    )

    assert base in matching
    assert base not in nonmatching
    assert base not in bool_vs_number

    numeric_document = _document()
    alternate = _entry(numeric_document, "content/alternate")
    alternate["applicability"] = {
        "facet": "context.available",
        "operator": "equals",
        "value": 1,
    }
    numeric_index = _load_document(numeric_document)
    float_query = {
        "facet": "context.available",
        "operator": "equals",
        "value": 1.0,
    }
    matches = numeric_index.filter_static(
        StaticCatalogQuery((StaticPredicate(StaticField.APPLICABILITY, float_query),))
    )
    assert numeric_index.get("content/alternate") in matches


def test_static_query_rejects_ambiguous_or_unsupported_fields() -> None:
    with pytest.raises(ValueError, match="unique"):
        StaticCatalogQuery(
            (
                StaticPredicate(StaticField.OWNER, "registry"),
                StaticPredicate(StaticField.OWNER, "registry"),
            )
        )
    with pytest.raises(ValueError):
        StaticField("enforcement-class")
    with pytest.raises(ValueError, match="rule axis"):
        StaticPredicate(StaticField.AXIS, "unknown")
    with pytest.raises(TypeError, match="StaticPredicate"):
        StaticCatalogQuery(cast(tuple[StaticPredicate, ...], ("not-a-predicate",)))
    with pytest.raises(ValueError, match="failure-mode"):
        StaticPredicate(StaticField.FAILURE_MODE, {"unexpected": True})
    with pytest.raises(ValueError, match="required-visibility"):
        StaticPredicate(StaticField.REQUIRED_VISIBILITY, ["pre-action"])
