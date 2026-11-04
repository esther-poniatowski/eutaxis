"""Load and apply the packaged static catalog-index schema."""

from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Mapping, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import best_match  # type: ignore[import-untyped]

from .. import data_path
from .exceptions import DeclarationCatalogError

CATALOG_INDEX_SCHEMA_FILENAME = "catalog-index-v2.schema.json"
_CATALOG_INDEX_SCHEMA_FILENAMES = {
    1: "catalog-index-v1.schema.json",
    2: CATALOG_INDEX_SCHEMA_FILENAME,
}


def catalog_index_schema_path() -> Path:
    """Return the packaged path of the current static catalog-index schema."""
    return data_path() / "schemas" / CATALOG_INDEX_SCHEMA_FILENAME


@lru_cache(maxsize=2)
def _catalog_index_schema(revision: int) -> dict[str, object]:
    """Load and meta-validate one private catalog-index schema."""
    filename = _CATALOG_INDEX_SCHEMA_FILENAMES.get(revision)
    if filename is None:
        raise DeclarationCatalogError(f"unsupported index revision {revision!r}")
    schema = cast(
        dict[str, object],
        json.loads((data_path() / "schemas" / filename).read_text(encoding="utf-8")),
    )
    Draft202012Validator.check_schema(schema)
    return schema


def catalog_index_schema() -> dict[str, object]:
    """Return an isolated copy of the current static catalog-index schema."""
    return deepcopy(_catalog_index_schema(2))


@lru_cache(maxsize=2)
def _catalog_index_validator(revision: int) -> Draft202012Validator:
    """Return the shared validator for one emitted or loaded index revision."""
    return Draft202012Validator(_catalog_index_schema(revision))


def validate_catalog_index_payload(
    payload: object,
    *,
    source: Path | None = None,
) -> Mapping[str, object]:
    """Validate one index payload and return its mapping representation."""
    revision = payload.get("index-revision") if isinstance(payload, Mapping) else None
    if type(revision) is not int or revision not in _CATALOG_INDEX_SCHEMA_FILENAMES:
        raise DeclarationCatalogError(f"unsupported index revision {revision!r}")
    error = best_match(_catalog_index_validator(revision).iter_errors(payload))
    if error is not None:
        location = _json_path(tuple(error.absolute_path))
        source_text = f" in {source}" if source is not None else ""
        raise DeclarationCatalogError(
            f"Invalid catalog index{source_text} at {location}: {error.message}"
        )
    return cast(Mapping[str, object], payload)


def _json_path(parts: tuple[object, ...]) -> str:
    """Format a JSON path for one schema diagnostic."""
    result = "$"
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += f".{part}"
    return result
