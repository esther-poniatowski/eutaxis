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


class EvaluatorFixtureError(Exception):
    """Base exception for evaluator-fixture source failures."""


class EvaluatorFixtureSchemaError(EvaluatorFixtureError):
    """Report a structural violation in an evaluator-fixture descriptor."""

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
            f"Invalid evaluator fixture in {path} at {location}{source}: {message}"
        )
        self.path = path
        self.location = location
        self.line = line
        self.column = column


class EvaluatorFixtureSemanticError(EvaluatorFixtureError):
    """Report a resolved-resource or typed-input fixture violation."""

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
            f"Invalid evaluator fixture semantics in {path} at {location}{source}: "
            f"{message}"
        )
        self.path = path
        self.location = location
        self.line = line
        self.column = column


class CheckerRunnerRegistryError(Exception):
    """Report an invalid code-owned checker runner binding."""

    def __init__(self, location: str, message: str) -> None:
        super().__init__(f"Invalid checker runner registry at {location}: {message}")
        self.location = location


class DetectorRunnerRegistryError(Exception):
    """Report an invalid code-owned detector runner binding."""

    def __init__(self, location: str, message: str) -> None:
        super().__init__(f"Invalid detector runner registry at {location}: {message}")
        self.location = location


class CheckerExecutionError(Exception):
    """Report an invalid checker invocation, fixture binding, or result."""

    def __init__(
        self,
        location: str,
        message: str,
        *,
        document_path: tuple[str | int, ...] | None = None,
        path: Path | None = None,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        source_path = f" in {path}" if path is not None else ""
        source = f" (line {line}, column {column})" if line and column else ""
        super().__init__(
            f"Invalid checker execution{source_path} at {location}{source}: {message}"
        )
        self.path = path
        self.location = location
        self.document_path = document_path
        self.detail = message
        self.line = line
        self.column = column


class DetectorExecutionError(Exception):
    """Report an invalid detector invocation or returned result."""

    def __init__(
        self,
        location: str,
        message: str,
        *,
        document_path: tuple[str | int, ...] | None = None,
        path: Path | None = None,
    ) -> None:
        source_path = f" in {path}" if path is not None else ""
        super().__init__(
            f"Invalid detector execution{source_path} at {location}: {message}"
        )
        self.path = path
        self.location = location
        self.document_path = document_path
        self.detail = message


class AttentionPlanningError(Exception):
    """Report a failed attention requirement or packet planning boundary."""

    def __init__(self, location: str, message: str) -> None:
        super().__init__(f"Invalid attention plan at {location}: {message}")
        self.location = location
        self.detail = message


class ProcedureRunPlanningError(Exception):
    """Report a failed procedure-run preflight boundary."""

    def __init__(self, location: str, message: str) -> None:
        super().__init__(f"Invalid procedure run plan at {location}: {message}")
        self.location = location
        self.detail = message


class ProcedureEvaluationPlanningError(Exception):
    """Report a failed run-scoped evaluator-input planning boundary."""

    def __init__(self, location: str, message: str) -> None:
        super().__init__(f"Invalid procedure evaluation plan at {location}: {message}")
        self.location = location
        self.detail = message


class ObservationProviderRegistryError(Exception):
    """Report an invalid code-owned observation provider binding."""

    def __init__(self, location: str, message: str) -> None:
        super().__init__(
            f"Invalid observation provider registry at {location}: {message}"
        )
        self.location = location
        self.detail = message


class ProcedureObservationError(Exception):
    """Report a failed procedure-boundary observation."""

    def __init__(self, location: str, message: str) -> None:
        super().__init__(f"Invalid procedure observation at {location}: {message}")
        self.location = location
        self.detail = message


class OperationRunnerRegistryError(Exception):
    """Report an invalid code-owned operation runner binding."""

    def __init__(self, location: str, message: str) -> None:
        super().__init__(f"Invalid operation runner registry at {location}: {message}")
        self.location = location


class OperationExecutionError(Exception):
    """Report an invalid operation invocation or returned result."""

    def __init__(self, location: str, message: str) -> None:
        super().__init__(f"Invalid operation execution at {location}: {message}")
        self.location = location
        self.detail = message


class CompositionError(Exception):
    """Report a deterministic composition-plan failure."""

    def __init__(
        self,
        location: str,
        message: str,
        *,
        path: Path | None = None,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        source_path = f" in {path}" if path is not None else ""
        source = f" (line {line}, column {column})" if line and column else ""
        super().__init__(
            f"Invalid composition plan{source_path} at {location}{source}: {message}"
        )
        self.path = path
        self.location = location
        self.detail = message
        self.line = line
        self.column = column


class DeclarationCatalogError(Exception):
    """Report a static catalog construction or serialization failure."""


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
