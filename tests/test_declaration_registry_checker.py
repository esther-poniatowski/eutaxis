"""Contract tests for the code-owned declaration-registry checker."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Protocol, cast

import pytest

import eutaxis.declarations.registry_checker as checker_module
from eutaxis.declarations import (
    DECLARATION_REGISTRY_EVALUATOR,
    DECLARATION_REGISTRY_INPUT_REVISION,
    LOAD_DECLARATION_REGISTRY_OPERATION,
    DeclarationRegistry,
    DeclarationRegistryError,
    DeclarationSchemaError,
    DeclarationSemanticError,
    EvaluationState,
    FacetRegistrySchemaError,
    FacetRegistrySemanticError,
    declaration_registry_checker,
    declaration_registry_checker_binding,
)
from eutaxis.declarations.models import JsonValue

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY_FIXTURES = FIXTURES / "registry" / "valid"
FACET_FIXTURE = FIXTURES / "facets" / "valid" / "context-facets.yaml"

_SourceError = (
    DeclarationSchemaError
    | DeclarationSemanticError
    | DeclarationRegistryError
    | FacetRegistrySchemaError
    | FacetRegistrySemanticError
)


class _SourceErrorFactory(Protocol):
    """Construct one public located source error for a mapping test."""

    def __call__(
        self,
        path: Path,
        location: str,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
    ) -> _SourceError: ...


def _valid_input() -> Mapping[str, JsonValue]:
    """Return one complete checker input over the registry fixture corpus."""
    return {
        "sources": tuple(str(path) for path in REGISTRY_FIXTURES.glob("*.yaml")),
        "facet-registry": str(FACET_FIXTURE),
    }


def test_valid_corpus_returns_complete_registry_counts() -> None:
    result = declaration_registry_checker(_valid_input())

    assert result.evaluator == DECLARATION_REGISTRY_EVALUATOR
    assert result.input_revision == DECLARATION_REGISTRY_INPUT_REVISION
    assert result.state is EvaluationState.SATISFIED
    assert result.evidence == {
        "outcome": "valid",
        "record-count": 10,
        "family-count": 2,
        "conflict-count": 1,
    }


@pytest.mark.parametrize(
    ("error_type", "error_class", "loader_name"),
    [
        (DeclarationSchemaError, "declaration-schema", "declarations"),
        (DeclarationSemanticError, "declaration-semantic", "declarations"),
        (DeclarationRegistryError, "declaration-registry", "declarations"),
        (FacetRegistrySchemaError, "facet-registry-schema", "facets"),
        (FacetRegistrySemanticError, "facet-registry-semantic", "facets"),
    ],
)
def test_public_source_errors_return_located_violations(
    monkeypatch: pytest.MonkeyPatch,
    error_type: _SourceErrorFactory,
    error_class: str,
    loader_name: str,
) -> None:
    source = Path("broken.yaml")
    error = error_type(source, "$.broken", "planted", line=3, column=7)

    def fail(*args: object, **kwargs: object) -> object:
        raise error

    if loader_name == "facets":
        monkeypatch.setattr(checker_module, "load_facet_registry", fail)
    else:
        monkeypatch.setattr(checker_module, "load_declaration_registry", fail)

    result = declaration_registry_checker(_valid_input())

    assert result.state is EvaluationState.VIOLATED
    assert result.evidence == {
        "outcome": "invalid",
        "error-class": error_class,
        "source": str(source),
        "location": "$.broken",
        "message": str(error),
        "line": 3,
        "column": 7,
    }


def test_public_source_error_subclass_inherits_declared_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SpecializedRegistryError(DeclarationRegistryError):
        """Represent a future specialized registry diagnostic."""

    error = SpecializedRegistryError(Path("broken.yaml"), "$.target", "planted")

    def fail(*args: object, **kwargs: object) -> object:
        raise error

    monkeypatch.setattr(checker_module, "load_declaration_registry", fail)
    result = declaration_registry_checker(_valid_input())

    assert result.state is EvaluationState.VIOLATED
    assert result.evidence["error-class"] == "declaration-registry"


def test_undeclared_exception_returns_blocked_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(path: Path) -> object:
        raise RuntimeError("planted internal failure")

    monkeypatch.setattr(checker_module, "load_facet_registry", fail)
    result = declaration_registry_checker(_valid_input())

    assert result.state is EvaluationState.BLOCKED
    assert result.evidence == {
        "outcome": "blocked",
        "internal-exception-class": "RuntimeError",
        "message": "planted internal failure",
    }


def test_result_construction_exception_returns_blocked_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenRecords:
        """Fail when successful evidence requests the record count."""

        def __len__(self) -> int:
            raise RuntimeError("planted count failure")

    class BrokenRegistry:
        """Expose the first registry field used by successful evidence."""

        records = BrokenRecords()

    monkeypatch.setattr(
        checker_module,
        "load_declaration_registry",
        lambda *args, **kwargs: cast(DeclarationRegistry, BrokenRegistry()),
    )
    result = declaration_registry_checker(_valid_input())

    assert result.state is EvaluationState.BLOCKED
    assert result.evidence == {
        "outcome": "blocked",
        "internal-exception-class": "RuntimeError",
        "message": "planted count failure",
    }


def test_exception_with_broken_string_form_still_returns_blocked_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenMessageError(RuntimeError):
        """Raise when the blocked path requests the diagnostic message."""

        def __str__(self) -> str:
            raise ValueError("planted formatting failure")

    def fail(path: Path) -> object:
        raise BrokenMessageError()

    monkeypatch.setattr(checker_module, "load_facet_registry", fail)
    result = declaration_registry_checker(_valid_input())

    assert result.state is EvaluationState.BLOCKED
    assert result.evidence == {
        "outcome": "blocked",
        "internal-exception-class": "BrokenMessageError",
        "message": (
            "BrokenMessageError message unavailable; formatting raised ValueError"
        ),
    }


def test_shipped_binding_names_exact_contracts_and_callable() -> None:
    binding = declaration_registry_checker_binding()

    assert binding.evaluator == DECLARATION_REGISTRY_EVALUATOR
    assert binding.operation == LOAD_DECLARATION_REGISTRY_OPERATION
    assert binding.runner is declaration_registry_checker
    assert binding.runner(_valid_input()).state is EvaluationState.SATISFIED
