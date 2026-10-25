"""Adversarial contract tests for the detector runner registry."""

from __future__ import annotations

import copy
import pickle
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
import yaml

from eutaxis.declarations import (
    DetectorResult,
    DetectorRunner,
    DetectorRunnerBinding,
    DetectorRunnerRegistry,
    DetectorRunnerRegistryError,
    VersionedReference,
    build_detector_runner_registry,
    load_declaration_registry,
    load_facet_registry,
)
from eutaxis.declarations.models import JsonValue
from eutaxis.declarations.runners import _is_builder_issued_detector_registry

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY_FIXTURES = FIXTURES / "registry" / "valid"
FACET_FIXTURE = FIXTURES / "facets" / "valid" / "context-facets.yaml"
DETECTOR = VersionedReference("registry/detector", 1)
SECOND_DETECTOR = VersionedReference("registry/a-detector", 1)
CHECKER = VersionedReference("registry/checker", 1)
MANUAL = VersionedReference("registry/manual", 1)
OPERATION = VersionedReference("registry/write", 1)


def _runner(input_data: Mapping[str, JsonValue], /) -> DetectorResult:
    """Return candidate evidence for a later execution-layer test."""
    return DetectorResult(
        evaluator=DETECTOR,
        input_revision="declaration-v1",
        evidence={"received": input_data},
    )


def _registry(tmp_path: Path):
    """Build a closed registry with two detectors, one checker, and one manual."""
    directory = tmp_path / "registry"
    shutil.copytree(REGISTRY_FIXTURES, directory)
    template = yaml.safe_load(
        (directory / "evaluator.yaml").read_text(encoding="utf-8")
    )
    for index, reference in enumerate((DETECTOR, SECOND_DETECTOR)):
        detector = dict(template)
        detector.update(
            {
                "id": reference.id,
                "evaluator-kind": "detector",
                "coverage": "partial",
                "adjudication": "candidate",
                "residual-question": "Does the candidate violate the obligation?",
                "failure-behavior": "block",
            }
        )
        (directory / f"detector-{index}.yaml").write_text(
            yaml.safe_dump(detector, sort_keys=False), encoding="utf-8"
        )
    checker = dict(template)
    checker.update(
        {
            "id": CHECKER.id,
            "evaluator-kind": "checker",
            "coverage": "total",
            "adjudication": "authoritative",
            "known-failure-fixtures": ["fixture/known-failure"],
        }
    )
    (directory / "checker.yaml").write_text(
        yaml.safe_dump(checker, sort_keys=False), encoding="utf-8"
    )
    return load_declaration_registry(
        tuple(sorted(directory.glob("*.yaml"))),
        load_facet_registry(FACET_FIXTURE),
    )


def _binding(
    *,
    evaluator: VersionedReference = DETECTOR,
    operation: VersionedReference = OPERATION,
    runner: object = _runner,
) -> DetectorRunnerBinding:
    """Return one detector binding with overridable exact references."""
    return DetectorRunnerBinding(
        evaluator=evaluator,
        operation=operation,
        runner=cast(DetectorRunner, runner),
    )


def test_registry_binds_exact_detector_callable_and_operation_input(
    tmp_path: Path,
) -> None:
    declarations = _registry(tmp_path)
    registry = build_detector_runner_registry(declarations, [_binding()])

    assert registry.declarations is declarations
    assert tuple(registry.bindings) == (DETECTOR,)
    assert registry.bindings[DETECTOR].runner is _runner
    assert registry.bindings[DETECTOR].operation == OPERATION
    assert registry.input_contracts[DETECTOR]["type"] == "object"
    assert _is_builder_issued_detector_registry(registry)
    with pytest.raises(TypeError):
        registry.bindings[DETECTOR] = _binding()  # type: ignore[index]


def test_registry_order_is_independent_of_binding_iterable_order(
    tmp_path: Path,
) -> None:
    declarations = _registry(tmp_path)
    registry = build_detector_runner_registry(
        declarations,
        [_binding(), _binding(evaluator=SECOND_DETECTOR)],
    )

    assert tuple(registry.bindings) == (SECOND_DETECTOR, DETECTOR)


@pytest.mark.parametrize("reference", [CHECKER, MANUAL])
def test_non_detector_evaluators_cannot_receive_detector_runners(
    tmp_path: Path, reference: VersionedReference
) -> None:
    declarations = _registry(tmp_path)

    with pytest.raises(DetectorRunnerRegistryError) as captured:
        build_detector_runner_registry(declarations, [_binding(evaluator=reference)])

    assert captured.value.location == "$.bindings[0].evaluator"
    assert "not 'detector'" in str(captured.value)


