"""Bind exact checker declarations to reviewed in-process callables."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping, Protocol, cast

from ._runner_support import validate_synchronous_runner
from .exceptions import CheckerRunnerRegistryError
from .fixtures import EvaluatorInputContracts
from .models import (
    DeclarationKind,
    EvaluatorDeclaration,
    JsonValue,
    OperationDeclaration,
    VersionedReference,
)
from .registry import DeclarationRegistry, RegisteredDeclaration
from .results import CheckerResult


class CheckerRunner(Protocol):
    """A reviewed callable whose result is validated by the execution layer."""

    def __call__(self, input_data: Mapping[str, JsonValue], /) -> CheckerResult:
        """Evaluate one immutable input payload."""


@dataclass(frozen=True)
class CheckerRunnerBinding:
    """One exact checker-to-callable and checker-to-input-contract binding."""

    evaluator: VersionedReference
    operation: VersionedReference
    runner: CheckerRunner


@dataclass(frozen=True)
class CheckerRunnerRegistry:
    """An immutable registry of validated checker runner bindings."""

    declarations: DeclarationRegistry
    bindings: Mapping[VersionedReference, CheckerRunnerBinding]
    input_contracts: EvaluatorInputContracts
    evaluator_records: Mapping[VersionedReference, RegisteredDeclaration]


def build_checker_runner_registry(
    declarations: DeclarationRegistry,
    bindings: Iterable[CheckerRunnerBinding],
) -> CheckerRunnerRegistry:
    """Validate and freeze code-owned checker runner bindings."""
    ordered = sorted(
        bindings,
        key=lambda binding: (
            binding.evaluator.id,
            binding.evaluator.version,
            binding.operation.id,
            binding.operation.version,
        ),
    )
    _reject_duplicate_evaluators(ordered)
    registered: dict[VersionedReference, CheckerRunnerBinding] = {}
    input_contracts: dict[VersionedReference, Mapping[str, object]] = {}
    evaluator_records: dict[VersionedReference, RegisteredDeclaration] = {}
    for index, binding in enumerate(ordered):
        base = f"$.bindings[{index}]"
        evaluator_record = _resolve_exact(
            declarations,
            binding.evaluator,
            expected_kind=DeclarationKind.EVALUATOR,
            location=f"{base}.evaluator",
        )
        evaluator = cast(EvaluatorDeclaration, evaluator_record.declaration)
        if evaluator.evaluator_kind != "checker":
            raise CheckerRunnerRegistryError(
                f"{base}.evaluator",
                f"evaluator {evaluator.id!r}@{evaluator.version} is {evaluator.evaluator_kind!r}, not 'checker'",
            )
        operation_record = _resolve_exact(
            declarations,
            binding.operation,
            expected_kind=DeclarationKind.OPERATION,
            location=f"{base}.operation",
        )
        operation = cast(OperationDeclaration, operation_record.declaration)
        _validate_runner(binding.runner, f"{base}.runner")
        registered[binding.evaluator] = binding
        input_contracts[binding.evaluator] = cast(
            Mapping[str, object], operation.inputs
        )
        evaluator_records[binding.evaluator] = evaluator_record
    return CheckerRunnerRegistry(
        declarations=declarations,
        bindings=MappingProxyType(registered),
        input_contracts=MappingProxyType(input_contracts),
        evaluator_records=MappingProxyType(evaluator_records),
    )


def _reject_duplicate_evaluators(
    bindings: list[CheckerRunnerBinding],
) -> None:
    """Reject repeated exact evaluator keys before inspecting their runners."""
    seen: set[VersionedReference] = set()
    for index, binding in enumerate(bindings):
        if binding.evaluator in seen:
            raise CheckerRunnerRegistryError(
                f"$.bindings[{index}].evaluator",
                f"duplicate checker binding {binding.evaluator.id!r}@{binding.evaluator.version}",
            )
        seen.add(binding.evaluator)


def _validate_runner(runner: object, location: str) -> None:
    """Require a synchronous callable invocable with one positional payload."""
    validate_synchronous_runner(
        runner, lambda message: CheckerRunnerRegistryError(location, message)
    )


def _resolve_exact(
    declarations: DeclarationRegistry,
    reference: VersionedReference,
    *,
    expected_kind: DeclarationKind,
    location: str,
) -> RegisteredDeclaration:
    """Resolve one exact contract with field-specific binding diagnostics."""
    family = declarations.families.get(reference.id)
    if family is None:
        raise CheckerRunnerRegistryError(
            f"{location}.id", f"unknown contract family {reference.id!r}"
        )
    if family.kind is not expected_kind:
        raise CheckerRunnerRegistryError(
            f"{location}.id",
            f"contract family {reference.id!r} is not an {expected_kind.value}",
        )
    record = family.versions.get(reference.version)
    if record is None:
        raise CheckerRunnerRegistryError(
            f"{location}.version",
            f"unknown contract version {reference.id!r}@{reference.version}",
        )
    return record
