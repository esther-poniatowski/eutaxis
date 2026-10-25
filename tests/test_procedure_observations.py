"""Adversarial tests for coherent evaluator-less procedure observations."""

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
    AtomicApplicabilityTrace,
    BooleanApplicabilityTrace,
    ObservationProvider,
    ObservationProviderRegistry,
    ObservationProviderRegistryError,
    ObservationRequest,
    OperationFailure,
    OperationRunner,
    OperationRunnerBinding,
    PredicatePhase,
    ProcedureObservationError,
    ProcedurePreconditionObservation,
    ProcedurePredicateKey,
    ProcedurePredicateObservation,
    TruthValue,
    VersionedReference,
    build_observation_provider_registry,
    build_operation_runner_registry,
    derive_attention_requirements,
    load_declaration_registry,
    load_facet_registry,
    observe_procedure_preconditions,
    plan_attention,
    prepare_procedure_run,
    resolve_compilation_unit,
)
from eutaxis.declarations.models import JsonValue
from eutaxis.declarations.observations import (
    _is_builder_issued_observation_registry,
    _is_issued_procedure_precondition_observation,
)
from eutaxis.declarations.procedure_runs import ProcedureRunPlan

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY_FIXTURES = FIXTURES / "registry" / "valid"
FACET_FIXTURE = FIXTURES / "facets" / "valid" / "context-facets.yaml"
PROCEDURE = "content/write"
WRITE = VersionedReference("registry/write", 1)


def _context() -> dict[str, object]:
    """Return the complete context required to resolve the fixture manifest."""
    return {
        "artifact.created": True,
        "artifact.written": True,
        "context.available": True,
        "filesystem.writable": True,
        "scope.project": True,
        "source.available": True,
        "target.codex": True,
    }


def _nested_expression() -> dict[str, object]:
    """Reference two facets recursively while repeating the first facet."""
    return {
        "all": [
            {"facet": "context.available", "operator": "equals", "value": True},
            {
                "any": [
                    {
                        "facet": "source.available",
                        "operator": "equals",
                        "value": True,
                    },
                    {
                        "facet": "context.available",
                        "operator": "equals",
                        "value": False,
                    },
                ]
            },
            {
                "not": {
                    "facet": "context.available",
                    "operator": "equals",
                    "value": False,
                }
            },
        ]
    }


def _precondition(identifier: str, expression: object) -> dict[str, object]:
    """Build one evaluator-less procedure precondition fixture."""
    return {"id": identifier, "class": "assumption", "expression": expression}


def _run_plan(tmp_path: Path, *, empty: bool = False) -> ProcedureRunPlan:
    """Build one issued run plan over an isolated mutable fixture corpus."""
    root = tmp_path / "registry"
    shutil.copytree(REGISTRY_FIXTURES, root)
    procedure_path = root / "procedure.yaml"
    procedure = yaml.safe_load(procedure_path.read_text(encoding="utf-8"))
    procedure["preconditions"] = (
        []
        if empty
        else [
            _precondition("nested", _nested_expression()),
            _precondition(
                "present",
                {"facet": "context.available", "operator": "exists"},
            ),
        ]
    )
    procedure_path.write_text(
        yaml.safe_dump(procedure, sort_keys=False), encoding="utf-8"
    )
    facets = load_facet_registry(FACET_FIXTURE)
    declarations = load_declaration_registry(sorted(root.glob("*.yaml")), facets)
    resolution = resolve_compilation_unit(declarations, "registry/manifest", _context())
    requirements = derive_attention_requirements(resolution)
    attention = plan_attention(requirements, {})

    def runner(input_data: Mapping[str, JsonValue], /) -> OperationFailure:
        return OperationFailure(WRITE, "write-failed")

    operations = build_operation_runner_registry(
        declarations,
        [OperationRunnerBinding(WRITE, cast(OperationRunner, runner))],
    )
    return prepare_procedure_run(
        attention, PROCEDURE, {"path": "artifact.txt"}, operations
    )


def _registry(run: ProcedureRunPlan, provider: object) -> ObservationProviderRegistry:
    """Build one observer registry correlated with ``run``."""
    declarations = run.attention.resolution.registry
    return build_observation_provider_registry(
        declarations,
        declarations.facet_registry,
        cast(ObservationProvider, provider),
    )


