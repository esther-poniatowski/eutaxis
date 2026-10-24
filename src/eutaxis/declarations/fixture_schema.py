"""Load and apply the packaged evaluator-fixture schema."""

from __future__ import annotations

import json
from collections.abc import Iterable
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Mapping, NoReturn, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import (  # type: ignore[import-untyped]
    ValidationError,
    best_match,
)

from .. import data_path
from .exceptions import EvaluatorFixtureSchemaError
from .source import DocumentPath, SourceMap, format_document_path, nearest_location

FIXTURE_SCHEMA_FILENAME = "evaluator-fixture-v1.schema.json"


def evaluator_fixture_schema_path() -> Path:
    """Return the packaged path of evaluator-fixture schema version 1."""
    return data_path() / "schemas" / FIXTURE_SCHEMA_FILENAME


@lru_cache(maxsize=1)
def _fixture_schema() -> dict[str, object]:
    """Load and meta-validate the private fixture schema."""
    schema = cast(
        dict[str, object],
        json.loads(evaluator_fixture_schema_path().read_text(encoding="utf-8")),
    )
    Draft202012Validator.check_schema(schema)
    return schema


def evaluator_fixture_schema() -> dict[str, object]:
    """Return an isolated copy of evaluator-fixture schema version 1."""
    return deepcopy(_fixture_schema())


@lru_cache(maxsize=1)
def _fixture_validator() -> Draft202012Validator:
    """Return the validator for version 1 fixture descriptors."""
    return Draft202012Validator(_fixture_schema())


def validate_evaluator_fixture_document(
    document: object,
    *,
    path: Path,
    locations: SourceMap | None = None,
) -> Mapping[str, object]:
    """Validate one evaluator-fixture descriptor mapping."""
    source_map = locations or {}
    error = _actionable_schema_error(_fixture_validator().iter_errors(document))
    if error is not None:
        parts = tuple(error.absolute_path)
        unexpected = _unexpected_property(error, parts, source_map)
        if unexpected is not None:
            parts += (unexpected,)
        _raise_fixture_schema_error(path, parts, error.message, source_map)
    return cast(Mapping[str, object], document)


def _actionable_schema_error(
    errors: Iterable[ValidationError],
) -> ValidationError | None:
    """Select the deepest concrete schema failure."""
    return best_match(list(errors))


def _unexpected_property(
    error: ValidationError,
    parts: DocumentPath,
    locations: SourceMap,
) -> str | None:
    """Return the first unexpected property in source order."""
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

    def source_order(name: str) -> tuple[int, int, str]:
        location = locations.get(parts + (name,))
        if location is None:
            return (2**31, 2**31, name)
        return (location.line, location.column, name)

    return min(names, key=source_order)


def _raise_fixture_schema_error(
    path: Path,
    parts: DocumentPath,
    message: str,
    locations: SourceMap,
) -> NoReturn:
    """Raise one fixture schema error at its closest source position."""
    source = nearest_location(locations, parts)
    raise EvaluatorFixtureSchemaError(
        path,
        format_document_path(parts),
        message,
        line=source.line if source else None,
        column=source.column if source else None,
    )
