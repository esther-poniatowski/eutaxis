"""Tests for portable query packets projected from external resolution."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

import eutaxis.declarations.external_resolution as external_resolution_module
from eutaxis.declarations import (
    AcquisitionContractError,
    QueryPacket,
    QueryPacketError,
    QuerySelectionOutcome,
    acquire_external_declarations_from_path,
    build_external_query_packet,
    query_packet_json_bytes,
    resolve_external_compilation_unit,
    validate_query_packet_payload,
)
from eutaxis.declarations.external_result import _retire_external_result_tree
from eutaxis.declarations.canonical_json import jcs_bytes
from tests.test_external_acquisition import _write_contract


def _rule(identifier: str, *, applicable: bool, conflicts: str | None = None) -> bytes:
    relations = (
        f"[{{type: incompatible-with, target: packet/{conflicts}}}]"
        if conflicts is not None
        else "[]"
    )
    return f"""\
_schema: eutaxis:declaration@1
id: packet/{identifier}
kind: rule
owner: packet
status: active
source-revision: {identifier}-revision
applicability: {{facet: packet.enabled, operator: equals, value: {str(applicable).lower()}}}
relations: {relations}
axis: reasoning-target
failure-mode: visible
norms:
  - id: {identifier}-norm
    modality: must
    subject: agent
    action: {{verb: apply, object: the {identifier} rule}}
criteria:
  - id: {identifier}-criterion
    norms: [{identifier}-norm]
    evaluator: {{id: eutaxis/manual-judgment, version: 1}}
    statement: The {identifier} rule is applied
""".encode()


POLICY = b"""\
_schema: eutaxis:declaration@1
id: packet/prefer-primary
kind: resolution-policy
owner: packet
status: active
source-revision: policy-revision
applicability: {facet: packet.enabled, operator: equals, value: true}
relations: []
conflicts: [packet/primary, packet/alternate]
when: {facet: packet.enabled, operator: equals, value: true}
order: 10
strategy: {kind: retain, retain: packet/primary}
"""

MANIFEST = b"""\
_schema: eutaxis:declaration@1
id: packet/manifest
kind: composition-manifest
owner: packet
status: active
source-revision: manifest-revision
applicability: {facet: packet.enabled, operator: equals, value: true}
relations: []
mechanism: cumulative
scope: project
target: AGENTS.md
sections:
  - id: core
    declarations: [packet/primary, packet/alternate, packet/contextual, packet/package]
policies: [packet/prefer-primary]
"""

RULE_SET = b"""\
_schema: eutaxis:declaration@1
id: packet/package
kind: rule-set
owner: packet
status: active
source-revision: package-revision
applicability: {facet: packet.enabled, operator: equals, value: true}
relations: []
purpose: Exercises inactive candidate reporting
rules:
  - _schema: eutaxis:declaration@1
    id: packet/inactive
    kind: rule
    owner: packet
    status: retired
    source-revision: inactive-revision
    applicability: {facet: packet.enabled, operator: equals, value: true}
    relations: []
    axis: reasoning-target
    failure-mode: visible
    norms:
      - id: inactive-norm
        modality: must
        subject: agent
        action: {verb: apply, object: the inactive rule}
    criteria:
      - id: inactive-criterion
        norms: [inactive-norm]
        evaluator: {id: eutaxis/manual-judgment, version: 1}
        statement: The inactive rule is applied