def _atomic_traces(trace: object) -> tuple[AtomicApplicabilityTrace, ...]:
    """Flatten the atomic leaves of one issued applicability trace."""
    if isinstance(trace, AtomicApplicabilityTrace):
        return (trace,)
    assert isinstance(trace, BooleanApplicabilityTrace)
    return tuple(child for item in trace.children for child in _atomic_traces(item))


def test_observation_uses_one_minimal_coherent_snapshot(tmp_path: Path) -> None:
    run = _run_plan(tmp_path)
    calls: list[ObservationRequest] = []
    source = {"context.available": True, "source.available": True}

    def provider(request: ObservationRequest) -> Mapping[str, object]:
        calls.append(request)
        assert request.procedure == PROCEDURE
        assert request.phase is PredicatePhase.PRECONDITION
        assert request.occurrence == 0
        assert request.facets == ("context.available", "source.available")
        assert request.parameters == {"path": "artifact.txt"}
        with pytest.raises(TypeError):
            request.parameters["path"] = "changed"  # type: ignore[index]
        return source

    registry = _registry(run, provider)
    evidence = observe_procedure_preconditions(run, registry)
    source["context.available"] = False

    assert len(calls) == 1
    assert evidence.run is run
    assert evidence.registry is registry
    assert evidence.phase is PredicatePhase.PRECONDITION
    assert evidence.occurrence == 0
    assert _is_issued_procedure_precondition_observation(evidence)
    assert tuple(record.requirement for record in evidence.observations) == (
        evidence.requirements
    )
    assert all(
        actual is expected
        for actual, expected in zip(
            evidence.requirements,
            (
                item
                for item in run.requirements
                if item.evaluator is None
                and isinstance(item.key, ProcedurePredicateKey)
                and item.key.phase is PredicatePhase.PRECONDITION
            ),
        )
    )
    assert tuple(record.truth for record in evidence.observations) == (
        TruthValue.TRUE,
        TruthValue.TRUE,
    )
    leaves = _atomic_traces(evidence.observations[0].trace)
    assert tuple(item.facet for item in leaves) == (
        "context.available",
        "source.available",
        "context.available",
        "context.available",
    )
    assert tuple(item.observed for item in leaves) == (True, True, True, True)
    assert not hasattr(evidence, "context")


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (
            {"context.available": False, "source.available": True},
            TruthValue.FALSE,
        ),
        ({"context.available": True}, TruthValue.UNKNOWN),
    ],
)
def test_false_and_unknown_are_issued_as_evidence(
    tmp_path: Path, result: dict[str, object], expected: TruthValue
) -> None:
    run = _run_plan(tmp_path)
    evidence = observe_procedure_preconditions(
        run, _registry(run, lambda request: result)
    )

    assert evidence.observations[0].truth is expected


def test_empty_selection_does_not_invoke_provider(tmp_path: Path) -> None:
    run = _run_plan(tmp_path, empty=True)

    def provider(request: ObservationRequest) -> Mapping[str, object]:
        raise AssertionError("provider must not run for an empty selection")

    evidence = observe_procedure_preconditions(run, _registry(run, provider))

    assert evidence.requirements == ()
    assert evidence.observations == ()


def test_observation_authorities_are_private_and_identity_valued(
    tmp_path: Path,
) -> None:
    run = _run_plan(tmp_path)
    first_registry = _registry(run, lambda request: {})
    second_registry = _registry(run, lambda request: {})
    first = observe_procedure_preconditions(run, first_registry)
    second = observe_procedure_preconditions(run, first_registry)

    assert first_registry is not second_registry
    assert first_registry != second_registry
    assert _is_builder_issued_observation_registry(first_registry)
    assert first is not second
    assert first != second
    with pytest.raises(TypeError, match="issued by its builder"):
        ObservationProviderRegistry()
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(first_registry)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.deepcopy(first_registry)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(first_registry)
    with pytest.raises(TypeError, match="issued by observation"):
        ProcedurePreconditionObservation()
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(first)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.deepcopy(first)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(first)
    with pytest.raises(TypeError, match="issued by observation"):
        ObservationRequest()

    reconstructed = object.__new__(ProcedurePreconditionObservation)
    for field in (
        "run",
        "registry",
        "phase",
        "occurrence",
        "requirements",
        "observations",
    ):
        object.__setattr__(reconstructed, field, getattr(first, field))
    assert not _is_issued_procedure_precondition_observation(reconstructed)


