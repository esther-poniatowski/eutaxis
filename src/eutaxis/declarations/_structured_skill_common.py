"""Share authenticated planning boundaries across structured Skill kinds."""

from __future__ import annotations

from typing import NoReturn, cast

from ..names import is_portable_skill_name
from .catalog import (
    DeclarationCatalog,
    _CatalogAuthorityState,
    _issued_catalog_state,
)
from .exceptions import CompositionError
from .external_resolution import (
    ExternalResolutionResult,
    _ExternalResolutionState,
    _issued_external_resolution_state,
)
from .models import CompositionManifestDeclaration, CompositionMechanism
from .registry import RegisteredDeclaration
from .source import DocumentPath, format_document_path, nearest_location

_MAX_DESCRIPTION_CHARACTERS = 1024


def require_manifest(record: RegisteredDeclaration) -> CompositionManifestDeclaration:
    """Return one valid separate-directory manifest."""
    declaration = record.declaration
    if not isinstance(declaration, CompositionManifestDeclaration):
        record_error(record, (), "resolved root is not a composition manifest")
    manifest = cast(CompositionManifestDeclaration, declaration)
    if manifest.mechanism is not CompositionMechanism.SEPARATE_DIRECTORY:
        record_error(
            record,
            ("mechanism",),
            f"manifest mechanism {manifest.mechanism.value!r} is not separate-directory",
        )
    if not is_portable_skill_name(manifest.target):
        record_error(
            record,
            ("target",),
            "Skill name is not one portable segment of at most 64 UTF-8 bytes",
        )
    return manifest


def is_one_line_description(value: str) -> bool:
    """Return whether one description satisfies the shared host contract."""
    return (
        bool(value.strip())
        and value == value.strip()
        and value.splitlines(keepends=True) == [value]
        and len(value) <= _MAX_DESCRIPTION_CHARACTERS
    )


def raise_changed_catalog(
    catalog: DeclarationCatalog,
    expected: _CatalogAuthorityState,
    error: BaseException,
) -> None:
    """Give temporary catalog corruption precedence over a planning failure."""
    try:
        current = _issued_catalog_state(catalog)
    except BaseException as authority_error:
        raise authority_error from error
    if current is not expected:
        raise CompositionError(
            "$", "declaration catalog authority state changed"
        ) from error


def require_same_resolution_owner(
    resolution: ExternalResolutionResult,
    expected: _ExternalResolutionState,
) -> None:
    """Require one resolution to retain its exact issued state."""
    if _issued_external_resolution_state(resolution) is not expected:
        raise CompositionError("$", "external resolution authority state changed")


def require_same_inputs(
    resolution: ExternalResolutionResult,
    resolution_state: _ExternalResolutionState,
    catalog: DeclarationCatalog,
    catalog_state: _CatalogAuthorityState,
) -> None:
    """Authenticate one planner's resolution and catalog correlation."""
    if _issued_external_resolution_state(resolution) is not resolution_state:
        raise CompositionError("$", "external resolution authority state changed")
    if _issued_catalog_state(catalog) is not catalog_state:
        raise CompositionError("$", "declaration catalog authority state changed")
    if (
        catalog_state.result is not resolution_state.acquisition
        or catalog_state.result_state is not resolution_state.acquisition_state
    ):
        raise CompositionError("$", "catalog belongs to another acquisition")


def record_error(
    record: RegisteredDeclaration,
    parts: DocumentPath,
    message: str,
) -> NoReturn:
    """Raise a composition error at one declaration-owned source field."""
    path = record.root + parts
    source = nearest_location(record.source.locations, path)
    raise CompositionError(
        format_document_path(path),
        message,
        path=record.source.path,
        line=source.line if source else None,
        column=source.column if source else None,
    )