"""


def _acquire(
    tmp_path: Path,
    *,
    facet_bytes: bytes | None = None,
    workspace_path: str | None = None,
):
    files = (
        (
            "declarations/primary.yaml",
            _rule("primary", applicable=True, conflicts="alternate"),
        ),
        ("declarations/alternate.yaml", _rule("alternate", applicable=True)),
        ("declarations/contextual.yaml", _rule("contextual", applicable=False)),
        ("declarations/package.yaml", RULE_SET),
        ("declarations/policy.yaml", POLICY),
        ("declarations/manifest.yaml", MANIFEST),
    )
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="packet",
        declaration_files=files,
        facet_bytes=facet_bytes,
        resource_files=(
            (
                "packet/reference",
                "support/reference.py",
                "text/x-python; charset=utf-8",
                b"reference\n",
            ),
        ),
    )
    return acquire_external_declarations_from_path(
        workspace_path or str(tmp_path), manifest_path, lock_path
    )


def _packet(tmp_path: Path):
    acquisition = _acquire(tmp_path)
    context = {"context.available": True, "packet.enabled": True}
    resolution = resolve_external_compilation_unit(
        acquisition, "packet/manifest", context
    )
    return acquisition, resolution, build_external_query_packet(resolution)


def _redigest(record: dict[str, object]) -> None:
    material = {
        "document": record["document"],
        "effective-rule": record.get("effective-rule"),
        "version": record.get("version"),
    }
    record["record-digest"] = (
        "sha256:" + hashlib.sha256(jcs_bytes(material)).hexdigest()
    )


def test_packet_explains_every_considered_declaration(tmp_path: Path) -> None:
    _acquisition, _resolution, packet = _packet(tmp_path)

    assert packet.manifest == "packet/manifest"
    assert packet.context == {
        "context.available": True,
        "packet.enabled": True,
    }
    assert {item.declaration: item.outcome for item in packet.selections} == {
        "packet/alternate": QuerySelectionOutcome.EXCLUDED,
        "packet/contextual": QuerySelectionOutcome.INAPPLICABLE,
        "packet/inactive": QuerySelectionOutcome.INACTIVE,
        "packet/primary": QuerySelectionOutcome.EFFECTIVE,
    }
    payload = json.loads(query_packet_json_bytes(packet))
    assert payload["_schema"] == "eutaxis:query-packet@1"
    assert payload["completion"] == "complete"
    assert payload["catalog-index-revision"] == 2
    assert payload["acquisition-schema-version"] == 1
    assert payload["facet-registry"]["schema-version"] == 1
    assert payload["unit"]["components"] == [
        {"declaration": "packet/primary", "rank": 0, "section": "core"}
    ]
    primary = next(
        item for item in payload["declarations"] if item["id"] == "packet/primary"
    )
    assert primary["document"]["norms"][0]["modality"] == "must"
    assert primary["document"]["norms"][0]["action"] == {
        "verb": "apply",
        "object": "the primary rule",
    }
    assert primary["effective-rule"] == {
        "norms": ["primary-norm"],
        "criteria": ["primary-criterion"],
    }
    assert payload["resources"][0]["text"] == "reference\n"
    assert [item["id"] for item in payload["controls"]] == [
        "packet/manifest",
        "packet/package",
        "packet/prefer-primary",
    ]
    reasons = {
        item["declaration"]: item["reason-events"] for item in payload["selections"]
    }
    assert all(reasons.values())


def test_packet_is_relocatable_and_deterministic(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_acquisition, _first_resolution, first = _packet(first_root)
    _second_acquisition, _second_resolution, second = _packet(second_root)

    first_bytes = query_packet_json_bytes(first)
    assert first_bytes == query_packet_json_bytes(second)
    assert str(first_root).encode() not in first_bytes

    _retire_external_result_tree(first_acquisition)
    assert query_packet_json_bytes(first) == first_bytes


def test_packet_build_does_not_depend_on_later_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquisition = _acquire(tmp_path)
    resolution = resolve_external_compilation_unit(
        acquisition,
        "packet/manifest",
        {"context.available": True, "packet.enabled": True},
    )
    monkeypatch.chdir(tmp_path.parent)

    packet = build_external_query_packet(resolution)

    assert packet.manifest == "packet/manifest"


def test_external_resolution_binds_sources_before_resolver_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    acquisition = _acquire(tmp_path, workspace_path=".")
    original = external_resolution_module.resolve_compilation_unit

    def changing_resolver(registry, manifest_id, context):
        resolution = original(registry, manifest_id, context)
        monkeypatch.chdir("/")
        return resolution

    monkeypatch.setattr(
        external_resolution_module,
        "resolve_compilation_unit",
        changing_resolver,
    )
    resolution = resolve_external_compilation_unit(
        acquisition,
        "packet/manifest",
        {"context.available": True, "packet.enabled": True},
    )

    assert build_external_query_packet(resolution).manifest == "packet/manifest"


def test_packet_build_rejects_noncanonical_json_number(tmp_path: Path) -> None:
    facets = b"""\
