"""Bind and execute reviewed callables for exact operation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping, NoReturn, Protocol, SupportsIndex, TypeAlias, cast

from ._runner_support import exception_detail, validate_synchronous_runner
from .embedded_schema import validate_json_instance
from .exceptions import OperationExecutionError, OperationRunnerRegistryError
from .models import (
    DeclarationKind,
    JsonValue,
    OperationDeclaration,
    VersionedReference,
    freeze_json,
)
from .registry import DeclarationRegistry
from .source import DocumentPath, format_document_path

_REGISTRY_ISSUER = object()


@dataclass(frozen=True)
class OperationSuccess:
    """The outputs returned by one successful exact operation."""

    operation: VersionedReference
    outputs: Mapping[str, JsonValue]


@dataclass(frozen=True)
class OperationFailure:
    """One declared failure outcome returned by an exact operation."""

    operation: VersionedReference
    outcome: str


OperationResult: TypeAlias = OperationSuccess | OperationFailure


class OperationRunner(Protocol):
    """A reviewed callable whose result is validated before use."""

    def __call__(self, input_data: Mapping[str, JsonValue], /) -> OperationResult:
        """Execute one operation from immutable validated inputs."""


@dataclass(frozen=True)
class OperationRunnerBinding:
    """One exact operation-to-callable binding."""

    operation: VersionedReference
    runner: OperationRunner


@dataclass(frozen=True, init=False, eq=False)
class OperationRunnerRegistry:
    """A process-local registry of validated operation runner bindings."""

    declarations: DeclarationRegistry
    bindings: Mapping[VersionedReference, OperationRunnerBinding]
    contracts: Mapping[VersionedReference, OperationDeclaration]
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Reject construction outside the registry builder."""
        raise TypeError(
            "OperationRunnerRegistry instances must be issued by the registry builder"
        )

    def __copy__(self) -> NoReturn:
        raise TypeError("OperationRunnerRegistry instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("OperationRunnerRegistry instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("OperationRunnerRegistry instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("OperationRunnerRegistry instances cannot be serialized")


def build_operation_runner_registry(
    declarations: DeclarationRegistry,
    bindings: Iterable[OperationRunnerBinding],
) -> OperationRunnerRegistry:
    """Validate and freeze code-owned operation runner bindings."""
    ordered = sorted(
        bindings,
        key=lambda binding: (binding.operation.id, binding.operation.version),
    )
    _reject_duplicate_operations(ordered)
    registered: dict[VersionedReference, OperationRunnerBinding] = {}
    contracts: dict[VersionedReference, OperationDeclaration] = {}
    for index, binding in enumerate(ordered):
        base = f"$.bindings[{index}]"
        family = declarations.families.get(binding.operation.id)
        if family is None:
            raise OperationRunnerRegistryError(
                f"{base}.operation.id",
                f"unknown contract family {binding.operation.id!r}",
            )
        if family.kind is not DeclarationKind.OPERATION:
            raise OperationRunnerRegistryError(
                f"{base}.operation.id",
                f"contract family {binding.operation.id!r} is not an operation",
            )
        record = family.versions.get(binding.operation.version)
        if record is None:
            raise OperationRunnerRegistryError(
                f"{base}.operation.version",
                f"unknown contract version {binding.operation.id!r}@{binding.operation.version}",
            )
        _validate_runner(binding.runner, f"{base}.runner")
        registered[binding.operation] = binding
        contracts[binding.operation] = cast(OperationDeclaration, record.declaration)
    registry = object.__new__(OperationRunnerRegistry)
    object.__setattr__(registry, "declarations", declarations)
    object.__setattr__(registry, "bindings", MappingProxyType(registered))
    object.__setattr__(registry, "contracts", MappingProxyType(contracts))
    object.__setattr__(registry, "_issuer", _REGISTRY_ISSUER)
    return registry


def _is_builder_issued_operation_registry(registry: object) -> bool:
    """Return whether ``registry`` carries this process's builder authority."""
    return (
        isinstance(registry, OperationRunnerRegistry)
        and getattr(registry, "_issuer", None) is _REGISTRY_ISSUER
    )


def _reject_duplicate_operations(
    bindings: list[OperationRunnerBinding],
) -> None:
    """Reject repeated exact operation keys before inspecting their runners."""
    seen: set[VersionedReference] = set()
    for index, binding in enumerate(bindings):
        if binding.operation in seen:
            raise OperationRunnerRegistryError(
                f"$.bindings[{index}].operation",
                f"duplicate operation binding {binding.operation.id!r}@{binding.operation.version}",
            )
        seen.add(binding.operation)


def execute_operation(
    runners: OperationRunnerRegistry,
    operation: VersionedReference,
    *,
    input_data: Mapping[str, object],
) -> OperationResult:
    """Invoke one exact operation and validate its input and returned contract."""
    if not _is_builder_issued_operation_registry(runners):
        _raise_execution_error(
            ("registry",),
            "operation runner registry was not issued by the registry builder",
        )
    binding = runners.bindings.get(operation)
    if binding is None:
        _raise_execution_error(
            ("operation",),
            f"no runner is registered for operation {operation.id!r}@{operation.version}",
        )
    contract = runners.contracts[operation]
    try:
        frozen_input = freeze_json(input_data)
    except Exception as exc:
        _raise_execution_error(
            ("input",),
            f"input is not finite JSON: {exception_detail(exc)}",
            cause=exc,
        )
    if not isinstance(frozen_input, Mapping):
        _raise_execution_error(("input",), "input must be a JSON object")
    immutable_input = cast(Mapping[str, JsonValue], frozen_input)
    input_error = validate_json_instance(
        cast(Mapping[str, object], contract.inputs), immutable_input
    )
    if input_error is not None:
        _raise_execution_error(
            ("input",) + tuple(input_error.absolute_path),
            f"input violates the operation contract: {input_error.message}",
        )
    try:
        returned = binding.runner(immutable_input)
    except Exception as exc:
        _raise_execution_error(
            ("runner",),
            f"runner raised {exception_detail(exc)}",
            cause=exc,
        )
    if not isinstance(returned, (OperationSuccess, OperationFailure)):
        _raise_execution_error(("result",), "runner did not return an operation result")
    if returned.operation != operation:
        _raise_execution_error(
            ("result", "operation"),
            "returned operation identity differs from the invocation",
        )
    if isinstance(returned, OperationFailure):
        if returned.outcome not in contract.failure_outcomes:
            _raise_execution_error(
                ("result", "outcome"),
                f"undeclared failure outcome {returned.outcome!r}",
            )
        return returned
    if not isinstance(returned.outputs, Mapping):
        _raise_execution_error(("result", "outputs"), "outputs must be a JSON object")
    try:
        outputs = freeze_json(returned.outputs)
    except Exception as exc:
        _raise_execution_error(
            ("result", "outputs"),
            f"outputs are not finite JSON: {exception_detail(exc)}",
            cause=exc,
        )
    if not isinstance(outputs, Mapping):
        _raise_execution_error(("result", "outputs"), "outputs must be a JSON object")
    immutable_outputs = cast(Mapping[str, JsonValue], outputs)
    output_error = validate_json_instance(
        cast(Mapping[str, object], contract.outputs), immutable_outputs
    )
    if output_error is not None:
        _raise_execution_error(
            ("result", "outputs") + tuple(output_error.absolute_path),
            f"outputs violate the operation contract: {output_error.message}",
        )
    return OperationSuccess(operation=operation, outputs=immutable_outputs)


def _validate_runner(runner: object, location: str) -> None:
    """Require a synchronous callable invocable with one positional payload."""
    validate_synchronous_runner(
        runner, lambda message: OperationRunnerRegistryError(location, message)
    )


def _raise_execution_error(
    parts: DocumentPath,
    message: str,
    *,
    cause: Exception | None = None,
) -> NoReturn:
    """Raise one operation error with a structured result path."""
    error = OperationExecutionError(format_document_path(parts), message)
    if cause is not None:
        raise error from cause
    raise error
