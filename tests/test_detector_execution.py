"""Adversarial contract tests for detector execution and certification."""

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
    DetectorExecution,
    DetectorExecutionError,
    DetectorResult,
    DetectorRunner,
    DetectorRunnerBinding,
    DetectorRunnerRegistry,
    VersionedReference,
    build_detector_runner_registry,
    execute_detector,
    load_declaration_registry,
    load_facet_registry,
)
from eutaxis.declarations.models import JsonValue
from eutaxis.declarations.execution import _is_issued_detector_execution

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY_FIXTURES = FIXTURES / "registry" / "valid"
FACETS = FIXTURES / "facets" / "valid" / "context-facets.yaml"
DETECTOR = VersionedReference("registry/detector", 1)
OPERATION = VersionedReference("registry/write", 1)


def _setup(
    tmp_path: Path,
    runner: object,
    *,
    evidence_schema: Mapping[str, object] | None = None,
):
    directory = tmp_path / "registry"
    shutil.copytree(REGISTRY_FIXTURES, directory)
    detector = yaml.safe_load(
        (directory / "evaluator.yaml").read_text(encoding="utf-8")
    )
    detector.update(
        {
            "id": DETECTOR.id,
            "evaluator-kind": "detector",
            "coverage": "partial",
            "adjudication": "candidate",
            "residual-question": "Does the candidate violate the obligation?",
            "failure-behavior": "block",
            "evidence-schema": {
                "type": "object",
                "properties": {"accepted": {"type": "boolean"}},
                "required": ["accepted"],
                "additionalProperties": False,
            },
        }
    )
    if evidence_schema is not None:
        detector["evidence-schema"] = evidence_schema
    (directory / "detector.yaml").write_text(
        yaml.safe_dump(detector, sort_keys=False), encoding="utf-8"
    )
    declarations = load_declaration_registry(
        tuple(sorted(directory.glob("*.yaml"))), load_facet_registry(FACETS)
    )
    binding = DetectorRunnerBinding(
        evaluator=DETECTOR,
        operation=OPERATION,
        runner=cast(DetectorRunner, runner),
    )
    return build_detector_runner_registry(declarations, [binding])


def _result(
    *,
    evaluator: VersionedReference = DETECTOR,
    revision: str = "declaration-v1",
    evidence: object = None,
) -> DetectorResult:
    return DetectorResult(
        evaluator=evaluator,
        input_revision=revision,
        evidence=cast(
            Mapping[str, JsonValue],
            {"accepted": True} if evidence is None else evidence,
        ),
    )


def _input() -> dict[str, object]:
    return {"path": "artifact.txt", "content": "candidate"}


def test_detector_execution_is_private_correlated_and_immutable(tmp_path: Path) -> None:
    source_evidence = {"accepted": True}
    registry = _setup(tmp_path, lambda input_data: _result(evidence=source_evidence))
    source_input = _input()

    execution = execute_detector(
        registry, DETECTOR, input_revision="declaration-v1", input_data=source_input
    )
    second = execute_detector(
        registry, DETECTOR, input_revision="declaration-v1", input_data=_input()
    )

    source_evidence["accepted"] = False
    source_input["path"] = "changed"
    assert execution.registry is registry
    assert second.registry is registry
    assert execution is not second
    assert execution != second
    assert _is_issued_detector_execution(execution)
    assert execution.evaluator == DETECTOR
    assert execution.input_data == _input()
    assert execution.evidence["accepted"] is True
    with pytest.raises(TypeError):
        execution.evidence["accepted"] = False  # type: ignore[index]
    with pytest.raises(TypeError, match="issued by execution"):
        DetectorExecution()
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(execution)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.deepcopy(execution)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(execution)

    reconstructed = object.__new__(DetectorExecution)
    for field in ("registry", "evaluator", "input_revision", "input_data", "evidence"):
        object.__setattr__(reconstructed, field, getattr(execution, field))
    assert not _is_issued_detector_execution(reconstructed)


def test_empty_candidate_collection_is_successful_and_immutable(tmp_path: Path) -> None:
    schema = {
        "type": "object",
        "required": ["candidates"],
        "properties": {"candidates": {"type": "array"}},
        "additionalProperties": False,
    }
    registry = _setup(
        tmp_path,
        lambda input_data: _result(evidence={"candidates": []}),
        evidence_schema=schema,
    )

    execution = execute_detector(
        registry, DETECTOR, input_revision="declaration-v1", input_data=_input()
    )

    assert execution.evidence["candidates"] == ()


