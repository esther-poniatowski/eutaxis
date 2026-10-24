"""Execute checker runners and validate every declared result contract."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Mapping, NoReturn, cast

from .embedded_schema import validate_json_instance
from .exceptions import CheckerExecutionError
from .fixtures import EvaluatorFixture, EvaluatorFixtureIndex
from .models import (
    DeclarationKind,
    EvaluatorDeclaration,
    JsonValue,
    VersionedReference,
    freeze_json,
)
from .registry import DeclarationRegistry, RegisteredDeclaration
from .results import CheckerResult, EvaluationState
from .runners import CheckerRunnerRegistry
from .source import DocumentPath, SourceMap, format_document_path, nearest_location


def execute_checker(
    runners: CheckerRunnerRegistry,
    evaluator: VersionedReference,
    *,
    input_revision: str,
    input_data: Mapping[str, object],
    expected_state: EvaluationState | None = None,
    path: Path | None = None,
) -> CheckerResult:
    """Invoke one exact checker and validate its complete returned contract."""
    binding = runners.bindings.get(evaluator)
    if binding is None:
        _raise_execution_error(
            ("evaluator",),
            f"no runner is registered for evaluator {evaluator.id!r}@{evaluator.version}",
            path=path,
        )
    evaluator_record = runners.evaluator_records[evaluator]
    contract = cast(EvaluatorDeclaration, evaluator_record.declaration)
    if input_revision not in contract.input_revisions:
        _raise_execution_error(
            ("input-revision",),
            f"input revision {input_revision!r} is not admitted by the evaluator",
            path=path,
        )
    try:
        frozen_input = freeze_json(input_data)
    except Exception as exc:
        _raise_execution_error(
            ("input",),
            f"input is not finite JSON: {type(exc).__name__}: {exc}",
            path=path,
            cause=exc,
        )
    if not isinstance(frozen_input, Mapping):
        _raise_execution_error(("input",), "input must be a JSON object", path=path)
    immutable_input = cast(Mapping[str, JsonValue], frozen_input)
    input_error = validate_json_instance(
        runners.input_contracts[evaluator], immutable_input
    )
    if input_error is not None:
        parts = ("input",) + tuple(input_error.absolute_path)
        _raise_execution_error(
            parts,
            f"input violates the registered operation contract: {input_error.message}",
            path=path,
        )
    try:
        returned = binding.runner(immutable_input)
    except Exception as exc:
        _raise_execution_error(
            ("runner",),
            f"runner raised {type(exc).__name__}: {exc}",
            path=path,
            cause=exc,
        )
    return _validate_result(
        returned,
        contract=contract,
        evaluator=evaluator,
        input_revision=input_revision,
        expected_state=expected_state,
        path=path,
    )


def execute_known_failure_fixtures(
    declarations: DeclarationRegistry,
    fixtures: EvaluatorFixtureIndex,
    runners: CheckerRunnerRegistry,
) -> Mapping[str, CheckerResult]:
    """Resolve and execute every checker-declared known-failure fixture."""
    if declarations is not runners.declarations:
        raise CheckerExecutionError(
            "$",
            "runner registry was built from a different declaration registry",
        )
    owners: dict[str, VersionedReference] = {}
    for family_id in sorted(declarations.families):
        family = declarations.families[family_id]
        if family.kind is not DeclarationKind.EVALUATOR:
            continue
        for version in sorted(family.versions):
            record = family.versions[version]
            evaluator_contract = cast(EvaluatorDeclaration, record.declaration)
            if evaluator_contract.evaluator_kind != "checker":
                continue
            reference = VersionedReference(
                evaluator_contract.id, evaluator_contract.version
            )
            for index, fixture_id in enumerate(
                evaluator_contract.known_failure_fixtures
            ):
                fixture = fixtures.fixtures.get(fixture_id)
                if fixture is None:
                    _raise_record_error(
                        record,
                        ("known-failure-fixtures", index),
                        f"unknown evaluator fixture {fixture_id!r}",
                    )
                if fixture.evaluator != reference:
                    _raise_fixture_error(
                        fixture,
                        ("evaluator",),
                        f"fixture points to {fixture.evaluator.id!r}@{fixture.evaluator.version}, not {reference.id!r}@{reference.version}",
                    )
                owners[fixture_id] = reference

    results: dict[str, CheckerResult] = {}
    for fixture_id, fixture in fixtures.fixtures.items():
        owner_reference = owners.get(fixture_id)
        if owner_reference is None:
            continue
        if owner_reference not in runners.bindings:
            _raise_fixture_error(
                fixture,
                ("evaluator",),
                f"no runner is registered for evaluator {owner_reference.id!r}@{owner_reference.version}",
            )
        raw_input_error = validate_json_instance(
            runners.input_contracts[owner_reference], fixture.input
        )
        if raw_input_error is not None:
            _raise_fixture_error(
                fixture,
                ("input",) + tuple(raw_input_error.absolute_path),
                f"input violates the registered operation contract: {raw_input_error.message}",
            )
        invocation_input: Mapping[str, object] = {
            "sources": [str(path) for path in fixture.sources],
            "facet-registry": str(fixture.facet_registry),
        }
        try:
            expected_state = EvaluationState(fixture.expected_state)
        except ValueError:
            _raise_fixture_error(
                fixture,
                ("expected-state",),
                f"unknown expected state {fixture.expected_state!r}",
            )
        try:
            results[fixture_id] = execute_checker(
                runners,
                owner_reference,
                input_revision=fixture.input_revision,
                input_data=invocation_input,
                expected_state=expected_state,
                path=fixture.path,
            )
        except CheckerExecutionError as exc:
            if exc.document_path in {
                ("evaluator",),
                ("input-revision",),
            }:
                _raise_fixture_error(
                    fixture,
                    cast(DocumentPath, exc.document_path),
                    exc.detail,
                )
            if exc.document_path and exc.document_path[0] == "input":
                _raise_fixture_error(
                    fixture,
                    cast(DocumentPath, exc.document_path),
                    exc.detail,
                )
            raise
    return MappingProxyType(results)


def _validate_result(
    returned: object,
    *,
    contract: EvaluatorDeclaration,
    evaluator: VersionedReference,
    input_revision: str,
    expected_state: EvaluationState | None,
    path: Path | None,
) -> CheckerResult:
    """Validate untrusted runner output and return an immutable copy."""
    if not isinstance(returned, CheckerResult):
        _raise_execution_error(
            ("result",), "runner did not return CheckerResult", path=path
        )
    if returned.evaluator != evaluator:
        _raise_execution_error(
            ("result", "evaluator"),
            "returned evaluator identity differs from the invocation",
            path=path,
        )
    if returned.input_revision != input_revision:
        _raise_execution_error(
            ("result", "input-revision"),
            "returned input revision differs from the invocation",
            path=path,
        )
    if not isinstance(returned.state, EvaluationState):
        _raise_execution_error(
            ("result", "state"),
            f"unknown result state {returned.state!r}",
            path=path,
        )
    if expected_state is not None and returned.state is not expected_state:
        _raise_execution_error(
            ("result", "state"),
            f"result state {returned.state.value!r} differs from expected {expected_state.value!r}",
            path=path,
        )
    if not isinstance(returned.evidence, Mapping):
        _raise_execution_error(
            ("result", "evidence"),
            "result evidence must be a JSON object",
            path=path,
        )
    try:
        evidence = cast(Mapping[str, JsonValue], freeze_json(returned.evidence))
    except Exception as exc:
        _raise_execution_error(
            ("result", "evidence"),
            f"result evidence is not finite JSON: {type(exc).__name__}: {exc}",
            path=path,
            cause=exc,
        )
    evidence_error = validate_json_instance(
        cast(Mapping[str, object], contract.evidence_schema), evidence
    )
    if evidence_error is not None:
        parts = ("result", "evidence") + tuple(evidence_error.absolute_path)
        _raise_execution_error(
            parts,
            f"result evidence violates the evaluator contract: {evidence_error.message}",
            path=path,
        )
    return CheckerResult(
        evaluator=evaluator,
        input_revision=input_revision,
        state=returned.state,
        evidence=evidence,
    )


def _raise_record_error(
    record: RegisteredDeclaration,
    parts: DocumentPath,
    message: str,
) -> NoReturn:
    """Raise one execution error at an evaluator declaration field."""
    absolute = record.root + parts
    source = nearest_location(record.source.locations, absolute)
    raise CheckerExecutionError(
        format_document_path(absolute),
        message,
        document_path=absolute,
        path=record.source.path,
        line=source.line if source else None,
        column=source.column if source else None,
    )


def _raise_fixture_error(
    fixture: EvaluatorFixture,
    parts: DocumentPath,
    message: str,
) -> NoReturn:
    """Raise one execution error at a fixture descriptor field."""
    source = nearest_location(fixture.locations, parts)
    raise CheckerExecutionError(
        format_document_path(parts),
        message,
        document_path=parts,
        path=fixture.path,
        line=source.line if source else None,
        column=source.column if source else None,
    )


def _raise_execution_error(
    parts: DocumentPath,
    message: str,
    *,
    path: Path | None,
    cause: Exception | None = None,
) -> NoReturn:
    """Raise one execution error with a reusable structured result path."""
    error = CheckerExecutionError(
        format_document_path(parts),
        message,
        document_path=parts,
        path=path,
    )
    if cause is not None:
        raise error from cause
    raise error
