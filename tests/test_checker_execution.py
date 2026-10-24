"""Adversarial contract tests for checker invocation and result validation."""

from __future__ import annotations

import shutil
from collections.abc import ItemsView, Iterator, Mapping
from pathlib import Path
from typing import cast

import pytest
import yaml

from eutaxis.declarations import (
    CheckerExecutionError,
    CheckerResult,
    CheckerRunner,
    CheckerRunnerBinding,
    EvaluationState,
    VersionedReference,
    build_checker_runner_registry,
    execute_checker,
    execute_known_failure_fixtures,
    load_declaration_registry,
    load_evaluator_fixture_index,
    load_facet_registry,
)
from eutaxis.declarations.models import JsonValue

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY_FIXTURES = FIXTURES / "registry" / "valid"
FACET_FIXTURE = FIXTURES / "facets" / "valid" / "context-facets.yaml"
CHECKER = VersionedReference("registry/checker", 1)
OPERATION = VersionedReference("registry/check-input", 1)
FIXTURE_ID = "registry/checker/known-failure"


def _result(
    *,
    evaluator: VersionedReference = CHECKER,
    input_revision: str = "declaration-v1",
    state: object = EvaluationState.VIOLATED,
    evidence: object = None,
) -> CheckerResult:
    """Build one result, including deliberately mistyped test values."""
    if evidence is None:
        evidence = {"outcome": "invalid", "detail": "planted failure"}
    return CheckerResult(
        evaluator=evaluator,
        input_revision=input_revision,
        state=cast(EvaluationState, state),
        evidence=cast(Mapping[str, JsonValue], evidence),
    )


