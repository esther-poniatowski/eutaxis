"""Project authenticated external resolution into portable query packets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
import hashlib
from pathlib import Path
from types import MappingProxyType
from typing import Literal, NoReturn, SupportsIndex, cast

from ._authority import IdentityAuthorityStore, identity_value_state
from .canonical_json import CanonicalJsonError, jcs_bytes
from .catalog import CATALOG_INDEX_REVISION
from .external_resolution import (
    ExternalResolutionResult,
    _issued_external_resolution_state,
)
from .external_result import AcquiredResource, AcquisitionSourceCoordinate
from .exceptions import QueryPacketError
from .models import (
    CompositionManifestDeclaration,
    JsonValue,
    OperationDeclaration,
    ProcedureDeclaration,
    RuleDeclaration,
    RuleSetDeclaration,
    VersionedReference,
)
from .registry import RegisteredDeclaration
from .query_packet_schema import validate_query_packet_payload
from .resolution import ResolutionEvent, ResolutionEventKind
from .resolution_serialization import coordinate_payload, event_payload, plain_json

QUERY_PACKET_SCHEMA = "eutaxis:query-packet@1"


class QuerySelectionOutcome(StrEnum):
    """The closed final-state vocabulary for considered declarations."""

    EFFECTIVE = "effective"
    EXCLUDED = "excluded"
    INAPPLICABLE = "inapplicable"
    INACTIVE = "inactive"


@dataclass(frozen=True)
class QuerySourceRevision:
    """Identify one acquired source group and its content revision."""

    role: Literal["facet-base", "facet-extension", "declaration-source"]
    namespace: str
    kind: str
    content_revision: str


@dataclass(frozen=True)
class QuerySelection:
    """Explain the final state of one declaration considered by resolution."""

    declaration: str
    outcome: QuerySelectionOutcome
    source_revision: str
    source: AcquisitionSourceCoordinate
    reason_events: tuple[int, ...]


class QueryPacket:
    """One module-issued, deterministic projection of a completed query.

    Callers cannot construct, copy or pickle this capability. Obtain an issued
    value from :func:`build_external_query_packet` and use
    :func:`query_packet_json_bytes` for its portable, unsigned projection.
    """

    __slots__ = ("__weakref__",)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("query packets must be issued")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("query packets cannot be subclassed")

    @property
    def payload(self) -> Mapping[str, JsonValue]:
        """Return the immutable normalized packet payload."""
        return _issued_query_packet_payload(self)

    @property
    def manifest(self) -> str:
        """Return the resolved manifest identifier."""
        return cast(str, self.payload["manifest"])

    @property
    def context(self) -> Mapping[str, JsonValue]:
        """Return the normalized context used by resolution."""
        return cast(Mapping[str, JsonValue], self.payload["context"])

    @property
    def source_revisions(self) -> tuple[QuerySourceRevision, ...]:
        """Return the acquired source groups and their exact revisions."""
        rows = cast(
            tuple[Mapping[str, JsonValue], ...], self.payload["source-revisions"]
        )
        return tuple(
            QuerySourceRevision(
                cast(
                    Literal["facet-base", "facet-extension", "declaration-source"],
                    row["role"],
                ),
                cast(str, row["namespace"]),
                cast(str, row["kind"]),
                cast(str, row["content-revision"]),
            )
            for row in rows
        )

    @property
    def sources(self) -> tuple[AcquisitionSourceCoordinate, ...]:
        """Return the portable coordinates of every acquired declaration file."""
        rows = cast(tuple[Mapping[str, JsonValue], ...], self.payload["sources"])
        return tuple(
            AcquisitionSourceCoordinate(
                cast(str, row["namespace"]),
                cast(str, row["path"]),
                cast(str, row["sha256"]),
            )
            for row in rows
        )

    @property
    def selections(self) -> tuple[QuerySelection, ...]:
        """Return the final state and explanation events of each candidate."""
        rows = cast(tuple[Mapping[str, JsonValue], ...], self.payload["selections"])
        return tuple(_selection_from_payload(row) for row in rows)

    def __copy__(self) -> NoReturn:
        raise TypeError("query packets cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("query packets cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("query packets cannot be serialized directly")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("query packets cannot be serialized directly")


_QUERY_PACKET_AUTHORITIES: IdentityAuthorityStore[object] = IdentityAuthorityStore()


def build_external_query_packet(result: ExternalResolutionResult) -> QueryPacket:
    """Build a portable packet from one authenticated completed resolution.

    The packet deliberately includes the complete normalized context and
    applicability observations. Callers must therefore apply their disclosure
    policy before storing or forwarding its canonical bytes.
    """
    state = _issued_external_resolution_state(result)
    resolution = state.resolution
    acquisition = state.acquisition_state
    source_by_path = MappingProxyType(dict(state.source_coordinates_by_path))
    selections = _selection_records(resolution, acquisition.source_map)
    source_revisions = _source_revisions(acquisition.evidence_state.lock)
    declarations, controls, contracts, decisions = _consumer_records(
        resolution,
        acquisition.source_map,
        selections,
    )
    payload = _packet_payload(
        manifest=resolution.unit.manifest,
        context=resolution.context,
        acquisition_schema_version=acquisition.evidence_state.lock.schema_version,
        facet_registry=resolution.trace.facet_registry,
        facet_schema_version=resolution.registry.facet_registry.schema_version,
        facet_content_revision=resolution.trace.facet_content_revision,
        source_revisions=source_revisions,
        sources=acquisition.source_coordinates,
        source_map=acquisition.source_map,
        resources=acquisition.resources,
        declarations=declarations,
        controls=controls,
        contracts=contracts,
        decisions=decisions,
        selections=selections,
        events=resolution.trace.events,
        source_by_path=source_by_path,
        resolution=resolution,
    )
    validate_query_packet_payload(payload)
    try:
        jcs_bytes(payload)
    except CanonicalJsonError as exc:
        raise QueryPacketError(f"query packet is not canonical JSON: {exc}") from exc
    packet = _issue_query_packet(
        cast(
            Mapping[str, JsonValue],
            _freeze_packet(validate_query_packet_payload(payload)),
        )
    )
    _issued_external_resolution_state(result)
    return packet


def query_packet_json_bytes(packet: QueryPacket) -> bytes:
    """Return canonical JSON bytes for one module-issued query packet."""
    payload = plain_json(_issued_query_packet_payload(packet))
    validate_query_packet_payload(payload)
    return jcs_bytes(payload)


def _issue_query_packet(payload: Mapping[str, JsonValue]) -> QueryPacket:
    packet = object.__new__(QueryPacket)
    state = (payload, identity_value_state(payload))
    _QUERY_PACKET_AUTHORITIES.issue(packet, state)
    _issued_query_packet_payload(packet)
    return packet


def _issued_query_packet_payload(packet: object) -> Mapping[str, JsonValue]:
    if type(packet) is not QueryPacket:
        raise QueryPacketError("query packet is not issued here")
    state = _QUERY_PACKET_AUTHORITIES.state(packet)
    if (
        type(state) is not tuple
        or len(state) != 2
        or not isinstance(state[0], Mapping)
        or identity_value_state(state[0]) != state[1]
    ):
        _QUERY_PACKET_AUTHORITIES.retire(packet)
        raise QueryPacketError("query packet authority changed")
    return cast(Mapping[str, JsonValue], state[0])


def _source_revisions(lock: object) -> tuple[QuerySourceRevision, ...]:
    """Project the authenticated lock's ordered source revisions."""
    from .acquisition_contract import AcquisitionLock

    if type(lock) is not AcquisitionLock:
        raise TypeError("query packet requires an exact acquisition lock")
    admitted = cast(AcquisitionLock, lock)
    facet_items = (admitted.facet_registry.base, *admitted.facet_registry.extensions)
    revisions = [
        QuerySourceRevision(
            "facet-base" if index == 0 else "facet-extension",
            item.namespace,
            item.kind,
            item.content_revision,
        )
        for index, item in enumerate(facet_items)
    ]
    internal = admitted.internal_source
    revisions.append(
        QuerySourceRevision(
            "declaration-source",
            internal.namespace,
            internal.kind,
            internal.content_revision,
        )
    )
    revisions.extend(
        QuerySourceRevision(
            "declaration-source",
            item.namespace,
            item.kind.value,
            item.content_revision,
        )
        for item in admitted.sources
    )
    return tuple(revisions)


