"""Execute checker runners and validate every declared result contract."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import NoReturn, SupportsIndex, cast

from ._runner_support import exception_detail
from .embedded_schema import validate_json_instance
from .exceptions import CheckerExecutionError, DetectorExecutionError
from .fixtures import (
    EvaluatorFixture,
    EvaluatorFixtureIndex,
    _is_loader_issued_fixture_index,
)
from .models import (
    DeclarationKind,
    EvaluatorDeclaration,
    JsonValue,
    VersionedReference,
    freeze_json,
)
from .registry import DeclarationRegistry, RegisteredDeclaration
from .results import CheckerResult, DetectorResult, EvaluationState
from .runners import (
    CheckerRunnerRegistry,
    DetectorRunnerRegistry,
    _is_builder_issued_detector_registry,
)
from .source import DocumentPath, SourceMap, format_document_path, nearest_location

_ASSURANCE_ISSUER = object()
_DETECTOR_EXECUTION_ISSUER = object()


@dataclass(frozen=True, init=False, eq=False)
class DetectorExecution:
    """Process-local proof of one structurally validated detector run."""

    registry: DetectorRunnerRegistry
    evaluator: VersionedReference
    input_revision: str
    input_data: Mapping[str, JsonValue]
    evidence: Mapping[str, JsonValue]
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Reject construction outside detector execution."""
        raise TypeError("DetectorExecution instances must be issued by execution")

    def __copy__(self) -> NoReturn:
        raise TypeError("DetectorExecution instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("DetectorExecution instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("DetectorExecution instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("DetectorExecution instances cannot be serialized")


def _is_issued_detector_execution(execution: object) -> bool:
    """Return whether ``execution`` carries this process's executor authority."""
    return (
        isinstance(execution, DetectorExecution)
        and getattr(execution, "_issuer", None) is _DETECTOR_EXECUTION_ISSUER
    )


@dataclass(frozen=True)
class KnownFailureFixtureResult:
    """One declared fixture identifier paired with its validated result."""

    fixture_id: str
    result: CheckerResult


@dataclass(frozen=True)
class KnownFailureEvaluatorAssurance:
    """The complete authored fixture sequence validated for one checker."""

    evaluator: VersionedReference
    fixtures: tuple[KnownFailureFixtureResult, ...]


@dataclass(frozen=True, init=False, eq=False)
class KnownFailureAssurance(Mapping[str, CheckerResult]):
    """Process-local proof that one exact known-failure run succeeded."""

    declarations: DeclarationRegistry
    fixtures: EvaluatorFixtureIndex
    runners: CheckerRunnerRegistry
    evaluators: Mapping[VersionedReference, KnownFailureEvaluatorAssurance]
    _results: Mapping[str, CheckerResult]
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Reject construction outside known-failure execution."""
        raise TypeError(
            "KnownFailureAssurance instances must be issued by known-failure execution"
        )

    def __getitem__(self, fixture_id: str) -> CheckerResult:
        """Return the validated result for one declared fixture."""
        return self._results[fixture_id]

    def __iter__(self) -> Iterator[str]:
        """Iterate fixture identifiers in canonical execution order."""
        return iter(self._results)

    def __len__(self) -> int:
        """Return the number of executed declared fixtures."""
        return len(self._results)

    def __eq__(self, other: object) -> bool:
        """Compare assurances only by process-local object identity."""
        return self is other

    def __ne__(self, other: object) -> bool:
        """Distinguish assurances only by process-local object identity."""
        return self is not other

    __hash__ = object.__hash__

    def __copy__(self) -> NoReturn:
        """Reject reconstruction by shallow copying."""
        raise TypeError("KnownFailureAssurance instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        """Reject reconstruction by deep copying."""
        raise TypeError("KnownFailureAssurance instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        """Reject serialization and reconstruction."""
        raise TypeError("KnownFailureAssurance instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        """Reject protocol-specific serialization and reconstruction."""
        raise TypeError("KnownFailureAssurance instances cannot be serialized")


def execute_detector(
    registry: DetectorRunnerRegistry,
    evaluator: VersionedReference,
    *,
    input_revision: str,
    input_data: Mapping[str, object],
    path: Path | None = None,
) -> DetectorExecution:
    """Invoke one detector and issue its immutable validated execution."""
    if not _is_builder_issued_detector_registry(registry):
        _raise_detector_execution_error(
            (), "detector registry was not issued by its validated builder", path=path
        )
    binding = registry.bindings.get(evaluator)
    if binding is None:
        _raise_detector_execution_error(
            ("evaluator",),
            f"no runner is registered for evaluator {evaluator.id!r}@{evaluator.version}",
            path=path,
        )
    record = registry.evaluator_records[evaluator]
    contract = cast(EvaluatorDeclaration, record.declaration)
    if input_revision not in contract.input_revisions:
        _raise_detector_execution_error(
            ("input-revision",),
            f"input revision {input_revision!r} is not admitted by the evaluator",
            path=path,
        )
    immutable_input = _freeze_validate_input(
        input_data,
        registry.input_contracts[evaluator],
        path=path,
        detector=True,
    )
    try:
        returned = binding.runner(immutable_input)
    except Exception as exc:
        _raise_detector_execution_error(
            ("runner",),
            f"runner raised {exception_detail(exc)}",
            path=path,
            cause=exc,
        )
    if not isinstance(returned, DetectorResult):
        _raise_detector_execution_error(
            ("result",), "runner did not return DetectorResult", path=path
        )
    if returned.evaluator != evaluator:
        _raise_detector_execution_error(
            ("result", "evaluator"),
            "returned evaluator identity differs from the invocation",
            path=path,
        )
    if returned.input_revision != input_revision:
        _raise_detector_execution_error(
            ("result", "input-revision"),
            "returned input revision differs from the invocation",
            path=path,
        )
    evidence = _freeze_validate_evidence(
        returned.evidence,
        cast(Mapping[str, object], contract.evidence_schema),
        path=path,
        detector=True,
    )
    execution = object.__new__(DetectorExecution)
    object.__setattr__(execution, "registry", registry)
    object.__setattr__(execution, "evaluator", evaluator)
    object.__setattr__(execution, "input_revision", input_revision)
    object.__setattr__(execution, "input_data", immutable_input)
    object.__setattr__(execution, "evidence", evidence)
    object.__setattr__(execution, "_issuer", _DETECTOR_EXECUTION_ISSUER)
    return execution


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
    immutable_input = _freeze_validate_input(
        input_data,
        runners.input_contracts[evaluator],
        path=path,
        detector=False,
    )
    try:
        returned = binding.runner(immutable_input)
    except Exception as exc:
        _raise_execution_error(
            ("runner",),
            f"runner raised {exception_detail(exc)}",
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
) -> KnownFailureAssurance:
    """Execute every declared known failure and issue its correlated assurance."""
    if not _is_loader_issued_fixture_index(fixtures):
        raise CheckerExecutionError(
            "$",
            "fixture index was not issued by validated fixture loading",
        )
    if declarations is not runners.declarations:
        raise CheckerExecutionError(
            "$",
            "runner registry was built from a different declaration registry",
        )
    plans: list[
        tuple[
            VersionedReference,
            RegisteredDeclaration,
            tuple[EvaluatorFixture, ...],
        ]
    ] = []
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
            authored_fixtures: list[EvaluatorFixture] = []
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
                authored_fixtures.append(fixture)
            plans.append((reference, record, tuple(authored_fixtures)))

    results: dict[str, CheckerResult] = {}
    evaluator_assurances: dict[VersionedReference, KnownFailureEvaluatorAssurance] = {}
    for reference, _record, plan_fixtures in plans:
        paired_results: list[KnownFailureFixtureResult] = []
        for fixture in plan_fixtures:
            if reference not in runners.bindings:
                _raise_fixture_error(
                    fixture,
                    ("evaluator",),
                    f"no runner is registered for evaluator {reference.id!r}@{reference.version}",
                )
            raw_input_error = validate_json_instance(
                runners.input_contracts[reference], fixture.input
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
            _verify_fixture_digests(fixture)
            try:
                try:
                    result = execute_checker(
                        runners,
                        reference,
                        input_revision=fixture.input_revision,
                        input_data=invocation_input,
                        expected_state=expected_state,
                        path=fixture.path,
                    )
                finally:
                    _verify_fixture_digests(fixture)
            except CheckerExecutionError as exc:
                _relocate_fixture_execution_error(fixture, exc)
            results[fixture.id] = result
            paired_results.append(
                KnownFailureFixtureResult(fixture_id=fixture.id, result=result)
            )
        expected_ids = tuple(fixture.id for fixture in plan_fixtures)
        actual_ids = tuple(pair.fixture_id for pair in paired_results)
        if len(paired_results) != len(expected_ids) or actual_ids != expected_ids:
            raise AssertionError("known-failure assurance lost declared fixture order")
        evaluator_assurances[reference] = KnownFailureEvaluatorAssurance(
            evaluator=reference,
            fixtures=tuple(paired_results),
        )

    for _reference, _record, plan_fixtures in plans:
        for fixture in plan_fixtures:
            _verify_fixture_digests(fixture)

    return _issue_known_failure_assurance(
        declarations,
        fixtures,
        runners,
        evaluator_assurances,
        results,
    )


def _issue_known_failure_assurance(
    declarations: DeclarationRegistry,
    fixtures: EvaluatorFixtureIndex,
    runners: CheckerRunnerRegistry,
    evaluators: Mapping[VersionedReference, KnownFailureEvaluatorAssurance],
    results: Mapping[str, CheckerResult],
) -> KnownFailureAssurance:
    """Issue one process-local aggregate after complete execution validation."""
    assurance = object.__new__(KnownFailureAssurance)
    object.__setattr__(assurance, "declarations", declarations)
    object.__setattr__(assurance, "fixtures", fixtures)
    object.__setattr__(assurance, "runners", runners)
    object.__setattr__(assurance, "evaluators", MappingProxyType(dict(evaluators)))
    object.__setattr__(assurance, "_results", MappingProxyType(dict(results)))
    object.__setattr__(assurance, "_issuer", _ASSURANCE_ISSUER)
    return assurance


def _verify_fixture_digests(fixture: EvaluatorFixture) -> None:
    """Reject a fixture file occurrence that differs from its loaded bytes."""
    cache: dict[Path, str] = {}
    for digest in fixture.digests:
        try:
            if digest.path not in cache:
                cache[digest.path] = hashlib.sha256(
                    digest.path.read_bytes()
                ).hexdigest()
            observed = cache[digest.path]
        except OSError as exc:
            _raise_fixture_error(
                fixture,
                digest.document_path,
                f"{digest.role} file cannot be read during assurance: {exc}",
            )
        if observed != digest.sha256:
            _raise_fixture_error(
                fixture,
                digest.document_path,
                f"{digest.role} file changed after the fixture index was loaded",
            )


def _relocate_fixture_execution_error(
    fixture: EvaluatorFixture, error: CheckerExecutionError
) -> NoReturn:
    """Move input-contract failures from invocation paths to descriptor fields."""
    if error.document_path in {
        ("evaluator",),
        ("input-revision",),
    }:
        _raise_fixture_error(
            fixture,
            cast(DocumentPath, error.document_path),
            error.detail,
        )
    if error.document_path and error.document_path[0] == "input":
        _raise_fixture_error(
            fixture,
            cast(DocumentPath, error.document_path),
            error.detail,
        )
    raise error


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
    evidence = _freeze_validate_evidence(
        returned.evidence,
        cast(Mapping[str, object], contract.evidence_schema),
        path=path,
        detector=False,
    )
    return CheckerResult(
        evaluator=evaluator,
        input_revision=input_revision,
        state=returned.state,
        evidence=evidence,
    )


def _freeze_validate_input(
    input_data: object,
    input_schema: Mapping[str, object],
    *,
    path: Path | None,
    detector: bool,
) -> Mapping[str, JsonValue]:
    """Freeze one evaluator input and validate its operation contract."""
    try:
        frozen_input = freeze_json(input_data)
    except Exception as exc:
        _raise_evaluator_execution_error(
            detector,
            ("input",),
            f"input is not finite JSON: {exception_detail(exc)}",
            path=path,
            cause=exc,
        )
    if not isinstance(frozen_input, Mapping):
        _raise_evaluator_execution_error(
            detector, ("input",), "input must be a JSON object", path=path
        )
    immutable_input = cast(Mapping[str, JsonValue], frozen_input)
    input_error = validate_json_instance(input_schema, immutable_input)
    if input_error is not None:
        parts = ("input",) + tuple(input_error.absolute_path)
        _raise_evaluator_execution_error(
            detector,
            parts,
            f"input violates the registered operation contract: {input_error.message}",
            path=path,
        )
    return immutable_input


def _freeze_validate_evidence(
    evidence_data: object,
    evidence_schema: Mapping[str, object],
    *,
    path: Path | None,
    detector: bool,
) -> Mapping[str, JsonValue]:
    """Freeze one evaluator evidence object and validate its contract."""
    if not isinstance(evidence_data, Mapping):
        _raise_evaluator_execution_error(
            detector,
            ("result", "evidence"),
            "result evidence must be a JSON object",
            path=path,
        )
    try:
        evidence = cast(Mapping[str, JsonValue], freeze_json(evidence_data))
    except Exception as exc:
        _raise_evaluator_execution_error(
            detector,
            ("result", "evidence"),
            f"result evidence is not finite JSON: {exception_detail(exc)}",
            path=path,
            cause=exc,
        )
    evidence_error = validate_json_instance(evidence_schema, evidence)
    if evidence_error is not None:
        parts = ("result", "evidence") + tuple(evidence_error.absolute_path)
        _raise_evaluator_execution_error(
            detector,
            parts,
            f"result evidence violates the evaluator contract: {evidence_error.message}",
            path=path,
        )
    return evidence


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


def _raise_detector_execution_error(
    parts: DocumentPath,
    message: str,
    *,
    path: Path | None,
    cause: Exception | None = None,
) -> NoReturn:
    """Raise one detector-owned invocation or result diagnostic."""
    error = DetectorExecutionError(
        format_document_path(parts),
        message,
        document_path=parts,
        path=path,
    )
    if cause is not None:
        raise error from cause
    raise error


def _raise_evaluator_execution_error(
    detector: bool,
    parts: DocumentPath,
    message: str,
    *,
    path: Path | None,
    cause: Exception | None = None,
) -> NoReturn:
    """Dispatch a shared validation defect to its public façade."""
    if detector:
        _raise_detector_execution_error(parts, message, path=path, cause=cause)
    _raise_execution_error(parts, message, path=path, cause=cause)
