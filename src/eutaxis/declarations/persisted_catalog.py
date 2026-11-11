"""Load an immutable static projection from persisted catalog-index JSON."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import NoReturn, cast

from .acquisition_paths import AcquisitionPathError, normalized_relative_path
from .catalog import CATALOG_INDEX_REVISION, CatalogSource, ExactContractKey
from .catalog_schema import validate_catalog_index_payload
from .exceptions import DeclarationCatalogError
from .models import (
    DeclarationKind,
    DeclarationStatus,
    EXACT_CONTRACT_KINDS,
    JsonValue,
    freeze_json,
)
from .static_query import StaticCatalogQuery, matches_static_query

_EFFECTIVE_KINDS = frozenset({DeclarationKind.RULE, DeclarationKind.PROCEDURE})
_NAMESPACE = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?")
_V1_DIGEST = re.compile(r"[0-9a-f]{64}")
_V2_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass(frozen=True)
class PersistedCatalogRelation:
    """One typed relation retained by a persisted index row."""

    type: str
    target: str


@dataclass(frozen=True)
class PersistedCatalogProvenance:
    """Portable source coordinates retained by a persisted index row."""

    namespace: str | None
    path: str
    document_path: tuple[str | int, ...]
    line: int
    column: int


@dataclass(frozen=True)
class PersistedCatalogEntry:
    """A lossy static index row, not a semantic source declaration."""

    id: str
    kind: DeclarationKind
    owner: str
    status: DeclarationStatus
    source_revision: str
    schema_version: int
    applicability: Mapping[str, JsonValue]
    relations: tuple[PersistedCatalogRelation, ...]
    query: Mapping[str, JsonValue]
    containing_rule_set: str | None
    source: PersistedCatalogProvenance
    version: int | None


@dataclass(frozen=True)
class PersistedCatalogIndex:
    """An immutable query projection, never a registry or resolver input."""

    revision: int
    facet_content_revision: str | None
    sources: tuple[CatalogSource, ...]
    declarations: Mapping[str, PersistedCatalogEntry]
    contracts: Mapping[ExactContractKey, PersistedCatalogEntry]
    conflicts: tuple[tuple[str, str], ...]

    def get(self, identifier: str) -> PersistedCatalogEntry | None:
        """Return one unversioned row, or ``None`` when it is absent."""
        return self.declarations.get(identifier)

    def get_contract(
        self,
        kind: DeclarationKind,
        identifier: str,
        version: int,
    ) -> PersistedCatalogEntry | None:
        """Return one exact evaluator or operation row when present."""
        if kind not in EXACT_CONTRACT_KINDS:
            raise ValueError(f"{kind.value!r} is not an exact contract kind")
        return self.contracts.get(ExactContractKey(kind, identifier, version))

    def filter_static(
        self, query: StaticCatalogQuery
    ) -> tuple[PersistedCatalogEntry, ...]:
        """Return rows whose stored fields satisfy every exact predicate."""
        declaration_rows = tuple(row for _, row in sorted(self.declarations.items()))
        contract_rows = tuple(
            row
            for _, row in sorted(
                self.contracts.items(),
                key=lambda item: (item[0].kind.value, item[0].id, item[0].version),
            )
        )
        rows = (*declaration_rows, *contract_rows)
        return tuple(
            row
            for row in rows
            if matches_static_query(
                query,
                owner=row.owner,
                kind=row.kind,
                applicability=row.applicability,
                query_fields=row.query,
            )
        )


class _DuplicateKeyError(ValueError):
    """Mark a repeated JSON object key before a mapping can discard it."""


def load_persisted_catalog_index(
    data: bytes,
    *,
    source: Path | None = None,
) -> PersistedCatalogIndex:
    """Load and validate one persisted static index without semantic recovery."""
    if data.startswith(b"\xef\xbb\xbf"):
        _fail(source, "$", "a UTF-8 byte-order mark is not admitted")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeError as error:
        _fail(source, "$", f"invalid UTF-8: {error}")
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (_DuplicateKeyError, ValueError, json.JSONDecodeError) as error:
        _fail(source, "$", str(error))
    revision = parsed.get("index-revision") if isinstance(parsed, Mapping) else None
    if type(revision) is not int or revision not in (1, CATALOG_INDEX_REVISION):
        _fail(
            source,
            "$.index-revision",
            f"unsupported index revision {revision!r}",
        )
    document = validate_catalog_index_payload(parsed, source=source)
    return _build_persisted_index(document, revision=revision, source=source)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build one JSON object while rejecting a repeated key."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    """Reject non-finite numeric tokens that standard JSON excludes."""
    raise ValueError(f"non-JSON numeric constant {value!r}")


def _source_key(value: tuple[str | None, str]) -> tuple[str, str]:
    """Sort legacy and namespaced source coordinates deterministically."""
    return value[0] or "", value[1]


def _build_persisted_index(
    document: Mapping[str, object],
    *,
    revision: int,
    source: Path | None,
) -> PersistedCatalogIndex:
    """Freeze validated rows after checking cross-entry index integrity."""
    facet_content_revision = cast(str | None, document.get("facet-content-revision"))
    if revision == CATALOG_INDEX_REVISION:
        _validate_digest(
            cast(str, facet_content_revision),
            revision=revision,
            source=source,
            location="$.facet-content-revision",
        )
    source_rows = cast(list[dict[str, object]], document["sources"])
    sources: dict[tuple[str | None, str], CatalogSource] = {}
    for index, source_row in enumerate(source_rows):
        path = cast(str, source_row["path"])
        namespace = (
            cast(str, source_row["namespace"])
            if revision == CATALOG_INDEX_REVISION
            else None
        )
        _validate_portable_path(
            path, source=source, location=f"$.sources[{index}].path"
        )
        if namespace is not None:
            _validate_namespace(
                namespace,
                source=source,
                location=f"$.sources[{index}].namespace",
            )
        _validate_digest(
            cast(str, source_row["sha256"]),
            revision=revision,
            source=source,
            location=f"$.sources[{index}].sha256",
        )
        source_key = (namespace, path)
        if source_key in sources:
            _fail(
                source,
                f"$.sources[{index}].path",
                f"duplicate source coordinate {source_key!r}",
            )
        sources[source_key] = CatalogSource(
            namespace=namespace,
            path=path,
            sha256=cast(str, source_row["sha256"]),
        )

    declarations: dict[str, PersistedCatalogEntry] = {}
    entry_locations: dict[int, str] = {}
    for index, declaration_row in enumerate(
        cast(list[Mapping[str, object]], document["declarations"])
    ):
        entry = _entry(declaration_row, version=None, revision=revision)
        if entry.id in declarations:
            _fail(
                source,
                f"$.declarations[{index}].id",
                f"duplicate declaration id {entry.id!r}",
            )
        declarations[entry.id] = entry
        entry_locations[id(entry)] = f"$.declarations[{index}]"

    contracts: dict[ExactContractKey, PersistedCatalogEntry] = {}
    family_signatures: dict[str, tuple[DeclarationKind, str]] = {}
    for index, contract_row in enumerate(
        cast(list[Mapping[str, object]], document["contracts"])
    ):
        version = cast(int, contract_row["version"])
        entry = _entry(contract_row, version=version, revision=revision)
        if entry.id in declarations:
            _fail(
                source,
                f"$.contracts[{index}].id",
                f"identifier {entry.id!r} occurs in both index spaces",
            )
        key = ExactContractKey(entry.kind, entry.id, version)
        if key in contracts:
            _fail(
                source,
                f"$.contracts[{index}]",
                f"duplicate exact contract {entry.id!r}@{version}",
            )
        signature = (entry.kind, entry.owner)
        prior = family_signatures.setdefault(entry.id, signature)
        if prior != signature:
            _fail(
                source,
                f"$.contracts[{index}]",
                f"contract family {entry.id!r} changes kind or owner",
            )
        contracts[key] = entry
        entry_locations[id(entry)] = f"$.contracts[{index}]"

    all_entries = (*declarations.values(), *contracts.values())
    _validate_entry_integrity(
        all_entries,
        declarations,
        frozenset(sources),
        cast(list[list[str]], document["conflicts"]),
        entry_locations,
        source=source,
    )
    conflicts = _validated_conflicts(
        cast(list[list[str]], document["conflicts"]), source=source
    )
    used_sources = {
        (entry.source.namespace, entry.source.path) for entry in all_entries
    }
    orphaned = sorted(set(sources) - used_sources)
    if orphaned:
        _fail(source, "$.sources", f"orphan source path {orphaned[0]!r}")

    contract_items = sorted(
        contracts.items(),
        key=lambda item: (item[0].kind.value, item[0].id, item[0].version),
    )
    return PersistedCatalogIndex(
        revision=revision,
        facet_content_revision=facet_content_revision,
        sources=tuple(sources[key] for key in sorted(sources, key=_source_key)),
        declarations=MappingProxyType(
            {
                identifier: declarations[identifier]
                for identifier in sorted(declarations)
            }
        ),
        contracts=MappingProxyType(dict(contract_items)),
        conflicts=conflicts,
    )


def _entry(
    row: Mapping[str, object],
    *,
    version: int | None,
    revision: int,
) -> PersistedCatalogEntry:
    """Copy one schema-valid mutable row into immutable value objects."""
    kind = DeclarationKind(cast(str, row["kind"]))
    query_input = cast(Mapping[str, object], row["query"])
    if kind is DeclarationKind.OPERATION:
        query_input = {
            **query_input,
            "effects": sorted(cast(list[str], query_input["effects"])),
            "failure-outcomes": sorted(
                cast(list[str], query_input["failure-outcomes"])
            ),
        }
    applicability = _canonical_json(row["applicability"])
    query = _canonical_json(query_input)
    if not isinstance(applicability, Mapping) or not isinstance(query, Mapping):
        raise AssertionError("catalog schema admitted a non-object field")
    source_row = cast(Mapping[str, object], row["source"])
    relations = tuple(
        sorted(
            (
                PersistedCatalogRelation(
                    type=cast(str, relation["type"]),
                    target=cast(str, relation["target"]),
                )
                for relation in cast(list[Mapping[str, object]], row["relations"])
            ),
            key=lambda relation: (relation.type, relation.target),
        )
    )
    return PersistedCatalogEntry(
        id=cast(str, row["id"]),
        kind=kind,
        owner=cast(str, row["owner"]),
        status=DeclarationStatus(cast(str, row["status"])),
        source_revision=cast(str, row["source-revision"]),
        schema_version=cast(int, row["schema-version"]),
        applicability=applicability,
        relations=relations,
        query=query,
        containing_rule_set=cast(str | None, row["containing-rule-set"]),
        source=PersistedCatalogProvenance(
            namespace=(
                cast(str, source_row["namespace"])
                if revision == CATALOG_INDEX_REVISION
                else None
            ),
            path=cast(str, source_row["path"]),
            document_path=tuple(cast(list[str | int], source_row["document-path"])),
            line=cast(int, source_row["line"]),
            column=cast(int, source_row["column"]),
        ),
        version=version,
    )


def _validate_entry_integrity(
    entries: tuple[PersistedCatalogEntry, ...],
    declarations: Mapping[str, PersistedCatalogEntry],
    source_paths: frozenset[tuple[str | None, str]],
    raw_conflicts: list[list[str]],
    entry_locations: Mapping[int, str],
    *,
    source: Path | None,
) -> None:
    """Check references whose validity spans several persisted rows."""
    effective = {
        identifier: entry
        for identifier, entry in declarations.items()
        if entry.kind in _EFFECTIVE_KINDS
    }
    asserted_conflicts: dict[tuple[str, str], str] = {}
    dependency_edges: dict[str, list[tuple[str, str]]] = {}
    supersedes_edges: dict[str, list[tuple[str, str]]] = {}
    incoming_supersedes: set[str] = set()
    coordinates: dict[tuple[str | None, str, tuple[str | int, ...]], str] = {}
    for entry in entries:
        entry_location = entry_locations[id(entry)]
        _validate_portable_path(
            entry.source.path,
            source=source,
            location=f"{entry_location}.source.path",
        )
        if entry.source.namespace is not None:
            _validate_namespace(
                entry.source.namespace,
                source=source,
                location=f"{entry_location}.source.namespace",
            )
        source_key = (entry.source.namespace, entry.source.path)
        if source_key not in source_paths:
            _fail(
                source,
                f"{entry_location}.source.path",
                f"unknown source path {entry.source.path!r}",
            )
        coordinate = (
            entry.source.namespace,
            entry.source.path,
            entry.source.document_path,
        )
        if coordinate in coordinates:
            _fail(
                source,
                f"{entry_location}.source.document-path",
                f"duplicate source coordinate {coordinate!r}",
            )
        coordinates[coordinate] = entry_location
        seen_relations: set[tuple[str, str]] = set()
        for relation in entry.relations:
            relation_key = (relation.type, relation.target)
            if relation_key in seen_relations:
                _fail(
                    source,
                    f"{entry_location}.relations",
                    f"duplicate relation {relation_key!r}",
                )
            seen_relations.add(relation_key)
            target = declarations.get(relation.target)
            if target is None:
                target_class = (
                    "indexed declaration"
                    if relation.type == "supersedes"
                    else "indexed content"
                )
                _fail(
                    source,
                    f"{entry_location}.relations",
                    f"relation target {relation.target!r} is not {target_class}",
                )
            if relation.target == entry.id:
                _fail(
                    source,
                    f"{entry_location}.relations",
                    "a row cannot relate to itself",
                )
            assert target is not None
            if relation.type == "supersedes":
                if entry.status is not DeclarationStatus.ACTIVE:
                    _fail(
                        source,
                        f"{entry_location}.status",
                        "a superseding row must be active",
                    )
                if target.status is not DeclarationStatus.SUPERSEDED:
                    _fail(
                        source,
                        f"{entry_location}.relations",
                        "a supersedes target must have status 'superseded'",
                    )
                if target.kind is not entry.kind:
                    _fail(
                        source,
                        f"{entry_location}.relations",
                        "a supersedes relation must preserve declaration kind",
                    )
                incoming_supersedes.add(target.id)
                supersedes_edges.setdefault(entry.id, []).append(
                    (relation.target, entry_location)
                )
                continue
            if entry.kind not in _EFFECTIVE_KINDS:
                _fail(
                    source,
                    f"{entry_location}.relations",
                    f"{entry.kind.value} rows admit only supersedes relations",
                )
            if entry.status is not DeclarationStatus.ACTIVE:
                _fail(
                    source,
                    f"{entry_location}.status",
                    "a row with operative relations must be active",
                )
            if target.kind not in _EFFECTIVE_KINDS:
                _fail(
                    source,
                    f"{entry_location}.relations",
                    f"relation target {relation.target!r} is not effective content",
                )
            if target.status is not DeclarationStatus.ACTIVE:
                _fail(
                    source,
                    f"{entry_location}.relations",
                    f"relation target {relation.target!r} is not active",
                )
            if relation.type == "incompatible-with":
                pair = cast(tuple[str, str], tuple(sorted((entry.id, relation.target))))
                if pair in asserted_conflicts:
                    _fail(
                        source,
                        f"{entry_location}.relations",
                        f"duplicate incompatibility pair {pair!r}",
                    )
                asserted_conflicts[pair] = entry_location
            elif relation.type in {"requires", "refines"}:
                dependency_edges.setdefault(entry.id, []).append(
                    (relation.target, entry_location)
                )
        if entry.kind is DeclarationKind.RULE:
            for identifier in cast(tuple[str, ...], entry.query.get("decided-by", ())):
                decision = declarations.get(identifier)
                if decision is None or decision.kind is not DeclarationKind.DECISION:
                    _fail(
                        source,
                        f"{entry_location}.query.decided-by",
                        f"rule decision {identifier!r} is not indexed",
                    )
                if decision.status is not DeclarationStatus.ACTIVE:
                    _fail(
                        source,
                        f"{entry_location}.query.decided-by",
                        f"rule decision {identifier!r} is not active",
                    )
        container = entry.containing_rule_set
        if container is None:
            if entry.source.document_path:
                _fail(
                    source,
                    f"{entry_location}.source.document-path",
                    "a top-level row must use the source root",
                )
        else:
            target = declarations.get(container)
            if entry.kind is not DeclarationKind.RULE:
                _fail(
                    source,
                    f"{entry_location}.containing-rule-set",
                    "only rules may name a containing rule set",
                )
            if target is None or target.kind is not DeclarationKind.RULE_SET:
                _fail(
                    source,
                    f"{entry_location}.containing-rule-set",
                    f"{container!r} is not an indexed rule set",
                )
            assert target is not None
            if (
                target.source.namespace,
                target.source.path,
            ) != (
                entry.source.namespace,
                entry.source.path,
            ):
                _fail(
                    source,
                    f"{entry_location}.containing-rule-set",
                    "an embedded rule and its containing rule set must share a source",
                )
            if target.source.document_path:
                _fail(
                    source,
                    f"{entry_locations[id(target)]}.source.document-path",
                    "a containing rule set must use the source root",
                )
            document_path = entry.source.document_path
            if not (
                len(document_path) == 2
                and document_path[0] == "rules"
                and type(document_path[1]) is int
                and document_path[1] >= 0
            ):
                _fail(
                    source,
                    f"{entry_location}.source.document-path",
                    "an embedded rule must use the path ['rules', nonnegative-index]",
                )

    for entry in declarations.values():
        if (
            entry.status is DeclarationStatus.SUPERSEDED
            and entry.id not in incoming_supersedes
        ):
            _fail(
                source,
                f"{entry_locations[id(entry)]}.status",
                "a superseded row lacks an incoming supersedes relation",
            )

    _reject_relation_cycles(effective, dependency_edges, "dependency", source=source)
    _reject_relation_cycles(declarations, supersedes_edges, "supersedes", source=source)

    conflicts = _validated_conflicts(raw_conflicts, source=source)
    conflict_set = set(conflicts)
    asserted_conflict_set = set(asserted_conflicts)
    if conflict_set != asserted_conflict_set:
        missing_assertion = sorted(conflict_set - asserted_conflict_set)
        missing_index = sorted(asserted_conflict_set - conflict_set)
        detail = (
            f"conflict {missing_assertion[0]!r} lacks an incompatibility assertion"
            if missing_assertion
            else f"incompatibility {missing_index[0]!r} is absent from conflicts"
        )
        _fail(source, "$.conflicts", detail)
    for entry in declarations.values():
        if entry.kind is not DeclarationKind.RESOLUTION_POLICY:
            continue
        pair_value = entry.query["conflicts"]
        pair = cast(tuple[str, str], pair_value)
        if pair != tuple(sorted(pair)) or pair not in conflict_set:
            _fail(
                source,
                f"{entry_locations[id(entry)]}.query.conflicts",
                f"policy conflict pair {pair!r} is not a normalized indexed conflict",
            )


def _reject_relation_cycles(
    content: Mapping[str, PersistedCatalogEntry],
    edges: Mapping[str, list[tuple[str, str]]],
    graph_name: str,
    *,
    source: Path | None,
) -> None:
    """Reject a deterministic edge that closes one persisted relation cycle."""
    states: dict[str, int] = {}

    def visit(identifier: str) -> None:
        states[identifier] = 1
        for target, entry_location in sorted(edges.get(identifier, [])):
            if states.get(target) == 1:
                _fail(
                    source,
                    f"{entry_location}.relations",
                    f"{graph_name} relation closes a cycle",
                )
            if states.get(target, 0) == 0:
                visit(target)
        states[identifier] = 2

    for identifier in sorted(content):
        if states.get(identifier, 0) == 0:
            visit(identifier)


def _validated_conflicts(
    raw_conflicts: list[list[str]],
    *,
    source: Path | None,
) -> tuple[tuple[str, str], ...]:
    """Return unique normalized conflict pairs without repairing input."""
    conflicts: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for index, raw_pair in enumerate(raw_conflicts):
        pair = (raw_pair[0], raw_pair[1])
        if pair != tuple(sorted(pair)):
            _fail(source, f"$.conflicts[{index}]", "conflict pair is not normalized")
        if pair in seen:
            _fail(source, f"$.conflicts[{index}]", f"duplicate conflict pair {pair!r}")
        seen.add(pair)
        conflicts.append(pair)
    return tuple(sorted(conflicts))


def _validate_portable_path(
    value: str,
    *,
    source: Path | None,
    location: str,
) -> None:
    """Reject paths that are not normalized relative POSIX paths."""
    try:
        normalized_relative_path(value, allow_dot=False)
    except AcquisitionPathError:
        _fail(source, location, f"path {value!r} is not portable and normalized")


def _validate_namespace(
    value: str,
    *,
    source: Path | None,
    location: str,
) -> None:
    """Require an exact namespace grammar match."""
    if _NAMESPACE.fullmatch(value) is None:
        _fail(source, location, f"namespace {value!r} is invalid")


def _validate_digest(
    value: str,
    *,
    revision: int,
    source: Path | None,
    location: str,
) -> None:
    """Require the exact digest grammar of one index revision."""
    pattern = _V2_DIGEST if revision == CATALOG_INDEX_REVISION else _V1_DIGEST
    if pattern.fullmatch(value) is None:
        _fail(source, location, f"digest {value!r} is invalid")


def _canonical_json(value: object) -> JsonValue:
    """Freeze JSON while sorting object keys and retaining array order."""
    return _sort_frozen_json(freeze_json(value))


def _sort_frozen_json(value: JsonValue) -> JsonValue:
    """Sort keys recursively in an already validated immutable JSON value."""
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _sort_frozen_json(value[key]) for key in sorted(value)}
        )
    if isinstance(value, tuple):
        return tuple(_sort_frozen_json(item) for item in value)
    return value


def _fail(source: Path | None, location: str, detail: str) -> NoReturn:
    """Raise a source-aware persisted-index error."""
    source_text = f" in {source}" if source is not None else ""
    raise DeclarationCatalogError(
        f"Invalid catalog index{source_text} at {location}: {detail}"
    )
