"""Load and apply the packaged query-packet schema."""

from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Mapping, NoReturn, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import best_match  # type: ignore[import-untyped]

from .. import data_path
from .acquisition_contract import (
    LockedFile,
    LockedResource,
    composite_facet_content_revision,
    source_content_revision,
)
from .exceptions import QueryPacketError
from .canonical_json import jcs_bytes
from .models import json_values_equal

QUERY_PACKET_SCHEMA_FILENAME = "query-packet-v1.schema.json"


def query_packet_schema_path() -> Path:
    """Return the packaged path of the query-packet schema."""
    return data_path() / "schemas" / QUERY_PACKET_SCHEMA_FILENAME


@lru_cache(maxsize=1)
def _query_packet_schema() -> dict[str, object]:
    """Load the immutable shared schema source."""
    try:
        value = json.loads(query_packet_schema_path().read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QueryPacketError(f"cannot load query-packet schema: {exc}") from exc
    if type(value) is not dict:
        raise QueryPacketError("query-packet schema root must be an object")
    Draft202012Validator.check_schema(value)
    return cast(dict[str, object], value)


def query_packet_schema() -> dict[str, object]:
    """Return an isolated copy of the query-packet schema."""
    return deepcopy(_query_packet_schema())


@lru_cache(maxsize=1)
def _query_packet_validator() -> Draft202012Validator:
    """Return the shared validator for emitted packet values."""
    return Draft202012Validator(_query_packet_schema())


def validate_query_packet_payload(payload: object) -> Mapping[str, object]:
    """Validate one query-packet payload and return its mapping."""
    error = best_match(_query_packet_validator().iter_errors(payload))
    if error is not None:
        location = _json_path(tuple(error.absolute_path))
        raise QueryPacketError(f"Invalid query packet at {location}: {error.message}")
    admitted = cast(Mapping[str, object], payload)
    _validate_packet_relations(admitted)
    return admitted


_SELECTION_REASON_KINDS = frozenset(
    {
        "manifest-selected",
        "rule-set-member-expanded",
        "rule-set-member-inactive",
        "dependency-discovered",
        "policy-result-discovered",
        "declaration-evaluated",
        "declaration-excluded",
        "alias-created",
        "declaration-effective",
    }
)
_EVENT_FIELDS = {
    "manifest-evaluated": frozenset({"truth", "applicability"}),
    "manifest-selected": frozenset({"anchor"}),
    "rule-set-member-expanded": frozenset({"anchor"}),
    "rule-set-member-inactive": frozenset({"anchor"}),
    "dependency-discovered": frozenset({"anchor", "relation", "dependant"}),
    "policy-result-discovered": frozenset({"anchor", "policy", "conflict"}),
    "declaration-evaluated": frozenset({"anchor", "truth", "applicability"}),
    "conflict-detected": frozenset({"conflict"}),
    "policy-evaluated": frozenset({"conflict", "truth", "applicability"}),
    "conflict-resolved": frozenset({"policy", "conflict"}),
    "declaration-excluded": frozenset({"policy", "conflict"}),
    "alias-created": frozenset({"policy", "conflict", "replacement"}),
    "declaration-effective": frozenset({"anchor"}),
    "norm-evaluated": frozenset({"norm", "truth", "applicability"}),
    "exception-evaluated": frozenset({"exception", "truth", "applicability"}),
    "norm-removed": frozenset({"norm", "exception"}),
    "norm-substituted": frozenset({"norm", "exception"}),
    "norm-effective": frozenset({"norm"}),
    "criterion-effective": frozenset({"criterion"}),
    "criterion-inactive": frozenset({"criterion"}),
    "unit-issued": frozenset(),
}
_EVENT_BASE_FIELDS = frozenset({"ordinal", "kind", "declaration", "source", "causes"})


def _validate_packet_relations(payload: Mapping[str, object]) -> None:
    """Require every packet reference and final outcome to agree."""
    trace = cast(list[Mapping[str, object]], payload["trace"])
    manifest = cast(str, payload["manifest"])
    context = cast(Mapping[str, object], payload["context"])
    if not trace:
        _semantic_fail("$.trace", "completed packet requires resolver events")
    for index, event in enumerate(trace):
        if event["ordinal"] != index:
            _semantic_fail(
                f"$.trace[{index}].ordinal",
                "event ordinals must equal their sequence positions",
            )
        causes = cast(list[int], event["causes"])
        if causes != sorted(set(causes)):
            _semantic_fail(
                f"$.trace[{index}].causes",
                "event causes must be sorted and unique",
            )
        if any(cause >= index for cause in causes):
            _semantic_fail(
                f"$.trace[{index}].causes",
                "each cause must refer to an earlier event",
            )
        kind = cast(str, event["kind"])
        expected_fields = _EVENT_BASE_FIELDS | _EVENT_FIELDS[kind]
        if frozenset(event) != expected_fields:
            _semantic_fail(
                f"$.trace[{index}]",
                f"{kind!r} event fields must be {sorted(expected_fields)!r}",
            )
        if "applicability" in event:
            applicability = cast(Mapping[str, object], event["applicability"])
            evaluated = _validate_applicability(applicability, context, ())
            if event["truth"] != evaluated:
                _semantic_fail(
                    f"$.trace[{index}].truth",
                    "truth must equal applicability evaluated against packet context",
                )
    if trace[0]["kind"] != "manifest-evaluated" or trace[0]["declaration"] != manifest:
        _semantic_fail("$.trace[0]", "trace must open by evaluating its manifest")
    if trace[-1]["kind"] != "unit-issued" or trace[-1]["declaration"] != manifest:
        _semantic_fail("$.trace", "trace must close by issuing its manifest unit")

    source_keys = {
        _source_key(cast(Mapping[str, object], source))
        for source in cast(list[Mapping[str, object]], payload["sources"])
    }
    if len(source_keys) != len(cast(list[object], payload["sources"])):
        _semantic_fail("$.sources", "source coordinates must be unique")
    _validate_source_revisions(payload, source_keys)
    _validate_source_index_identifiers(payload)
    for index, event in enumerate(trace):
        if _source_key(cast(Mapping[str, object], event["source"])) not in source_keys:
            _semantic_fail(
                f"$.trace[{index}].source",
                "event source is absent from the acquired sources",
            )

    candidate_ids = {
        cast(str, event["declaration"])
        for event in trace
        if event["kind"] in {"declaration-evaluated", "rule-set-member-inactive"}
    }
    effective_events = {
        cast(str, event["declaration"])
        for event in trace
        if event["kind"] == "declaration-effective"
    }
    selections = cast(list[Mapping[str, object]], payload["selections"])
    selection_ids = [cast(str, selection["declaration"]) for selection in selections]
    if len(set(selection_ids)) != len(selection_ids):
        _semantic_fail("$.selections", "selection declarations must be unique")
    if set(selection_ids) != candidate_ids:
        _semantic_fail(
            "$.selections",
            "selections must cover exactly the declarations considered as candidates",
        )
    for index, selection in enumerate(selections):
        _validate_selection(index, selection, trace, source_keys)

    components = cast(
        list[Mapping[str, object]],
        cast(Mapping[str, object], payload["unit"])["components"],
    )
    component_ids = [cast(str, component["declaration"]) for component in components]
    if len(set(component_ids)) != len(component_ids):
        _semantic_fail("$.unit.components", "component declarations must be unique")
    effective_selections = {
        cast(str, selection["declaration"])
        for selection in selections
        if selection["outcome"] == "effective"
    }
    if (
        set(component_ids) != effective_selections
        or set(component_ids) != effective_events
    ):
        _semantic_fail(
            "$.unit.components",
            "components must equal the effective selections and resolver events",
        )
    expected_components = [
        {
            "section": cast(Mapping[str, object], event["anchor"])["section"],
            "declaration": event["declaration"],
            "rank": cast(Mapping[str, object], event["anchor"])["rank"],
        }
        for event in trace
        if event["kind"] == "declaration-effective"
    ]
    if components != expected_components:
        _semantic_fail(
            "$.unit.components",
            "component order and anchors must equal declaration-effective events",
        )
    _validate_dependencies(payload, trace, set(component_ids))
    _validate_rule_projections(payload, trace, set(component_ids))
    _validate_consumer_records(
        payload,
        selections,
        source_keys,
        trace,
    )
    _validate_source_record_bindings(payload)
    _validate_lifecycle_authority(payload)
    _validate_authored_relations(payload, trace)
    _validate_event_provenance(payload, trace)
    _validate_anchors(payload, trace)
    _validate_authored_applicability(payload, trace)
    _validate_complete_conflicts(payload, trace)
    _validate_complete_rule_semantics(payload, trace)
    _validate_event_causes(payload, trace)


def _validate_selection(
    index: int,
    selection: Mapping[str, object],
    trace: list[Mapping[str, object]],
    source_keys: set[tuple[object, object, object]],
) -> None:
    declaration = cast(str, selection["declaration"])
    expected_reasons = [
        event_index
        for event_index, event in enumerate(trace)
        if event["declaration"] == declaration
        and event["kind"] in _SELECTION_REASON_KINDS
    ]
    if selection["reason-events"] != expected_reasons:
        _semantic_fail(
            f"$.selections[{index}].reason-events",
            "reason events must be the complete ordered explanation for the declaration",
        )
    if _source_key(cast(Mapping[str, object], selection["source"])) not in source_keys:
        _semantic_fail(
            f"$.selections[{index}].source",
            "selection source is absent from the acquired sources",
        )
    events = [trace[event_index] for event_index in expected_reasons]
    candidate_sources = [
        _source_key(cast(Mapping[str, object], event["source"]))
        for event in events
        if event["kind"] in {"declaration-evaluated", "rule-set-member-inactive"}
    ]
    selection_source = _source_key(cast(Mapping[str, object], selection["source"]))
    if len(candidate_sources) != 1 or selection_source != candidate_sources[0]:
        _semantic_fail(
            f"$.selections[{index}].source",
            "selection source must equal its candidate-defining event source",
        )
    outcome = selection["outcome"]
    final_kinds = {
        cast(str, event["kind"])
        for event in events
        if event["kind"]
        in {
            "declaration-effective",
            "declaration-excluded",
            "rule-set-member-inactive",
        }
    }
    false_evaluation = any(
        event["kind"] == "declaration-evaluated" and event.get("truth") == "false"
        for event in events
    )
    expected = {
        "effective": ({"declaration-effective"}, False),
        "excluded": ({"declaration-excluded"}, False),
        "inactive": ({"rule-set-member-inactive"}, False),
        "inapplicable": (set(), True),
    }[cast(str, outcome)]
    if final_kinds != expected[0] or false_evaluation is not expected[1]:
        _semantic_fail(
            f"$.selections[{index}].outcome",
            "outcome contradicts the declaration's terminal resolver events",
        )


def _validate_source_revisions(
    payload: Mapping[str, object],
    source_keys: set[tuple[object, object, object]],
) -> None:
    revisions = cast(list[Mapping[str, object]], payload["source-revisions"])
    roles = [cast(str, revision["role"]) for revision in revisions]
    if not roles or roles[0] != "facet-base":
        _semantic_fail(
            "$.source-revisions", "the first revision must be the facet base"
        )
    declaration_offset = next(
        (index for index, role in enumerate(roles) if role == "declaration-source"),
        len(roles),
    )
    if any(role != "facet-extension" for role in roles[1:declaration_offset]):
        _semantic_fail(
            "$.source-revisions", "facet extensions must precede declaration sources"
        )
    if any(role != "declaration-source" for role in roles[declaration_offset:]):
        _semantic_fail(
            "$.source-revisions",
            "declaration sources must form the final revision group",
        )
    identities = [(revision["role"], revision["namespace"]) for revision in revisions]
    if len(set(identities)) != len(identities):
        _semantic_fail(
            "$.source-revisions", "source revision identities must be unique"
        )
    admitted_kinds = {"packaged", "workspace", "vendored", "git-submodule"}
    if any(revision["kind"] not in admitted_kinds for revision in revisions):
        _semantic_fail(
            "$.source-revisions",
            "source revision kinds must use the acquisition vocabulary",
        )
    source_namespaces = {cast(str, key[0]) for key in source_keys}
    revision_namespaces = {
        cast(str, revision["namespace"])
        for revision in revisions
        if revision["role"] == "declaration-source"
    }
    if revision_namespaces != source_namespaces:
        _semantic_fail(
            "$.source-revisions",
            "declaration-source revisions must cover every acquired source namespace",
        )
    facet_revisions = revisions[:declaration_offset]
    expected_composite = composite_facet_content_revision(
        cast(str, facet_revisions[0]["content-revision"]),
        tuple(
            cast(str, revision["content-revision"]) for revision in facet_revisions[1:]
        ),
    )
    facet_registry = cast(Mapping[str, object], payload["facet-registry"])
    if facet_registry["content-revision"] != expected_composite:
        _semantic_fail(
            "$.facet-registry.content-revision",
            "composite revision must bind the complete ordered facet revision list",
        )
    sources = cast(list[Mapping[str, object]], payload["sources"])
    resources = cast(list[Mapping[str, object]], payload["resources"])
    resource_ids: set[tuple[str, str]] = set()
    for index, resource in enumerate(resources):
        identity = (cast(str, resource["namespace"]), cast(str, resource["id"]))
        if identity in resource_ids:
            _semantic_fail("$.resources", "resource identities must be unique")
        resource_ids.add(identity)
        digest = (
            "sha256:"
            + hashlib.sha256(cast(str, resource["text"]).encode("utf-8")).hexdigest()
        )
        if resource["sha256"] != digest:
            _semantic_fail(
                f"$.resources[{index}].sha256",
                "resource digest differs from its UTF-8 text",
            )
    for revision in revisions[declaration_offset:]:
        namespace = cast(str, revision["namespace"])
        files = tuple(
            LockedFile(cast(str, source["path"]), cast(str, source["sha256"]))
            for source in sources
            if source["namespace"] == namespace
        )
        locked_resources = tuple(
            LockedResource(
                cast(str, resource["id"]),
                cast(str, resource["path"]),
                cast(str, resource["media-type"]),
                cast(str, resource["sha256"]),
            )
            for resource in resources
            if resource["namespace"] == namespace
        )
        expected_revision = source_content_revision(
            namespace,
            files,
            locked_resources,
        )
        if revision["content-revision"] != expected_revision:
            _semantic_fail(
                "$.source-revisions",
                f"content revision differs from emitted hashes for {namespace!r}",
            )


def _validate_source_index_identifiers(payload: Mapping[str, object]) -> None:
    """Reapply global declaration and exact-family identity invariants."""
    entries = [
        entry
        for source in cast(list[Mapping[str, object]], payload["sources"])
        for entry in cast(list[Mapping[str, object]], source["records"])
    ]
    unversioned = [
        cast(str, entry["id"]) for entry in entries if "version" not in entry
    ]
    if len(unversioned) != len(set(unversioned)):
        _semantic_fail(
            "$.sources", "unversioned declaration identifiers must be globally unique"
        )
    families: dict[str, dict[int, str]] = {}
    for entry in entries:
        if "version" not in entry:
            continue
        identifier = cast(str, entry["id"])
        version = cast(int, entry["version"])
        versions = families.setdefault(identifier, {})
        if version in versions:
            _semantic_fail(
                "$.sources", "contract family versions must be globally unique"
            )
        versions[version] = cast(str, entry["kind"])
    overlap = set(unversioned) & set(families)
    if overlap:
        _semantic_fail(
            "$.sources",
            "an identifier cannot name both a declaration and a contract family",
        )
    if any(len(set(versions.values())) != 1 for versions in families.values()):
        _semantic_fail(
            "$.sources", "every contract family must retain one declaration kind"
        )


def _validate_dependencies(
    payload: Mapping[str, object],
    trace: list[Mapping[str, object]],
    components: set[str],
) -> None:
    unit = cast(Mapping[str, object], payload["unit"])
    dependencies = cast(list[Mapping[str, object]], unit["dependencies"])
    actual = {
        (cast(str, edge["prerequisite"]), cast(str, edge["dependant"]))
        for edge in dependencies
    }
    if len(actual) != len(dependencies) or any(
        prerequisite not in components or dependant not in components
        for prerequisite, dependant in actual
    ):
        _semantic_fail(
            "$.unit.dependencies",
            "dependency endpoints must be unique effective components",
        )
    aliases = {
        cast(str, event["declaration"]): cast(str, event["replacement"])
        for event in trace
        if event["kind"] == "alias-created"
    }
    expected = {
        (
            aliases.get(
                cast(str, event["declaration"]), cast(str, event["declaration"])
            ),
            cast(str, event["dependant"]),
        )
        for event in trace
        if event["kind"] == "dependency-discovered" and event["dependant"] in components
    }
    if actual != expected:
        _semantic_fail(
            "$.unit.dependencies",
            "dependencies must equal the effective dependency-discovery events",
        )


def _validate_rule_projections(
    payload: Mapping[str, object],
    trace: list[Mapping[str, object]],
    components: set[str],
) -> None:
    unit = cast(Mapping[str, object], payload["unit"])
    projections = cast(list[Mapping[str, object]], unit["rule-projections"])
    actual_ids = [cast(str, projection["declaration"]) for projection in projections]
    if len(set(actual_ids)) != len(actual_ids) or any(
        identifier not in components for identifier in actual_ids
    ):
        _semantic_fail(
            "$.unit.rule-projections",
            "rule projections must identify unique effective components",
        )
    records = {
        cast(str, record["id"]): cast(Mapping[str, object], record["document"])
        for record in cast(list[Mapping[str, object]], payload["declarations"])
    }
    expected_ids = [
        cast(str, component["declaration"])
        for component in cast(
            list[Mapping[str, object]],
            cast(Mapping[str, object], payload["unit"])["components"],
        )
        if records[cast(str, component["declaration"])]["kind"] == "rule"
    ]
    if actual_ids != expected_ids:
        _semantic_fail(
            "$.unit.rule-projections",
            "rule projections must cover exactly the effective rules",
        )
    for index, projection in enumerate(projections):
        declaration = cast(str, projection["declaration"])
        document = records.get(declaration)
        if document is None or document.get("kind") != "rule":
            _semantic_fail(
                f"$.unit.rule-projections[{index}].declaration",
                "rule projection must identify an authored rule record",
            )
        authored_norms = {
            cast(str, item["id"])
            for item in cast(list[Mapping[str, object]], document["norms"])
        }
        authored_criteria = {
            cast(str, item["id"]): item
            for item in cast(list[Mapping[str, object]], document["criteria"])
        }
        norms = [
            cast(str, event["norm"])
            for event in trace
            if event["kind"] == "norm-effective" and event["declaration"] == declaration
        ]
        criteria = [
            cast(str, event["criterion"])
            for event in trace
            if event["kind"] == "criterion-effective"
            and event["declaration"] == declaration
        ]
        if projection["norms"] != norms or projection["criteria"] != criteria:
            _semantic_fail(
                f"$.unit.rule-projections[{index}]",
                "projection norms and criteria must equal their effective events",
            )
        if not set(norms).issubset(authored_norms):
            _semantic_fail(
                f"$.unit.rule-projections[{index}].norms",
                "effective norms must exist in the authored rule",
            )
        if not set(criteria).issubset(authored_criteria):
            _semantic_fail(
                f"$.unit.rule-projections[{index}].criteria",
                "effective criteria must exist in the authored rule",
            )
        for criterion in criteria:
            required = set(cast(list[str], authored_criteria[criterion]["norms"]))
            if not required.issubset(set(norms)):
                _semantic_fail(
                    f"$.unit.rule-projections[{index}].criteria",
                    "an effective criterion requires a non-effective norm",
                )


def _validate_consumer_records(
    payload: Mapping[str, object],
    selections: list[Mapping[str, object]],
    source_keys: set[tuple[object, object, object]],
    trace: list[Mapping[str, object]],
) -> None:
    """Bind complete consumer records to the certified unit and source evidence."""
    from .exceptions import DeclarationError
    from .schema import validate_document

    records = cast(list[Mapping[str, object]], payload["declarations"])
    record_ids = [cast(str, record["id"]) for record in records]
    selection_ids = [cast(str, selection["declaration"]) for selection in selections]
    if record_ids != selection_ids:
        _semantic_fail(
            "$.declarations",
            "declaration records must follow the complete candidate sequence",
        )
    selection_by_id = {
        cast(str, selection["declaration"]): selection for selection in selections
    }
    unit = cast(Mapping[str, object], payload["unit"])
    projections = {
        cast(str, projection["declaration"]): projection
        for projection in cast(list[Mapping[str, object]], unit["rule-projections"])
    }
    for index, record in enumerate(records):
        if "version" in record:
            _semantic_fail(
                f"$.declarations[{index}].version",
                "unversioned declarations cannot carry a contract version",
            )
        _validate_record_identity(index, record, source_keys, "declarations")
        document = cast(dict[str, object], record["document"])
        try:
            validate_document(document, path=Path("<query-packet>"))
        except DeclarationError as exc:
            _semantic_fail(f"$.declarations[{index}].document", str(exc))
        identifier = cast(str, record["id"])
        selection = selection_by_id[identifier]
        if record["source-revision"] != selection["source-revision"] or _source_key(
            cast(Mapping[str, object], record["source"])
        ) != _source_key(cast(Mapping[str, object], selection["source"])):
            _semantic_fail(
                f"$.declarations[{index}]",
                "record source and revision must equal its effective selection",
            )
        projection = projections.get(identifier)
        if projection is None:
            if "effective-rule" in record:
                _semantic_fail(
                    f"$.declarations[{index}].effective-rule",
                    "only resolved rules carry an effective projection",
                )
        elif record.get("effective-rule") != {
            "norms": projection["norms"],
            "criteria": projection["criteria"],
        }:
            _semantic_fail(
                f"$.declarations[{index}].effective-rule",
                "effective rule must equal the certified rule projection",
            )

    candidate_ids = set(selection_by_id)
    manifest_id = cast(str, payload["manifest"])
    controls = cast(list[Mapping[str, object]], payload["controls"])
    manifest_control = next(
        (item for item in controls if item["id"] == manifest_id), None
    )
    if manifest_control is None:
        _semantic_fail("$.controls", "manifest control is missing")
    manifest_document = cast(
        Mapping[str, object], cast(Mapping[str, object], manifest_control)["document"]
    )
    expected_control_ids = [manifest_id]
    for event in trace:
        if event["kind"] == "manifest-selected":
            identifier = cast(str, event["declaration"])
            if identifier not in candidate_ids:
                expected_control_ids.append(identifier)
    expected_control_ids.extend(cast(list[str], manifest_document["policies"]))
    expected_control_ids = list(dict.fromkeys(expected_control_ids))
    if [control["id"] for control in controls] != expected_control_ids:
        _semantic_fail(
            "$.controls",
            "controls must contain the manifest, selected rule sets and evaluated policies",
        )
    for index, control in enumerate(controls):
        if "version" in control or "effective-rule" in control:
            _semantic_fail(
                f"$.controls[{index}]",
                "resolution controls cannot carry contract or effective-rule fields",
            )
        _validate_record_identity(index, control, source_keys, "controls")
        try:
            validate_document(
                cast(dict[str, object], control["document"]),
                path=Path("<query-packet>"),
            )
        except DeclarationError as exc:
            _semantic_fail(f"$.controls[{index}].document", str(exc))
    _validate_resolution_controls(payload, trace, controls)

    decisions = cast(list[Mapping[str, object]], payload["decisions"])
    expected_decision_ids = sorted(
        {
            cast(str, identifier)
            for record in records
            if selection_by_id[cast(str, record["id"])]["outcome"] == "effective"
            for identifier in cast(
                list[object],
                cast(Mapping[str, object], record["document"]).get("decided-by", []),
            )
        }
    )
    if [record["id"] for record in decisions] != expected_decision_ids:
        _semantic_fail(
            "$.decisions",
            "decision records must equal the effective rule decision closure",
        )
    for index, decision in enumerate(decisions):
        if (
            decision["kind"] != "decision"
            or "version" in decision
            or "effective-rule" in decision
        ):
            _semantic_fail(
                f"$.decisions[{index}]", "decision closure requires decision records"
            )
        _validate_record_identity(index, decision, source_keys, "decisions")
        try:
            validate_document(
                cast(dict[str, object], decision["document"]),
                path=Path("<query-packet>"),
            )
        except DeclarationError as exc:
            _semantic_fail(f"$.decisions[{index}].document", str(exc))

    contracts = cast(list[Mapping[str, object]], payload["contracts"])
    contract_by_key: dict[tuple[str, int], Mapping[str, object]] = {}
    for index, contract in enumerate(contracts):
        if (
            contract["kind"] not in {"evaluator", "operation"}
            or "effective-rule" in contract
        ):
            _semantic_fail(
                f"$.contracts[{index}]",
                "consumer contracts must be evaluator or operation records",
            )
        _validate_record_identity(index, contract, source_keys, "contracts")
        document = cast(dict[str, object], contract["document"])
        try:
            validate_document(document, path=Path("<query-packet>"))
        except DeclarationError as exc:
            _semantic_fail(f"$.contracts[{index}].document", str(exc))
        key = (cast(str, contract["id"]), cast(int, contract["version"]))
        if key in contract_by_key:
            _semantic_fail("$.contracts", "contract keys must be unique")
        if document.get("version") != key[1]:
            _semantic_fail(
                f"$.contracts[{index}].version",
                "contract version must equal its declaration document",
            )
        contract_by_key[key] = contract

    expected: set[tuple[str, str, int]] = set()
    for record in records:
        if selection_by_id[cast(str, record["id"])]["outcome"] != "effective":
            continue
        effective = cast(Mapping[str, object] | None, record.get("effective-rule"))
        expected.update(
            _document_contract_references(
                cast(Mapping[str, object], record["document"]),
                rule_criteria=(
                    set(cast(list[str], effective["criteria"]))
                    if effective is not None
                    else None
                ),
            )
        )
    pending = list(expected)
    while pending:
        expected_kind, identifier, version = pending.pop()
        key = (identifier, version)
        required_contract = contract_by_key.get(key)
        if required_contract is None:
            _semantic_fail("$.contracts", f"required contract {key!r} is missing")
        if required_contract["kind"] != expected_kind:
            _semantic_fail(
                "$.contracts",
                f"required {expected_kind} contract {key!r} has the wrong kind",
            )
        for reference in _document_contract_references(
            cast(Mapping[str, object], required_contract["document"])
        ):
            if reference not in expected:
                expected.add(reference)
                pending.append(reference)
    actual_contracts = {
        (cast(str, record["kind"]), identifier, version)
        for (identifier, version), record in contract_by_key.items()
    }
    if actual_contracts != expected:
        _semantic_fail("$.contracts", "contracts must equal the consumer closure")
    _validate_procedure_contracts(records, selection_by_id, contract_by_key)

    resource_ids = {
        cast(str, resource["id"])
        for resource in cast(list[Mapping[str, object]], payload["resources"])
    }
    required_resources = {
        cast(str, resource["resource"])
        for contract in contracts
        for resource in cast(
            list[Mapping[str, object]],
            cast(Mapping[str, object], contract["document"]).get(
                "support-resources", []
            ),
        )
    }
    if not required_resources.issubset(resource_ids):
        _semantic_fail("$.resources", "operation support resources are incomplete")


def _validate_procedure_contracts(
    records: list[Mapping[str, object]],
    selections: Mapping[str, Mapping[str, object]],
    contracts: Mapping[tuple[str, int], Mapping[str, object]],
) -> None:
    """Reapply procedure-to-operation compatibility to packet documents."""
    from .embedded_schema import normalize_json_subschema, validate_json_subschema
    from .registry import _property_schemas, _required_properties

    for record in records:
        identifier = cast(str, record["id"])
        document = cast(Mapping[str, object], record["document"])
        if (
            selections[identifier]["outcome"] != "effective"
            or document["kind"] != "procedure"
        ):
            continue
        parameter_schema = cast(Mapping[str, object], document["parameters"])
        parameter_schemas = _property_schemas(parameter_schema)
        authorized_effects = set(cast(list[str], document["effects"]))
        invariants = cast(list[Mapping[str, object]], document["invariants"])
        for action_index, action in enumerate(
            cast(list[Mapping[str, object]], document["actions"])
        ):
            reference = cast(Mapping[str, object], action["operation"])
            key = (cast(str, reference["id"]), cast(int, reference["version"]))
            operation_record = contracts.get(key)
            if operation_record is None or operation_record["kind"] != "operation":
                _semantic_fail(
                    f"$.declarations[{identifier}].actions[{action_index}].operation",
                    "procedure action requires an operation contract",
                )
            operation = cast(Mapping[str, object], operation_record["document"])
            input_schema = cast(Mapping[str, object], operation["inputs"])
            input_schemas = _property_schemas(input_schema)
            bindings = cast(Mapping[str, Mapping[str, object]], action.get("with", {}))
            missing = set(_required_properties(input_schema)) - set(bindings)
            if missing:
                _semantic_fail(
                    f"$.declarations[{identifier}].actions[{action_index}].with",
                    "procedure action omits required operation inputs",
                )
            for input_name, binding in bindings.items():
                if input_name not in input_schemas:
                    _semantic_fail(
                        f"$.declarations[{identifier}].actions[{action_index}].with",
                        "procedure action binds an unknown operation input",
                    )
                if "parameter" in binding:
                    parameter = cast(str, binding["parameter"])
                    if parameter not in parameter_schemas or not json_values_equal(
                        normalize_json_subschema(
                            parameter_schema, ("properties", parameter)
                        ),
                        normalize_json_subschema(
                            input_schema, ("properties", input_name)
                        ),
                    ):
                        _semantic_fail(
                            f"$.declarations[{identifier}].actions[{action_index}].with",
                            "procedure parameter and operation input schemas differ",
                        )
                else:
                    error = validate_json_subschema(
                        input_schema,
                        ("properties", input_name),
                        binding["literal"],
                    )
                    if error is not None:
                        _semantic_fail(
                            f"$.declarations[{identifier}].actions[{action_index}].with",
                            "literal binding violates the operation input schema",
                        )
            operation_failures = set(cast(list[str], operation["failure-outcomes"]))
            action_failures = set(cast(Mapping[str, object], action["on-failure"]))
            if operation_failures != action_failures:
                _semantic_fail(
                    f"$.declarations[{identifier}].actions[{action_index}].on-failure",
                    "procedure action outcomes differ from the operation failures",
                )
            operation_effects = set(cast(list[str], operation["effects"]))
            if not operation_effects.issubset(authorized_effects):
                _semantic_fail(
                    f"$.declarations[{identifier}].actions[{action_index}].operation",
                    "operation effects exceed the procedure mutation footprint",
                )
            if any(
                observed in operation_effects
                for invariant in invariants
                for observed in cast(list[str], invariant.get("observes", []))
            ):
                _semantic_fail(
                    f"$.declarations[{identifier}].invariants",
                    "operation may mutate state observed by a procedure invariant",
                )


def _validate_record_identity(
    index: int,
    record: Mapping[str, object],
    source_keys: set[tuple[object, object, object]],
    group: str,
) -> None:
    document = cast(Mapping[str, object], record["document"])
    if (
        record["id"] != document.get("id")
        or record["kind"] != document.get("kind")
        or record["source-revision"] != document.get("source-revision")
    ):
        _semantic_fail(
            f"$.{group}[{index}]",
            "record identity must equal its declaration document",
        )
    digest_material = {
        "document": document,
        "effective-rule": record.get("effective-rule"),
        "version": record.get("version"),
    }
    expected_digest = "sha256:" + hashlib.sha256(jcs_bytes(digest_material)).hexdigest()
    if record["record-digest"] != expected_digest:
        _semantic_fail(
            f"$.{group}[{index}].record-digest",
            "record digest differs from its normalized content",
        )
    if _source_key(cast(Mapping[str, object], record["source"])) not in source_keys:
        _semantic_fail(
            f"$.{group}[{index}].source",
            "record source is absent from the acquired sources",
        )


def _validate_resolution_controls(
    payload: Mapping[str, object],
    trace: list[Mapping[str, object]],
    controls: list[Mapping[str, object]],
) -> None:
    """Bind manifest, rule-set and policy records to their trace effects."""
    by_id = {cast(str, item["id"]): item for item in controls}
    candidate_by_id = {
        cast(str, item["id"]): item
        for item in cast(list[Mapping[str, object]], payload["declarations"])
    }
    manifest_id = cast(str, payload["manifest"])
    manifest = cast(Mapping[str, object], by_id[manifest_id]["document"])
    selected_events = [event for event in trace if event["kind"] == "manifest-selected"]
    selected_ids = [cast(str, event["declaration"]) for event in selected_events]
    authored_ids = [
        cast(str, identifier)
        for section in cast(list[Mapping[str, object]], manifest["sections"])
        for identifier in cast(list[object], section["declarations"])
    ]
    if selected_ids != authored_ids:
        _semantic_fail(
            "$.controls",
            "manifest selections must equal the authored section declarations",
        )
    evaluated_policy_ids = {
        cast(str, event["declaration"])
        for event in trace
        if event["kind"] == "policy-evaluated"
    }
    if not evaluated_policy_ids.issubset(set(cast(list[str], manifest["policies"]))):
        _semantic_fail(
            "$.controls",
            "evaluated policies must be selected by the manifest",
        )

    for selected in selected_events:
        identifier = cast(str, selected["declaration"])
        control = by_id.get(identifier)
        if control is None:
            continue
        document = cast(Mapping[str, object], control["document"])
        if document.get("kind") != "rule-set":
            continue
        member_events = [
            event
            for event in trace
            if event["kind"] in {"rule-set-member-expanded", "rule-set-member-inactive"}
            and event["causes"] == [selected["ordinal"]]
        ]
        authored_rules = cast(list[Mapping[str, object]], document["rules"])
        expected = [
            (
                cast(str, rule["id"]),
                (
                    "rule-set-member-expanded"
                    if rule["status"] == "active"
                    else "rule-set-member-inactive"
                ),
            )
            for rule in authored_rules
        ]
        actual = [
            (cast(str, event["declaration"]), cast(str, event["kind"]))
            for event in member_events
        ]
        if actual != expected:
            _semantic_fail(
                "$.controls",
                f"rule-set {identifier!r} members must equal its trace expansion",
            )
        control_source = cast(Mapping[str, object], control["source"])
        control_root = cast(list[object], control_source["document-path"])
        for rule_index, rule in enumerate(authored_rules):
            candidate = candidate_by_id.get(cast(str, rule["id"]))
            if candidate is None or not json_values_equal(candidate["document"], rule):
                _semantic_fail(
                    "$.controls",
                    f"rule-set {identifier!r} member differs from its candidate record",
                )
            candidate_source = cast(Mapping[str, object], candidate["source"])
            if _source_key(candidate_source) != _source_key(
                control_source
            ) or candidate_source["document-path"] != [
                *control_root,
                "rules",
                rule_index,
            ]:
                _semantic_fail(
                    "$.controls",
                    f"rule-set {identifier!r} member provenance differs from its candidate",
                )

    for event in trace:
        if event["kind"] != "policy-evaluated":
            continue
        policy_id = cast(str, event["declaration"])
        policy = cast(Mapping[str, object], by_id[policy_id]["document"])
        conflict = sorted(cast(list[str], policy["conflicts"]))
        if event["conflict"] != conflict:
            _semantic_fail(
                f"$.trace[{event['ordinal']}].conflict",
                "evaluated conflict must equal the policy conflict",
            )
        caused_results = [
            candidate
            for candidate in trace
            if candidate["kind"] == "policy-result-discovered"
            and candidate["causes"] == [event["ordinal"]]
        ]
        caused_resolutions = [
            candidate
            for candidate in trace
            if candidate["kind"] == "conflict-resolved"
            and candidate["causes"] == [event["ordinal"]]
        ]
        if event["truth"] != "true":
            if caused_results or caused_resolutions:
                _semantic_fail(
                    f"$.trace[{event['ordinal']}]",
                    "a non-matching policy cannot resolve a conflict",
                )
            continue
        strategy = cast(Mapping[str, object], policy["strategy"])
        kind = cast(str, strategy["kind"])
        if kind == "error" or len(caused_resolutions) != 1:
            _semantic_fail(
                f"$.trace[{event['ordinal']}]",
                "a matching policy must produce exactly one admitted resolution",
            )
        resolution = caused_resolutions[0]
        excluded = sorted(
            cast(str, candidate["declaration"])
            for candidate in trace
            if candidate["kind"] == "declaration-excluded"
            and candidate["causes"] == [resolution["ordinal"]]
        )
        aliases = sorted(
            (
                cast(str, candidate["declaration"]),
                cast(str, candidate["replacement"]),
            )
            for candidate in trace
            if candidate["kind"] == "alias-created"
            and candidate["causes"] == [resolution["ordinal"]]
        )
        expected_results: list[str] = []
        expected_aliases: list[tuple[str, str]] = []
        if kind == "retain":
            retained = cast(str, strategy["retain"])
            expected_excluded = sorted(item for item in conflict if item != retained)
        elif kind == "substitute":
            replaced = cast(str, strategy["replace"])
            replacement = cast(str, strategy["with"])
            expected_excluded = [replaced]
            expected_results = [replacement]
            expected_aliases = [(replaced, replacement)]
        else:
            result = cast(str, strategy["result"])
            expected_excluded = conflict
            expected_results = [result]
            expected_aliases = sorted((item, result) for item in conflict)
        actual_results = [cast(str, item["declaration"]) for item in caused_results]
        if (
            excluded != expected_excluded
            or actual_results != expected_results
            or aliases != expected_aliases
        ):
            _semantic_fail(
                f"$.trace[{event['ordinal']}]",
                "policy effects must equal its authored strategy",
            )


def _document_contract_references(
    document: Mapping[str, object],
    *,
    rule_criteria: set[str] | None = None,
) -> set[tuple[str, str, int]]:
    kind = document.get("kind")
    references: set[tuple[str, str, int]] = set()
    if kind == "rule":
        predicates = cast(list[Mapping[str, object]], document.get("criteria", []))
        references.update(
            _reference_key("evaluator", cast(Mapping[str, object], item["evaluator"]))
            for item in predicates
            if rule_criteria is None or item["id"] in rule_criteria
        )
    elif kind == "procedure":
        for field in ("preconditions", "invariants", "postconditions"):
            for predicate in cast(list[Mapping[str, object]], document.get(field, [])):
                evaluator = predicate.get("evaluator")
                if isinstance(evaluator, Mapping):
                    references.add(_reference_key("evaluator", evaluator))
        references.update(
            _reference_key("operation", cast(Mapping[str, object], action["operation"]))
            for action in cast(list[Mapping[str, object]], document.get("actions", []))
        )
    elif kind == "operation":
        for predicate in cast(
            list[Mapping[str, object]], document.get("preconditions", [])
        ):
            evaluator = predicate.get("evaluator")
            if isinstance(evaluator, Mapping):
                references.add(_reference_key("evaluator", evaluator))
    return references


def _reference_key(kind: str, reference: Mapping[str, object]) -> tuple[str, str, int]:
    return kind, cast(str, reference["id"]), cast(int, reference["version"])


def _packet_records(payload: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    return {
        cast(str, record["id"]): record
        for group in ("declarations", "controls", "contracts", "decisions")
        for record in cast(list[Mapping[str, object]], payload[group])
    }


def _validate_source_record_bindings(payload: Mapping[str, object]) -> None:
    """Locate every emitted record identity in its acquisition-derived index."""
    sources = {
        _source_key(source): source
        for source in cast(list[Mapping[str, object]], payload["sources"])
    }
    for group in ("declarations", "controls", "contracts", "decisions"):
        for index, record in enumerate(
            cast(list[Mapping[str, object]], payload[group])
        ):
            record_source = cast(Mapping[str, object], record["source"])
            source = sources.get(_source_key(record_source))
            candidates = (
                []
                if source is None
                else [
                    item
                    for item in cast(list[Mapping[str, object]], source["records"])
                    if item["document-path"] == record_source["document-path"]
                ]
            )
            if len(candidates) != 1:
                _semantic_fail(
                    f"$.{group}[{index}].source",
                    "record document path does not locate an acquired declaration",
                )
            located = candidates[0]
            fields = ("id", "kind", "source-revision")
            if any(
                located.get(field) != record[field] for field in fields
            ) or located.get("version") != record.get("version"):
                _semantic_fail(
                    f"$.{group}[{index}].source",
                    "record identity differs from its acquired declaration location",
                )
            expected_content_digest = (
                "sha256:" + hashlib.sha256(jcs_bytes(record["document"])).hexdigest()
            )
            if located["content-digest"] != expected_content_digest:
                _semantic_fail(
                    f"$.{group}[{index}].document",
                    "record content differs from its acquisition-derived binding",
                )
            namespace = cast(str, record_source["namespace"])
            document = cast(Mapping[str, object], record["document"])
            if document["owner"] != namespace or not cast(
                str, document["id"]
            ).startswith(namespace + "/"):
                _semantic_fail(
                    f"$.{group}[{index}].document.owner",
                    "record owner and identifier must match its source namespace",
                )


def _validate_lifecycle_authority(payload: Mapping[str, object]) -> None:
    """Require the statuses and ownership under which resolution can succeed."""
    selections = {
        cast(str, item["declaration"]): cast(str, item["outcome"])
        for item in cast(list[Mapping[str, object]], payload["selections"])
    }
    for index, record in enumerate(
        cast(list[Mapping[str, object]], payload["declarations"])
    ):
        document = cast(Mapping[str, object], record["document"])
        inactive = selections[cast(str, record["id"])] == "inactive"
        if (document["status"] == "active") is inactive:
            _semantic_fail(
                f"$.declarations[{index}].document.status",
                "candidate status contradicts its resolved lifecycle outcome",
            )
    controls = cast(list[Mapping[str, object]], payload["controls"])
    manifest_id = cast(str, payload["manifest"])
    manifest = next(record for record in controls if record["id"] == manifest_id)
    manifest_document = cast(Mapping[str, object], manifest["document"])
    if manifest_document["status"] != "active":
        _semantic_fail(
            "$.controls[0].document.status", "resolved manifest must be active"
        )
    manifest_owner = manifest_document["owner"]
    policy_ids = set(cast(list[str], manifest_document["policies"]))
    for index, control in enumerate(controls[1:], start=1):
        document = cast(Mapping[str, object], control["document"])
        if document["status"] != "active":
            _semantic_fail(
                f"$.controls[{index}].document.status",
                "selected rule sets and manifest policies must be active",
            )
        if control["id"] in policy_ids and document["owner"] != manifest_owner:
            _semantic_fail(
                f"$.controls[{index}].document.owner",
                "manifest policy owner must equal the manifest owner",
            )
    for index, contract in enumerate(
        cast(list[Mapping[str, object]], payload["contracts"])
    ):
        document = cast(Mapping[str, object], contract["document"])
        if document["status"] != "active":
            _semantic_fail(
                f"$.contracts[{index}].document.status",
                "consumer contracts must be active",
            )
    for index, decision in enumerate(
        cast(list[Mapping[str, object]], payload["decisions"])
    ):
        document = cast(Mapping[str, object], decision["document"])
        if document["status"] != "active":
            _semantic_fail(
                f"$.decisions[{index}].document.status",
                "decision dependencies must be active",
            )


def _relation_index(
    document: Mapping[str, object], relation_types: set[str], target: str
) -> int | None:
    for index, relation in enumerate(
        cast(list[Mapping[str, object]], document["relations"])
    ):
        if relation["type"] in relation_types and relation["target"] == target:
            return index
    return None


def _conflict_relation(
    records: Mapping[str, Mapping[str, object]], conflict: list[str]
) -> tuple[Mapping[str, object], int] | None:
    for identifier in conflict:
        record = records.get(identifier)
        if record is None:
            continue
        document = cast(Mapping[str, object], record["document"])
        index = _relation_index(
            document,
            {"incompatible-with"},
            next(item for item in conflict if item != identifier),
        )
        if index is not None:
            return record, index
    return None


def _validate_authored_relations(
    payload: Mapping[str, object], trace: list[Mapping[str, object]]
) -> None:
    """Require resolver relations to exist in the emitted declaration records."""
    records = _packet_records(payload)
    actual_dependencies: list[tuple[str, str, str]] = []
    for index, event in enumerate(trace):
        if event["kind"] == "dependency-discovered":
            actual_dependencies.append(
                (
                    cast(str, event["declaration"]),
                    cast(str, event["dependant"]),
                    cast(str, event["relation"]),
                )
            )
            dependant = records.get(cast(str, event["dependant"]))
            relation_index = (
                None
                if dependant is None
                else _relation_index(
                    cast(Mapping[str, object], dependant["document"]),
                    {"requires", "refines"},
                    cast(str, event["declaration"]),
                )
            )
            if relation_index is None or event["relation"] not in {
                "requires",
                "refines",
            }:
                _semantic_fail(
                    f"$.trace[{index}]",
                    "dependency event lacks its authored relation",
                )
            relation = cast(
                Mapping[str, object],
                cast(
                    list[object],
                    cast(
                        Mapping[str, object],
                        cast(Mapping[str, object], dependant)["document"],
                    )["relations"],
                )[relation_index],
            )
            if relation["type"] != event["relation"]:
                _semantic_fail(
                    f"$.trace[{index}].relation",
                    "dependency relation type differs from its authored relation",
                )
        elif event["kind"] == "conflict-detected":
            conflict = cast(list[str], event["conflict"])
            if _conflict_relation(records, conflict) is None:
                _semantic_fail(
                    f"$.trace[{index}].conflict",
                    "detected conflict lacks its authored incompatible relation",
                )
    resolved_candidates = {
        cast(str, selection["declaration"])
        for selection in cast(list[Mapping[str, object]], payload["selections"])
        if selection["outcome"] in {"effective", "excluded"}
    }
    expected_dependencies = [
        (
            cast(str, relation["target"]),
            identifier,
            cast(str, relation["type"]),
        )
        for identifier in sorted(resolved_candidates)
        for relation in cast(
            list[Mapping[str, object]],
            cast(Mapping[str, object], records[identifier]["document"])["relations"],
        )
        if relation["type"] in {"requires", "refines"}
    ]
    if sorted(actual_dependencies) != sorted(expected_dependencies):
        _semantic_fail(
            "$.trace",
            "dependency events must cover every authored relation of resolved candidates",
        )


def _event_source_matches(
    event: Mapping[str, object],
    record: Mapping[str, object],
    suffix: tuple[object, ...],
) -> bool:
    event_source = cast(Mapping[str, object], event["source"])
    record_source = cast(Mapping[str, object], record["source"])
    return _source_key(event_source) == _source_key(record_source) and event_source[
        "document-path"
    ] == [*cast(list[object], record_source["document-path"]), *suffix]


def _member_index(
    document: Mapping[str, object], group: str, identifier: object
) -> int | None:
    for index, item in enumerate(cast(list[Mapping[str, object]], document[group])):
        if item["id"] == identifier:
            return index
    return None


def _validate_event_provenance(
    payload: Mapping[str, object], trace: list[Mapping[str, object]]
) -> None:
    """Bind each resolver event to the record and document path that owns it."""
    records = _packet_records(payload)
    manifest_id = cast(str, payload["manifest"])
    manifest_record = records[manifest_id]
    manifest = cast(Mapping[str, object], manifest_record["document"])
    selection_paths = [
        ("sections", section_index, "declarations", declaration_index)
        for section_index, section in enumerate(
            cast(list[Mapping[str, object]], manifest["sections"])
        )
        for declaration_index, _identifier in enumerate(
            cast(list[object], section["declarations"])
        )
    ]
    selection_index = 0
    for index, event in enumerate(trace):
        kind = cast(str, event["kind"])
        declaration = cast(str, event["declaration"])
        record: Mapping[str, object]
        suffix: tuple[object, ...]
        if kind == "manifest-evaluated":
            record, suffix = manifest_record, ("applicability",)
        elif kind == "manifest-selected":
            record, suffix = manifest_record, selection_paths[selection_index]
            selection_index += 1
        elif kind in {"rule-set-member-expanded", "rule-set-member-inactive"}:
            record = records[declaration]
            suffix = () if kind == "rule-set-member-expanded" else ("status",)
        elif kind == "dependency-discovered":
            record = records[cast(str, event["dependant"])]
            relation_index = _relation_index(
                cast(Mapping[str, object], record["document"]),
                {cast(str, event["relation"])},
                declaration,
            )
            if relation_index is None:
                _semantic_fail(f"$.trace[{index}]", "dependency provenance is absent")
            suffix = ("relations", relation_index, "target")
        elif kind == "conflict-detected":
            relation = _conflict_relation(records, cast(list[str], event["conflict"]))
            if relation is None:
                _semantic_fail(f"$.trace[{index}]", "conflict provenance is absent")
            record, relation_index = relation
            suffix = ("relations", relation_index, "target")
        elif kind in {
            "policy-result-discovered",
            "policy-evaluated",
            "conflict-resolved",
            "declaration-excluded",
            "alias-created",
        }:
            policy_id = (
                declaration
                if kind == "policy-evaluated"
                else cast(str, event["policy"])
            )
            record = records[policy_id]
            policy = cast(Mapping[str, object], record["document"])
            strategy = cast(Mapping[str, object], policy["strategy"])
            strategy_kind = cast(str, strategy["kind"])
            if kind == "policy-evaluated":
                suffix = ()
            elif kind == "conflict-resolved":
                suffix = ("strategy", "kind")
            elif kind == "declaration-excluded":
                field = (
                    "retain"
                    if strategy_kind == "retain"
                    else "replace" if strategy_kind == "substitute" else "kind"
                )
                suffix = ("strategy", field)
            else:
                field = "with" if strategy_kind == "substitute" else "result"
                suffix = ("strategy", field)
        elif kind in {"declaration-evaluated", "declaration-effective"}:
            record = records[declaration]
            suffix = ("applicability",) if kind == "declaration-evaluated" else ()
        elif kind in {
            "norm-evaluated",
            "exception-evaluated",
            "norm-removed",
            "norm-substituted",
            "norm-effective",
            "criterion-effective",
            "criterion-inactive",
        }:
            record = records[declaration]
            document = cast(Mapping[str, object], record["document"])
            if kind in {"norm-evaluated", "norm-effective"}:
                member_index = _member_index(document, "norms", event["norm"])
                suffix = ("norms", member_index)
            elif kind == "exception-evaluated":
                member_index = _member_index(document, "exceptions", event["exception"])
                suffix = ("exceptions", member_index, "when")
            elif kind in {"criterion-effective", "criterion-inactive"}:
                member_index = _member_index(document, "criteria", event["criterion"])
                suffix = ("criteria", member_index)
            else:
                exception_index = _member_index(
                    document, "exceptions", event["exception"]
                )
                exception = cast(
                    Mapping[str, object],
                    cast(list[object], document["exceptions"])[
                        cast(int, exception_index)
                    ],
                )
                field = "affects" if kind == "norm-removed" else "substitutes"
                norm_index = cast(list[object], exception[field]).index(event["norm"])
                suffix = ("exceptions", exception_index, field, norm_index)
            if None in suffix:
                _semantic_fail(f"$.trace[{index}]", "rule provenance is absent")
        else:
            record, suffix = manifest_record, ()
        if not _event_source_matches(event, record, suffix):
            _semantic_fail(
                f"$.trace[{index}].source",
                "event source differs from its authored record and document path",
            )


def _anchor_value(event: Mapping[str, object]) -> tuple[str, int]:
    anchor = cast(Mapping[str, object], event["anchor"])
    return cast(str, anchor["section"]), cast(int, anchor["rank"])


def _current_anchor(
    identifier: str,
    direct: Mapping[str, tuple[str, int]],
    discoveries: Mapping[str, list[tuple[str, int]]],
) -> tuple[str, int] | None:
    if identifier in direct:
        return direct[identifier]
    candidates = discoveries.get(identifier, [])
    return min(candidates, key=lambda item: item[1]) if candidates else None


def _validate_anchors(
    payload: Mapping[str, object], trace: list[Mapping[str, object]]
) -> None:
    """Reconstruct every anchor from manifest order and discovery semantics."""
    records = _packet_records(payload)
    manifest = cast(
        Mapping[str, object], records[cast(str, payload["manifest"])]["document"]
    )
    expected_selections: list[tuple[str, tuple[str, int], bool]] = []
    rank = 0
    for section in cast(list[Mapping[str, object]], manifest["sections"]):
        section_id = cast(str, section["id"])
        for identifier_value in cast(list[object], section["declarations"]):
            identifier = cast(str, identifier_value)
            control = records.get(identifier)
            is_rule_set = (
                control is not None
                and cast(Mapping[str, object], control["document"]).get("kind")
                == "rule-set"
            )
            expected_selections.append((identifier, (section_id, rank), is_rule_set))
            if is_rule_set:
                admitted_control = cast(Mapping[str, object], control)
                rules = cast(
                    list[Mapping[str, object]],
                    cast(Mapping[str, object], admitted_control["document"])["rules"],
                )
                rank += len(rules)
            else:
                rank += 1

    selected_events = [event for event in trace if event["kind"] == "manifest-selected"]
    if len(selected_events) != len(expected_selections):
        _semantic_fail("$.trace", "manifest anchor reconstruction is incomplete")
    direct: dict[str, tuple[str, int]] = {}
    discoveries: dict[str, list[tuple[str, int]]] = {}
    member_expectations: dict[int, list[tuple[str, tuple[str, int], str]]] = {}
    for event, (identifier, anchor, is_rule_set) in zip(
        selected_events, expected_selections, strict=True
    ):
        if event["declaration"] != identifier or _anchor_value(event) != anchor:
            _semantic_fail(
                f"$.trace[{event['ordinal']}].anchor",
                "manifest selection anchor differs from authored section order",
            )
        if is_rule_set:
            control = records[identifier]
            rules = cast(
                list[Mapping[str, object]],
                cast(Mapping[str, object], control["document"])["rules"],
            )
            member_expectations[cast(int, event["ordinal"])] = [
                (
                    cast(str, rule["id"]),
                    (anchor[0], anchor[1] + offset),
                    (
                        "rule-set-member-expanded"
                        if rule["status"] == "active"
                        else "rule-set-member-inactive"
                    ),
                )
                for offset, rule in enumerate(rules)
            ]
        else:
            direct[identifier] = anchor

    member_offsets = {ordinal: 0 for ordinal in member_expectations}
    for index, event in enumerate(trace):
        kind = cast(str, event["kind"])
        declaration = cast(str, event["declaration"])
        if kind == "manifest-selected":
            if declaration in direct:
                discoveries.setdefault(declaration, []).append(_anchor_value(event))
            continue
        if kind in {"rule-set-member-expanded", "rule-set-member-inactive"}:
            selection_ordinal = cast(list[int], event["causes"])[0]
            offset = member_offsets[selection_ordinal]
            expected = member_expectations[selection_ordinal][offset]
            member_offsets[selection_ordinal] += 1
            if (declaration, _anchor_value(event), kind) != expected:
                _semantic_fail(
                    f"$.trace[{index}].anchor",
                    "rule-set member anchor differs from authored expansion order",
                )
            if kind == "rule-set-member-expanded":
                discoveries.setdefault(declaration, []).append(_anchor_value(event))
            continue
        if kind == "dependency-discovered":
            expected_anchor = _current_anchor(
                cast(str, event["dependant"]), direct, discoveries
            )
            if expected_anchor is None or _anchor_value(event) != expected_anchor:
                _semantic_fail(
                    f"$.trace[{index}].anchor",
                    "dependency anchor differs from its dependant anchor",
                )
            discoveries.setdefault(declaration, []).append(_anchor_value(event))
        elif kind == "policy-result-discovered":
            policy = cast(
                Mapping[str, object], records[cast(str, event["policy"])]["document"]
            )
            strategy = cast(Mapping[str, object], policy["strategy"])
            if strategy["kind"] == "substitute":
                source_ids = [cast(str, strategy["replace"])]
            else:
                source_ids = cast(list[str], event["conflict"])
            source_anchors = [
                _current_anchor(identifier, direct, discoveries)
                for identifier in source_ids
            ]
            if any(anchor is None for anchor in source_anchors):
                _semantic_fail(f"$.trace[{index}].anchor", "policy anchor is absent")
            expected_anchor = min(
                cast(list[tuple[str, int]], source_anchors), key=lambda item: item[1]
            )
            if _anchor_value(event) != expected_anchor:
                _semantic_fail(
                    f"$.trace[{index}].anchor",
                    "policy result anchor differs from its strategy source",
                )
            discoveries.setdefault(declaration, []).append(_anchor_value(event))
        elif kind in {"declaration-evaluated", "declaration-effective"}:
            expected_anchor = _current_anchor(declaration, direct, discoveries)
            if expected_anchor is None or _anchor_value(event) != expected_anchor:
                _semantic_fail(
                    f"$.trace[{index}].anchor",
                    "declaration anchor differs from its manifest-derived discovery",
                )


def _validate_authored_applicability(
    payload: Mapping[str, object],
    trace: list[Mapping[str, object]],
) -> None:
    records = {
        cast(str, record["id"]): record
        for group in ("declarations", "controls")
        for record in cast(list[Mapping[str, object]], payload[group])
    }
    for index, event in enumerate(trace):
        if "applicability" not in event:
            continue
        record = records.get(cast(str, event["declaration"]))
        if record is None:
            _semantic_fail(
                f"$.trace[{index}]",
                "applicability event lacks its authored declaration record",
            )
        document = cast(Mapping[str, object], record["document"])
        kind = cast(str, event["kind"])
        if kind in {"manifest-evaluated", "declaration-evaluated"}:
            expected = document["applicability"]
        elif kind == "policy-evaluated":
            expected = {
                "all": [document["applicability"], document["when"]],
            }
        elif kind == "norm-evaluated":
            norm = _record_member(document, "norms", event["norm"], index)
            expected = norm["applies-when"]
        elif kind == "exception-evaluated":
            exception = _record_member(
                document, "exceptions", event["exception"], index
            )
            expected = exception["when"]
        else:
            _semantic_fail(
                f"$.trace[{index}]",
                f"unexpected applicability event kind {kind!r}",
            )
        actual = _trace_predicate(cast(Mapping[str, object], event["applicability"]))
        if not json_values_equal(actual, expected):
            _semantic_fail(
                f"$.trace[{index}].applicability",
                "evaluated predicate differs from the normalized authored predicate",
            )


def _predicate_truth(
    predicate: Mapping[str, object], context: Mapping[str, object]
) -> str:
    if "all" in predicate:
        values = [
            _predicate_truth(child, context)
            for child in cast(list[Mapping[str, object]], predicate["all"])
        ]
        return (
            "false"
            if "false" in values
            else "true" if all(value == "true" for value in values) else "unknown"
        )
    if "any" in predicate:
        values = [
            _predicate_truth(child, context)
            for child in cast(list[Mapping[str, object]], predicate["any"])
        ]
        return (
            "true"
            if "true" in values
            else "false" if all(value == "false" for value in values) else "unknown"
        )
    if "not" in predicate:
        value = _predicate_truth(cast(Mapping[str, object], predicate["not"]), context)
        return (
            "unknown" if value == "unknown" else "false" if value == "true" else "true"
        )
    facet = cast(str, predicate["facet"])
    operator = cast(str, predicate["operator"])
    if operator == "exists":
        return "true" if facet in context else "false"
    if facet not in context:
        return "unknown"
    if operator == "equals":
        return (
            "true"
            if json_values_equal(context[facet], predicate.get("value"))
            else "false"
        )
    return (
        "true"
        if any(
            json_values_equal(context[facet], candidate)
            for candidate in cast(list[object], predicate["value"])
        )
        else "false"
    )


def _authored_conflicts(
    active: set[str], records: Mapping[str, Mapping[str, object]]
) -> list[list[str]]:
    pairs: set[tuple[str, str]] = set()
    for identifier in active:
        record = records.get(identifier)
        if record is None:
            continue
        document = cast(Mapping[str, object], record["document"])
        for relation in cast(list[Mapping[str, object]], document["relations"]):
            target = cast(str, relation["target"])
            if relation["type"] == "incompatible-with" and target in active:
                pair = (
                    (identifier, target)
                    if identifier < target
                    else (target, identifier)
                )
                pairs.add(pair)
    return [list(pair) for pair in sorted(pairs)]


def _validate_complete_conflicts(
    payload: Mapping[str, object], trace: list[Mapping[str, object]]
) -> None:
    """Reconstruct conflict batches and each policy's exact evaluation prefix."""
    records = _packet_records(payload)
    context = cast(Mapping[str, object], payload["context"])
    manifest = cast(
        Mapping[str, object], records[cast(str, payload["manifest"])]["document"]
    )
    policy_records = [
        records[identifier] for identifier in cast(list[str], manifest["policies"])
    ]
    active: set[str] = set()
    for index, event in enumerate(trace):
        kind = cast(str, event["kind"])
        if kind == "declaration-evaluated" and event["truth"] == "true":
            active.add(cast(str, event["declaration"]))
            continue
        if kind == "declaration-excluded":
            active.discard(cast(str, event["declaration"]))
            continue
        if kind != "conflict-detected":
            continue
        if index == 0 or trace[index - 1]["kind"] not in {
            "conflict-detected",
            "policy-evaluated",
        }:
            batch: list[list[str]] = []
            cursor = index
            while cursor < len(trace) and trace[cursor]["kind"] in {
                "conflict-detected",
                "policy-evaluated",
            }:
                if trace[cursor]["kind"] == "conflict-detected":
                    batch.append(cast(list[str], trace[cursor]["conflict"]))
                cursor += 1
            if batch != _authored_conflicts(active, records):
                _semantic_fail(
                    f"$.trace[{index}]",
                    "conflict batch must cover every authored conflict among active declarations",
                )
        conflict = cast(list[str], event["conflict"])
        matching = sorted(
            (
                record
                for record in policy_records
                if sorted(
                    cast(
                        list[str],
                        cast(Mapping[str, object], record["document"])["conflicts"],
                    )
                )
                == conflict
            ),
            key=lambda record: (
                cast(Mapping[str, object], record["document"])["order"],
                record["id"],
            ),
        )
        expected_policy_ids: list[str] = []
        for record in matching:
            document = cast(Mapping[str, object], record["document"])
            expected_policy_ids.append(cast(str, record["id"]))
            predicate = {
                "all": [document["applicability"], document["when"]],
            }
            if _predicate_truth(predicate, context) == "true":
                break
        else:
            _semantic_fail(
                f"$.trace[{index}]",
                "detected conflict lacks an applicable manifest policy",
            )
        actual_policy_ids = [
            cast(str, candidate["declaration"])
            for candidate in trace
            if candidate["kind"] == "policy-evaluated"
            and candidate["causes"] == [event["ordinal"]]
        ]
        if actual_policy_ids != expected_policy_ids:
            _semantic_fail(
                f"$.trace[{index}]",
                "policy evaluations must equal the ordered prefix through the first match",
            )
    remaining = _authored_conflicts(active, records)
    if remaining:
        _semantic_fail(
            "$.trace",
            "completed resolution retains an authored conflict without a resolution batch",
        )


def _validate_complete_rule_semantics(
    payload: Mapping[str, object], trace: list[Mapping[str, object]]
) -> None:
    """Recompute each effective rule from every authored norm and exception."""
    records = _packet_records(payload)
    projections = cast(
        list[Mapping[str, object]],
        cast(Mapping[str, object], payload["unit"])["rule-projections"],
    )
    for projection_index, projection in enumerate(projections):
        identifier = cast(str, projection["declaration"])
        document = cast(Mapping[str, object], records[identifier]["document"])
        norms = cast(list[Mapping[str, object]], document["norms"])
        exceptions = cast(list[Mapping[str, object]], document.get("exceptions", []))
        norm_events = [
            event
            for event in trace
            if event["kind"] == "norm-evaluated" and event["declaration"] == identifier
        ]
        exception_events = [
            event
            for event in trace
            if event["kind"] == "exception-evaluated"
            and event["declaration"] == identifier
        ]
        if [event["norm"] for event in norm_events] != [norm["id"] for norm in norms]:
            _semantic_fail(
                f"$.unit.rule-projections[{projection_index}]",
                "norm evaluations must cover every authored norm in order",
            )
        if [event["exception"] for event in exception_events] != [
            exception["id"] for exception in exceptions
        ]:
            _semantic_fail(
                f"$.unit.rule-projections[{projection_index}]",
                "exception evaluations must cover every authored exception in order",
            )
        norm_truth = {cast(str, event["norm"]): event["truth"] for event in norm_events}
        initial = {
            cast(str, norm["id"])
            for norm in norms
            if norm_truth[cast(str, norm["id"])] == "true"
        }
        removed: set[str] = set()
        substituted: set[str] = set()
        expected_transformations: list[tuple[str, str, str]] = []
        exception_truth = {
            cast(str, event["exception"]): event["truth"] for event in exception_events
        }
        for exception in exceptions:
            exception_id = cast(str, exception["id"])
            if exception_truth[exception_id] != "true":
                continue
            for norm_id in cast(list[str], exception.get("affects", [])):
                removed.add(norm_id)
                if norm_id in initial:
                    expected_transformations.append(
                        ("norm-removed", norm_id, exception_id)
                    )
            for norm_id in cast(list[str], exception.get("substitutes", [])):
                if norm_truth[norm_id] != "true":
                    _semantic_fail(
                        f"$.unit.rule-projections[{projection_index}]",
                        "a matching exception substitutes an inapplicable norm",
                    )
                substituted.add(norm_id)
                expected_transformations.append(
                    ("norm-substituted", norm_id, exception_id)
                )
        actual_transformations = [
            (
                cast(str, event["kind"]),
                cast(str, event["norm"]),
                cast(str, event["exception"]),
            )
            for event in trace
            if event["kind"] in {"norm-removed", "norm-substituted"}
            and event["declaration"] == identifier
        ]
        if actual_transformations != expected_transformations:
            _semantic_fail(
                f"$.unit.rule-projections[{projection_index}]",
                "norm transformations must equal every matching exception effect",
            )
        final = (initial - removed) | substituted
        expected_norms = [
            cast(str, norm["id"]) for norm in norms if cast(str, norm["id"]) in final
        ]
        effective_norm_events = [
            event
            for event in trace
            if event["kind"] == "norm-effective" and event["declaration"] == identifier
        ]
        if [event["norm"] for event in effective_norm_events] != expected_norms:
            _semantic_fail(
                f"$.unit.rule-projections[{projection_index}].norms",
                "effective norms differ from recomputed exception semantics",
            )
        expected_criteria: list[tuple[str, str]] = []
        for criterion in cast(list[Mapping[str, object]], document["criteria"]):
            criterion_norms = set(cast(list[str], criterion["norms"]))
            selected = criterion_norms & final
            if selected == criterion_norms:
                expected_criteria.append(
                    ("criterion-effective", cast(str, criterion["id"]))
                )
            elif not selected:
                expected_criteria.append(
                    ("criterion-inactive", cast(str, criterion["id"]))
                )
            else:
                _semantic_fail(
                    f"$.unit.rule-projections[{projection_index}]",
                    "criterion has only some effective authored norms",
                )
        actual_criteria = [
            (cast(str, event["kind"]), cast(str, event["criterion"]))
            for event in trace
            if event["kind"] in {"criterion-effective", "criterion-inactive"}
            and event["declaration"] == identifier
        ]
        if actual_criteria != expected_criteria:
            _semantic_fail(
                f"$.unit.rule-projections[{projection_index}].criteria",
                "criterion states differ from recomputed norm semantics",
            )


def _record_member(
    document: Mapping[str, object], group: str, identifier: object, event_index: int
) -> Mapping[str, object]:
    for item in cast(list[Mapping[str, object]], document[group]):
        if item["id"] == identifier:
            return item
    _semantic_fail(
        f"$.trace[{event_index}]",
        f"event references an unauthored {group[:-1]}",
    )


def _trace_predicate(trace: Mapping[str, object]) -> object:
    operator = cast(str, trace["operator"])
    if "facet" in trace:
        predicate: dict[str, object] = {
            "facet": trace["facet"],
            "operator": operator,
        }
        if operator != "exists":
            predicate["value"] = trace["expected"]
        return predicate
    children = [
        _trace_predicate(child)
        for child in cast(list[Mapping[str, object]], trace["children"])
    ]
    return {operator: children[0] if operator == "not" else children}


_CAUSE_KINDS = {
    "manifest-evaluated": frozenset(),
    "manifest-selected": frozenset({"manifest-evaluated"}),
    "rule-set-member-expanded": frozenset({"manifest-selected"}),
    "rule-set-member-inactive": frozenset({"manifest-selected"}),
    "dependency-discovered": frozenset(
        {
            "manifest-selected",
            "rule-set-member-expanded",
            "dependency-discovered",
            "policy-result-discovered",
        }
    ),
    "policy-result-discovered": frozenset({"policy-evaluated"}),
    "declaration-evaluated": frozenset(
        {
            "manifest-selected",
            "rule-set-member-expanded",
            "dependency-discovered",
            "policy-result-discovered",
        }
    ),
    "conflict-detected": frozenset(
        {
            "manifest-selected",
            "rule-set-member-expanded",
            "dependency-discovered",
            "policy-result-discovered",
        }
    ),
    "policy-evaluated": frozenset({"conflict-detected"}),
    "conflict-resolved": frozenset({"policy-evaluated"}),
    "declaration-excluded": frozenset({"conflict-resolved"}),
    "alias-created": frozenset({"conflict-resolved"}),
    "declaration-effective": frozenset(
        {
            "manifest-selected",
            "rule-set-member-expanded",
            "dependency-discovered",
            "policy-result-discovered",
        }
    ),
    "norm-evaluated": frozenset(),
    "exception-evaluated": frozenset(),
    "norm-removed": frozenset({"norm-evaluated", "exception-evaluated"}),
    "norm-substituted": frozenset({"norm-evaluated", "exception-evaluated"}),
    "norm-effective": frozenset({"norm-evaluated", "norm-removed", "norm-substituted"}),
    "criterion-effective": frozenset({"norm-effective"}),
    "criterion-inactive": frozenset({"norm-evaluated"}),
    "unit-issued": frozenset(
        {
            "declaration-effective",
            "norm-effective",
            "criterion-effective",
            "criterion-inactive",
        }
    ),
}


def _validate_event_causes(
    payload: Mapping[str, object], trace: list[Mapping[str, object]]
) -> None:
    records = {
        cast(str, record["id"]): cast(Mapping[str, object], record["document"])
        for group in ("declarations", "controls")
        for record in cast(list[Mapping[str, object]], payload[group])
    }
    for index, event in enumerate(trace):
        kind = cast(str, event["kind"])
        causes = cast(list[int], event["causes"])
        allowed = _CAUSE_KINDS[kind]
        if any(trace[cause]["kind"] not in allowed for cause in causes):
            _semantic_fail(
                f"$.trace[{index}].causes",
                f"{kind!r} event has a cause of an inadmissible kind",
            )
        if allowed and kind != "unit-issued" and not causes:
            _semantic_fail(
                f"$.trace[{index}].causes",
                f"{kind!r} event requires at least one cause",
            )
        predecessors = [trace[cause] for cause in causes]
        declaration = cast(str, event["declaration"])
        if kind == "manifest-selected" and causes != [0]:
            _cause_fail(
                index, "manifest selection must be caused by manifest evaluation"
            )
        elif kind in {
            "declaration-evaluated",
            "declaration-effective",
            "dependency-discovered",
        }:
            expected_declaration = (
                cast(str, event["dependant"])
                if kind == "dependency-discovered"
                else declaration
            )
            if any(
                item["declaration"] != expected_declaration for item in predecessors
            ):
                _cause_fail(index, "discovery causes must concern the same declaration")
        elif kind == "conflict-detected":
            conflict = set(cast(list[str], event["conflict"]))
            caused = {cast(str, item["declaration"]) for item in predecessors}
            if caused != conflict:
                _cause_fail(index, "conflict causes must cover exactly both members")
        elif kind == "policy-evaluated":
            if any(item["conflict"] != event["conflict"] for item in predecessors):
                _cause_fail(index, "policy cause must concern the same conflict")
        elif kind == "policy-result-discovered":
            if any(
                item["declaration"] != event["policy"]
                or item["conflict"] != event["conflict"]
                for item in predecessors
            ):
                _cause_fail(index, "policy result cause must concern the same policy")
        elif kind == "conflict-resolved":
            if any(
                item["declaration"] != event["policy"]
                or item["conflict"] != event["conflict"]
                for item in predecessors
            ):
                _cause_fail(index, "resolution cause must concern the same policy")
        elif kind in {"declaration-excluded", "alias-created"}:
            if any(
                item["declaration"] != event["policy"]
                or item["policy"] != event["policy"]
                or item["conflict"] != event["conflict"]
                for item in predecessors
            ):
                _cause_fail(
                    index, "policy effect cause must concern the same resolution"
                )
        elif kind in {"norm-removed", "norm-substituted"}:
            expected_transformation_causes = {
                ("norm-evaluated", event["norm"]),
                ("exception-evaluated", event["exception"]),
            }
            actual = {
                (item["kind"], item.get("norm", item.get("exception")))
                for item in predecessors
                if item["declaration"] == declaration
            }
            if actual != expected_transformation_causes:
                _cause_fail(
                    index, "norm transformation causes must name its norm and exception"
                )
        elif kind == "norm-effective":
            if not any(
                item["kind"] == "norm-evaluated"
                and item["declaration"] == declaration
                and item["norm"] == event["norm"]
                for item in predecessors
            ) or any(
                item["declaration"] != declaration or item.get("norm") != event["norm"]
                for item in predecessors
            ):
                _cause_fail(
                    index, "effective norm causes must concern that authored norm"
                )
        elif kind in {"criterion-effective", "criterion-inactive"}:
            document = records.get(declaration)
            if document is None:
                _cause_fail(index, "criterion event lacks its authored rule")
            criterion = _record_member(
                cast(Mapping[str, object], document),
                "criteria",
                event["criterion"],
                index,
            )
            expected_norms = cast(list[str], criterion["norms"])
            actual_norms = [cast(str, item["norm"]) for item in predecessors]
            if actual_norms != expected_norms or any(
                item["declaration"] != declaration for item in predecessors
            ):
                _cause_fail(index, "criterion causes must equal its authored norms")
        elif kind == "unit-issued":
            expected_unit_causes = [
                ordinal
                for ordinal, item in enumerate(trace)
                if item["kind"]
                in {
                    "declaration-effective",
                    "norm-effective",
                    "criterion-effective",
                    "criterion-inactive",
                }
            ]
            if causes != expected_unit_causes:
                _cause_fail(
                    index, "unit causes must equal all terminal effective events"
                )


def _cause_fail(index: int, detail: str) -> NoReturn:
    _semantic_fail(f"$.trace[{index}].causes", detail)


def _source_key(source: Mapping[str, object]) -> tuple[object, object, object]:
    return source["namespace"], source["path"], source["sha256"]


def _validate_applicability(
    trace: Mapping[str, object],
    context: Mapping[str, object],
    expected_path: tuple[object, ...],
) -> str:
    """Recompute one emitted applicability tree against packet context."""
    if trace["predicate-path"] != list(expected_path):
        _semantic_fail(
            "$.trace.applicability.predicate-path",
            "predicate path differs from its position in the applicability tree",
        )
    operator = cast(str, trace["operator"])
    if "facet" in trace:
        facet = cast(str, trace["facet"])
        present = facet in context
        observed = context.get(facet)
        if trace["observed-present"] is not present or not json_values_equal(
            trace["observed"], observed
        ):
            _semantic_fail(
                "$.trace.applicability",
                "atomic observation differs from the packet context",
            )
        if operator == "exists":
            result = "true" if present else "false"
        elif not present:
            result = "unknown"
        elif operator == "equals":
            result = (
                "true" if json_values_equal(observed, trace["expected"]) else "false"
            )
        else:
            candidates = cast(list[object], trace["expected"])
            result = (
                "true"
                if any(
                    json_values_equal(observed, candidate) for candidate in candidates
                )
                else "false"
            )
    else:
        child_traces = cast(list[Mapping[str, object]], trace["children"])
        children = [
            _validate_applicability(
                child,
                context,
                expected_path
                + (("not",) if operator == "not" else (operator, child_index)),
            )
            for child_index, child in enumerate(child_traces)
        ]
        if operator == "all":
            result = (
                "false"
                if "false" in children
                else "true" if all(item == "true" for item in children) else "unknown"
            )
        elif operator == "any":
            result = (
                "true"
                if "true" in children
                else "false" if all(item == "false" for item in children) else "unknown"
            )
        else:
            if len(children) != 1:
                _semantic_fail(
                    "$.trace.applicability.children",
                    "not applicability must contain exactly one child",
                )
            child = children[0]
            result = (
                "unknown"
                if child == "unknown"
                else "false" if child == "true" else "true"
            )
    if trace["result"] != result:
        _semantic_fail(
            "$.trace.applicability",
            "applicability result differs from its emitted observations",
        )
    return result


def _semantic_fail(location: str, detail: str) -> NoReturn:
    raise QueryPacketError(f"Invalid query packet at {location}: {detail}")


def _json_path(parts: tuple[object, ...]) -> str:
    """Format one JSON path for a schema diagnostic."""
    result = "$"
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += f".{part}"
    return result
