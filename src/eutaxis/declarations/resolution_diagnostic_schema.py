"""Load and apply the packaged failed-resolution diagnostic schema."""

from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Mapping, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import best_match  # type: ignore[import-untyped]

from .. import data_path
from .exceptions import ResolutionDiagnosticError
from .query_packet_schema import _EVENT_BASE_FIELDS, _EVENT_FIELDS
from .resolution import ResolutionErrorCode

RESOLUTION_DIAGNOSTIC_SCHEMA_FILENAME = "resolution-diagnostic-v1.schema.json"


def resolution_diagnostic_schema_path() -> Path:
    """Return the packaged path of the failed-resolution schema."""
    return data_path() / "schemas" / RESOLUTION_DIAGNOSTIC_SCHEMA_FILENAME


@lru_cache(maxsize=1)
def _resolution_diagnostic_schema() -> dict[str, object]:
    """Load and meta-validate the immutable schema source."""
    try:
        value = json.loads(
            resolution_diagnostic_schema_path().read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResolutionDiagnosticError(
            f"cannot load resolution-diagnostic schema: {exc}"
        ) from exc
    if type(value) is not dict:
        raise ResolutionDiagnosticError(
            "resolution-diagnostic schema root must be an object"
        )
    Draft202012Validator.check_schema(value)
    return cast(dict[str, object], value)


def resolution_diagnostic_schema() -> dict[str, object]:
    """Return an isolated copy of the failed-resolution schema."""
    return deepcopy(_resolution_diagnostic_schema())


@lru_cache(maxsize=1)
def _resolution_diagnostic_validator() -> Draft202012Validator:
    """Return the shared validator for emitted diagnostic values."""
    return Draft202012Validator(_resolution_diagnostic_schema())


def validate_resolution_diagnostic_payload(payload: object) -> Mapping[str, object]:
    """Validate one closed failed-resolution diagnostic projection."""
    error = best_match(_resolution_diagnostic_validator().iter_errors(payload))
    if error is not None:
        location = _json_path(tuple(error.absolute_path))
        raise ResolutionDiagnosticError(
            f"Invalid resolution diagnostic at {location}: {error.message}"
        )
    admitted = cast(Mapping[str, object], payload)
    _validate_relations(admitted)
    return admitted


def _validate_relations(payload: Mapping[str, object]) -> None:
    """Require failure, trace, and portable source membership to agree."""
    sources = cast(list[Mapping[str, object]], payload["sources"])
    source_keys = [_source_key(source) for source in sources]
    if len(source_keys) != len(set(source_keys)):
        _fail("$.sources", "acquired sources must be unique")
    admitted_sources = set(source_keys)
    failure = cast(Mapping[str, object], payload["error"])
    code = cast(str, failure["code"])
    predicate_failure = code.endswith(("inapplicable", "indeterminate"))
    has_truth = "truth" in failure
    has_applicability = "applicability" in failure
    if has_truth != has_applicability or predicate_failure != has_truth:
        _fail(
            "$.error",
            "predicate failures require paired truth and applicability fields",
        )
    if has_applicability:
        applicability = cast(Mapping[str, object], failure["applicability"])
        if failure["truth"] != applicability["result"]:
            _fail(
                "$.error.truth",
                "truth must equal the applicability root result",
            )
    if code not in {item.value for item in ResolutionErrorCode}:
        _fail("$.error.code", "unknown resolution error code")
    if "source" in failure:
        _require_source(
            cast(Mapping[str, object], failure["source"]),
            admitted_sources,
            "$.error.source",
        )
    trace = payload["trace"]
    if trace is None:
        return
    trace_mapping = cast(Mapping[str, object], trace)
    events = cast(list[Mapping[str, object]], trace_mapping["events"])
    for index, event in enumerate(events):
        location = f"$.trace.events[{index}]"
        if event["ordinal"] != index:
            _fail(f"{location}.ordinal", "event ordinal must equal its position")
        causes = cast(list[int], event["causes"])
        if causes != sorted(set(causes)) or any(cause >= index for cause in causes):
            _fail(
                f"{location}.causes",
                "event causes must be unique earlier ordinals in sorted order",
            )
        kind = cast(str, event["kind"])
        expected = _EVENT_BASE_FIELDS | _EVENT_FIELDS[kind]
        if frozenset(event) != expected:
            _fail(
                location,
                f"{kind!r} event fields must be {sorted(expected)!r}",
            )
        _require_source(
            cast(Mapping[str, object], event["source"]),
            admitted_sources,
            f"{location}.source",
        )
        if "applicability" in event:
            applicability = cast(Mapping[str, object], event["applicability"])
            if event["truth"] != applicability["result"]:
                _fail(
                    f"{location}.truth",
                    "truth must equal the root applicability result",
                )
    if events and (
        events[0]["kind"] != "manifest-evaluated"
        or events[0]["declaration"] != trace_mapping["manifest"]
    ):
        _fail("$.trace.events[0]", "trace must open by evaluating its manifest")
    if events and events[-1]["kind"] == "unit-issued":
        _fail("$.trace.events", "failed trace cannot issue a compilation unit")


def _require_source(
    source: Mapping[str, object],
    admitted: set[tuple[object, object, object]],
    location: str,
) -> None:
    """Require one record source to name an acquired portable coordinate."""
    if _source_key(source) not in admitted:
        _fail(location, "source is absent from the acquired source set")


def _source_key(source: Mapping[str, object]) -> tuple[object, object, object]:
    return source["namespace"], source["path"], source["sha256"]


def _json_path(parts: tuple[object, ...]) -> str:
    result = "$"
    for part in parts:
        result += f"[{part}]" if isinstance(part, int) else f".{part}"
    return result


def _fail(location: str, detail: str) -> None:
    raise ResolutionDiagnosticError(
        f"Invalid resolution diagnostic at {location}: {detail}"
    )
