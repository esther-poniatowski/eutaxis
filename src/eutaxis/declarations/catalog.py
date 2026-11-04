"""Build a portable static catalog from a validated declaration registry."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable, NamedTuple, TypeVar, cast

from ._authority import IdentityAuthorityStore, identity_value_state
from .catalog_schema import validate_catalog_index_payload
from .composite_facets import CompositeFacetRegistry
from .enforcement import (
    EnforcementClass,
    EnforcementLocator,
    _EnforcementRecordSource,
    _enumerate_enforcement,
)
from .exceptions import DeclarationCatalogError
from .external_result import (
    ExternalAcquisitionResult,
    _ExternalAcquisitionResultState,
    _issued_external_result_state,
)
from .loader import LoadedDeclarationSource
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

CATALOG_INDEX_REVISION = 2
_T = TypeVar("_T")


@dataclass(frozen=True, order=True)
class ExactContractKey:
    """One exact evaluator or operation contract key."""

    kind: DeclarationKind
    id: str
    version: int


@dataclass(frozen=True)
class CatalogSource:
    """Portable provenance for one source snapshot."""

    namespace: str | None
    path: str
    sha256: str


@dataclass(frozen=True)
class DeclarationCatalog:
    """Immutable static lookups over one validated declaration registry."""

    revision: int
    facet_content_revision: str | None
    source_root: Path | None
    sources: tuple[CatalogSource, ...]
    declarations: Mapping[str, RegisteredDeclaration]
    contracts: Mapping[ExactContractKey, RegisteredDeclaration]
    conflicts: tuple[tuple[str, str], ...]

    def get(self, identifier: str) -> RegisteredDeclaration | None:
        """Return one unversioned record, or ``None`` when it is absent."""
        return _authenticated_catalog_operation(
            self, lambda: self.declarations.get(identifier)
        )

    def get_contract(
        self,
        kind: DeclarationKind,
        identifier: str,
        version: int,
    ) -> RegisteredDeclaration | None:
        """Return one exact evaluator or operation contract when present."""

        def lookup() -> RegisteredDeclaration | None:
            if kind not in EXACT_CONTRACT_KINDS:
                raise ValueError(f"{kind.value!r} is not an exact contract kind")
            return self.contracts.get(ExactContractKey(kind, identifier, version))

        return _authenticated_catalog_operation(self, lookup)

    def filter_static(
        self, query: StaticCatalogQuery
    ) -> tuple[RegisteredDeclaration, ...]:
        """Return records whose stored fields satisfy every exact predicate."""
        return _authenticated_catalog_operation(
            self, lambda: self._filter_static(query)
        )

    def _filter_static(
        self, query: StaticCatalogQuery
    ) -> tuple[RegisteredDeclaration, ...]:
        """Apply one static query inside an authenticated operation."""
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
        return _authenticated_catalog_operation(
            self, lambda: self._filter_enforcement(enforcement)
        )

    def _filter_enforcement(
        self, enforcement: EnforcementClass
    ) -> tuple[EnforcementLocator, ...]:
        """Enumerate obligations inside an authenticated operation."""
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


class _CatalogAuthorityState(NamedTuple):
    """Bind one catalog identity to its complete private authority graph."""

    result: ExternalAcquisitionResult | None
    result_state: _ExternalAcquisitionResultState | None
    source_map: tuple[tuple[LoadedDeclarationSource, CatalogSource], ...]
    source_map_state: object
    projection_state: object


_CATALOG_AUTHORITIES: IdentityAuthorityStore[object] = IdentityAuthorityStore()


def build_declaration_catalog(
    result: ExternalAcquisitionResult,
) -> DeclarationCatalog:
    """Build revision 2 lookups from one issued external acquisition result."""
    state = _issued_external_result_state(result)
    catalog: DeclarationCatalog | None = None
    try:
        catalog = _build_external_catalog(state, result)
    except BaseException as error:
        try:
            _issued_external_result_state(result)
        except BaseException as authority_error:
            if catalog is not None:
                _CATALOG_AUTHORITIES.retire(catalog)
            raise authority_error from error
        raise
    try:
        if _issued_external_result_state(result) is not state:
            raise DeclarationCatalogError(
                "external acquisition authority state changed"
            )
        _issued_catalog_state(catalog)
    except BaseException:
        _CATALOG_AUTHORITIES.retire(catalog)
        raise
    return catalog


def _build_external_catalog(
    state: _ExternalAcquisitionResultState,
    result: ExternalAcquisitionResult,
) -> DeclarationCatalog:
    """Project one authenticated result state without using transport paths."""
    registry = state.external_registry_state.registry
    declarations, contracts = _catalog_records(registry)
    records = (*declarations.values(), *contracts.values())
    registered_sources = {id(record.source): record.source for record in records}
    sources: list[CatalogSource] = []
    source_map: list[tuple[LoadedDeclarationSource, CatalogSource]] = []
    for loaded, coordinate in state.source_map:
        if id(loaded) not in registered_sources:
            continue
        source = CatalogSource(
            namespace=coordinate.namespace,
            path=coordinate.path,
            sha256=coordinate.sha256,
        )
        sources.append(source)
        source_map.append((loaded, source))
    if (
        len(state.source_map) != len(registered_sources)
        or len(source_map) != len(registered_sources)
        or len(registry.paths) != len(state.source_map)
        or any(
            path is not loaded.path
            for path, (loaded, _coordinate) in zip(
                registry.paths, state.source_map, strict=True
            )
        )
        or any(
            loaded is not registered_sources[id(loaded)]
            for loaded, _source in source_map
        )
    ):
        raise DeclarationCatalogError(
            "acquisition result does not map every registered source exactly once"
        )
    source_map.sort(key=lambda item: (item[1].namespace or "", item[1].path))
    sources = [source for _loaded, source in source_map]
    if len({(source.namespace, source.path) for source in sources}) != len(sources):
        raise DeclarationCatalogError("duplicate portable source coordinate")
    catalog = DeclarationCatalog(
        revision=CATALOG_INDEX_REVISION,
        facet_content_revision=cast(
            CompositeFacetRegistry, state.stage_state.composite
        ).content_revision,
        source_root=None,
        sources=tuple(sources),
        declarations=declarations,
        contracts=contracts,
        conflicts=tuple(sorted(registry.conflicts)),
    )
    return _issue_catalog(catalog, result, state, tuple(source_map))


def _build_declaration_catalog_from_registry(
    registry: DeclarationRegistry,
    *,
    source_root: Path,
) -> DeclarationCatalog:
    """Build the legacy live projection for internal compatibility tests."""
    root = source_root.resolve()
    if not root.is_dir():
        raise DeclarationCatalogError(f"source root {root} is not a directory")
    declarations, contracts = _catalog_records(registry)
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
        sources.append(CatalogSource(None, relative_path.as_posix(), source.sha256))
    sources.sort(key=lambda item: item.path)
    catalog_source_by_path = {source.path: source for source in sources}
    catalog = DeclarationCatalog(
        revision=1,
        facet_content_revision=None,
        source_root=root,
        sources=tuple(sources),
        declarations=declarations,
        contracts=contracts,
        conflicts=tuple(sorted(registry.conflicts)),
    )
    source_map = tuple(
        (
            source_by_path[path.resolve()],
            catalog_source_by_path[path.resolve().relative_to(root).as_posix()],
        )
        for path in registry.paths
    )
    return _issue_catalog(catalog, None, None, source_map)


def _issue_catalog(
    catalog: DeclarationCatalog,
    result: ExternalAcquisitionResult | None,
    result_state: _ExternalAcquisitionResultState | None,
    source_map: tuple[tuple[LoadedDeclarationSource, CatalogSource], ...],
) -> DeclarationCatalog:
    """Issue one exact catalog and keep every authority field private."""
    state = _CatalogAuthorityState(
        result=result,
        result_state=result_state,
        source_map=source_map,
        source_map_state=identity_value_state(source_map),
        projection_state=_catalog_projection_state(catalog),
    )
    try:
        _CATALOG_AUTHORITIES.issue(catalog, state)
        _issued_catalog_state(catalog)
        return catalog
    except BaseException:
        _CATALOG_AUTHORITIES.retire(catalog)
        raise


def _issued_catalog_state(catalog: object) -> _CatalogAuthorityState:
    """Authenticate one catalog or retire its complete private authority."""
    try:
        return _authenticate_catalog_state(catalog)
    except BaseException:
        _CATALOG_AUTHORITIES.retire(catalog)
        raise


def _authenticate_catalog_state(catalog: object) -> _CatalogAuthorityState:
    """Check one catalog, its projection and its acquisition result."""
    if type(catalog) is not DeclarationCatalog:
        raise DeclarationCatalogError("catalog is not issued here")
    state = _CATALOG_AUTHORITIES.state(catalog)
    if type(state) is not _CatalogAuthorityState:
        raise DeclarationCatalogError("catalog is not issued here")
    if state.result is not None:
        result_state = _issued_external_result_state(state.result)
        if result_state is not state.result_state:
            raise DeclarationCatalogError("catalog acquisition authority state changed")
    elif state.result_state is not None:
        raise DeclarationCatalogError("legacy catalog carries an external result state")
    if identity_value_state(state.source_map) != state.source_map_state:
        raise DeclarationCatalogError("catalog source correlation changed")
    if _catalog_projection_state(catalog) != state.projection_state:
        raise DeclarationCatalogError("catalog projection state changed")
    return state


def _authenticated_catalog_operation(
    catalog: DeclarationCatalog,
    operation: Callable[[], _T],
) -> _T:
    """Bracket one public catalog traversal with complete authentication."""
    state = _issued_catalog_state(catalog)
    try:
        value = operation()
    except BaseException as error:
        try:
            _issued_catalog_state(catalog)
        except BaseException as authority_error:
            raise authority_error from error
        raise
    if _issued_catalog_state(catalog) is not state:
        raise DeclarationCatalogError("catalog authority state changed")
    return value


def _catalog_records(
    registry: DeclarationRegistry,
) -> tuple[
    Mapping[str, RegisteredDeclaration],
    Mapping[ExactContractKey, RegisteredDeclaration],
]:
    """Return canonical immutable record maps for one validated registry."""
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
    return declarations, MappingProxyType(dict(contract_items))


def catalog_json_bytes(catalog: DeclarationCatalog) -> bytes:
    """Serialize one revision 2 catalog as deterministic portable JSON."""

    def serialize() -> bytes:
        if catalog.revision != CATALOG_INDEX_REVISION:
            raise DeclarationCatalogError("the public emitter accepts revision 2 only")
        state = _issued_catalog_state(catalog)
        if state.result is None:
            raise DeclarationCatalogError(
                "revision 2 catalog lacks acquisition authority"
            )
        return _catalog_json_bytes(catalog, state.source_map)

    return _authenticated_catalog_operation(catalog, serialize)


def _legacy_catalog_json_bytes(catalog: DeclarationCatalog) -> bytes:
    """Serialize one private revision 1 catalog for compatibility tests."""

    def serialize() -> bytes:
        if catalog.revision != 1:
            raise DeclarationCatalogError("the legacy emitter accepts revision 1 only")
        return _catalog_json_bytes(catalog, _issued_catalog_state(catalog).source_map)

    return _authenticated_catalog_operation(catalog, serialize)


def _catalog_json_bytes(
    catalog: DeclarationCatalog,
    source_map: tuple[tuple[LoadedDeclarationSource, CatalogSource], ...],
) -> bytes:
    """Serialize one admitted catalog revision."""
    contract_items = sorted(
        catalog.contracts.items(),
        key=lambda item: (item[0].kind.value, item[0].id, item[0].version),
    )
    conflicts = sorted(tuple(sorted(pair)) for pair in catalog.conflicts)
    payload: dict[str, object] = {
        "index-revision": catalog.revision,
        "sources": [
            _source_payload(source)
            for source in sorted(
                catalog.sources, key=lambda item: (item.namespace or "", item.path)
            )
        ],
        "declarations": [
            _entry_payload(record, source_map=source_map)
            for _, record in sorted(catalog.declarations.items())
        ],
        "contracts": [
            _entry_payload(record, source_map=source_map, version=key.version)
            for key, record in contract_items
        ],
        "conflicts": [list(pair) for pair in conflicts],
    }
    if catalog.revision == CATALOG_INDEX_REVISION:
        if catalog.facet_content_revision is None:
            raise DeclarationCatalogError("revision 2 lacks a facet content revision")
        payload["facet-content-revision"] = catalog.facet_content_revision
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


def _source_payload(source: CatalogSource) -> dict[str, object]:
    """Project one source row according to its catalog revision."""
    payload: dict[str, object] = {"path": source.path, "sha256": source.sha256}
    if source.namespace is not None:
        payload["namespace"] = source.namespace
    return payload


def _catalog_projection_state(catalog: DeclarationCatalog) -> object:
    """Snapshot every public projection field that can affect emitted bytes."""
    return tuple(
        identity_value_state(value)
        for value in (
            catalog.revision,
            catalog.facet_content_revision,
            catalog.sources,
            catalog.declarations,
            catalog.contracts,
            catalog.conflicts,
        )
    )


def _entry_payload(
    record: RegisteredDeclaration,
    *,
    source_map: tuple[tuple[LoadedDeclarationSource, CatalogSource], ...],
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
            **_record_source_payload(source_map, record),
            "document-path": list(record.root),
            "line": location.line if location is not None else None,
            "column": location.column if location is not None else None,
        },
    }
    if version is not None:
        payload["version"] = version
    return payload


def _record_source_payload(
    source_map: tuple[tuple[LoadedDeclarationSource, CatalogSource], ...],
    record: RegisteredDeclaration,
) -> dict[str, object]:
    """Resolve one record through the exact source identity retained by a catalog."""
    matches = [source for loaded, source in source_map if loaded is record.source]
    if len(matches) != 1:
        raise DeclarationCatalogError(
            f"record {record.declaration.id!r} lacks one exact source coordinate"
        )
    source = matches[0]
    payload: dict[str, object] = {"path": source.path}
    if source.namespace is not None:
        payload["namespace"] = source.namespace
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