def test_observation_validator_rejects_corrupted_issued_correlations(
    tmp_path: Path,
) -> None:
    run = _run_plan(tmp_path / "primary")
    registry = _registry(run, lambda request: {})
    foreign_run = _run_plan(tmp_path / "foreign")
    foreign_registry = _registry(foreign_run, lambda request: {})

    def issued() -> ProcedurePreconditionObservation:
        return observe_procedure_preconditions(run, registry)

    baseline = issued()
    corrupted_fields = (
        ("run", foreign_run),
        ("registry", foreign_registry),
        ("phase", PredicatePhase.INVARIANT),
        ("occurrence", 1),
        ("occurrence", False),
        ("requirements", tuple(reversed(baseline.requirements))),
        ("requirements", list(baseline.requirements)),
        ("observations", tuple(reversed(baseline.observations))),
        ("observations", list(baseline.observations)),
    )
    for field, value in corrupted_fields:
        evidence = issued()
        object.__setattr__(evidence, field, value)
        assert not _is_issued_procedure_precondition_observation(evidence)

    evidence = issued()
    first = evidence.observations[0]
    wrong_requirement = ProcedurePredicateObservation(
        evidence.requirements[1], first.trace, first.truth
    )
    object.__setattr__(
        evidence, "observations", (wrong_requirement, *evidence.observations[1:])
    )
    assert not _is_issued_procedure_precondition_observation(evidence)

    evidence = issued()
    object.__setattr__(evidence.observations[0], "truth", TruthValue.FALSE)
    assert not _is_issued_procedure_precondition_observation(evidence)

    evidence = issued()
    object.__setattr__(evidence.observations[0].trace, "result", TruthValue.FALSE)
    assert not _is_issued_procedure_precondition_observation(evidence)

    evidence = issued()
    first, second = evidence.observations
    wrong_trace = ProcedurePredicateObservation(
        first.requirement, second.trace, first.truth
    )
    object.__setattr__(evidence, "observations", (wrong_trace, second))
    assert not _is_issued_procedure_precondition_observation(evidence)


def test_observation_validator_rejects_cross_snapshot_splicing(tmp_path: Path) -> None:
    run = _run_plan(tmp_path)
    snapshots = iter(
        (
            {"context.available": True, "source.available": True},
            {"context.available": False, "source.available": True},
        )
    )
    registry = _registry(run, lambda request: next(snapshots))
    first = observe_procedure_preconditions(run, registry)
    second = observe_procedure_preconditions(run, registry)

    object.__setattr__(
        first,
        "observations",
        (first.observations[0], second.observations[1]),
    )

    assert not _is_issued_procedure_precondition_observation(first)


def test_observation_rejects_forged_and_cross_registry_authorities(
    tmp_path: Path,
) -> None:
    run = _run_plan(tmp_path / "primary")
    foreign_run = _run_plan(tmp_path / "foreign")
    valid = _registry(run, lambda request: {})
    foreign = _registry(foreign_run, lambda request: {})

    forged_run = object.__new__(ProcedureRunPlan)
    object.__setattr__(forged_run, "_issuer", object())
    with pytest.raises(ProcedureObservationError) as bad_run:
        observe_procedure_preconditions(forged_run, valid)
    assert bad_run.value.location == "$.run"

    forged_registry = object.__new__(ObservationProviderRegistry)
    object.__setattr__(forged_registry, "_issuer", object())
    with pytest.raises(ProcedureObservationError) as bad_registry:
        observe_procedure_preconditions(run, forged_registry)
    assert bad_registry.value.location == "$.registry"

    with pytest.raises(ProcedureObservationError) as cross_registry:
        observe_procedure_preconditions(run, foreign)
    assert cross_registry.value.location == "$.registry"


class _HostileResult(Mapping[str, object]):
    """Raise before exposing any provider-result pair."""

    def __getitem__(self, key: str) -> object:
        raise KeyError(key)

    def __iter__(self):
        raise AssertionError("iteration should use items exactly once")

    def __len__(self) -> int:
        return 1

    def items(self):
        raise RuntimeError("items unavailable")


class _SingleReadResult(Mapping[str, object]):
    """Expose a stable snapshot only through one ``items`` traversal."""

    def __init__(self) -> None:
        self.items_calls = 0

    def __getitem__(self, key: str) -> object:
        raise AssertionError("snapshotting must not perform keyed rereads")

    def __iter__(self):
        raise AssertionError("snapshotting must not traverse keys separately")

    def __len__(self) -> int:
        return 2

    def items(self):
        self.items_calls += 1
        if self.items_calls != 1:
            raise AssertionError("provider results must be traversed exactly once")
        return (
            ("context.available", True),
            ("source.available", True),
        )


