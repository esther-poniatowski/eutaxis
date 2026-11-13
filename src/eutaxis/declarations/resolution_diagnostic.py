"""Project failed external resolutions into closed diagnostic JSON."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from .canonical_json import jcs_bytes
from .external_result import (
    AcquisitionSourceCoordinate,
)
from .external_resolution import (
    ExternalResolutionError,
    _issued_external_resolution_error_state,
)
from .resolution_diagnostic_schema import validate_resolution_diagnostic_payload
from .resolution_serialization import (
    applicability_payload,
    coordinate_payload,
    event_payload,
    resolution_source_payload,
)

RESOLUTION_DIAGNOSTIC_SCHEMA = "eutaxis:resolution-diagnostic@1"


def external_resolution_failure_json_bytes(
    error: ExternalResolutionError,
) -> bytes:
    """Return canonical JSON for one authenticated failed resolution."""
    state = _issued_external_resolution_error_state(error)
    original = state.error
    coordinates = dict(state.source_coordinates_by_path)
    trace = original.trace
    payload: dict[str, object] = {
        "_schema": RESOLUTION_DIAGNOSTIC_SCHEMA,
        "completion": "failed",
        "sources": [
            coordinate_payload(coordinate)
            for coordinate in state.acquisition_state.source_coordinates
        ],
        "error": {
            "code": original.code.value,
            "detail": original.detail,
        },
        "trace": None,
    }
    error_payload = payload["error"]
    assert isinstance(error_payload, dict)
    if original.source is not None:
        error_payload["source"] = resolution_source_payload(
            original.source,
            _coordinate_for_path(coordinates, original.source.path),
        )
    if original.truth is not None:
        error_payload["truth"] = original.truth.value
    if original.applicability is not None:
        error_payload["applicability"] = applicability_payload(
            original.applicability
        )
    if trace is not None:
        payload["trace"] = {
            "manifest": trace.manifest,
            "facet-registry": trace.facet_registry,
            "facet-content-revision": trace.facet_content_revision,
            "events": [
                event_payload(
                    event,
                    _coordinate_for_path(coordinates, event.source.path),
                )
                for event in trace.events
            ],
        }
    validate_resolution_diagnostic_payload(payload)
    return jcs_bytes(payload)


def _coordinate_for_path(
    coordinates: Mapping[Path, AcquisitionSourceCoordinate],
    path: Path,
) -> AcquisitionSourceCoordinate:
    """Return the acquired coordinate for one resolver-local source path."""
    coordinate = coordinates.get(path.resolve())
    if coordinate is None:
        raise ValueError(f"resolution source {path} has no acquired coordinate")
    return coordinate
