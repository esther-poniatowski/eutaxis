"""Validate closed external-acquisition manifest and lock documents."""

from __future__ import annotations

import json
import math
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import ValidationError, best_match  # type: ignore[import-untyped]

from .. import data_path
from .exceptions import AcquisitionContractError
from .canonical_json import CanonicalJsonError, require_unicode_scalar_text

MANIFEST_SCHEMA_FILENAME = "external-acquisition-manifest-v1.schema.json"
LOCK_SCHEMA_FILENAME = "external-acquisition-lock-v1.schema.json"


def acquisition_manifest_schema_path() -> Path:
    """Return the packaged external-acquisition manifest schema path."""
    return data_path() / "schemas" / MANIFEST_SCHEMA_FILENAME


def acquisition_lock_schema_path() -> Path:
    """Return the packaged external-acquisition lock schema path."""
    return data_path() / "schemas" / LOCK_SCHEMA_FILENAME


@lru_cache(maxsize=2)
def _schema(path: Path) -> dict[str, object]:
    schema = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    Draft202012Validator.check_schema(schema)
    return schema


def acquisition_manifest_schema() -> dict[str, object]:
    """Return an isolated copy of manifest schema version 1."""
    return deepcopy(_schema(acquisition_manifest_schema_path()))


def acquisition_lock_schema() -> dict[str, object]:
    """Return an isolated copy of lock schema version 1."""
    return deepcopy(_schema(acquisition_lock_schema_path()))


@lru_cache(maxsize=2)
def _validator(path: Path) -> Draft202012Validator:
    return Draft202012Validator(_schema(path))


def validate_acquisition_manifest_document(document: object) -> dict[str, object]:
    """Validate one exact built-in manifest document."""
    _require_plain_json(document, ())
    _require_exact_version(document)
    _validate(document, acquisition_manifest_schema_path())
    return cast(dict[str, object], document)


def validate_acquisition_lock_document(document: object) -> dict[str, object]:
    """Validate one exact built-in lock document."""
    _require_plain_json(document, ())
    _require_exact_version(document)
    _validate(document, acquisition_lock_schema_path())
    return cast(dict[str, object], document)


def _require_exact_version(document: object) -> None:
    if type(document) is not dict:
        return
    version = cast(dict[object, object], document).get("schema-version")
    if type(version) is not int or version != 1:
        raise AcquisitionContractError(
            "$.schema-version", "schema version must be the exact integer 1"
        )


def _validate(document: object, schema_path: Path) -> None:
    error = best_match(_validator(schema_path).iter_errors(document))
    if error is None:
        return
    parts = tuple(error.absolute_path)
    unexpected = _unexpected_property(error)
    if unexpected is not None:
        parts += (unexpected,)
    raise AcquisitionContractError(_json_path(parts), error.message)


def _unexpected_property(error: ValidationError) -> str | None:
    if error.validator != "additionalProperties" or type(error.instance) is not dict:
        return None
    properties = error.schema.get("properties", {})
    admitted = set(properties) if type(properties) is dict else set()
    names = [
        name for name in error.instance if type(name) is str and name not in admitted
    ]
    return min(names) if names else None


def _require_plain_json(
    value: object,
    parts: tuple[str | int, ...],
    active: set[int] | None = None,
) -> None:
    active = set() if active is None else active
    if type(value) is dict:
        _enter_container(value, parts, active)
        try:
            for key, item in cast(dict[object, object], value).items():
                if type(key) is not str:
                    raise AcquisitionContractError(
                        _json_path(parts), "object keys must be exact strings"
                    )
                _require_scalar_text(cast(str, key), parts)
                _require_plain_json(item, (*parts, cast(str, key)), active)
        finally:
            active.remove(id(value))
        return
    if type(value) is list:
        _enter_container(value, parts, active)
        try:
            for index, item in enumerate(cast(list[object], value)):
                _require_plain_json(item, (*parts, index), active)
        finally:
            active.remove(id(value))
        return
    if type(value) is str:
        _require_scalar_text(cast(str, value), parts)
        return
    if type(value) is int and abs(cast(int, value)) > 2**53 - 1:
        raise AcquisitionContractError(
            _json_path(parts), "integer is outside the interoperable range"
        )
    if type(value) is float and not math.isfinite(cast(float, value)):
        raise AcquisitionContractError(_json_path(parts), "number is not finite")
    if value is None or type(value) in {bool, int, float}:
        return
    raise AcquisitionContractError(
        _json_path(parts),
        f"value type {type(value).__name__} is not an exact JSON carrier",
    )


def _enter_container(
    value: object, parts: tuple[str | int, ...], active: set[int]
) -> None:
    identity = id(value)
    if identity in active:
        raise AcquisitionContractError(
            _json_path(parts), "cyclic JSON containers are not admitted"
        )
    active.add(identity)


def _require_scalar_text(value: str, parts: tuple[str | int, ...]) -> None:
    try:
        require_unicode_scalar_text(value)
    except CanonicalJsonError as exc:
        raise AcquisitionContractError(_json_path(parts), str(exc)) from exc


def _json_path(parts: tuple[object, ...]) -> str:
    result = "$"
    for part in parts:
        result += f"[{part}]" if type(part) is int else f".{part}"
    return result