def test_duplicate_detector_binding_fails_at_later_canonical_binding(
    tmp_path: Path,
) -> None:
    declarations = _registry(tmp_path)

    with pytest.raises(DetectorRunnerRegistryError) as captured:
        build_detector_runner_registry(declarations, [_binding(), _binding()])

    assert captured.value.location == "$.bindings[1].evaluator"
    assert "duplicate detector binding" in str(captured.value)


@pytest.mark.parametrize(
    ("evaluator", "operation", "location", "message"),
    [
        (
            VersionedReference("registry/missing", 1),
            OPERATION,
            "$.bindings[0].evaluator.id",
            "unknown contract family",
        ),
        (
            VersionedReference(DETECTOR.id, 2),
            OPERATION,
            "$.bindings[0].evaluator.version",
            "unknown contract version",
        ),
        (
            DETECTOR,
            VersionedReference("registry/missing", 1),
            "$.bindings[0].operation.id",
            "unknown contract family",
        ),
    ],
)
def test_exact_reference_failures_keep_detector_specific_diagnostics(
    tmp_path: Path,
    evaluator: VersionedReference,
    operation: VersionedReference,
    location: str,
    message: str,
) -> None:
    declarations = _registry(tmp_path)

    with pytest.raises(DetectorRunnerRegistryError) as captured:
        build_detector_runner_registry(
            declarations,
            [_binding(evaluator=evaluator, operation=operation)],
        )

    assert captured.value.location == location
    assert message in str(captured.value)


@pytest.mark.parametrize("runner", ["module:function", 3, object()])
def test_detector_runner_must_be_synchronous_callable(
    tmp_path: Path, runner: object
) -> None:
    declarations = _registry(tmp_path)

    with pytest.raises(DetectorRunnerRegistryError) as captured:
        build_detector_runner_registry(declarations, [_binding(runner=runner)])

    assert captured.value.location == "$.bindings[0].runner"


@pytest.mark.parametrize("runner", [lambda: None, lambda first, second: None])
def test_detector_runner_rejects_incompatible_arity(
    tmp_path: Path, runner: object
) -> None:
    declarations = _registry(tmp_path)

    with pytest.raises(DetectorRunnerRegistryError) as captured:
        build_detector_runner_registry(declarations, [_binding(runner=runner)])

    assert captured.value.location == "$.bindings[0].runner"
    assert "one positional input payload" in str(captured.value)


async def _async_runner(input_data: Mapping[str, JsonValue], /) -> DetectorResult:
    return _runner(input_data)


async def _async_generator_runner(input_data: Mapping[str, JsonValue], /):
    yield _runner(input_data)


class _AsyncCallable:
    async def __call__(self, input_data: Mapping[str, JsonValue], /) -> DetectorResult:
        return _runner(input_data)


class _AsyncGeneratorCallable:
    async def __call__(self, input_data: Mapping[str, JsonValue], /):
        yield _runner(input_data)


@pytest.mark.parametrize(
    "runner",
    [
        _async_runner,
        _async_generator_runner,
        _AsyncCallable(),
        _AsyncGeneratorCallable(),
    ],
)
def test_detector_runner_rejects_asynchronous_callable_forms(
    tmp_path: Path, runner: object
) -> None:
    declarations = _registry(tmp_path)

    with pytest.raises(DetectorRunnerRegistryError) as captured:
        build_detector_runner_registry(declarations, [_binding(runner=runner)])

    assert captured.value.location == "$.bindings[0].runner"
    assert "must be synchronous" in str(captured.value)


def test_detector_registry_rejects_public_reconstruction(
    tmp_path: Path,
) -> None:
    declarations = _registry(tmp_path)
    registry = build_detector_runner_registry(declarations, [_binding()])

    with pytest.raises(TypeError, match="issued by detector registry building"):
        DetectorRunnerRegistry()
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(registry)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.deepcopy(registry)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(registry)

    reconstructed = object.__new__(DetectorRunnerRegistry)
    object.__setattr__(reconstructed, "declarations", registry.declarations)
    object.__setattr__(reconstructed, "bindings", registry.bindings)
    object.__setattr__(reconstructed, "input_contracts", registry.input_contracts)
    object.__setattr__(reconstructed, "evaluator_records", registry.evaluator_records)
    assert not _is_builder_issued_detector_registry(reconstructed)
