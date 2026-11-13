"""Serialize authenticated resolution evidence into portable JSON values."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from .applicability import (
    ApplicabilityTrace,
    AtomicApplicabilityTrace,
    BooleanApplicabilityTrace,
)
from .external_result import AcquisitionSourceCoordinate
from .resolution import ResolutionEvent, ResolutionSource


def coordinate_payload(item: AcquisitionSourceCoordinate) -> dict[str, object]:
    """Serialize one portable acquired-source coordinate."""
    return {"namespace": item.namespace, "path": item.path, "sha256": item.sha256}


def resolution_source_payload(
    source: ResolutionSource,
    coordinate: AcquisitionSourceCoordinate,
) -> dict[str, object]:
    """Serialize one resolver source against its acquired file coordinate."""
    return {
        **coordinate_payload(coordinate),
        "document-path": list(source.document_path),
        "line": source.line,
        "column": source.column,
    }


def event_payload(
    event: ResolutionEvent,
    source: AcquisitionSourceCoordinate,
) -> dict[str, object]:
    """Serialize one resolver event without its machine-local path."""
    payload: dict[str, object] = {
        "ordinal": event.ordinal,
        "kind": event.kind.value,
        "declaration": event.declaration,
        "source": {
            **coordinate_payload(source),
            "document-path": list(event.source.document_path),
        },
        "causes": list(event.causes),
    }
    if event.anchor is not None:
        payload["anchor"] = {
            "section": event.anchor.section,
            "rank": event.anchor.rank,
        }
    for name in (
        "relation",
        "dependant",
        "policy",
        "exception",
        "norm",
        "criterion",
        "replacement",
    ):
        value = getattr(event, name)
        if value is not None:
            payload[name] = value
    if event.conflict is not None:
        payload["conflict"] = list(event.conflict)
    if event.truth is not None:
        payload["truth"] = event.truth.value
    if event.applicability is not None:
        payload["applicability"] = applicability_payload(event.applicability)
    return payload


def applicability_payload(trace: ApplicabilityTrace) -> dict[str, object]:
    """Serialize one normalized predicate evaluation tree."""
    if isinstance(trace, AtomicApplicabilityTrace):
        return {
            "predicate-path": list(trace.predicate_path),
            "operator": trace.operator,
            "facet": trace.facet,
            "result": trace.result.value,
            "observed-present": trace.observed_present,
            "observed": plain_json(trace.observed),
            "expected": plain_json(trace.expected),
        }
    if isinstance(trace, BooleanApplicabilityTrace):
        return {
            "predicate-path": list(trace.predicate_path),
            "operator": trace.operator,
            "result": trace.result.value,
            "children": [applicability_payload(child) for child in trace.children],
        }
    raise TypeError("unknown applicability trace")


def plain_json(value: object) -> object:
    """Convert immutable JSON containers to ordinary JSON containers."""
    if isinstance(value, Mapping):
        return {cast(str, key): plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [plain_json(item) for item in value]
    if isinstance(value, list):
        return [plain_json(item) for item in value]
    return value
