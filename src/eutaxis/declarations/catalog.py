"""Build a portable static catalog from a validated declaration registry."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .exceptions import DeclarationCatalogError
from .models import (
    AnyDeclaration,
    CompositionManifestDeclaration,
    DeclarationKind,
    EvaluatorDeclaration,
    JsonValue,
    OperationDeclaration,
    ProcedureDeclaration,
    ResolutionPolicyDeclaration,
    RuleDeclaration,
    RuleSetDeclaration,
)
from .registry import DeclarationRegistry, RegisteredDeclaration
from .source import nearest_location

CATALOG_INDEX_REVISION = 1
_EXACT_KINDS = frozenset({DeclarationKind.EVALUATOR, DeclarationKind.OPERATION})


@dataclass(frozen=True, order=True)
class ExactContractKey:
    """One exact evaluator or operation contract key."""

    kind: DeclarationKind
    id: str
    version: int


@dataclass(frozen=True)
class CatalogSource:
    """Portable provenance for one source snapshot."""

    path: str
    sha256: str


@dataclass(frozen=True)
class DeclarationCatalog:
    """Immutable static lookups over one validated declaration registry."""

    source_root: Path
    sources: tuple[CatalogSource, ...]
    declarations: Mapping[str, RegisteredDeclaration]
    contracts: Mapping[ExactContractKey, RegisteredDeclaration]
    conflicts: tuple[tuple[str, str], ...]

    def get(self, identifier: str) -> RegisteredDeclaration | None:
        """Return one unversioned record, or ``None`` when it is absent."""
        return self.declarations.get(identifier)

    def get_contract(
        self,
        kind: DeclarationKind,
        identifier: str,
        version: int,
    ) -> RegisteredDeclaration | None:
        """Return one exact evaluator or operation contract when present."""
        if kind not in _EXACT_KINDS:
            raise ValueError(f"{kind.value!r} is not an exact contract kind")
        return self.contracts.get(ExactContractKey(kind, identifier, version))


def build_declaration_catalog(
    registry: DeclarationRegistry,
    *,
    source_root: Path,
) -> DeclarationCatalog:
    """Build static portable lookups without revisiting declaration semantics."""
    root = source_root.resolve()
    if not root.is_dir():
        raise DeclarationCatalogError(f"source root {root} is not a directory")
    declarations = MappingProxyType(
        {
            identifier: registry.records[identifier]
            for identifier in sorted(registry.records)
        }
    )
    contract_items = [
        (ExactContractKey(family.kind, family.id, version), family.versions[version])
        for family in registry.families.values()
        for version in family.versions
    ]
    contract_items.sort(
        key=lambda item: (item[0].kind.value, item[0].id, item[0].version)
    )
    contracts = MappingProxyType(dict(contract_items))
    records = (*declarations.values(), *contracts.values())
    source_by_path = {record.source.path.resolve(): record.source for record in records}
    sources: list[CatalogSource] = []
    for path in registry.paths:
        canonical_path = path.resolve()
        source = source_by_path.get(canonical_path)
        if source is None:
            raise DeclarationCatalogError(
                f"registry source {canonical_path} has no registered declaration"
            )
        try:
            relative_path = canonical_path.relative_to(root)
        except ValueError as error:
            raise DeclarationCatalogError(
                f"registry source {canonical_path} is outside source root {root}"
            ) from error
        sources.append(CatalogSource(relative_path.as_posix(), source.sha256))
    sources.sort(key=lambda item: item.path)
    return DeclarationCatalog(
        source_root=root,
        sources=tuple(sources),
        declarations=declarations,
        contracts=contracts,
        conflicts=tuple(sorted(registry.conflicts)),
    )


def catalog_json_bytes(catalog: DeclarationCatalog) -> bytes:
    """Serialize one catalog as deterministic, portable UTF-8 JSON."""
    contract_items = sorted(
        catalog.contracts.items(),
        key=lambda item: (item[0].kind.value, item[0].id, item[0].version),
    )
    conflicts = sorted(tuple(sorted(pair)) for pair in catalog.conflicts)
    payload = {
        "index-revision": CATALOG_INDEX_REVISION,
        "sources": [
            {"path": source.path, "sha256": source.sha256}
            for source in sorted(catalog.sources, key=lambda item: item.path)
        ],
        "declarations": [
            _entry_payload(catalog, record)
            for _, record in sorted(catalog.declarations.items())
        ],
        "contracts": [
            _entry_payload(catalog, record, version=key.version)
            for key, record in contract_items
        ],
        "conflicts": [list(pair) for pair in conflicts],
    }
    text = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (text + "\n").encode("utf-8", errors="strict")


def _entry_payload(
    catalog: DeclarationCatalog,
    record: RegisteredDeclaration,
    *,
    version: int | None = None,
) -> dict[str, object]:
    """Project one registered record into the static index contract."""
    declaration = record.declaration
    location = nearest_location(record.source.locations, record.root)
    payload: dict[str, object] = {
        "id": declaration.id,
        "kind": declaration.kind.value,
        "owner": declaration.owner,
        "status": declaration.status,
        "source-revision": declaration.source_revision,
        "schema-version": declaration.schema_version,
        "applicability": _json_value(declaration.applicability),
        "relations": [
            {"type": relation.type, "target": relation.target}
            for relation in sorted(
                declaration.relations, key=lambda item: (item.type, item.target)
            )
        ],
        "query": _query_fields(declaration),
        "containing-rule-set": record.containing_rule_set,
        "source": {
            "path": record.source.path.resolve()
            .relative_to(catalog.source_root)
            .as_posix(),
            "document-path": list(record.root),
            "line": location.line if location is not None else None,
            "column": location.column if location is not None else None,
        },
    }
    if version is not None:
        payload["version"] = version
    return payload


def _query_fields(declaration: AnyDeclaration) -> dict[str, object]:
    """Return only static fields admitted by catalog queries."""
    if isinstance(declaration, RuleSetDeclaration):
        return {"purpose": declaration.purpose}
    if isinstance(declaration, RuleDeclaration):
        return {
            "axis": declaration.axis.value,
            "failure-mode": declaration.failure_mode,
            "required-visibility": declaration.required_visibility,
        }
    if isinstance(declaration, ProcedureDeclaration):
        return {"purpose": declaration.purpose}
    if isinstance(declaration, ResolutionPolicyDeclaration):
        return {
            "conflicts": sorted(declaration.conflicts),
            "order": declaration.order,
            "strategy": declaration.strategy.kind,
        }
    if isinstance(declaration, CompositionManifestDeclaration):
        return {
            "mechanism": declaration.mechanism.value,
            "scope": declaration.scope,
            "target": declaration.target,
        }
    if isinstance(declaration, EvaluatorDeclaration):
        return {
            "evaluator-kind": declaration.evaluator_kind,
            "coverage": declaration.coverage,
            "adjudication": declaration.adjudication,
            "timing": declaration.timing,
            "failure-behavior": declaration.failure_behavior,
        }
    if isinstance(declaration, OperationDeclaration):
        return {
            "effects": sorted(declaration.effects),
            "failure-outcomes": sorted(declaration.failure_outcomes),
        }
    raise TypeError(f"unsupported declaration kind {declaration.kind.value!r}")


def _json_value(value: JsonValue) -> object:
    """Thaw one immutable JSON value for serialization."""
    if isinstance(value, Mapping):
        return {key: _json_value(value[key]) for key in sorted(value)}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value