def _selection_records(
    resolution: object, source_map: object
) -> tuple[QuerySelection, ...]:
    """Derive one closed outcome for every considered declaration."""
    from .loader import LoadedDeclarationSource
    from .resolution import ResolutionResult

    if type(resolution) is not ResolutionResult or type(source_map) is not tuple:
        raise TypeError("query selection requires authenticated resolver state")
    admitted = cast(ResolutionResult, resolution)
    coordinates: dict[int, AcquisitionSourceCoordinate] = {}
    for item in cast(
        tuple[tuple[LoadedDeclarationSource, AcquisitionSourceCoordinate], ...],
        source_map,
    ):
        coordinates[id(item[0])] = item[1]
    relevant = {
        ResolutionEventKind.MANIFEST_SELECTED,
        ResolutionEventKind.RULE_SET_MEMBER_EXPANDED,
        ResolutionEventKind.RULE_SET_MEMBER_INACTIVE,
        ResolutionEventKind.DEPENDENCY_DISCOVERED,
        ResolutionEventKind.POLICY_RESULT_DISCOVERED,
        ResolutionEventKind.DECLARATION_EVALUATED,
        ResolutionEventKind.DECLARATION_EXCLUDED,
        ResolutionEventKind.ALIAS_CREATED,
        ResolutionEventKind.DECLARATION_EFFECTIVE,
    }
    candidates = {
        event.declaration
        for event in admitted.trace.events
        if event.kind
        in {
            ResolutionEventKind.RULE_SET_MEMBER_INACTIVE,
            ResolutionEventKind.DECLARATION_EVALUATED,
        }
    }
    records: list[QuerySelection] = []
    for identifier in sorted(candidates):
        events = tuple(
            event
            for event in admitted.trace.events
            if event.declaration == identifier and event.kind in relevant
        )
        outcome = _selection_outcome(events)
        record = admitted.registry.records[identifier]
        coordinate = coordinates.get(id(record.source))
        if coordinate is None:
            raise ValueError(f"source coordinate missing for {identifier!r}")
        records.append(
            QuerySelection(
                identifier,
                outcome,
                record.declaration.source_revision,
                coordinate,
                tuple(event.ordinal for event in events),
            )
        )
    return tuple(records)


