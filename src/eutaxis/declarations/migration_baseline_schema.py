"""Load and apply the packaged migration-baseline schema."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import NoReturn, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import ValidationError, best_match  # type: ignore[import-untyped]

from .. import data_path
from .exceptions import MigrationBaselineError
from .source import DocumentPath, SourceMap, format_document_path, nearest_location

MIGRATION_BASELINE_SCHEMA_FILENAME = "migration-baseline-v1.schema.json"


def migration_baseline_schema_path() -> Path:
    """Return the packaged version 1 migration-baseline schema path."""
    return data_path() / "schemas" / MIGRATION_BASELINE_SCHEMA_FILENAME


@lru_cache(maxsize=1)
def _schema() -> dict[str, object]:
    schema = cast(
        dict[str, object],
        json.loads(migration_baseline_schema_path().read_text(encoding="utf-8")),
    )
    Draft202012Validator.check_schema(schema)
    return schema


def migration_baseline_schema() -> dict[str, object]:
    """Return an isolated copy of the version 1 source schema."""
    return deepcopy(_schema())


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema())


def validate_migration_baseline_document(
    document: object,
    *,
    path: Path,
    locations: SourceMap,
) -> Mapping[str, object]:
    """Validate one closed migration-baseline source document."""
    error = best_match(list(_validator().iter_errors(document)))
    if error is not None:
        parts = tuple(error.absolute_path)
        unexpected = _unexpected_property(error, parts, locations)
        if unexpected is not None:
            parts += (unexpected,)
        _fail(path, parts, error.message, locations)
    return cast(Mapping[str, object], document)


def _unexpected_property(
    error: ValidationError,
    parts: DocumentPath,
    locations: SourceMap,
) -> str | None:
    if error.validator != "additionalProperties" or not isinstance(
        error.instance, Mapping
    ):
        return None
    properties = error.schema.get("properties", {})
    admitted = set(properties) if isinstance(properties, Mapping) else set()
    names = [
        name
        for name in error.instance
        if isinstance(name, str) and name not in admitted
    ]
    if not names:
        return None

    def source_order(name: str) -> tuple[int, str]:
        location = locations.get(parts + (name,))
        return (location.line if location is not None else 2**31, name)

    return min(names, key=source_order)


def _fail(
    path: Path,
    parts: DocumentPath,
    message: str,
    locations: SourceMap,
) -> NoReturn:
    source = nearest_location(locations, parts)
    raise MigrationBaselineError(
        path,
        format_document_path(parts),
        message,
        line=source.line if source else None,
        column=source.column if source else None,
    )
