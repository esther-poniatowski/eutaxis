"""Bind exact evaluator declarations to reviewed in-process callables."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping, NoReturn, Protocol, SupportsIndex, TypeVar, cast

from ._runner_support import validate_synchronous_runner
from .exceptions import CheckerRunnerRegistryError, DetectorRunnerRegistryError
from .fixtures import EvaluatorInputContracts
from .models import (
    DeclarationKind,
    EvaluatorDeclaration,
    JsonValue,
    OperationDeclaration,
    VersionedReference,
)
from .registry import DeclarationRegistry, RegisteredDeclaration
from .results import CheckerResult, DetectorResult

_CHECKER_REGISTRY_ISSUER = object()
_DETECTOR_REGISTRY_ISSUER = object()


class CheckerRunner(Protocol):
    """A reviewed callable whose result is validated by checker execution."""

    def __call__(self, input_data: Mapping[str, JsonValue], /) -> CheckerResult:
        """Evaluate one immutable input payload."""


class DetectorRunner(Protocol):
    """A reviewed callable whose result is validated by detector execution."""

    def __call__(self, input_data: Mapping[str, JsonValue], /) -> DetectorResult:
        """Produce candidate evidence from one immutable input payload."""


@dataclass(frozen=True)
class CheckerRunnerBinding:
    """One exact checker-to-callable and checker-to-input-contract binding."""

    evaluator: VersionedReference
    operation: VersionedReference
    runner: CheckerRunner


@dataclass(frozen=True)
class DetectorRunnerBinding:
    """One exact detector-to-callable and detector-to-input-contract binding."""

    evaluator: VersionedReference
    operation: VersionedReference
    runner: DetectorRunner


@dataclass(frozen=True, init=False, eq=False)
class CheckerRunnerRegistry:
    """A process-local checker registry issued by the validated builder."""

    declarations: DeclarationRegistry
    bindings: Mapping[VersionedReference, CheckerRunnerBinding]
    input_contracts: EvaluatorInputContracts
    evaluator_records: Mapping[VersionedReference, RegisteredDeclaration]
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Reject construction outside checker registry building."""
        raise TypeError(
            "CheckerRunnerRegistry instances must be issued by checker registry building"
        )

    def __copy__(self) -> NoReturn:
        """Reject reconstruction by shallow copying."""
        raise TypeError("CheckerRunnerRegistry instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        """Reject reconstruction by deep copying."""
        raise TypeError("CheckerRunnerRegistry instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        """Reject serialization and reconstruction."""
        raise TypeError("CheckerRunnerRegistry instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        """Reject protocol-specific serialization and reconstruction."""
        raise TypeError("CheckerRunnerRegistry instances cannot be serialized")


@dataclass(frozen=True, init=False, eq=False)
class DetectorRunnerRegistry:
    """A process-local detector registry issued by the validated builder."""

    declarations: DeclarationRegistry
    bindings: Mapping[VersionedReference, DetectorRunnerBinding]
    input_contracts: EvaluatorInputContracts
    evaluator_records: Mapping[VersionedReference, RegisteredDeclaration]
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Reject construction outside detector registry building."""
        raise TypeError(
            "DetectorRunnerRegistry instances must be issued by detector registry building"
        )

    def __copy__(self) -> NoReturn:
        """Reject reconstruction by shallow copying."""
        raise TypeError("DetectorRunnerRegistry instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        """Reject reconstruction by deep copying."""
        raise TypeError("DetectorRunnerRegistry instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        """Reject serialization and reconstruction."""
        raise TypeError("DetectorRunnerRegistry instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        """Reject protocol-specific serialization and reconstruction."""
        raise TypeError("DetectorRunnerRegistry instances cannot be serialized")


class _RunnerBindingLike(Protocol):
    """Structural fields shared by the two public binding façades."""

    @property
    def evaluator(self) -> VersionedReference: ...

    @property
    def operation(self) -> VersionedReference: ...

    @property
    def runner(self) -> object: ...


BindingT = TypeVar("BindingT", bound=_RunnerBindingLike)
RegistryErrorFactory = Callable[[str, str], Exception]


def build_checker_runner_registry(
    declarations: DeclarationRegistry,
    bindings: Iterable[CheckerRunnerBinding],
) -> CheckerRunnerRegistry:
    """Validate and freeze code-owned checker runner bindings."""
    registered, input_contracts, evaluator_records = _build_runner_registry(
        declarations,
        bindings,
        expected_evaluator_kind="checker",
        binding_label="checker",
        error_factory=CheckerRunnerRegistryError,
    )
    return cast(
        CheckerRunnerRegistry,
        _issue_runner_registry(
            CheckerRunnerRegistry,
            declarations=declarations,
            bindings=registered,
            input_contracts=input_contracts,
            evaluator_records=evaluator_records,
            issuer=_CHECKER_REGISTRY_ISSUER,
        ),
    )


def build_detector_runner_registry(
    declarations: DeclarationRegistry,
    bindings: Iterable[DetectorRunnerBinding],
) -> DetectorRunnerRegistry:
    """Validate bindings and issue one process-local detector registry."""
    registered, input_contracts, evaluator_records = _build_runner_registry(
        declarations,
        bindings,
        expected_evaluator_kind="detector",
        binding_label="detector",
        error_factory=DetectorRunnerRegistryError,
    )
    return cast(
        DetectorRunnerRegistry,
        _issue_runner_registry(
            DetectorRunnerRegistry,
            declarations=declarations,
            bindings=registered,
            input_contracts=input_contracts,
            evaluator_records=evaluator_records,
            issuer=_DETECTOR_REGISTRY_ISSUER,
        ),
    )


def _issue_runner_registry(
    registry_type: type[CheckerRunnerRegistry] | type[DetectorRunnerRegistry],
    *,
    declarations: DeclarationRegistry,
    bindings: Mapping[VersionedReference, object],
    input_contracts: EvaluatorInputContracts,
    evaluator_records: Mapping[VersionedReference, RegisteredDeclaration],
    issuer: object,
) -> CheckerRunnerRegistry | DetectorRunnerRegistry:
    """Issue one immutable evaluator registry after shared validation."""
    registry = object.__new__(registry_type)
    object.__setattr__(registry, "declarations", declarations)
    object.__setattr__(registry, "bindings", MappingProxyType(dict(bindings)))
    object.__setattr__(
        registry, "input_contracts", MappingProxyType(dict(input_contracts))
    )
    object.__setattr__(
        registry, "evaluator_records", MappingProxyType(dict(evaluator_records))
    )
    object.__setattr__(registry, "_issuer", issuer)
    return registry


def _is_builder_issued_checker_registry(registry: object) -> bool:
    """Return whether ``registry`` carries this process's builder authority."""
    return (
        isinstance(registry, CheckerRunnerRegistry)
        and getattr(registry, "_issuer", None) is _CHECKER_REGISTRY_ISSUER
    )


def _is_builder_issued_detector_registry(registry: object) -> bool:
    """Return whether ``registry`` carries this process's builder authority."""
    return (
        isinstance(registry, DetectorRunnerRegistry)
        and getattr(registry, "_issuer", None) is _DETECTOR_REGISTRY_ISSUER
    )


def _build_runner_registry(
    declarations: DeclarationRegistry,
    bindings: Iterable[BindingT],
    *,
    expected_evaluator_kind: str,
    binding_label: str,
    error_factory: RegistryErrorFactory,
) -> tuple[
    dict[VersionedReference, BindingT],
    dict[VersionedReference, Mapping[str, object]],
    dict[VersionedReference, RegisteredDeclaration],
]:
    """Apply the structural binding contract shared by evaluator façades."""
    ordered = sorted(
        bindings,
        key=lambda binding: (
            binding.evaluator.id,
            binding.evaluator.version,
            binding.operation.id,
            binding.operation.version,
        ),
    )
    _reject_duplicate_evaluators(
        ordered, binding_label=binding_label, error_factory=error_factory
    )
    registered: dict[VersionedReference, BindingT] = {}
    input_contracts: dict[VersionedReference, Mapping[str, object]] = {}
    evaluator_records: dict[VersionedReference, RegisteredDeclaration] = {}
    for index, binding in enumerate(ordered):
        base = f"$.bindings[{index}]"
        evaluator_record = _resolve_exact(
            declarations,
            binding.evaluator,
            expected_kind=DeclarationKind.EVALUATOR,
            location=f"{base}.evaluator",
            error_factory=error_factory,
        )
        evaluator = cast(EvaluatorDeclaration, evaluator_record.declaration)
        if evaluator.evaluator_kind != expected_evaluator_kind:
            raise error_factory(
                f"{base}.evaluator",
                f"evaluator {evaluator.id!r}@{evaluator.version} is {evaluator.evaluator_kind!r}, not {expected_evaluator_kind!r}",
            )
        operation_record = _resolve_exact(
            declarations,
            binding.operation,
            expected_kind=DeclarationKind.OPERATION,
            location=f"{base}.operation",
            error_factory=error_factory,
        )
        operation = cast(OperationDeclaration, operation_record.declaration)
        _validate_runner(binding.runner, f"{base}.runner", error_factory)
        registered[binding.evaluator] = binding
        input_contracts[binding.evaluator] = cast(
            Mapping[str, object], operation.inputs
        )
        evaluator_records[binding.evaluator] = evaluator_record
    return registered, input_contracts, evaluator_records


def _reject_duplicate_evaluators(
    bindings: list[BindingT],
    *,
    binding_label: str,
    error_factory: RegistryErrorFactory,
) -> None:
    """Reject repeated exact evaluator keys before inspecting their runners."""
    seen: set[VersionedReference] = set()
    for index, binding in enumerate(bindings):
        if binding.evaluator in seen:
            raise error_factory(
                f"$.bindings[{index}].evaluator",
                f"duplicate {binding_label} binding {binding.evaluator.id!r}@{binding.evaluator.version}",
            )
        seen.add(binding.evaluator)


def _validate_runner(
    runner: object, location: str, error_factory: RegistryErrorFactory
) -> None:
    """Require a synchronous callable invocable with one positional payload."""
    validate_synchronous_runner(
        runner, lambda message: error_factory(location, message)
    )


def _resolve_exact(
    declarations: DeclarationRegistry,
    reference: VersionedReference,
    *,
    expected_kind: DeclarationKind,
    location: str,
    error_factory: RegistryErrorFactory,
) -> RegisteredDeclaration:
    """Resolve one exact contract with field-specific binding diagnostics."""
    family = declarations.families.get(reference.id)
    if family is None:
        raise error_factory(
            f"{location}.id", f"unknown contract family {reference.id!r}"
        )
    if family.kind is not expected_kind:
        raise error_factory(
            f"{location}.id",
            f"contract family {reference.id!r} is not an {expected_kind.value}",
        )
    record = family.versions.get(reference.version)
    if record is None:
        raise error_factory(
            f"{location}.version",
            f"unknown contract version {reference.id!r}@{reference.version}",
        )
    return record