def _selection_outcome(events: tuple[ResolutionEvent, ...]) -> QuerySelectionOutcome:
    kinds = {event.kind for event in events}
    if ResolutionEventKind.DECLARATION_EFFECTIVE in kinds:
        return QuerySelectionOutcome.EFFECTIVE
    if ResolutionEventKind.DECLARATION_EXCLUDED in kinds:
        return QuerySelectionOutcome.EXCLUDED
    if ResolutionEventKind.RULE_SET_MEMBER_INACTIVE in kinds:
        return QuerySelectionOutcome.INACTIVE
    evaluations = [
        event
        for event in events
        if event.kind is ResolutionEventKind.DECLARATION_EVALUATED
    ]
    if len(evaluations) == 1 and evaluations[0].truth is not None:
        if evaluations[0].truth.value == "false":
            return QuerySelectionOutcome.INAPPLICABLE
    raise ValueError("completed resolution left a considered declaration unresolved")


def _consumer_records(
    resolution: object,
    source_map: object,
    selections: tuple[QuerySelection, ...],
) -> tuple[
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
]:
    """Project the effective declarations and their exact contract closure."""
    from .loader import LoadedDeclarationSource
    from .resolution import ResolutionResult

    if type(resolution) is not ResolutionResult or type(source_map) is not tuple:
        raise TypeError("query records require authenticated resolver state")
    admitted = cast(ResolutionResult, resolution)
    coordinates = {
        id(loaded): coordinate
        for loaded, coordinate in cast(
            tuple[tuple[LoadedDeclarationSource, AcquisitionSourceCoordinate], ...],
            source_map,
        )
    }
    projections = {
        projection.declaration: projection
        for projection in admitted.unit.rule_projections
    }
    declarations: list[dict[str, object]] = []
    references: set[VersionedReference] = set()
    decision_ids: set[str] = set()
    for selection in selections:
        record = admitted.registry.records[selection.declaration]
        projection = projections.get(selection.declaration)
        declarations.append(_record_payload(record, coordinates, projection))
        if selection.outcome is not QuerySelectionOutcome.EFFECTIVE:
            continue
        declaration = record.declaration
        if isinstance(declaration, RuleDeclaration):
            assert projection is not None
            effective_criteria = set(projection.criteria)
            references.update(
                criterion.evaluator
                for criterion in declaration.criteria
                if criterion.id in effective_criteria
            )
            decision_ids.update(declaration.decided_by)
        elif isinstance(declaration, ProcedureDeclaration):
            references.update(
                predicate.evaluator
                for predicate in (
                    *declaration.preconditions,
                    *declaration.invariants,
                    *declaration.postconditions,
                )
                if predicate.evaluator is not None
            )
            references.update(action.operation for action in declaration.actions)

    pending = list(references)
    records: dict[tuple[str, int], RegisteredDeclaration] = {}
    while pending:
        reference = pending.pop()
        key = (reference.id, reference.version)
        if key in records:
            continue
        family = admitted.registry.families[reference.id]
        record = family.versions[reference.version]
        records[key] = record
        if isinstance(record.declaration, OperationDeclaration):
            for predicate in record.declaration.preconditions:
                if predicate.evaluator is not None:
                    pending.append(predicate.evaluator)
    contracts = tuple(
        _record_payload(record, coordinates, None, version=version)
        for (identifier, version), record in sorted(records.items())
    )
    candidate_ids = {selection.declaration for selection in selections}
    control_ids: list[str] = [admitted.unit.manifest]
    for event in admitted.trace.events:
        if event.kind is ResolutionEventKind.MANIFEST_SELECTED:
            if event.declaration not in candidate_ids:
                control_ids.append(event.declaration)
    manifest = cast(
        CompositionManifestDeclaration, admitted.manifest_record.declaration
    )
    control_ids.extend(manifest.policies)
    controls = tuple(
        _record_payload(admitted.registry.records[identifier], coordinates, None)
        for identifier in dict.fromkeys(control_ids)
    )
    decisions = tuple(
        _record_payload(admitted.registry.records[identifier], coordinates, None)
        for identifier in sorted(decision_ids)
    )
    return tuple(declarations), controls, contracts, decisions


