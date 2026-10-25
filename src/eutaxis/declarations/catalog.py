"""Build a portable static catalog from a validated declaration registry."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .catalog_schema import validate_catalog_index_payload
from .enforcement import (
    EnforcementClass,
    EnforcementLocator,
    _EnforcementRecordSource,
    _enumerate_enforcement,
)
from .exceptions import DeclarationCatalogError
from .models import (
    AnyDeclaration,
    CompositionManifestDeclaration,
    DeclarationKind,
    EXACT_CONTRACT_KINDS,
    EvaluatorDeclaration,
    JsonValue,
    OperationDeclaration,
    ProcedureDeclaration,
    ResolutionPolicyDeclaration,
    RuleDeclaration,
    RuleSetDeclaration,
    VersionedReference,
)
from .registry import DeclarationRegistry, RegisteredDeclaration
from .source import nearest_location
from .static_query import StaticCatalogQuery, matches_static_query

CATALOG_INDEX_REVISION = 1


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
        if kind not in EXACT_CONTRACT_KINDS:
            raise ValueError(f"{kind.value!r} is not an exact contract kind")
        return self.contracts.get(ExactContractKey(kind, identifier, version))

    def filter_static(
        self, query: StaticCatalogQuery
    ) -> tuple[RegisteredDeclaration, ...]:
        """Return records whose stored fields satisfy every exact predicate."""
        declaration_records = tuple(
            record for _, record in sorted(self.declarations.items())
        )
        contract_records = tuple(
            record
            for _, record in sorted(
                self.contracts.items(),
                key=lambda item: (item[0].kind.value, item[0].id, item[0].version),
            )
        )
        records = (*declaration_records, *contract_records)
        return tuple(
            record
            for record in records
            if matches_static_query(
                query,
                owner=record.declaration.owner,
                kind=record.declaration.kind,
                applicability=record.declaration.applicability,
                query_fields=_query_fields(record.declaration),
            )
        )

    def filter_enforcement(
        self, enforcement: EnforcementClass
    ) -> tuple[EnforcementLocator, ...]:
        """Return authored obligations with one declared enforcement class."""
        source = _EnforcementRecordSource(
            declarations=MappingProxyType(
                {
                    identifier: record.declaration
                    for identifier, record in self.declarations.items()
                }
            ),
            operations=tuple(
                (
                    VersionedReference(key.id, key.version),
                    record.declaration,
                )
                for key, record in sorted(
                    self.contracts.items(),
                    key=lambda item: (
                        item[0].kind.value,
                        item[0].id,
                        item[0].version,
                    ),
                )
                if key.kind is DeclarationKind.OPERATION
                and isinstance(record.declaration, OperationDeclaration)
            ),
            evaluator=self._evaluator_contract,
        )
        return tuple(
            locator
            for locator in _enumerate_enforcement(source)
            if locator.enforcement is enforcement
        )

    def _evaluator_contract(
        self, reference: VersionedReference
    ) -> EvaluatorDeclaration:
        """Resolve one exact evaluator for canonical enumeration."""
        key = ExactContractKey(
            DeclarationKind.EVALUATOR, reference.id, reference.version
        )
        record = self.contracts.get(key)
        if record is None or not isinstance(record.declaration, EvaluatorDeclaration):
            raise DeclarationCatalogError(
                "obligation references unknown evaluator "
                f"{reference.id!r}@{reference.version}"
            )
        return record.declaration


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
    validate_catalog_index_payload(payload)
    try:
        text = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except ValueError as error:
        raise DeclarationCatalogError(
            f"catalog index is not strict JSON: {error}"
        ) from error
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
        query: dict[str, object] = {
            "evaluator-kind": declaration.evaluator_kind,
            "coverage": declaration.coverage,
            "adjudication": declaration.adjudication,
            "timing": declaration.timing,
            "failure-behavior": declaration.failure_behavior,
        }
        if declaration.residual_question is not None:
            query["residual-question"] = declaration.residual_question
        return query
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