class _DuplicateKeyResult(_SingleReadResult):
    """Expose one repeated facet through a custom mapping traversal."""

    def items(self):
        return (
            ("context.available", True),
            ("context.available", False),
        )


def test_observation_snapshots_provider_result_in_one_traversal(
    tmp_path: Path,
) -> None:
    run = _run_plan(tmp_path)
    result = _SingleReadResult()

    evidence = observe_procedure_preconditions(
        run, _registry(run, lambda request: result)
    )

    assert result.items_calls == 1
    assert tuple(item.truth for item in evidence.observations) == (
        TruthValue.TRUE,
        TruthValue.TRUE,
    )


@pytest.mark.parametrize(
    ("returned", "location"),
    [
        ([], "$.provider.result"),
        ({"artifact.written": True}, "$.provider.result[0].key"),
        ({"unknown.facet": True}, "$.provider.result[0].key"),
        ({"context.available": "yes"}, "$.provider.result"),
        (_HostileResult(), "$.provider.result"),
        (_DuplicateKeyResult(), "$.provider.result[1].key"),
    ],
)
def test_observation_rejects_malformed_provider_results(
    tmp_path: Path, returned: object, location: str
) -> None:
    run = _run_plan(tmp_path)

    with pytest.raises(ProcedureObservationError) as captured:
        observe_procedure_preconditions(run, _registry(run, lambda request: returned))

    assert captured.value.location == location


def test_observation_rejects_cycles_and_contains_provider_exceptions(
    tmp_path: Path,
) -> None:
    run = _run_plan(tmp_path)
    cycle: dict[str, object] = {}
    cycle["context.available"] = cycle
    with pytest.raises(ProcedureObservationError) as cyclic:
        observe_procedure_preconditions(run, _registry(run, lambda request: cycle))
    assert cyclic.value.location == "$.provider.result.context.available"

    class HostileError(Exception):
        def __str__(self) -> str:
            raise RuntimeError("formatting failed")

    def provider(request: ObservationRequest) -> Mapping[str, object]:
        raise HostileError()

    with pytest.raises(ProcedureObservationError) as escaped:
        observe_procedure_preconditions(run, _registry(run, provider))
    assert escaped.value.location == "$.provider"
    assert "formatting raised RuntimeError" in str(escaped.value)


def test_registry_rejects_wrong_facets_and_async_or_invalid_provider(
    tmp_path: Path,
) -> None:
    run = _run_plan(tmp_path)
    declarations = run.attention.resolution.registry
    equal_but_distinct = load_facet_registry(FACET_FIXTURE)
    with pytest.raises(ObservationProviderRegistryError) as wrong_facets:
        build_observation_provider_registry(
            declarations,
            equal_but_distinct,
            cast(ObservationProvider, lambda request: {}),
        )
    assert wrong_facets.value.location == "$.facets"

    async def async_provider(request: ObservationRequest) -> Mapping[str, object]:
        return {}

    for provider in (object(), async_provider, lambda: {}):
        with pytest.raises(ObservationProviderRegistryError) as invalid:
            build_observation_provider_registry(
                declarations,
                declarations.facet_registry,
                cast(ObservationProvider, provider),
            )
        assert invalid.value.location == "$.provider"


def test_registry_contains_hostile_provider_introspection(tmp_path: Path) -> None:
    run = _run_plan(tmp_path)
    declarations = run.attention.resolution.registry

    class HostileCallLookup:
        def __call__(self, request: ObservationRequest) -> Mapping[str, object]:
            return {}

        def __getattribute__(self, name: str) -> object:
            if name == "__call__":
                raise RuntimeError("call lookup failed")
            return object.__getattribute__(self, name)

    class HostileSignature:
        @property
        def __signature__(self) -> object:
            raise RuntimeError("signature lookup failed")

        def __call__(self, request: ObservationRequest) -> Mapping[str, object]:
            return {}

    for provider in (HostileCallLookup(), HostileSignature()):
        with pytest.raises(ObservationProviderRegistryError) as captured:
            build_observation_provider_registry(
                declarations,
                declarations.facet_registry,
                cast(ObservationProvider, provider),
            )
        assert captured.value.location == "$.provider"