def _record_payload(
    record: RegisteredDeclaration,
    coordinates: Mapping[int, AcquisitionSourceCoordinate],
    projection: object,
    *,
    version: int | None = None,
) -> dict[str, object]:
    """Detach one complete declaration with its effective local projection."""
    from .resolution import ResolvedRuleProjection

    declaration = record.declaration
    coordinate = coordinates.get(id(record.source))
    if coordinate is None:
        raise ValueError(f"source coordinate missing for {declaration.id!r}")
    document = _normalized_document(record)
    payload: dict[str, object] = {
        "id": declaration.id,
        "kind": declaration.kind.value,
        "source-revision": declaration.source_revision,
        "source": {
            **coordinate_payload(coordinate),
            "document-path": list(record.root),
        },
        "document": document,
    }
    if version is not None:
        payload["version"] = version
    if projection is not None:
        admitted = cast(ResolvedRuleProjection, projection)
        payload["effective-rule"] = {
            "norms": list(admitted.norms),
            "criteria": list(admitted.criteria),
        }
    digest_material = {
        "document": document,
        "effective-rule": payload.get("effective-rule"),
        "version": version,
    }
    payload["record-digest"] = (
        "sha256:" + hashlib.sha256(jcs_bytes(digest_material)).hexdigest()
    )
    return payload


