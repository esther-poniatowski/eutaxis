"""Execute the packaged declaration-registry loading operation."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, cast

from .exceptions import DeclarationError, FacetRegistryError
from .facets import load_facet_registry
from .models import JsonValue
from .operations import (
    OperationFailure,
    OperationResult,
    OperationRunnerBinding,
    OperationSuccess,
)
from .registry import load_declaration_registry
from .registry_checker import LOAD_DECLARATION_REGISTRY_OPERATION


def load_declaration_registry_operation(
    input_data: Mapping[str, JsonValue], /
) -> OperationResult:
    """Load one registry and project the declared operation outputs."""
    sources = tuple(
        Path(cast(str, source))
        for source in cast(tuple[JsonValue, ...], input_data["sources"])
    )
    facet_path = Path(cast(str, input_data["facet-registry"]))
    try:
        registry = load_declaration_registry(sources, load_facet_registry(facet_path))
    except (DeclarationError, FacetRegistryError):
        return OperationFailure(
            operation=LOAD_DECLARATION_REGISTRY_OPERATION,
            outcome="invalid-registry",
        )
    record_count = len(registry.records) + sum(
        len(family.versions) for family in registry.families.values()
    )
    return OperationSuccess(
        operation=LOAD_DECLARATION_REGISTRY_OPERATION,
        outputs={
            "registry.valid": True,
            "record-count": record_count,
            "family-count": len(registry.families),
            "conflict-count": len(registry.conflicts),
        },
    )


def load_declaration_registry_operation_binding() -> OperationRunnerBinding:
    """Return the reviewed binding for the packaged registry operation."""
    return OperationRunnerBinding(
        operation=LOAD_DECLARATION_REGISTRY_OPERATION,
        runner=load_declaration_registry_operation,
    )
