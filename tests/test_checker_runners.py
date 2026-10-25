"""Contract tests for the code-owned checker runner registry."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
import yaml

from eutaxis.declarations import (
    CheckerRunner,
    CheckerRunnerBinding,
    CheckerRunnerRegistryError,
    VersionedReference,
    build_checker_runner_registry,
    load_declaration_registry,
    load_facet_registry,
)
from eutaxis.declarations.models import JsonValue

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY_FIXTURES = FIXTURES / "registry" / "valid"
FACET_FIXTURE = FIXTURES / "facets" / "valid" / "context-facets.yaml"
CHECKER = VersionedReference("registry/checker", 1)
OPERATION = VersionedReference("registry/write", 1)


def _runner(input_data: Mapping[str, JsonValue], /) -> object:
    """Return an opaque placeholder for the later execution layer."""
    return {"received": input_data}


def _registry(tmp_path: Path):
    """Build a closed registry containing one checker and one manual evaluator."""
    directory = tmp_path / "registry"
    shutil.copytree(REGISTRY_FIXTURES, directory)
    evaluator_path = directory / "checker.yaml"
    evaluator = yaml.safe_load(
        (directory / "evaluator.yaml").read_text(encoding="utf-8")
    )
    evaluator["id"] = CHECKER.id
    evaluator["evaluator-kind"] = "checker"
    evaluator["coverage"] = "total"
    evaluator["adjudication"] = "authoritative"
    evaluator["known-failure-fixtures"] = ["fixture/known-failure"]
    evaluator_path.write_text(
        yaml.safe_dump(evaluator, sort_keys=False), encoding="utf-8"
    )
    detector = dict(evaluator)
    detector["id"] = "registry/detector"
    detector["evaluator-kind"] = "detector"
    detector["coverage"] = "partial"
    detector["adjudication"] = "candidate"
    detector["residual-question"] = "Does the candidate violate the obligation?"
    detector.pop("known-failure-fixtures")
    (directory / "detector.yaml").write_text(
        yaml.safe_dump(detector, sort_keys=False), encoding="utf-8"
    )
    paths = tuple(sorted(directory.glob("*.yaml")))
    return load_declaration_registry(paths, load_facet_registry(FACET_FIXTURE))


def _binding(
    *,
    evaluator: VersionedReference = CHECKER,
    operation: VersionedReference = OPERATION,
    runner: object = _runner,
) -> CheckerRunnerBinding:
    """Return one runner binding with overridable exact references."""
    return CheckerRunnerBinding(
        evaluator=evaluator,
        operation=operation,
        runner=cast(CheckerRunner, runner),
    )


def test_registry_binds_exact_checker_callable_and_operation_input(
    tmp_path: Path,
) -> None:
    declarations = _registry(tmp_path)
    registry = build_checker_runner_registry(declarations, [_binding()])

    assert tuple(registry.bindings) == (CHECKER,)
    assert registry.bindings[CHECKER].runner is _runner
    assert registry.bindings[CHECKER].operation == OPERATION
    assert registry.input_contracts[CHECKER]["type"] == "object"
    assert cast(Mapping[str, object], registry.input_contracts[CHECKER]["properties"])[
        "path"
    ] == {"type": "string"}
    with pytest.raises(TypeError):
        registry.bindings[CHECKER] = _binding()  # type: ignore[index]
    with pytest.raises(TypeError):
        registry.input_contracts[CHECKER] = {}  # type: ignore[index]


@pytest.mark.parametrize("kind", ["manual", "detector"])
def test_non_checker_evaluators_cannot_receive_runners(
    tmp_path: Path, kind: str
) -> None:
    declarations = _registry(tmp_path)
    reference = VersionedReference(f"registry/{kind}", 1)
    with pytest.raises(CheckerRunnerRegistryError) as captured:
        build_checker_runner_registry(declarations, [_binding(evaluator=reference)])
    assert captured.value.location == "$.bindings[0].evaluator"
    assert f"{kind!r}, not 'checker'" in str(captured.value)


@pytest.mark.parametrize(
    ("field", "reference", "location", "message"),
    [
        (
            "evaluator",
            VersionedReference("registry/missing", 1),
            "$.bindings[0].evaluator.id",
            "unknown contract family",
        ),
        (
            "evaluator",
            VersionedReference(CHECKER.id, 2),
            "$.bindings[0].evaluator.version",
            "unknown contract version",
        ),
        (
            "evaluator",
            OPERATION,
            "$.bindings[0].evaluator.id",
            "is not an evaluator",
        ),
        (
            "operation",
            VersionedReference("registry/missing", 1),
            "$.bindings[0].operation.id",
            "unknown contract family",
        ),
        (
            "operation",
            VersionedReference(OPERATION.id, 2),
            "$.bindings[0].operation.version",
            "unknown contract version",
        ),
        (
            "operation",
            CHECKER,
            "$.bindings[0].operation.id",
            "is not an operation",
        ),
    ],
)
def test_exact_binding_references_split_family_version_and_kind_errors(
    tmp_path: Path,
    field: str,
    reference: VersionedReference,
    location: str,
    message: str,
) -> None:
    declarations = _registry(tmp_path)
    binding = (
        _binding(evaluator=reference)
        if field == "evaluator"
        else _binding(operation=reference)
    )
    with pytest.raises(CheckerRunnerRegistryError) as captured:
        build_checker_runner_registry(declarations, [binding])
    assert captured.value.location == location
    assert message in str(captured.value)


def test_duplicate_checker_binding_fails_at_the_later_binding(
    tmp_path: Path,
) -> None:
    declarations = _registry(tmp_path)
    with pytest.raises(CheckerRunnerRegistryError) as captured:
        build_checker_runner_registry(declarations, [_binding(), _binding()])
    assert captured.value.location == "$.bindings[1].evaluator"
    assert "duplicate checker binding" in str(captured.value)


@pytest.mark.parametrize("invalid_first", [False, True])
def test_duplicate_precedence_is_independent_of_runner_and_iterable_order(
    tmp_path: Path, invalid_first: bool
) -> None:
    declarations = _registry(tmp_path)
    valid = _binding()
    invalid = _binding(runner="module:function")
    bindings = [invalid, valid] if invalid_first else [valid, invalid]
    with pytest.raises(CheckerRunnerRegistryError) as captured:
        build_checker_runner_registry(declarations, bindings)
    assert captured.value.location == "$.bindings[1].evaluator"
    assert "duplicate checker binding" in str(captured.value)


def test_duplicate_precedence_accepts_a_single_pass_iterable(tmp_path: Path) -> None:
    declarations = _registry(tmp_path)
    bindings = (_binding(runner=runner) for runner in ("module:function", _runner))
    with pytest.raises(CheckerRunnerRegistryError) as captured:
        build_checker_runner_registry(declarations, bindings)
    assert captured.value.location == "$.bindings[1].evaluator"
    assert "duplicate checker binding" in str(captured.value)


def test_non_callable_binding_is_rejected_without_execution(tmp_path: Path) -> None:
    declarations = _registry(tmp_path)
    binding = _binding(runner=cast(object, "module:function"))
    with pytest.raises(CheckerRunnerRegistryError) as captured:
        build_checker_runner_registry(declarations, [binding])
    assert captured.value.location == "$.bindings[0].runner"
    assert "in-process callable" in str(captured.value)


@pytest.mark.parametrize(
    "runner",
    [lambda: None, lambda first, second: None],
)
def test_incompatible_runner_arity_is_rejected_without_execution(
    tmp_path: Path, runner
) -> None:
    declarations = _registry(tmp_path)
    with pytest.raises(CheckerRunnerRegistryError) as captured:
        build_checker_runner_registry(declarations, [_binding(runner=runner)])
    assert captured.value.location == "$.bindings[0].runner"
    assert "one positional input payload" in str(captured.value)


async def _async_runner(input_data: Mapping[str, JsonValue], /) -> object:
    """Represent an unsupported coroutine-based runner."""
    return {"received": input_data}


async def _async_generator_runner(input_data: Mapping[str, JsonValue], /):
    yield {"received": input_data}


class _AsyncCallable:
    async def __call__(self, input_data: Mapping[str, JsonValue], /) -> object:
        return {"received": input_data}


class _AsyncGeneratorCallable:
    async def __call__(self, input_data: Mapping[str, JsonValue], /):
        yield {"received": input_data}


def test_async_runner_is_rejected_without_creating_a_coroutine(tmp_path: Path) -> None:
    declarations = _registry(tmp_path)
    for runner in (
        _async_runner,
        _async_generator_runner,
        _AsyncCallable(),
        _AsyncGeneratorCallable(),
    ):
        with pytest.raises(CheckerRunnerRegistryError) as captured:
            build_checker_runner_registry(declarations, [_binding(runner=runner)])
        assert captured.value.location == "$.bindings[0].runner"
        assert "must be synchronous" in str(captured.value)
