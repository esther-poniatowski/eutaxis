"""Build the combined registry from one authenticated external stage."""

from __future__ import annotations

from .external_acquisition import _issued_external_stage_state
from .registry import (
    DeclarationRegistry,
    _build_declaration_registry_from_sources,
)


def _build_external_declaration_registry(stage: object) -> DeclarationRegistry:
    """Build one registry from the exact sources and facets retained by a stage."""
    state = _issued_external_stage_state(stage)
    try:
        registry = _build_declaration_registry_from_sources(
            state.declarations,
            state.composite,
        )
    except BaseException as primary_error:
        try:
            _issued_external_stage_state(stage)
        except BaseException as authority_error:
            authority_error.__cause__ = primary_error
            raise authority_error
        raise
    final_state = _issued_external_stage_state(stage)
    if final_state is not state:
        raise AssertionError("external acquisition stage state changed")
    if registry.facet_registry is not state.composite:
        raise AssertionError("combined registry changed the retained facet registry")
    return registry