def _declarations(
    tmp_path: Path,
    *,
    detail_type: str = "string",
    input_revisions: list[str] | None = None,
    relative_paths_only: bool = False,
    absolute_paths_only: bool = False,
):
    """Build declarations for one checker and its dedicated input operation."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    directory = tmp_path / "registry"
    shutil.copytree(REGISTRY_FIXTURES, directory)

    evaluator = yaml.safe_load(
        (directory / "evaluator.yaml").read_text(encoding="utf-8")
    )
    evaluator.update(
        {
            "id": CHECKER.id,
            "evaluator-kind": "checker",
            "coverage": "total",
            "adjudication": "authoritative",
            "known-failure-fixtures": [FIXTURE_ID],
            "evidence-schema": {
                "type": "object",
                "required": ["outcome", "detail"],
                "properties": {
                    "outcome": {"enum": ["valid", "invalid", "blocked"]},
                    "detail": {"type": detail_type},
                },
                "additionalProperties": False,
            },
        }
    )
    if input_revisions is not None:
        evaluator["input-revisions"] = input_revisions
    (directory / "checker.yaml").write_text(
        yaml.safe_dump(evaluator, sort_keys=False), encoding="utf-8"
    )

    operation = yaml.safe_load(
        (directory / "operation.yaml").read_text(encoding="utf-8")
    )
    operation.update(
        {
            "id": OPERATION.id,
            "inputs": {
                "type": "object",
                "required": ["sources", "facet-registry"],
                "properties": {
                    "sources": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                    "facet-registry": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "effects": [],
        }
    )
    if relative_paths_only:
        properties = operation["inputs"]["properties"]
        properties["sources"]["items"] = {
            "type": "string",
            "pattern": "^[^/]",
        }
    if absolute_paths_only:
        properties = operation["inputs"]["properties"]
        properties["sources"]["items"] = {
            "type": "string",
            "pattern": "^/",
        }
    (directory / "check-input.yaml").write_text(
        yaml.safe_dump(operation, sort_keys=False), encoding="utf-8"
    )
    return load_declaration_registry(
        tuple(sorted(directory.glob("*.yaml"))),
        load_facet_registry(FACET_FIXTURE),
    )


def _runners(declarations, runner: object):
    """Build one exact code-owned runner registry."""
    binding = CheckerRunnerBinding(
        evaluator=CHECKER,
        operation=OPERATION,
        runner=cast(CheckerRunner, runner),
    )
    return build_checker_runner_registry(declarations, [binding])


def _fixture_index(
    tmp_path: Path,
    input_contracts,
    *,
    evaluator: VersionedReference = CHECKER,
    include_descriptor: bool = True,
):
    """Build one confined known-failure fixture index."""
    root = tmp_path / "evaluator-fixtures"
    resources = root / "resources"
    resources.mkdir(parents=True)
    (resources / "invalid.yaml").write_text("invalid: true\n", encoding="utf-8")
    (resources / "facets.yaml").write_text("facets: []\n", encoding="utf-8")
    paths: list[Path] = []
    if include_descriptor:
        descriptor = {
            "schema-version": 1,
            "id": FIXTURE_ID,
            "evaluator": {"id": evaluator.id, "version": evaluator.version},
            "input-revision": "declaration-v1",
            "input": {
                "sources": ["resources/invalid.yaml"],
                "facet-registry": "resources/facets.yaml",
            },
            "expected-state": "violated",
        }
        path = root / "known-failure.yaml"
        path.write_text(yaml.safe_dump(descriptor, sort_keys=False), encoding="utf-8")
        paths.append(path)
    return load_evaluator_fixture_index(
        paths, root=root, input_contracts=input_contracts
    )


def _valid_input() -> dict[str, object]:
    """Return one operation-valid direct invocation payload."""
    return {"sources": ["one.yaml"], "facet-registry": "facets.yaml"}


def test_valid_result_is_returned_as_immutable_evidence(tmp_path: Path) -> None:
    declarations = _declarations(tmp_path)
    source_evidence = {"outcome": "invalid", "detail": "planted failure"}

    def runner(input_data: Mapping[str, JsonValue], /) -> CheckerResult:
        with pytest.raises(TypeError):
            input_data["facet-registry"] = "changed"  # type: ignore[index]
        return _result(evidence=source_evidence)

    result = execute_checker(
        _runners(declarations, runner),
        CHECKER,
        input_revision="declaration-v1",
        input_data=_valid_input(),
        expected_state=EvaluationState.VIOLATED,
    )
    source_evidence["detail"] = "mutated after return"
    assert result.evidence["detail"] == "planted failure"
    with pytest.raises(TypeError):
        result.evidence["detail"] = "changed"  # type: ignore[index]


def test_input_revision_and_payload_fail_before_runner(tmp_path: Path) -> None:
    declarations = _declarations(tmp_path)
    called = False

    def runner(input_data: Mapping[str, JsonValue], /) -> CheckerResult:
        nonlocal called
        called = True
        return _result()

    registry = _runners(declarations, runner)
    with pytest.raises(CheckerExecutionError) as revision_error:
        execute_checker(
            registry,
            CHECKER,
            input_revision="other-v1",
            input_data={"sources": []},
        )
    assert revision_error.value.location == "$.input-revision"
    assert not called

    with pytest.raises(CheckerExecutionError) as input_error:
        execute_checker(
            registry,
            CHECKER,
            input_revision="declaration-v1",
            input_data={"sources": [1], "facet-registry": "facets.yaml"},
        )
    assert input_error.value.location == "$.input.sources[0]"
    assert not called


class _FlippingInput(Mapping[str, object]):
    """Expose a valid first traversal and an invalid second traversal."""

    def __init__(self) -> None:
        self.traversals = 0

    def __getitem__(self, key: str) -> object:
        return dict(self.items())[key]

    def __iter__(self) -> Iterator[str]:
        return iter(dict(self.items()))

    def __len__(self) -> int:
        return 2

    def items(self) -> ItemsView[str, object]:
        self.traversals += 1
        source: object = "one.yaml" if self.traversals == 1 else 1
        return {
            "sources": [source],
            "facet-registry": "facets.yaml",
        }.items()


def test_input_is_frozen_before_the_same_value_is_validated(tmp_path: Path) -> None:
    declarations = _declarations(tmp_path)
    received: Mapping[str, JsonValue] | None = None

    def runner(input_data: Mapping[str, JsonValue], /) -> CheckerResult:
        nonlocal received
        received = input_data
        return _result()

    changing = _FlippingInput()
    execute_checker(
        _runners(declarations, runner),
        CHECKER,
        input_revision="declaration-v1",
        input_data=changing,
    )
    assert changing.traversals == 1
    assert received is not None
    assert received["sources"] == ("one.yaml",)


def test_cyclic_input_is_a_located_execution_error(tmp_path: Path) -> None:
    declarations = _declarations(tmp_path)
    cycle: dict[str, object] = {}
    cycle["sources"] = [cycle]
    cycle["facet-registry"] = "facets.yaml"
    with pytest.raises(CheckerExecutionError) as captured:
        execute_checker(
            _runners(declarations, lambda input_data: _result()),
            CHECKER,
            input_revision="declaration-v1",
            input_data=cycle,
        )
    assert captured.value.location == "$.input"
    assert "cyclic containers" in str(captured.value)


def test_missing_runner_and_escaped_exception_are_gate_failures(
    tmp_path: Path,
) -> None:
    declarations = _declarations(tmp_path)
    empty = build_checker_runner_registry(declarations, [])
    with pytest.raises(CheckerExecutionError) as missing:
        execute_checker(
            empty,
            CHECKER,
            input_revision="declaration-v1",
            input_data=_valid_input(),
        )
    assert missing.value.location == "$.evaluator"

    def broken(input_data: Mapping[str, JsonValue], /) -> CheckerResult:
        raise RuntimeError("unexpected")

    with pytest.raises(CheckerExecutionError) as escaped:
        execute_checker(
            _runners(declarations, broken),
            CHECKER,
            input_revision="declaration-v1",
            input_data=_valid_input(),
        )
    assert escaped.value.location == "$.runner"
    assert "RuntimeError" in str(escaped.value)


def test_runner_exception_with_broken_string_conversion_stays_located(
    tmp_path: Path,
) -> None:
    class HostileError(Exception):
        def __str__(self) -> str:
            raise RuntimeError("formatting failed")

    def runner(input_data: Mapping[str, JsonValue], /) -> CheckerResult:
        raise HostileError()

    declarations = _declarations(tmp_path)
    with pytest.raises(CheckerExecutionError) as captured:
        execute_checker(
            _runners(declarations, runner),
            CHECKER,
            input_revision="declaration-v1",
            input_data=_valid_input(),
        )
    assert captured.value.location == "$.runner"
    assert "HostileError" in str(captured.value)
    assert "formatting raised RuntimeError" in str(captured.value)


@pytest.mark.parametrize(
    ("returned", "location"),
    [
        ({"state": "violated"}, "$.result"),
        (_result(evaluator=VersionedReference("other", 1)), "$.result.evaluator"),
        (_result(input_revision="other-v1"), "$.result.input-revision"),
        (_result(state="unknown"), "$.result.state"),
        (_result(state=EvaluationState.SATISFIED), "$.result.state"),
        (_result(evidence="not-an-object"), "$.result.evidence"),
        (
            _result(evidence={"outcome": "invalid", "detail": object()}),
            "$.result.evidence",
        ),
        (
            _result(evidence={"outcome": "invalid", "detail": 3}),
            "$.result.evidence.detail",
        ),
    ],
)
def test_result_identity_revision_state_and_evidence_are_enforced(
    tmp_path: Path, returned: object, location: str
) -> None:
    declarations = _declarations(tmp_path)

    def runner(input_data: Mapping[str, JsonValue], /) -> CheckerResult:
        return cast(CheckerResult, returned)

    with pytest.raises(CheckerExecutionError) as captured:
        execute_checker(
            _runners(declarations, runner),
            CHECKER,
            input_revision="declaration-v1",
            input_data=_valid_input(),
            expected_state=EvaluationState.VIOLATED,
        )
    assert captured.value.location == location


def test_cyclic_evidence_is_a_located_execution_error(tmp_path: Path) -> None:
    declarations = _declarations(tmp_path)
    cycle: dict[str, object] = {"outcome": "invalid"}
    cycle["detail"] = cycle
    with pytest.raises(CheckerExecutionError) as captured:
        execute_checker(
            _runners(declarations, lambda input_data: _result(evidence=cycle)),
            CHECKER,
            input_revision="declaration-v1",
            input_data=_valid_input(),
        )
    assert captured.value.location == "$.result.evidence"
    assert "cyclic containers" in str(captured.value)


def test_known_failure_binding_executes_canonical_resources(
    tmp_path: Path,
) -> None:
    declarations = _declarations(tmp_path)
    received: Mapping[str, JsonValue] | None = None

    def runner(input_data: Mapping[str, JsonValue], /) -> CheckerResult:
        nonlocal received
        received = input_data
        return _result()

    runners = _runners(declarations, runner)
    fixtures = _fixture_index(tmp_path, runners.input_contracts)
    results = execute_known_failure_fixtures(declarations, fixtures, runners)

    assert tuple(results) == (FIXTURE_ID,)
    assert received is not None
    assert Path(cast(tuple[str, ...], received["sources"])[0]).is_absolute()
    assert Path(cast(str, received["facet-registry"])).is_absolute()
    with pytest.raises(TypeError):
        results["other"] = _result()  # type: ignore[index]


def test_missing_declared_fixture_is_located_at_the_declaration(
    tmp_path: Path,
) -> None:
    declarations = _declarations(tmp_path)
    runners = _runners(declarations, lambda input_data: _result())
    fixtures = _fixture_index(
        tmp_path, runners.input_contracts, include_descriptor=False
    )
    with pytest.raises(CheckerExecutionError) as captured:
        execute_known_failure_fixtures(declarations, fixtures, runners)
    assert captured.value.path is not None
    assert captured.value.path.name == "checker.yaml"
    assert captured.value.location == "$.known-failure-fixtures[0]"
    assert captured.value.line is not None


def test_runner_registry_cannot_validate_a_different_declaration_registry(
    tmp_path: Path,
) -> None:
    runner_declarations = _declarations(tmp_path / "runner", detail_type="string")
    execution_declarations = _declarations(
        tmp_path / "execution", detail_type="integer"
    )
    runners = _runners(runner_declarations, lambda input_data: _result())
    fixtures = _fixture_index(tmp_path, runners.input_contracts)
    with pytest.raises(CheckerExecutionError) as captured:
        execute_known_failure_fixtures(execution_declarations, fixtures, runners)
    assert captured.value.location == "$"
    assert "different declaration registry" in str(captured.value)


def test_fixture_must_point_back_to_its_declaring_evaluator(tmp_path: Path) -> None:
    declarations = _declarations(tmp_path)
    runners = _runners(declarations, lambda input_data: _result())
    manual = VersionedReference("registry/manual", 1)
    contracts = dict(runners.input_contracts)
    contracts[manual] = runners.input_contracts[CHECKER]
    fixtures = _fixture_index(tmp_path, contracts, evaluator=manual)
    with pytest.raises(CheckerExecutionError) as captured:
        execute_known_failure_fixtures(declarations, fixtures, runners)
    assert captured.value.path is not None
    assert captured.value.path.name == "known-failure.yaml"
    assert captured.value.location == "$.evaluator"
    assert captured.value.line is not None


def test_missing_runner_is_located_at_the_fixture_evaluator(tmp_path: Path) -> None:
    declarations = _declarations(tmp_path)
    complete = _runners(declarations, lambda input_data: _result())
    fixtures = _fixture_index(tmp_path, complete.input_contracts)
    empty = build_checker_runner_registry(declarations, [])
    with pytest.raises(CheckerExecutionError) as captured:
        execute_known_failure_fixtures(declarations, fixtures, empty)
    assert captured.value.path is not None
    assert captured.value.path.name == "known-failure.yaml"
    assert captured.value.location == "$.evaluator"
    assert captured.value.line is not None


def test_fixture_input_revision_failure_retains_source_location(tmp_path: Path) -> None:
    declarations = _declarations(tmp_path, input_revisions=["different-revision"])
    runners = _runners(declarations, lambda input_data: _result())
    fixtures = _fixture_index(tmp_path, runners.input_contracts)
    with pytest.raises(CheckerExecutionError) as captured:
        execute_known_failure_fixtures(declarations, fixtures, runners)
    assert captured.value.location == "$.input-revision"
    assert captured.value.line is not None


def test_canonicalized_input_failure_retains_descriptor_location(
    tmp_path: Path,
) -> None:
    declarations = _declarations(tmp_path, relative_paths_only=True)
    runners = _runners(declarations, lambda input_data: _result())
    fixtures = _fixture_index(tmp_path, runners.input_contracts)
    with pytest.raises(CheckerExecutionError) as captured:
        execute_known_failure_fixtures(declarations, fixtures, runners)
    assert captured.value.location == "$.input.sources[0]"
    assert captured.value.line is not None


def test_raw_fixture_input_is_revalidated_against_bound_operation_contract(
    tmp_path: Path,
) -> None:
    declarations = _declarations(tmp_path, absolute_paths_only=True)
    runners = _runners(declarations, lambda input_data: _result())
    permissive_schema = {
        "type": "object",
        "required": ["sources", "facet-registry"],
        "properties": {
            "sources": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string"},
            },
            "facet-registry": {"type": "string"},
        },
        "additionalProperties": False,
    }
    fixtures = _fixture_index(tmp_path, {CHECKER: permissive_schema})
    with pytest.raises(CheckerExecutionError) as captured:
        execute_known_failure_fixtures(declarations, fixtures, runners)
    assert captured.value.location == "$.input.sources[0]"
    assert captured.value.line is not None
    assert "operation contract" in str(captured.value)
