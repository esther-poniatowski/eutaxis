"""Exceptions raised while loading structured declarations."""

from __future__ import annotations

from pathlib import Path


class DeclarationError(Exception):
    """Base exception for structured-declaration failures."""


class DeclarationSchemaError(DeclarationError):
    """Report a JSON Schema violation at its declaration path."""

    def __init__(
        self,
        path: Path,
        location: str,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        source = f" (line {line}, column {column})" if line and column else ""
        super().__init__(
            f"Invalid declaration in {path} at {location}{source}: {message}"
        )
        self.path = path
        self.location = location
        self.line = line
        self.column = column


class DeclarationSemanticError(DeclarationError):
    """Report a cross-field invariant that JSON Schema cannot express."""

    def __init__(
        self,
        path: Path,
        location: str,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        source = f" (line {line}, column {column})" if line and column else ""
        super().__init__(
            f"Invalid declaration semantics in {path} at {location}{source}: {message}"
        )
        self.path = path
        self.location = location
        self.line = line
        self.column = column


class DeclarationRegistryError(DeclarationError):
    """Report a cross-record contract violation at its declaring source."""

    def __init__(
        self,
        path: Path,
        location: str,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        source = f" (line {line}, column {column})" if line and column else ""
        super().__init__(
            f"Invalid declaration registry in {path} at {location}{source}: {message}"
        )
        self.path = path
        self.location = location
        self.line = line
        self.column = column


class FacetRegistryError(Exception):
    """Base exception for context-facet registry failures."""


class FacetRegistrySchemaError(FacetRegistryError):
    """Report a structural violation in a context-facet registry."""

    def __init__(
        self,
        path: Path,
        location: str,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        source = f" (line {line}, column {column})" if line and column else ""
        super().__init__(
            f"Invalid facet registry in {path} at {location}{source}: {message}"
        )
        self.path = path
        self.location = location
        self.line = line
        self.column = column


class FacetRegistrySemanticError(FacetRegistryError):
    """Report a semantic violation in a context-facet registry."""

    def __init__(
        self,
        path: Path,
        location: str,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        source = f" (line {line}, column {column})" if line and column else ""
        super().__init__(
            f"Invalid facet registry semantics in {path} at {location}{source}: "
            f"{message}"
        )
        self.path = path
        self.location = location
        self.line = line
        self.column = column


class FacetContextError(FacetRegistryError):
    """Report an unknown or invalid value in a runtime context."""

    def __init__(self, facet: str, message: str) -> None:
        super().__init__(f"Invalid context facet {facet!r}: {message}")
        self.facet = facet