def _normalized_document(record: RegisteredDeclaration) -> dict[str, object]:
    """Return the complete consumer form of one registered declaration."""
    declaration = record.declaration
    document = cast(dict[str, object], plain_json(declaration.document))
    document["applicability"] = plain_json(declaration.applicability)
    if isinstance(declaration, RuleDeclaration):
        _normalize_rule_document(document, declaration)
    elif isinstance(declaration, RuleSetDeclaration):
        rules = cast(list[dict[str, object]], document["rules"])
        for rule_document, rule in zip(rules, declaration.rules, strict=True):
            rule_document["applicability"] = plain_json(rule.applicability)
            _normalize_rule_document(rule_document, rule)
    return document


def _normalize_rule_document(
    document: dict[str, object], declaration: RuleDeclaration
) -> None:
    """Project inherited rule predicates into one detached rule document."""
    norm_by_id = {norm.id: norm for norm in declaration.norms}
    for item in cast(list[dict[str, object]], document["norms"]):
        item["applies-when"] = plain_json(
            norm_by_id[cast(str, item["id"])].applicability
        )
    exception_by_id = {item.id: item for item in declaration.exceptions}
    for item in cast(list[dict[str, object]], document.get("exceptions", [])):
        item["when"] = plain_json(exception_by_id[cast(str, item["id"])].when)


def _packet_payload(
    *,
    manifest: str,
    context: Mapping[str, JsonValue],
    acquisition_schema_version: int,
    facet_registry: str,
    facet_schema_version: int,
    facet_content_revision: str,
    source_revisions: tuple[QuerySourceRevision, ...],
    sources: tuple[AcquisitionSourceCoordinate, ...],
    source_map: object,
    resources: tuple[AcquiredResource, ...],
    declarations: tuple[dict[str, object], ...],
    controls: tuple[dict[str, object], ...],
    contracts: tuple[dict[str, object], ...],
    decisions: tuple[dict[str, object], ...],
    selections: tuple[QuerySelection, ...],
    events: tuple[ResolutionEvent, ...],
    source_by_path: Mapping[Path, AcquisitionSourceCoordinate],
    resolution: object,
) -> dict[str, object]:
    from .resolution import ResolutionResult

    admitted = cast(ResolutionResult, resolution)
    return {
        "_schema": QUERY_PACKET_SCHEMA,
        "completion": "complete",
        "manifest": manifest,
        "context": plain_json(context),
        "acquisition-schema-version": acquisition_schema_version,
        "catalog-index-revision": CATALOG_INDEX_REVISION,
        "facet-registry": {
            "id": facet_registry,
            "schema-version": facet_schema_version,
            "content-revision": facet_content_revision,
        },
        "source-revisions": [
            {
                "role": item.role,
                "namespace": item.namespace,
                "kind": item.kind,
                "content-revision": item.content_revision,
            }
            for item in source_revisions
        ],
        "sources": _source_payloads(sources, source_map, admitted.registry),
        "resources": [
            {
                "namespace": item.namespace,
                "id": item.id,
                "path": item.path,
                "media-type": item.media_type,
                "sha256": item.sha256,
                "text": item.data.decode("utf-8", errors="strict"),
            }
            for item in resources
        ],
        "declarations": list(declarations),
        "controls": list(controls),
        "contracts": list(contracts),
        "decisions": list(decisions),
        "unit": {
            "components": [
                {
                    "section": item.section,
                    "declaration": item.declaration,
                    "rank": item.rank,
                }
                for item in admitted.unit.components
            ],
            "dependencies": [
                {"prerequisite": item.prerequisite, "dependant": item.dependant}
                for item in admitted.unit.dependencies
            ],
            "rule-projections": [
                {
                    "declaration": item.declaration,
                    "norms": list(item.norms),
                    "criteria": list(item.criteria),
                }
                for item in admitted.unit.rule_projections
            ],
        },
        "selections": [
            {
                "declaration": item.declaration,
                "outcome": item.outcome.value,
                "source-revision": item.source_revision,
                "source": coordinate_payload(item.source),
                "reason-events": list(item.reason_events),
            }
            for item in selections
        ],
        "trace": [
            event_payload(event, source_by_path[event.source.path]) for event in events
        ],
    }


