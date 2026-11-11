"""Render declaration-corpus validation outcomes as deterministic SARIF."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping
from urllib.parse import quote

from .exceptions import (
    AcquisitionContractError,
    ByteCarrierError,
    DeclarationRegistryError,
    DeclarationSchemaError,
    DeclarationSemanticError,
    FacetRegistryError,
    FacetRegistrySchemaError,
    FacetRegistrySemanticError,
)

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"

_RULES: Mapping[type[BaseException], tuple[str, str]] = {
    DeclarationSchemaError: (
        "eutaxis.declarations.schema",
        "Declaration schema violation",
    ),
    DeclarationSemanticError: (
        "eutaxis.declarations.semantic",
        "Declaration semantic violation",
    ),
    DeclarationRegistryError: (
        "eutaxis.declarations.registry",
        "Declaration registry violation",
    ),
    FacetRegistrySchemaError: (
        "eutaxis.facets.schema",
        "Context-facet schema violation",
    ),
    FacetRegistrySemanticError: (
        "eutaxis.facets.semantic",
        "Context-facet semantic violation",
    ),
    FacetRegistryError: (
        "eutaxis.facets.context",
        "Context-facet violation",
    ),
    AcquisitionContractError: (
        "eutaxis.acquisition.contract",
        "Acquisition contract violation",
    ),
    ByteCarrierError: (
        "eutaxis.acquisition.io",
        "Acquisition source unavailable",
    ),
    OSError: ("eutaxis.execution.io", "Declaration check I/O failure"),
}

_INTERNAL_RULE = (
    "eutaxis.execution.internal",
    "Declaration check internal failure",
)


def declaration_check_sarif(
    *errors: BaseException,
    execution_successful: bool = True,
) -> bytes:
    """Return one complete SARIF 2.1.0 log for a corpus-check outcome."""
    rules: list[dict[str, object]] = []
    results: list[dict[str, object]] = []
    rule_indices: dict[str, int] = {}
    for error in errors:
        rule_id, rule_name = _rule_for(error)
        rule_index = rule_indices.get(rule_id)
        if rule_index is None:
            rule_index = len(rules)
            rule_indices[rule_id] = rule_index
            rules.append(
                {
                    "id": rule_id,
                    "shortDescription": {"text": rule_name},
                }
            )
        results.append(_result(error, rule_id, rule_index))

    document = {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Eutaxis",
                        "rules": rules,
                    }
                },
                "invocations": [
                    {
                        "executionSuccessful": execution_successful,
                    }
                ],
                "results": results,
            }
        ],
    }
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _rule_for(error: BaseException) -> tuple[str, str]:
    """Return the most specific stable SARIF rule for one failure."""
    for error_type, rule in _RULES.items():
        if isinstance(error, error_type):
            return rule
    return _INTERNAL_RULE


def _result(
    error: BaseException,
    rule_id: str,
    rule_index: int,
) -> dict[str, object]:
    """Map one located failure to one SARIF result."""
    result: dict[str, object] = {
        "level": "error",
        "message": {"text": str(error)},
        "ruleId": rule_id,
        "ruleIndex": rule_index,
    }
    location = _location(error)
    if location is not None:
        result["locations"] = [location]
    return result


def _location(error: BaseException) -> dict[str, object] | None:
    """Return the physical and logical source information carried by ``error``."""
    path = getattr(error, "path", None)
    document_location = getattr(error, "location", None)
    line = getattr(error, "line", None)
    column = getattr(error, "column", None)
    if path is None and document_location is None:
        return None

    location: dict[str, object] = {}
    if path is not None:
        physical: dict[str, object] = {
            "artifactLocation": {"uri": _path_uri(path)},
        }
        region: dict[str, int] = {}
        if isinstance(line, int) and not isinstance(line, bool) and line > 0:
            region["startLine"] = line
        if isinstance(column, int) and not isinstance(column, bool) and column > 0:
            region["startColumn"] = column
        if region:
            physical["region"] = region
        location["physicalLocation"] = physical
    if isinstance(document_location, str) and document_location:
        location["logicalLocations"] = [{"name": document_location}]
    return location


def _path_uri(path: object) -> str:
    """Encode an absolute or relative source path as a SARIF URI reference."""
    source = Path(path) if isinstance(path, (str, Path)) else Path(str(path))
    if source.is_absolute():
        return source.as_uri()
    return quote(source.as_posix(), safe="/")