def test_unstamped_registry_fails_before_mapping_access(tmp_path: Path) -> None:
    registry = _setup(tmp_path, lambda input_data: _result())
    reconstructed = object.__new__(DetectorRunnerRegistry)
    with pytest.raises(DetectorExecutionError, match="not issued") as captured:
        execute_detector(
            reconstructed,
            DETECTOR,
            input_revision="declaration-v1",
            input_data=_input(),
        )
    assert captured.value.location == "$"


def test_missing_detector_binding_is_rejected(tmp_path: Path) -> None:
    complete = _setup(tmp_path, lambda input_data: _result())
    empty = build_detector_runner_registry(complete.declarations, [])

    with pytest.raises(DetectorExecutionError) as captured:
        execute_detector(
            empty, DETECTOR, input_revision="declaration-v1", input_data=_input()
        )

    assert captured.value.location == "$.evaluator"


@pytest.mark.parametrize(
    ("revision", "input_data", "location"),
    [
        ("other", _input(), "$.input-revision"),
        ("declaration-v1", [], "$.input"),
        ("declaration-v1", {"path": "missing-content"}, "$.input"),
    ],
)
def test_detector_rejects_revision_and_input_contract_defects(
    tmp_path: Path, revision: str, input_data: object, location: str
) -> None:
    registry = _setup(tmp_path, lambda payload: _result())
    with pytest.raises(DetectorExecutionError) as captured:
        execute_detector(
            registry,
            DETECTOR,
            input_revision=revision,
            input_data=cast(Mapping[str, object], input_data),
        )
    assert captured.value.location.startswith(location)


def test_runner_receives_immutable_input(tmp_path: Path) -> None:
    def runner(input_data: Mapping[str, JsonValue], /) -> DetectorResult:
        with pytest.raises(TypeError):
            input_data["path"] = "changed"  # type: ignore[index]
        return _result()

    execute_detector(
        _setup(tmp_path, runner),
        DETECTOR,
        input_revision="declaration-v1",
        input_data=_input(),
    )


def test_cyclic_input_and_evidence_are_rejected(tmp_path: Path) -> None:
    cyclic_input: dict[str, object] = {"path": "artifact.txt"}
    cyclic_input["content"] = cyclic_input
    registry = _setup(tmp_path, lambda input_data: _result())
    with pytest.raises(DetectorExecutionError, match="cyclic containers") as captured:
        execute_detector(
            registry,
            DETECTOR,
            input_revision="declaration-v1",
            input_data=cyclic_input,
        )
    assert captured.value.location == "$.input"

    cyclic_evidence: dict[str, object] = {"accepted": True}
    cyclic_evidence["detail"] = cyclic_evidence
    registry = _setup(
        tmp_path / "evidence", lambda input_data: _result(evidence=cyclic_evidence)
    )
    with pytest.raises(DetectorExecutionError, match="cyclic containers") as captured:
        execute_detector(
            registry, DETECTOR, input_revision="declaration-v1", input_data=_input()
        )
    assert captured.value.location == "$.result.evidence"


def test_runner_exception_with_hostile_string_blocks(tmp_path: Path) -> None:
    class HostileError(Exception):
        def __str__(self) -> str:
            raise RuntimeError("formatting failed")

    def runner(input_data: Mapping[str, JsonValue], /) -> DetectorResult:
        raise HostileError()

    with pytest.raises(DetectorExecutionError) as captured:
        execute_detector(
            _setup(tmp_path, runner),
            DETECTOR,
            input_revision="declaration-v1",
            input_data=_input(),
        )
    assert captured.value.location == "$.runner"
    assert "formatting raised RuntimeError" in str(captured.value)


@pytest.mark.parametrize(
    ("returned", "location"),
    [
        (object(), "$.result"),
        (_result(evaluator=VersionedReference("other", 1)), "$.result.evaluator"),
        (_result(revision="other"), "$.result.input-revision"),
        (_result(evidence=[]), "$.result.evidence"),
        (_result(evidence={"accepted": "yes"}), "$.result.evidence.accepted"),
    ],
)
def test_detector_validates_every_result_field(
    tmp_path: Path, returned: object, location: str
) -> None:
    registry = _setup(tmp_path, lambda input_data: returned)
    with pytest.raises(DetectorExecutionError) as captured:
        execute_detector(
            registry, DETECTOR, input_revision="declaration-v1", input_data=_input()
        )
    assert captured.value.location == location
