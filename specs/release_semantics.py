"""Encode semantic snapshots and recompute draft release differences."""

from __future__ import annotations

from collections.abc import Mapping

from eutaxis.declarations.canonical_json import jcs_bytes, parse_canonical_json_bytes
from eutaxis.declarations.markdown_projection import _thaw_json
from eutaxis.declarations.models import JsonValue, freeze_json
from eutaxis.declarations.semantic_comparison import (
    SemanticObjectKey,
    SemanticObjectKind,
    _compare_semantic_objects,
    _key_order,
)

SemanticObjects = Mapping[SemanticObjectKey, Mapping[str, JsonValue]]


def _identity(key: SemanticObjectKey) -> dict[str, object]:
    """Encode the kind, identifier and optional exact version."""
    return {"kind": key.object_kind.value, "id": key.id, "version": key.version}


def encode_snapshot(objects: SemanticObjects) -> bytes:
    """Retain the initial producer's canonical semantic snapshot format."""
    return jcs_bytes(
        [
            {**_identity(key), "value": _thaw_json(objects[key])}
            for key in sorted(objects, key=_key_order)
        ]
    )


def _decode_snapshot(source: bytes) -> SemanticObjects:
    """Recover typed comparison keys and values without accepting duplicates."""
    rows = parse_canonical_json_bytes(source)
    if not isinstance(rows, list):
        raise ValueError("Expected a list of typed semantic objects")
    objects: dict[SemanticObjectKey, Mapping[str, JsonValue]] = {}
    for row in rows:
        if not isinstance(row, dict) or row.keys() != {
            "kind",
            "id",
            "version",
            "value",
        }:
            raise ValueError("Invalid typed semantic object")
        kind = SemanticObjectKind(row["kind"])
        identifier, version, value = row["id"], row["version"], row["value"]
        if (
            not isinstance(identifier, str)
            or not identifier
            or (version is not None and (type(version) is not int or version < 1))
            or (kind is SemanticObjectKind.FACET and version is not None)
            or not isinstance(value, dict)
        ):
            raise ValueError("Invalid typed semantic identity or value")
        key = SemanticObjectKey(kind, identifier, version)
        if key in objects:
            raise ValueError(f"Duplicate typed semantic object: {key}")
        objects[key] = {name: freeze_json(item) for name, item in value.items()}
    if encode_snapshot(objects) != source:
        raise ValueError("Typed semantic objects are out of order")
    return objects


def encode_differences(baseline: bytes, candidate: bytes) -> bytes:
    """Compare canonical snapshots with the declaration comparator."""
    comparison = _compare_semantic_objects(
        _decode_snapshot(baseline), _decode_snapshot(candidate)
    )
    return jcs_bytes(
        [
            {
                **_identity(change.key),
                "change": change.change.value,
                "paths": [list(path) for path in change.paths],
                "baseline": _thaw_json(change.baseline),
                "candidate": _thaw_json(change.candidate),
            }
            for change in comparison.differences
        ]
    )
