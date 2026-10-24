"""Evaluate declaration corpora through the public source boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, cast

from .exceptions import (
    DeclarationRegistryError,
    DeclarationSchemaError,
    DeclarationSemanticError,
    FacetRegistrySchemaError,
    FacetRegistrySemanticError,
)
from .facets import load_facet_registry
from .models import JsonValue, VersionedReference
from .registry import DeclarationRegistry, load_declaration_registry
from .results import CheckerResult, EvaluationState
from .runners import CheckerRunnerBinding

DECLARATION_REGISTRY_EVALUATOR = VersionedReference("eutaxis/declaration-registry", 1)
LOAD_DECLARATION_REGISTRY_OPERATION = VersionedReference(
    "eutaxis/load-declaration-registry", 1
)
DECLARATION_REGISTRY_INPUT_REVISION = "declaration-v1"

_SOURCE_ERROR_CLASSES = (
    (DeclarationSchemaError, "declaration-schema"),
    (DeclarationSemanticError, "declaration-semantic"),
    (DeclarationRegistryError, "declaration-registry"),
    (FacetRegistrySchemaError, "facet-registry-schema"),
    (FacetRegistrySemanticError, "facet-registry-semantic"),
)
_SOURCE_ERROR_TYPES = tuple(error_type for error_type, _ in _SOURCE_ERROR_CLASSES)
_SourceError = (
    DeclarationSchemaError
    | DeclarationSemanticError
    | DeclarationRegistryError
    | FacetRegistrySchemaError
    | FacetRegistrySemanticError
)


def declaration_registry_checker(
    input_data: Mapping[str, JsonValue], /
) -> CheckerResult:
    """Load one declaration corpus and return its declared evaluation result.

    The checker assumes that the runner registry has already validated the input
    against the exact operation schema. Source-boundary failures are violations;
    all other exceptions are blocked internal evaluations.
    """
    try:
        try:
            sources = tuple(
                Path(cast(str, source))
                for source in cast(tuple[JsonValue, ...], input_data["sources"])
            )
            facet_path = Path(cast(str, input_data["facet-registry"]))
            facets = load_facet_registry(facet_path)
            registry = load_declaration_registry(sources, facets)
        except _SOURCE_ERROR_TYPES as exc:
            return _source_failure_result(cast(_SourceError, exc))
        return _valid_result(registry)
    except Exception as exc:
        return _blocked_result(exc)


def declaration_registry_checker_binding() -> CheckerRunnerBinding:
    """Return the reviewed exact binding for the shipped registry checker."""
    return CheckerRunnerBinding(
        evaluator=DECLARATION_REGISTRY_EVALUATOR,
        operation=LOAD_DECLARATION_REGISTRY_OPERATION,
        runner=declaration_registry_checker,
    )


def _valid_result(registry: DeclarationRegistry) -> CheckerResult:
    """Build satisfied evidence from the complete immutable registry."""
    record_count = len(registry.records) + sum(
        len(family.versions) for family in registry.families.values()
    )
    return CheckerResult(
        evaluator=DECLARATION_REGISTRY_EVALUATOR,
        input_revision=DECLARATION_REGISTRY_INPUT_REVISION,
        state=EvaluationState.SATISFIED,
        evidence={
            "outcome": "valid",
            "record-count": record_count,
            "family-count": len(registry.families),
            "conflict-count": len(registry.conflicts),
        },
    )


def _source_failure_result(error: _SourceError) -> CheckerResult:
    """Map one public source error to closed violated evidence."""
    evidence: dict[str, JsonValue] = {
        "outcome": "invalid",
        "error-class": _source_error_class(error),
        "source": str(error.path),
        "location": error.location,
        "message": str(error),
    }
    if error.line is not None:
        evidence["line"] = error.line
    if error.column is not None:
        evidence["column"] = error.column
    return CheckerResult(
        evaluator=DECLARATION_REGISTRY_EVALUATOR,
        input_revision=DECLARATION_REGISTRY_INPUT_REVISION,
        state=EvaluationState.VIOLATED,
        evidence=evidence,
    )


def _source_error_class(error: _SourceError) -> str:
    """Return the declared category inherited by one public source error."""
    for error_type, error_class in _SOURCE_ERROR_CLASSES:
        if isinstance(error, error_type):
            return error_class
    raise TypeError(f"unsupported source error {type(error).__name__}")


def _blocked_result(error: Exception) -> CheckerResult:
    """Map an undeclared internal exception to blocked evidence."""
    return CheckerResult(
        evaluator=DECLARATION_REGISTRY_EVALUATOR,
        input_revision=DECLARATION_REGISTRY_INPUT_REVISION,
        state=EvaluationState.BLOCKED,
        evidence={
            "outcome": "blocked",
            "internal-exception-class": type(error).__name__,
            "message": _safe_exception_message(error),
        },
    )


def _safe_exception_message(error: Exception) -> str:
    """Render one internal exception without reopening the blocked boundary."""
    try:
        return str(error)
    except Exception as formatting_error:
        return (
            f"{type(error).__name__} message unavailable; formatting raised "
            f"{type(formatting_error).__name__}"
        )
