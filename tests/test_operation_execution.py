"""Adversarial tests for exact operation binding and execution."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

from eutaxis import data_path
from eutaxis.declarations import (
    LOAD_DECLARATION_REGISTRY_OPERATION,
    OperationExecutionError,
    OperationFailure,
    OperationRunner,
    OperationRunnerBinding,
    OperationRunnerRegistryError,
    OperationSuccess,
    VersionedReference,
    build_operation_runner_registry,
    execute_operation,
    facet_registry_path,
    load_declaration_registry,
    load_facet_registry,
)
from eutaxis.declarations.models import JsonValue

DECLARATION_ROOT = data_path() / "declarations" / "v1"


def _declarations():
    return load_declaration_registry(
        tuple(sorted(DECLARATION_ROOT.glob("*.yaml"))),
        load_facet_registry(facet_registry_path()),
    )


def _binding(runner: object) -> OperationRunnerBinding:
    return OperationRunnerBinding(
        operation=LOAD_DECLARATION_REGISTRY_OPERATION,
        runner=cast(OperationRunner, runner),
    )


def _registry(runner: object):
    return build_operation_runner_registry(_declarations(), [_binding(runner)])


def _valid_input() -> dict[str, object]:
    return {"sources": ["one.yaml"], "facet-registry": "facets.yaml"}


def test_successful_outputs_and_inputs_are_immutable() -> None:
    source_outputs = {
        "registry.valid": True,
        "record-count": 1,
        "family-count": 1,
        "conflict-count": 0,
    }

    def runner(input_data: Mapping[str, JsonValue], /):
        with pytest.raises(TypeError):
            input_data["facet-registry"] = "changed"  # type: ignore[index]
        return OperationSuccess(
            operation=LOAD_DECLARATION_REGISTRY_OPERATION,
            outputs=source_outputs,
        )

    result = execute_operation(
        _registry(runner),
        LOAD_DECLARATION_REGISTRY_OPERATION,
        input_data=_valid_input(),
    )
    assert isinstance(result, OperationSuccess)
    source_outputs["record-count"] = 99
    assert result.outputs["record-count"] == 1
    with pytest.raises(TypeError):
        result.outputs["record-count"] = 2  # type: ignore[index]


def test_registry_rejects_missing_wrong_duplicate_and_invalid_bindings() -> None:
    declarations = _declarations()

    def runner(input_data: Mapping[str, JsonValue], /):
        return OperationFailure(LOAD_DECLARATION_REGISTRY_OPERATION, "invalid-registry")

    with pytest.raises(OperationRunnerRegistryError) as missing:
        build_operation_runner_registry(
            declarations,
            [
                OperationRunnerBinding(
                    VersionedReference("missing", 1), cast(OperationRunner, runner)
                )
            ],
        )
    assert missing.value.location == "$.bindings[0].operation.id"

    with pytest.raises(OperationRunnerRegistryError) as wrong_kind:
        build_operation_runner_registry(
            declarations,
            [
                OperationRunnerBinding(
                    VersionedReference("eutaxis/declaration-registry", 1),
                    cast(OperationRunner, runner),
                )
            ],
        )
    assert wrong_kind.value.location == "$.bindings[0].operation.id"

    with pytest.raises(OperationRunnerRegistryError) as not_callable:
        build_operation_runner_registry(declarations, [_binding("module:function")])
    assert not_callable.value.location == "$.bindings[0].runner"


@pytest.mark.parametrize("invalid_first", [False, True])
def test_duplicate_precedence_is_independent_of_runner_order(
    invalid_first: bool,
) -> None:
    def runner(input_data: Mapping[str, JsonValue], /):
        return OperationFailure(LOAD_DECLARATION_REGISTRY_OPERATION, "invalid-registry")

    valid = _binding(runner)
    invalid = _binding("module:function")
    bindings = [invalid, valid] if invalid_first else [valid, invalid]
    with pytest.raises(OperationRunnerRegistryError) as captured:
        build_operation_runner_registry(_declarations(), bindings)
    assert captured.value.location == "$.bindings[1].operation"
    assert "duplicate operation binding" in str(captured.value)


def test_duplicate_precedence_accepts_a_single_pass_iterable() -> None:
    bindings = (_binding(runner) for runner in ("module:function", lambda data: None))
    with pytest.raises(OperationRunnerRegistryError) as captured:
        build_operation_runner_registry(_declarations(), bindings)
    assert captured.value.location == "$.bindings[1].operation"
    assert "duplicate operation binding" in str(captured.value)


async def _async_runner(input_data: Mapping[str, JsonValue], /):
    return OperationFailure(LOAD_DECLARATION_REGISTRY_OPERATION, "invalid-registry")


async def _async_generator_runner(input_data: Mapping[str, JsonValue], /):
    yield OperationFailure(LOAD_DECLARATION_REGISTRY_OPERATION, "invalid-registry")


class _AsyncGeneratorCallable:
    async def __call__(self, input_data: Mapping[str, JsonValue], /):
        yield OperationFailure(LOAD_DECLARATION_REGISTRY_OPERATION, "invalid-registry")


class _AsyncCallable:
    async def __call__(self, input_data: Mapping[str, JsonValue], /):
        return OperationFailure(LOAD_DECLARATION_REGISTRY_OPERATION, "invalid-registry")


def test_registry_rejects_async_and_incompatible_runners() -> None:
    for runner in (
        _async_runner,
        _async_generator_runner,
        _AsyncCallable(),
        _AsyncGeneratorCallable(),
    ):
        with pytest.raises(OperationRunnerRegistryError, match="synchronous"):
            _registry(runner)
    with pytest.raises(OperationRunnerRegistryError, match="one positional"):
        _registry(lambda: None)


def test_invocation_rejects_missing_binding_invalid_input_and_runner_error() -> None:
    declarations = _declarations()
    empty = build_operation_runner_registry(declarations, [])
    with pytest.raises(OperationExecutionError) as missing:
        execute_operation(
            empty,
            LOAD_DECLARATION_REGISTRY_OPERATION,
            input_data=_valid_input(),
        )
    assert missing.value.location == "$.operation"

    called = False

    def runner(input_data: Mapping[str, JsonValue], /):
        nonlocal called
        called = True
        raise RuntimeError("planted")

    registry = _registry(runner)
    with pytest.raises(OperationExecutionError) as invalid:
        execute_operation(
            registry,
            LOAD_DECLARATION_REGISTRY_OPERATION,
            input_data={"sources": [], "facet-registry": "facets.yaml"},
        )
    assert invalid.value.location == "$.input.sources"
    assert not called

    with pytest.raises(OperationExecutionError) as escaped:
        execute_operation(
            registry,
            LOAD_DECLARATION_REGISTRY_OPERATION,
            input_data=_valid_input(),
        )
    assert escaped.value.location == "$.runner"
    assert "RuntimeError" in str(escaped.value)


def test_runner_exception_with_broken_string_conversion_stays_located() -> None:
    class HostileError(Exception):
        def __str__(self) -> str:
            raise RuntimeError("formatting failed")

    def runner(input_data: Mapping[str, JsonValue], /):
        raise HostileError()

    with pytest.raises(OperationExecutionError) as captured:
        execute_operation(
            _registry(runner),
            LOAD_DECLARATION_REGISTRY_OPERATION,
            input_data=_valid_input(),
        )
    assert captured.value.location == "$.runner"
    assert "HostileError" in str(captured.value)
    assert "formatting raised RuntimeError" in str(captured.value)


@pytest.mark.parametrize(
    ("returned", "location"),
    [
        ({"outputs": {}}, "$.result"),
        (
            OperationSuccess(VersionedReference("other", 1), {}),
            "$.result.operation",
        ),
        (
            OperationSuccess(
                LOAD_DECLARATION_REGISTRY_OPERATION,
                cast(Mapping[str, JsonValue], []),
            ),
            "$.result.outputs",
        ),
        (
            OperationSuccess(
                LOAD_DECLARATION_REGISTRY_OPERATION,
                {
                    "registry.valid": True,
                    "record-count": -1,
                    "family-count": 1,
                    "conflict-count": 0,
                },
            ),
            "$.result.outputs.record-count",
        ),
        (
            OperationFailure(LOAD_DECLARATION_REGISTRY_OPERATION, "other"),
            "$.result.outcome",
        ),
    ],
)
def test_returned_contract_is_enforced(returned: object, location: str) -> None:
    def runner(input_data: Mapping[str, JsonValue], /):
        return returned

    with pytest.raises(OperationExecutionError) as captured:
        execute_operation(
            _registry(runner),
            LOAD_DECLARATION_REGISTRY_OPERATION,
            input_data=_valid_input(),
        )
    assert captured.value.location == location


def test_cyclic_input_and_outputs_are_rejected() -> None:
    cycle: dict[str, object] = {}
    cycle["sources"] = [cycle]
    cycle["facet-registry"] = "facets.yaml"
    with pytest.raises(
        OperationExecutionError, match="cyclic containers"
    ) as input_error:
        execute_operation(
            _registry(lambda input_data: None),
            LOAD_DECLARATION_REGISTRY_OPERATION,
            input_data=cycle,
        )
    assert input_error.value.location == "$.input"

    output_cycle: dict[str, object] = {}
    output_cycle["registry.valid"] = output_cycle

    def runner(input_data: Mapping[str, JsonValue], /):
        return OperationSuccess(
            LOAD_DECLARATION_REGISTRY_OPERATION,
            cast(Mapping[str, JsonValue], output_cycle),
        )

    with pytest.raises(
        OperationExecutionError, match="cyclic containers"
    ) as output_error:
        execute_operation(
            _registry(runner),
            LOAD_DECLARATION_REGISTRY_OPERATION,
            input_data=_valid_input(),
        )
    assert output_error.value.location == "$.result.outputs"