def _source_payloads(
    sources: tuple[AcquisitionSourceCoordinate, ...],
    source_map: object,
    registry: object,
) -> list[dict[str, object]]:
    """Detach acquired record identities and normalized content bindings."""
    from .loader import LoadedDeclarationSource
    from .registry import DeclarationRegistry

    admitted = cast(
        tuple[tuple[LoadedDeclarationSource, AcquisitionSourceCoordinate], ...],
        source_map,
    )
    if tuple(coordinate for _loaded, coordinate in admitted) != sources:
        raise ValueError("query packet source map differs from acquired coordinates")
    registered = cast(DeclarationRegistry, registry)
    record_by_key: dict[tuple[str, int | None], RegisteredDeclaration] = {
        (identifier, None): record for identifier, record in registered.records.items()
    }
    record_by_key.update(
        {
            (identifier, version): record
            for identifier, family in registered.families.items()
            for version, record in family.versions.items()
        }
    )
    return [
        {
            **coordinate_payload(coordinate),
            "records": _source_record_entries(loaded, record_by_key),
        }
        for loaded, coordinate in admitted
    ]


def _source_record_entries(
    loaded: object,
    record_by_key: Mapping[tuple[str, int | None], RegisteredDeclaration],
) -> list[dict[str, object]]:
    """Index record identities directly from one acquired parsed document."""
    from .loader import LoadedDeclarationSource

    source = cast(LoadedDeclarationSource, loaded)
    document = source.document
    entries: list[dict[str, object]] = []

    def append_record(value: Mapping[str, JsonValue], path: list[object]) -> None:
        entry: dict[str, object] = {
            "id": value["id"],
            "kind": value["kind"],
            "source-revision": value["source-revision"],
            "document-path": path,
        }
        if "version" in value:
            entry["version"] = value["version"]
        key = (cast(str, value["id"]), cast(int | None, value.get("version")))
        record = record_by_key.get(key)
        if record is None or record.source is not source or list(record.root) != path:
            raise ValueError(f"source record index cannot locate {key!r}")
        entry["content-digest"] = (
            "sha256:"
            + hashlib.sha256(jcs_bytes(_normalized_document(record))).hexdigest()
        )
        entries.append(entry)

    append_record(document, [])
    if document.get("kind") == "rule-set":
        for index, rule in enumerate(
            cast(list[Mapping[str, JsonValue]], document["rules"])
        ):
            append_record(rule, ["rules", index])
    return entries


def _selection_from_payload(row: Mapping[str, JsonValue]) -> QuerySelection:
    source = cast(Mapping[str, JsonValue], row["source"])
    return QuerySelection(
        cast(str, row["declaration"]),
        QuerySelectionOutcome(cast(str, row["outcome"])),
        cast(str, row["source-revision"]),
        AcquisitionSourceCoordinate(
            cast(str, source["namespace"]),
            cast(str, source["path"]),
            cast(str, source["sha256"]),
        ),
        cast(tuple[int, ...], row["reason-events"]),
    )


def _freeze_packet(value: object) -> JsonValue:
    from .models import freeze_json

    return freeze_json(value)