_schema: eutaxis:context-facets@1
id: packet/context-facets
owner: packet
source-revision: fixture-1
facets:
  - id: packet.enabled
    value-schema: {type: boolean}
  - id: packet.count
    value-schema: {type: integer}
"""
    acquisition = _acquire(tmp_path, facet_bytes=facets)
    resolution = resolve_external_compilation_unit(
        acquisition,
        "packet/manifest",
        {
            "context.available": True,
            "packet.enabled": True,
            "packet.count": 2**53,
        },
    )

    with pytest.raises(QueryPacketError, match="interoperable range"):
        build_external_query_packet(resolution)


def test_packet_builder_rejects_changed_resolution_authority(tmp_path: Path) -> None:
    _acquisition, resolution, _packet_value = _packet(tmp_path)
    object.__setattr__(resolution.trace, "events", resolution.trace.events[:-1])

    with pytest.raises(AcquisitionContractError, match="authority changed"):
        build_external_query_packet(resolution)


def test_packet_schema_rejects_a_noncomplete_projection(tmp_path: Path) -> None:
    _acquisition, _resolution, packet = _packet(tmp_path)
    payload = json.loads(query_packet_json_bytes(packet))
    payload["completion"] = "failed"

    with pytest.raises(QueryPacketError, match=r"\$\.completion"):
        validate_query_packet_payload(payload)


def test_query_packet_cannot_be_publicly_forged() -> None:
    with pytest.raises(TypeError, match="must be issued"):
        QueryPacket(payload={})


@pytest.mark.parametrize(
    "defect",
    (
        "event-kind",
        "event-fields",
        "reason-reference",
        "contradictory-outcome",
        "dependency",
        "rule-projection",
        "component-anchor",
        "context",
        "selection-source",
        "selection-source-revision",
        "facet-extension",
        "source-content-revision",
        "resource-omission",
        "resource-text",
        "record-content",
        "authored-predicate",
        "cause-kind",
        "source-revisions",
    ),
)
def test_packet_schema_rejects_incoherent_explanations(
    tmp_path: Path, defect: str
) -> None:
    _acquisition, _resolution, packet = _packet(tmp_path)
    payload = json.loads(query_packet_json_bytes(packet))
    if defect == "event-kind":
        payload["trace"][0]["kind"] = "bogus-event"
    elif defect == "event-fields":
        payload["trace"][0]["norm"] = "unadmitted"
    elif defect == "reason-reference":
        payload["selections"][0]["reason-events"] = [999999]
    elif defect == "contradictory-outcome":
        inactive = next(
            item
            for item in payload["selections"]
            if item["declaration"] == "packet/inactive"
        )
        inactive["outcome"] = "effective"
    elif defect == "dependency":
        payload["unit"]["dependencies"] = [
            {"prerequisite": "ghost/a", "dependant": "ghost/b"}
        ]
    elif defect == "rule-projection":
        payload["unit"]["rule-projections"][0]["declaration"] = "ghost/rule"
    elif defect == "component-anchor":
        payload["unit"]["components"][0]["rank"] = 999
    elif defect == "context":
        payload["context"]["packet.enabled"] = False
    elif defect == "selection-source":
        payload["selections"][0]["source"] = payload["sources"][0]
    elif defect == "selection-source-revision":
        payload["selections"][0]["source-revision"] = "forged-revision"
    elif defect == "facet-extension":
        payload["source-revisions"] = [
            item
            for item in payload["source-revisions"]
            if item["role"] != "facet-extension"
        ]
    elif defect == "source-content-revision":
        external = next(
            item
            for item in payload["source-revisions"]
            if item["role"] == "declaration-source" and item["namespace"] == "packet"
        )
        external["content-revision"] = "sha256:" + "0" * 64
    elif defect == "resource-text":
        payload["resources"][0]["text"] = "forged\n"
    elif defect == "resource-omission":
        payload["resources"] = []
    elif defect == "record-content":
        primary = next(
            item for item in payload["declarations"] if item["id"] == "packet/primary"
        )
        primary["document"]["norms"][0]["action"]["object"] = "arbitrary code"
    elif defect == "authored-predicate":
        evaluated = next(
            item
            for item in payload["trace"]
            if item["kind"] == "declaration-evaluated"
            and item["declaration"] == "packet/primary"
        )
        evaluated["applicability"]["facet"] = "context.available"
    elif defect == "cause-kind":
        excluded = next(
            item for item in payload["trace"] if item["kind"] == "declaration-excluded"
        )
        excluded["causes"] = [0]
    else:
        payload["source-revisions"] = []

    with pytest.raises(QueryPacketError):
        validate_query_packet_payload(payload)


@pytest.mark.parametrize(
    "defect",
    (
        "unauthored-norm",
        "unauthored-criterion",
        "manifest-selection",
        "policy-strategy",
        "cause-object",
        "predicate-path",
    ),
)
def test_packet_schema_rejects_semantically_forged_closure(
    tmp_path: Path, defect: str
) -> None:
    _acquisition, _resolution, packet = _packet(tmp_path)
    payload = json.loads(query_packet_json_bytes(packet))
    primary = next(
        item for item in payload["declarations"] if item["id"] == "packet/primary"
    )
    if defect == "unauthored-norm":
        primary["effective-rule"]["norms"] = ["ghost-norm"]
        payload["unit"]["rule-projections"][0]["norms"] = ["ghost-norm"]
        for event in payload["trace"]:
            if event.get("norm") == "primary-norm":
                event["norm"] = "ghost-norm"
        _redigest(primary)
    elif defect == "unauthored-criterion":
        primary["effective-rule"]["criteria"] = ["ghost-criterion"]
        payload["unit"]["rule-projections"][0]["criteria"] = ["ghost-criterion"]
        for event in payload["trace"]:
            if event.get("criterion") == "primary-criterion":
                event["criterion"] = "ghost-criterion"
        _redigest(primary)
    elif defect == "manifest-selection":
        manifest = next(
            item for item in payload["controls"] if item["id"] == "packet/manifest"
        )
        declarations = manifest["document"]["sections"][0]["declarations"]
        declarations[0], declarations[1] = declarations[1], declarations[0]
        _redigest(manifest)
    elif defect == "policy-strategy":
        policy = next(
            item
            for item in payload["controls"]
            if item["id"] == "packet/prefer-primary"
        )
        policy["document"]["strategy"]["retain"] = "packet/alternate"
        _redigest(policy)
    elif defect == "cause-object":
        alternate_selection = next(
            event["ordinal"]
            for event in payload["trace"]
            if event["kind"] == "manifest-selected"
            and event["declaration"] == "packet/alternate"
        )
        primary_evaluation = next(
            event
            for event in payload["trace"]
            if event["kind"] == "declaration-evaluated"
            and event["declaration"] == "packet/primary"
        )
        primary_evaluation["causes"] = [alternate_selection]
    else:
        applicability = payload["trace"][0]["applicability"]
        applicability["predicate-path"] = ["forged"]

    with pytest.raises(QueryPacketError):
        validate_query_packet_payload(payload)


@pytest.mark.parametrize(
    "defect",
    (
        "authored-relation",
        "rule-set-member",
        "event-provenance",
        "record-provenance",
        "manifest-anchor",
        "duplicate-cause",
        "source-kind",
    ),
)
def test_packet_schema_rejects_forged_authored_resolution_links(
    tmp_path: Path, defect: str
) -> None:
    _acquisition, _resolution, packet = _packet(tmp_path)
    payload = json.loads(query_packet_json_bytes(packet))
    if defect == "authored-relation":
        primary = next(
            item for item in payload["declarations"] if item["id"] == "packet/primary"
        )
        primary["document"]["relations"] = []
        _redigest(primary)
    elif defect == "rule-set-member":
        rule_set = next(
            item for item in payload["controls"] if item["id"] == "packet/package"
        )
        rule_set["document"]["rules"][0]["norms"][0]["action"][
            "object"
        ] = "forged action"
        _redigest(rule_set)
    elif defect == "event-provenance":
        conflict = next(
            event for event in payload["trace"] if event["kind"] == "conflict-detected"
        )
        manifest = next(
            item for item in payload["controls"] if item["id"] == "packet/manifest"
        )
        conflict["source"] = manifest["source"]
    elif defect == "record-provenance":
        manifest = next(
            item for item in payload["controls"] if item["id"] == "packet/manifest"
        )
        policy = next(
            item
            for item in payload["controls"]
            if item["id"] == "packet/prefer-primary"
        )
        manifest["source"] = policy["source"]
    elif defect == "manifest-anchor":
        for event in payload["trace"]:
            if event["declaration"] == "packet/primary" and "anchor" in event:
                event["anchor"] = {"section": "forged-section", "rank": 99}
        payload["unit"]["components"][0].update(
            {"section": "forged-section", "rank": 99}
        )
    elif defect == "duplicate-cause":
        conflict = next(
            event for event in payload["trace"] if event["kind"] == "conflict-detected"
        )
        conflict["causes"].append(conflict["causes"][0])
    else:
        declaration_source = next(
            item
            for item in payload["source-revisions"]
            if item["role"] == "declaration-source"
        )
        declaration_source["kind"] = "forged-kind"

    with pytest.raises(QueryPacketError):
        validate_query_packet_payload(payload)


@pytest.mark.parametrize(
    "defect",
    (
        "omitted-norm",
        "omitted-exception",
        "omitted-dependency",
        "omitted-decision",
        "contract-provenance",
        "missing-manifest-policy",
    ),
)
def test_packet_schema_rejects_incomplete_authored_closure(
    tmp_path: Path, defect: str
) -> None:
    _acquisition, _resolution, packet = _packet(tmp_path)
    payload = json.loads(query_packet_json_bytes(packet))
    primary = next(
        item for item in payload["declarations"] if item["id"] == "packet/primary"
    )
    if defect == "omitted-norm":
        extra = json.loads(json.dumps(primary["document"]["norms"][0]))
        extra["id"] = "omitted-norm"
        extra["action"]["object"] = "the omitted rule"
        primary["document"]["norms"].append(extra)
        _redigest(primary)
    elif defect == "omitted-exception":
        primary["document"]["exceptions"] = [
            {
                "id": "omitted-exception",
                "when": primary["document"]["applicability"],
                "disposition": "waive",
                "affects": ["primary-norm"],
            }
        ]
        _redigest(primary)
    elif defect == "omitted-dependency":
        primary["document"]["relations"].append(
            {"type": "requires", "target": "packet/contextual"}
        )
        _redigest(primary)
    elif defect == "omitted-decision":
        primary["document"]["decided-by"] = ["packet/missing-decision"]
        _redigest(primary)
        _rebind_source_record(payload, primary)
    elif defect == "contract-provenance":
        contract = payload["contracts"][0]
        policy = next(
            item
            for item in payload["controls"]
            if item["id"] == "packet/prefer-primary"
        )
        contract["source"] = policy["source"]
    else:
        manifest = next(
            item for item in payload["controls"] if item["id"] == "packet/manifest"
        )
        manifest["document"]["policies"].append("packet/missing-policy")
        _redigest(manifest)
        _rebind_source_record(payload, manifest)

    with pytest.raises(QueryPacketError):
        validate_query_packet_payload(payload)


@pytest.mark.parametrize(
    "defect",
    ("missing-rule-projection", "omitted-winning-policy", "spurious-index-version"),
)
def test_packet_schema_rejects_omitted_controlled_semantics(
    tmp_path: Path, defect: str
) -> None:
    _acquisition, _resolution, packet = _packet(tmp_path)
    payload = json.loads(query_packet_json_bytes(packet))
    if defect == "missing-rule-projection":
        removed_kinds = {
            "norm-evaluated",
            "exception-evaluated",
            "norm-removed",
            "norm-substituted",
            "norm-effective",
            "criterion-effective",
            "criterion-inactive",
        }
        kept = [
            event for event in payload["trace"] if event["kind"] not in removed_kinds
        ]
        ordinal_map = {event["ordinal"]: index for index, event in enumerate(kept)}
        for index, event in enumerate(kept):
            event["ordinal"] = index
            event["causes"] = [
                ordinal_map[cause] for cause in event["causes"] if cause in ordinal_map
            ]
        payload["trace"] = kept
        for selection in payload["selections"]:
            selection["reason-events"] = [
                ordinal_map[cause]
                for cause in selection["reason-events"]
                if cause in ordinal_map
            ]
        payload["unit"]["rule-projections"] = []
        primary = next(
            item for item in payload["declarations"] if item["id"] == "packet/primary"
        )
        primary.pop("effective-rule")
        _redigest(primary)
    elif defect == "omitted-winning-policy":
        old = next(
            item
            for item in payload["controls"]
            if item["id"] == "packet/prefer-primary"
        )
        new = copy.deepcopy(old)
        new["id"] = "packet/prefer-alternate"
        new["source-revision"] = "alternate-policy-revision"
        new["document"]["id"] = new["id"]
        new["document"]["source-revision"] = new["source-revision"]
        new["document"]["order"] = 0
        new["document"]["strategy"]["retain"] = "packet/alternate"
        new["source"]["document-path"] = ["extra-policy"]
        _redigest(new)
        payload["controls"].insert(payload["controls"].index(old), new)
        manifest = next(
            item for item in payload["controls"] if item["id"] == "packet/manifest"
        )
        manifest["document"]["policies"].insert(0, new["id"])
        _redigest(manifest)
        source = next(
            item
            for item in payload["sources"]
            if _source_tuple(item) == _source_tuple(new["source"])
        )
        source["records"].append(
            {
                "id": new["id"],
                "kind": new["kind"],
                "source-revision": new["source-revision"],
                "document-path": ["extra-policy"],
                "content-digest": _content_digest(new["document"]),
            }
        )
    else:
        primary = next(
            item for item in payload["declarations"] if item["id"] == "packet/primary"
        )
        source = next(
            item
            for item in payload["sources"]
            if _source_tuple(item) == _source_tuple(primary["source"])
        )
        entry = next(
            item for item in source["records"] if item["id"] == "packet/primary"
        )
        entry["version"] = 1

    with pytest.raises(QueryPacketError):
        validate_query_packet_payload(payload)


def _source_tuple(source: dict[str, object]) -> tuple[object, object, object]:
    return source["namespace"], source["path"], source["sha256"]


def _content_digest(document: object) -> str:
    return "sha256:" + hashlib.sha256(jcs_bytes(document)).hexdigest()


def _rebind_source_record(
    payload: dict[str, object], record: dict[str, object]
) -> None:
    source = next(
        item
        for item in payload["sources"]
        if _source_tuple(item) == _source_tuple(record["source"])
    )
    entry = next(
        item
        for item in source["records"]
        if item["document-path"] == record["source"]["document-path"]
    )
    entry["content-digest"] = _content_digest(record["document"])


@pytest.mark.parametrize(
    "defect",
    (
        "policy-status",
        "rule-status",
        "manifest-status",
        "policy-owner",
        "rule-owner",
        "contract-status",
    ),
)
def test_packet_schema_rejects_invalid_lifecycle_authority(
    tmp_path: Path, defect: str
) -> None:
    _acquisition, _resolution, packet = _packet(tmp_path)
    payload = json.loads(query_packet_json_bytes(packet))
    policy = next(
        item for item in payload["controls"] if item["id"] == "packet/prefer-primary"
    )
    if defect == "policy-status":
        record = policy
        record["document"]["status"] = "retired"
    elif defect == "rule-status":
        record = next(
            item for item in payload["declarations"] if item["id"] == "packet/primary"
        )
        record["document"]["status"] = "retired"
    elif defect == "manifest-status":
        record = next(
            item for item in payload["controls"] if item["id"] == "packet/manifest"
        )
        record["document"]["status"] = "retired"
    elif defect == "policy-owner":
        record = policy
        record["document"]["owner"] = "other-owner"
    elif defect == "rule-owner":
        record = next(
            item for item in payload["declarations"] if item["id"] == "packet/primary"
        )
        record["document"]["owner"] = "other-owner"
    else:
        record = payload["contracts"][0]
        record["document"]["status"] = "retired"
    _redigest(record)
    _rebind_source_record(payload, record)

    with pytest.raises(QueryPacketError):
        validate_query_packet_payload(payload)
