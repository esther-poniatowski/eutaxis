"""Load and apply the packaged normative declaration schema."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Mapping, NoReturn, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError, best_match  # type: ignore[import-untyped]

from .. import data_path
from .exceptions import DeclarationSchemaError
from .source import (
    DocumentPath,
    SourceMap,
    format_document_path,
    nearest_location,
)

SCHEMA_FILENAME = "declaration-v1.schema.json"
DECLARATION_KINDS = frozenset(
    {
        "rule-set",
        "rule",
        "procedure",
        "resolution-policy",
        "composition-manifest",
        "evaluator",
        "operation",
    }
)
_UNEXPECTED_PROPERTY = re.compile(r"\('([^']+)' was unexpected\)")


def schema_path() -> Path:
    """Return the packaged path of declaration schema version 1."""
    return data_path() / "schemas" / SCHEMA_FILENAME


@lru_cache(maxsize=1)
def _declaration_schema() -> dict[str, object]:
    """Load and meta-validate the private schema used by validators."""
    schema = cast(
        dict[str, object], json.loads(schema_path().read_text(encoding="utf-8"))
    )
    Draft202012Validator.check_schema(schema)
    return schema


def declaration_schema() -> dict[str, object]:
    """Return an isolated copy of declaration schema version 1."""
    return deepcopy(_declaration_schema())


@lru_cache(maxsize=7)
def _validator_for_kind(kind: str) -> Draft202012Validator:
    """Return a discriminator-specific validator retaining shared definitions."""
    root = _declaration_schema()
    schema = {
        "$schema": root["$schema"],
        "$defs": root["$defs"],
        "$ref": f"#/$defs/{kind}",
    }
    return Draft202012Validator(schema)


def validate_document(
    document: object,
    *,
    path: Path,
    locations: SourceMap | None = None,
) -> Mapping[str, object]:
    """Validate ``document`` and return its mapping representation.

    Raises
    ------
    DeclarationSchemaError
        If the document violates the normative JSON Schema.
    """
    source_map = locations or {}
    if not isinstance(document, dict):
        _raise_schema_error(path, (), "declaration must be a mapping", source_map)
    kind = document.get("kind")
    if not isinstance(kind, str) or kind not in DECLARATION_KINDS:
        _raise_schema_error(
            path,
            ("kind",),
            f"kind must be one of {sorted(DECLARATION_KINDS)!r}",
            source_map,
        )

    error = best_match(_validator_for_kind(kind).iter_errors(document))
    if error is not None:
        parts = tuple(error.absolute_path)
        unexpected = _UNEXPECTED_PROPERTY.search(error.message)
        if unexpected is not None:
            parts += (unexpected.group(1),)
        _raise_schema_error(path, parts, error.message, source_map)
    return cast(Mapping[str, object], document)


def validate_embedded_schema(
    schema: object,
    *,
    path: Path,
    document_path: DocumentPath,
    locations: SourceMap,
) -> None:
    """Meta-validate one embedded Draft 2020-12 JSON Schema."""
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        parts = document_path + tuple(exc.path)
        _raise_schema_error(
            path, parts, f"invalid embedded JSON Schema: {exc.message}", locations
        )


def _raise_schema_error(
    path: Path,
    parts: DocumentPath,
    message: str,
    locations: SourceMap,
) -> NoReturn:
    """Raise a schema error at the closest known source position."""
    source = nearest_location(locations, parts)
    raise DeclarationSchemaError(
        path,
        format_document_path(parts),
        message,
        line=source.line if source else None,
        column=source.column if source else None,
    )
