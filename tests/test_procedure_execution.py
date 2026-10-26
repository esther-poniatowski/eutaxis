"""Exercise the high-level evaluator-less procedure execution boundary."""

from __future__ import annotations

import gc
import importlib
import pickle
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, fields, is_dataclass, replace
from inspect import signature
from threading import Barrier
from typing import cast
from weakref import ref
from weakref import WeakKeyDictionary

import pytest

from eutaxis.declarations import (
    EvaluationState,
    EvaluatorInput,
    ObservationProvider,
    OperationFailure,
    OperationRunner,
    OperationRunnerBinding,
    OperationSuccess,
    PreparedProcedureAction,
    ProcedureAdjudicationDisposition,
    ProcedureBoundaryKind,
    ProcedureAssistedBoundaryEvidence,
    ProcedureAssistedLifecycleBinding,
    ProcedureExecutionSessionState,
    ProcedureFailureStage,
    ProcedureGraphDisposition,
    ProcedureLifecycleManualJudgmentSubmission,
    ProcedureLifecycleResidualJudgmentSubmission,
    ProcedureManualBoundaryEvidence,
    ProcedureManualLifecycleBinding,
    ProcedureRequirementApplicabilityState,
    create_pre_action_evidence_session,
    create_procedure_execution_session,
)
from eutaxis.declarations.exceptions import ProcedureExecutionError
from eutaxis.declarations.procedure_execution import (
    _is_issued_procedure_execution_transcript,
)

from tests.test_attention import WRITE, _detector_result, _pre_action_authorities


def _entry_evidence(
    tmp_path,
    provider,
    *,
    operation_runner=None,
    detector_runner=None,
    later_requirements=True,
    evaluator_backed_lifecycle=False,
    lifecycle_location="invariant",
    lifecycle_timing=None,
    two_actions=False,
):
    plan, observation, manual, residual = _pre_action_authorities(
        tmp_path,
        observation_provider=cast(ObservationProvider, provider),
        later_requirements=later_requirements,
        evaluator_backed_lifecycle=evaluator_backed_lifecycle,
        lifecycle_location=lifecycle_location,
        lifecycle_timing=lifecycle_timing,
        two_actions=two_actions,
        **(
            {
                **(
                    {}
                    if operation_runner is None
                    else {"operation_runner": cast(OperationRunner, operation_runner)}
                ),
                **(
                    {}
                    if detector_runner is None
                    else {"detector_runner": detector_runner}
                ),
            }
        ),
    )
    evidence = create_pre_action_evidence_session(plan, observation).execute(
        manual=manual,
        residual_providers=residual,
    )
    return evidence, observation.registry


def test_evaluatorless_session_owns_boundaries_operation_and_failure_terminal(
    tmp_path,
) -> None:
    requests = []

    def provider(request):
        requests.append(request)
        return {facet: True for facet in request.facets}

    entry, registry = _entry_evidence(tmp_path, provider)
    session = create_procedure_execution_session(entry, registry)

    transcript = session.execute()

    assert session.state is ProcedureExecutionSessionState.TERMINAL
    assert session.transcript is transcript
    assert transcript.graph_disposition is ProcedureGraphDisposition.FAILURE_TERMINAL
    assert (
        transcript.adjudication_disposition is ProcedureAdjudicationDisposition.ACCEPTED
    )
    assert not transcript.successful
    assert tuple(item.coordinate.kind for item in transcript.boundaries) == (
        ProcedureBoundaryKind.ACTION,
        ProcedureBoundaryKind.TERMINAL,
    )
    assert tuple(item.coordinate.occurrence for item in transcript.boundaries) == (
        0,
        1,
    )
    assert len(transcript.actions) == 1
    assert len(requests) == 3  # entry, action, terminal
    assert any(
        item.state is ProcedureRequirementApplicabilityState.INAPPLICABLE
        for item in transcript.applicability
    )


def test_evaluatorless_session_aborts_authorization_without_operation(tmp_path) -> None:
    calls = 0

    def provider(request):
        nonlocal calls
        calls += 1
        if request.kind is ProcedureBoundaryKind.ACTION:
            return {}
        return {facet: True for facet in request.facets}

    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
    )
    lifecycle_registry = type(registry)
    from eutaxis.declarations import build_observation_provider_registry

    registry = build_observation_provider_registry(
        registry.declarations,
        registry.facets,
        cast(ObservationProvider, provider),
    )
    assert lifecycle_registry is type(registry)
    transcript = create_procedure_execution_session(entry, registry).execute()

    assert transcript.graph_disposition is ProcedureGraphDisposition.NO_TERMINAL
    assert (
        transcript.adjudication_disposition
        is ProcedureAdjudicationDisposition.AUTHORIZATION_ABORTED
    )
    assert transcript.actions == ()
    assert calls == 1
    assert any(
        item.state is ProcedureRequirementApplicabilityState.UNCHECKED
        for item in transcript.applicability
    )


def test_terminal_transcript_retains_predecessor_and_rejects_mutation(tmp_path) -> None:
    entry, registry = _entry_evidence(
        tmp_path, lambda request: {facet: True for facet in request.facets}
    )

    transcript = create_procedure_execution_session(entry, registry).execute()

    terminal = transcript.boundaries[-1].coordinate
    action = transcript.actions[-1]
    assert terminal.predecessor_action == action.action.node.id
    assert terminal.predecessor_operation == action.action.operation
    assert terminal.operation_result == action.result
    assert terminal.selected_transition == action.transition
    assert _is_issued_procedure_execution_transcript(transcript)
    object.__setattr__(terminal, "selected_transition", "changed")
    assert not _is_issued_procedure_execution_transcript(transcript)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(transcript)


def test_live_run_keeps_exact_once_claim_after_session_collection(tmp_path) -> None:
    entry, registry = _entry_evidence(
        tmp_path, lambda request: {facet: True for facet in request.facets}
    )
    session = create_procedure_execution_session(entry, registry)
    del session
    gc.collect()

    with pytest.raises(ProcedureExecutionError, match="already owns"):
        create_procedure_execution_session(entry, registry)


def test_provider_replacement_aborts_authority_with_transcript(tmp_path) -> None:
    entry, entry_registry = _entry_evidence(
        tmp_path, lambda request: {facet: True for facet in request.facets}
    )
    from eutaxis.declarations import build_observation_provider_registry

    lifecycle_registry = None

    def provider(request):
        assert lifecycle_registry is not None
        object.__setattr__(
            lifecycle_registry,
            "provider",
            cast(ObservationProvider, lambda later: {}),
        )
        return {facet: True for facet in request.facets}

    lifecycle_registry = build_observation_provider_registry(
        entry_registry.declarations,
        entry_registry.facets,
        cast(ObservationProvider, provider),
    )
    session = create_procedure_execution_session(entry, lifecycle_registry)

    transcript = session.execute()

    assert session.state is ProcedureExecutionSessionState.TERMINAL
    assert (
        transcript.adjudication_disposition
        is ProcedureAdjudicationDisposition.AUTHORITY_ABORTED
    )
    assert transcript.boundaries[0].evidence is not None
    assert not transcript.boundaries[0].evidence.complete
    assert transcript.boundaries[0].evidence.records == ()
    assert transcript.authority.lifecycle_observation_provider_origin is provider
    assert (
        transcript.authority.lifecycle_observation_registry_origin is lifecycle_registry
    )
    assert _is_issued_procedure_execution_transcript(transcript)


def test_transcript_registry_rejects_object_new_forgery_with_copied_fields(
    tmp_path,
) -> None:
    entry, registry = _entry_evidence(
        tmp_path, lambda request: {facet: True for facet in request.facets}
    )
    transcript = create_procedure_execution_session(entry, registry).execute()
    forged = object.__new__(type(transcript))
    for field in fields(transcript):
        object.__setattr__(forged, field.name, getattr(transcript, field.name))

    assert _is_issued_procedure_execution_transcript(transcript)
    assert not _is_issued_procedure_execution_transcript(forged)


@pytest.mark.parametrize(
    "path,replacement",
    [
        (("boundaries", 0, "coordinate", "occurrence"), 17),
        (("boundaries", 0, "requirements", 0, "enforcement"), "changed"),
        (("actions", 0, "action", "node", "on_success"), "changed"),
        (("actions", 0, "result", "outcome"), "changed"),
        (("applicability", 0, "state"), "changed"),
    ],
)
def test_transcript_nested_semantics_detect_every_public_carrier_mutation(
    tmp_path, path, replacement
) -> None:
    entry, registry = _entry_evidence(
        tmp_path, lambda request: {facet: True for facet in request.facets}
    )
    transcript = create_procedure_execution_session(entry, registry).execute()
    target = transcript
    for component in path[:-1]:
        target = (
            target[component]
            if isinstance(component, int)
            else getattr(target, component)
        )
    object.__setattr__(target, cast(str, path[-1]), replacement)

    assert not _is_issued_procedure_execution_transcript(transcript)


def test_transcript_rejects_equal_value_nested_identity_replacement(tmp_path) -> None:
    from types import MappingProxyType

    entry, registry = _entry_evidence(
        tmp_path, lambda request: {facet: True for facet in request.facets}
    )
    transcript = create_procedure_execution_session(entry, registry).execute()
    action = transcript.actions[0].action
    object.__setattr__(action, "input_data", MappingProxyType(dict(action.input_data)))

    assert not _is_issued_procedure_execution_transcript(transcript)


def test_canonical_authority_snapshot_survives_live_origin_mutation(tmp_path) -> None:
    entry, registry = _entry_evidence(
        tmp_path, lambda request: {facet: True for facet in request.facets}
    )
    transcript = create_procedure_execution_session(entry, registry).execute()
    retained_entry_state = transcript.authority.entry_evidence_state
    retained_provider = transcript.authority.lifecycle_observation_provider_origin

    object.__setattr__(entry, "cleared", False)
    object.__setattr__(
        registry, "provider", cast(ObservationProvider, lambda request: {})
    )

    assert transcript.authority.entry_evidence_origin is entry
    assert transcript.authority.entry_evidence_state is retained_entry_state
    assert transcript.authority.entry_evidence_state[0] is True
    assert transcript.authority.lifecycle_observation_registry_origin is registry
    assert (
        transcript.authority.lifecycle_observation_provider_origin is retained_provider
    )
    assert _is_issued_procedure_execution_transcript(transcript)


@pytest.mark.parametrize(
    "successful,terminal_satisfied,expected_graph,expected_adjudication",
    [
        (
            True,
            True,
            ProcedureGraphDisposition.SUCCESS_TERMINAL,
            ProcedureAdjudicationDisposition.ACCEPTED,
        ),
        (
            True,
            False,
            ProcedureGraphDisposition.SUCCESS_TERMINAL,
            ProcedureAdjudicationDisposition.TERMINAL_EVIDENCE_REJECTED,
        ),
        (
            False,
            True,
            ProcedureGraphDisposition.FAILURE_TERMINAL,
            ProcedureAdjudicationDisposition.ACCEPTED,
        ),
        (
            False,
            False,
            ProcedureGraphDisposition.FAILURE_TERMINAL,
            ProcedureAdjudicationDisposition.TERMINAL_EVIDENCE_REJECTED,
        ),
    ],
)
def test_terminal_success_failure_and_rejection_matrix(
    tmp_path,
    successful,
    terminal_satisfied,
    expected_graph,
    expected_adjudication,
) -> None:
    def provider(request):
        if (
            getattr(request, "kind", None) is ProcedureBoundaryKind.TERMINAL
            and not terminal_satisfied
        ):
            return {}
        return {facet: True for facet in request.facets}

    runner = (
        (lambda input_data: OperationSuccess(WRITE, {"written": True}))
        if successful
        else (lambda input_data: OperationFailure(WRITE, "write-failed"))
    )
    entry, registry = _entry_evidence(tmp_path, provider, operation_runner=runner)

    transcript = create_procedure_execution_session(entry, registry).execute()

    assert transcript.graph_disposition is expected_graph
    assert transcript.adjudication_disposition is expected_adjudication
    assert transcript.successful is (
        expected_graph is ProcedureGraphDisposition.SUCCESS_TERMINAL
        and expected_adjudication is ProcedureAdjudicationDisposition.ACCEPTED
    )


@pytest.mark.parametrize("successful", [True, False])
def test_terminal_provider_base_exception_publishes_before_reraising(
    tmp_path, successful
) -> None:
    def provider(request):
        if getattr(request, "kind", None) is ProcedureBoundaryKind.TERMINAL:
            raise KeyboardInterrupt
        return {facet: True for facet in request.facets}

    runner = (
        (lambda input_data: OperationSuccess(WRITE, {"written": True}))
        if successful
        else (lambda input_data: OperationFailure(WRITE, "write-failed"))
    )
    entry, registry = _entry_evidence(tmp_path, provider, operation_runner=runner)
    session = create_procedure_execution_session(entry, registry)

    with pytest.raises(KeyboardInterrupt):
        session.execute()

    transcript = session.transcript
    assert transcript is not None
    assert transcript.failure is not None
    assert transcript.failure.stage.value == "observation"
    assert transcript.boundaries[-1].coordinate.kind is ProcedureBoundaryKind.TERMINAL
    assert _is_issued_procedure_execution_transcript(transcript)


@pytest.mark.parametrize("kind", ["exception", "invalid", "base-exception"])
def test_runner_failure_classes_publish_terminal_transcript(tmp_path, kind) -> None:
    def runner(input_data):
        if kind == "exception":
            raise RuntimeError("runner-broke")
        if kind == "base-exception":
            raise KeyboardInterrupt
        return object()

    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        operation_runner=runner,
    )
    session = create_procedure_execution_session(entry, registry)

    if kind == "base-exception":
        with pytest.raises(KeyboardInterrupt):
            session.execute()
        transcript = session.transcript
        assert transcript is not None
    else:
        transcript = session.execute()
    assert (
        transcript.adjudication_disposition
        is ProcedureAdjudicationDisposition.EXECUTION_ABORTED
    )
    assert transcript.failure is not None
    assert transcript.failure.stage.value in {"operation-runner", "operation-result"}
    assert _is_issued_procedure_execution_transcript(transcript)


def test_action_with_no_requirements_and_terminal_applicability_partition(
    tmp_path,
) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        operation_runner=lambda input_data: OperationSuccess(WRITE, {"written": True}),
        later_requirements=False,
    )

    transcript = create_procedure_execution_session(entry, registry).execute()

    assert transcript.boundaries[0].requirements == ()
    assert transcript.boundaries[0].evidence is not None
    assert transcript.boundaries[0].evidence.records == ()
    assert all(
        item.state is ProcedureRequirementApplicabilityState.APPLICABLE
        for item in transcript.applicability
    )


def test_concurrent_factory_installs_only_one_exact_run_claim(tmp_path) -> None:
    entry, registry = _entry_evidence(
        tmp_path, lambda request: {facet: True for facet in request.facets}
    )
    barrier = Barrier(2)

    def create():
        barrier.wait()
        try:
            return create_procedure_execution_session(entry, registry)
        except ProcedureExecutionError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(lambda _: create(), range(2)))

    assert sum(not isinstance(item, Exception) for item in outcomes) == 1
    assert sum(isinstance(item, ProcedureExecutionError) for item in outcomes) == 1


def test_reentrant_execute_is_normalized_as_observation_failure(tmp_path) -> None:
    session = None

    def provider(request):
        assert session is not None
        session.execute()

    entry, registry = _entry_evidence(
        tmp_path, lambda request: {facet: True for facet in request.facets}
    )
    from eutaxis.declarations import build_observation_provider_registry

    lifecycle_registry = build_observation_provider_registry(
        registry.declarations, registry.facets, cast(ObservationProvider, provider)
    )
    session = create_procedure_execution_session(entry, lifecycle_registry)

    transcript = session.execute()

    assert (
        transcript.adjudication_disposition
        is ProcedureAdjudicationDisposition.EVIDENCE_ABORTED
    )
    assert transcript.failure is not None
    assert transcript.failure.stage.value == "observation"


def test_run_claim_releases_when_complete_authority_graph_is_unreachable(
    tmp_path,
) -> None:
    entry, registry = _entry_evidence(
        tmp_path, lambda request: {facet: True for facet in request.facets}
    )
    run_reference = ref(entry.plan.run)
    session = create_procedure_execution_session(entry, registry)

    del session, entry, registry
    gc.collect()

    assert run_reference() is None


def test_assisted_lifecycle_runs_at_each_realized_invariant_boundary(
    tmp_path,
) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle=True,
    )

    specification = entry.plan.run.lifecycle_evaluations[0]
    input_requests = []
    residual_requests = []

    def input_provider(request):
        input_requests.append(request)
        return EvaluatorInput(
            specification.invocation.input_revision,
            specification.invocation.input_data,
        )

    def residual_provider(request):
        residual_requests.append(request)
        return ProcedureLifecycleResidualJudgmentSubmission(
            1,
            request,
            EvaluationState.SATISFIED,
            "The detector candidate satisfies the invariant.",
        )

    session = create_procedure_execution_session(entry, registry)
    with pytest.raises(ProcedureExecutionError, match="bindings are absent"):
        session.execute()
    assert session.state is ProcedureExecutionSessionState.READY

    transcript = session.execute(
        evidence_bindings={
            specification.source_key: ProcedureAssistedLifecycleBinding(
                input_provider, residual_provider
            )
        }
    )

    assert session.state is ProcedureExecutionSessionState.TERMINAL
    assert len(input_requests) == 2
    assert len(residual_requests) == 2
    assert input_requests[0].coordinate.occurrence == 0
    assert input_requests[1].coordinate.occurrence == 1
    assert residual_requests[0] is not residual_requests[1]
    assert all(
        boundary.evidence is not None and boundary.evidence.complete
        for boundary in transcript.boundaries
    )
    assert (
        sum(
            isinstance(record, ProcedureAssistedBoundaryEvidence)
            for boundary in transcript.boundaries
            if boundary.evidence is not None
            for record in boundary.evidence.records
        )
        == 2
    )


def test_manual_lifecycle_derives_each_occurrence_from_its_exact_request(
    tmp_path,
) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle="manual",
    )
    specification = entry.plan.run.lifecycle_evaluations[0]
    requests = []

    def provider(request):
        requests.append(request)
        return ProcedureLifecycleManualJudgmentSubmission(
            request,
            specification.evaluator.input_revisions[0],
            {"conclusion": "satisfied"},
        )

    transcript = create_procedure_execution_session(entry, registry).execute(
        evidence_bindings={
            specification.source_key: ProcedureManualLifecycleBinding(provider)
        }
    )

    assert len(requests) == 2
    assert requests[0] is not requests[1]
    assert tuple(request.coordinate.occurrence for request in requests) == (0, 1)
    assert (
        sum(
            isinstance(record, ProcedureManualBoundaryEvidence)
            for boundary in transcript.boundaries
            if boundary.evidence is not None
            for record in boundary.evidence.records
        )
        == 2
    )


def test_mechanical_lifecycle_rejection_precedes_claim_installation(tmp_path) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle="mechanical",
    )

    for _ in range(2):
        with pytest.raises(ProcedureExecutionError, match="mechanical lifecycle"):
            create_procedure_execution_session(entry, registry)


@pytest.mark.parametrize("conclusion", ["violated", "blocked"])
def test_manual_lifecycle_denial_prevents_operation(tmp_path, conclusion) -> None:
    operation_calls = 0

    def operation_runner(input_data):
        nonlocal operation_calls
        operation_calls += 1
        return OperationSuccess(WRITE, {"written": True})

    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle="manual",
        operation_runner=operation_runner,
    )
    specification = entry.plan.run.lifecycle_evaluations[0]

    def provider(request):
        return ProcedureLifecycleManualJudgmentSubmission(
            request,
            specification.evaluator.input_revisions[0],
            {"conclusion": conclusion},
        )

    transcript = create_procedure_execution_session(entry, registry).execute(
        evidence_bindings={
            specification.source_key: ProcedureManualLifecycleBinding(provider)
        }
    )

    assert operation_calls == 0
    assert (
        transcript.adjudication_disposition
        is ProcedureAdjudicationDisposition.AUTHORIZATION_ABORTED
    )
    evidence = transcript.boundaries[0].evidence
    assert evidence is not None and evidence.complete
    manual = next(
        record
        for record in evidence.records
        if isinstance(record, ProcedureManualBoundaryEvidence)
    )
    assert manual.state is EvaluationState(conclusion)


def test_manual_lifecycle_replay_publishes_incomplete_terminal_prefix(tmp_path) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle="manual",
    )
    specification = entry.plan.run.lifecycle_evaluations[0]
    retained = None

    def provider(request):
        nonlocal retained
        if retained is None:
            retained = ProcedureLifecycleManualJudgmentSubmission(
                request,
                specification.evaluator.input_revisions[0],
                {"conclusion": "satisfied"},
            )
        return retained

    transcript = create_procedure_execution_session(entry, registry).execute(
        evidence_bindings={
            specification.source_key: ProcedureManualLifecycleBinding(provider)
        }
    )

    assert (
        transcript.adjudication_disposition
        is ProcedureAdjudicationDisposition.EVIDENCE_ABORTED
    )
    assert transcript.failure is not None
    assert transcript.failure.stage is ProcedureFailureStage.MANUAL
    terminal = transcript.boundaries[-1].evidence
    assert terminal is not None and not terminal.complete
    assert terminal.records == ()


def test_assisted_detector_failure_blocks_without_residual_or_operation(
    tmp_path,
) -> None:
    detector_calls = 0
    residual_calls = 0
    operation_calls = 0

    def detector_runner(input_data):
        nonlocal detector_calls
        detector_calls += 1
        if detector_calls > 1:
            raise RuntimeError("detector failed")
        return _detector_result()

    def operation_runner(input_data):
        nonlocal operation_calls
        operation_calls += 1
        return OperationSuccess(WRITE, {"written": True})

    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle=True,
        detector_runner=detector_runner,
        operation_runner=operation_runner,
    )
    specification = entry.plan.run.lifecycle_evaluations[0]

    def input_provider(request):
        return EvaluatorInput(
            specification.invocation.input_revision,
            specification.invocation.input_data,
        )

    def residual_provider(request):
        nonlocal residual_calls
        residual_calls += 1
        return ProcedureLifecycleResidualJudgmentSubmission(
            1, request, EvaluationState.SATISFIED, "Satisfied."
        )

    transcript = create_procedure_execution_session(entry, registry).execute(
        evidence_bindings={
            specification.source_key: ProcedureAssistedLifecycleBinding(
                input_provider, residual_provider
            )
        }
    )

    assert detector_calls == 2
    assert residual_calls == 0
    assert operation_calls == 0
    evidence = transcript.boundaries[0].evidence
    assert evidence is not None and evidence.complete
    assisted = next(
        record
        for record in evidence.records
        if isinstance(record, ProcedureAssistedBoundaryEvidence)
    )
    assert assisted.state is EvaluationState.BLOCKED
    assert assisted.execution is None and assisted.judgment is None
    assert (
        transcript.adjudication_disposition
        is ProcedureAdjudicationDisposition.AUTHORIZATION_ABORTED
    )


def test_lifecycle_binding_requires_exact_source_key_identity(tmp_path) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle="manual",
    )
    specification = entry.plan.run.lifecycle_evaluations[0]
    copied_key = replace(specification.source_key)
    session = create_procedure_execution_session(entry, registry)

    with pytest.raises(ProcedureExecutionError, match="exact required key"):
        session.execute(
            evidence_bindings={
                copied_key: ProcedureManualLifecycleBinding(lambda request: None)
            }
        )

    assert session.state is ProcedureExecutionSessionState.READY


def test_manual_operation_precondition_runs_at_its_action_boundary(tmp_path) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle="manual",
        lifecycle_location="operation-precondition",
    )
    specification = entry.plan.run.lifecycle_evaluations[0]
    requests = []

    def provider(request):
        requests.append(request)
        return ProcedureLifecycleManualJudgmentSubmission(
            request,
            specification.evaluator.input_revisions[0],
            {"conclusion": "satisfied"},
        )

    transcript = create_procedure_execution_session(entry, registry).execute(
        evidence_bindings={
            specification.source_key: ProcedureManualLifecycleBinding(provider)
        }
    )

    assert len(requests) == 1
    assert requests[0].coordinate.kind is ProcedureBoundaryKind.ACTION
    action_evidence = transcript.boundaries[0].evidence
    assert action_evidence is not None
    assert any(
        isinstance(record, ProcedureManualBoundaryEvidence)
        for record in action_evidence.records
    )


@pytest.mark.parametrize("operation_succeeds,expected_calls", [(True, 1), (False, 0)])
def test_assisted_postcondition_runs_only_at_its_reached_success_terminal(
    tmp_path, operation_succeeds, expected_calls
) -> None:
    result = (
        OperationSuccess(WRITE, {"written": True})
        if operation_succeeds
        else OperationFailure(WRITE, "write-failed")
    )
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle=True,
        lifecycle_location="postcondition",
        operation_runner=lambda input_data: result,
    )
    specification = entry.plan.run.lifecycle_evaluations[0]
    requests = []

    def input_provider(request):
        requests.append(request)
        return EvaluatorInput(
            specification.invocation.input_revision,
            specification.invocation.input_data,
        )

    def residual_provider(request):
        return ProcedureLifecycleResidualJudgmentSubmission(
            1, request, EvaluationState.SATISFIED, "Satisfied."
        )

    transcript = create_procedure_execution_session(entry, registry).execute(
        evidence_bindings={
            specification.source_key: ProcedureAssistedLifecycleBinding(
                input_provider, residual_provider
            )
        }
    )

    assert len(requests) == expected_calls
    if requests:
        assert requests[0].coordinate.kind is ProcedureBoundaryKind.TERMINAL
        assert requests[0].coordinate.terminal == "written"
    postcondition = next(
        item
        for item in transcript.applicability
        if item.requirement.evaluator is not None
    )
    assert postcondition.state is (
        ProcedureRequirementApplicabilityState.APPLICABLE
        if operation_succeeds
        else ProcedureRequirementApplicabilityState.INAPPLICABLE
    )


def test_post_action_timing_is_accepted_for_a_reached_postcondition(tmp_path) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle="manual",
        lifecycle_location="postcondition",
        lifecycle_timing="post-action",
        operation_runner=lambda input_data: OperationSuccess(WRITE, {"written": True}),
    )
    specification = entry.plan.run.lifecycle_evaluations[0]

    def provider(request):
        return ProcedureLifecycleManualJudgmentSubmission(
            request,
            specification.evaluator.input_revisions[0],
            {"conclusion": "satisfied"},
        )

    transcript = create_procedure_execution_session(entry, registry).execute(
        evidence_bindings={
            specification.source_key: ProcedureManualLifecycleBinding(provider)
        }
    )

    assert transcript.successful


@pytest.mark.parametrize("location", ["invariant", "operation-precondition"])
def test_post_action_timing_is_rejected_before_claim_for_action_boundaries(
    tmp_path, location
) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle="manual",
        lifecycle_location=location,
        lifecycle_timing="post-action",
    )

    for _ in range(2):
        with pytest.raises(ProcedureExecutionError, match="timing is later"):
            create_procedure_execution_session(entry, registry)


def test_assisted_input_must_equal_the_retained_invocation(tmp_path) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle=True,
    )
    specification = entry.plan.run.lifecycle_evaluations[0]

    def input_provider(request):
        return EvaluatorInput(
            specification.invocation.input_revision,
            {**specification.invocation.input_data, "content": "different"},
        )

    transcript = create_procedure_execution_session(entry, registry).execute(
        evidence_bindings={
            specification.source_key: ProcedureAssistedLifecycleBinding(
                input_provider, lambda request: None
            )
        }
    )

    assert transcript.failure is not None
    assert transcript.failure.stage is ProcedureFailureStage.EVALUATOR_INPUT


def test_assisted_residual_replay_cannot_authorize_a_later_occurrence(tmp_path) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle=True,
    )
    specification = entry.plan.run.lifecycle_evaluations[0]
    retained = None

    def input_provider(request):
        return EvaluatorInput(
            specification.invocation.input_revision,
            specification.invocation.input_data,
        )

    def residual_provider(request):
        nonlocal retained
        if retained is None:
            retained = ProcedureLifecycleResidualJudgmentSubmission(
                1, request, EvaluationState.SATISFIED, "Satisfied."
            )
        return retained

    transcript = create_procedure_execution_session(entry, registry).execute(
        evidence_bindings={
            specification.source_key: ProcedureAssistedLifecycleBinding(
                input_provider, residual_provider
            )
        }
    )

    assert transcript.failure is not None
    assert transcript.failure.stage is ProcedureFailureStage.RESIDUAL


def test_manual_binding_rejects_provider_swap_during_signature_inspection(
    tmp_path,
) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle="manual",
    )
    specification = entry.plan.run.lifecycle_evaluations[0]

    class SwappingProvider:
        binding = None

        @property
        def __signature__(self):
            assert self.binding is not None
            object.__setattr__(self.binding, "provider", lambda request: None)
            return signature(lambda request: None)

        def __call__(self, request):
            raise AssertionError("mutated provider must never run")

    provider = SwappingProvider()
    binding = ProcedureManualLifecycleBinding(provider)
    provider.binding = binding
    session = create_procedure_execution_session(entry, registry)

    with pytest.raises(ProcedureExecutionError, match="manual provider changed"):
        session.execute(evidence_bindings={specification.source_key: binding})

    assert session.state is ProcedureExecutionSessionState.READY


def test_assisted_binding_rejects_cross_swap_during_signature_inspection(
    tmp_path,
) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle=True,
    )
    specification = entry.plan.run.lifecycle_evaluations[0]

    class SwappingProvider:
        binding = None

        @property
        def __signature__(self):
            assert self.binding is not None
            original_input = self.binding.input_provider
            object.__setattr__(
                self.binding, "input_provider", self.binding.residual_provider
            )
            object.__setattr__(self.binding, "residual_provider", original_input)
            return signature(lambda request: None)

        def __call__(self, request):
            raise AssertionError("mutated provider must never run")

    input_provider = SwappingProvider()
    residual_provider = lambda request: None
    binding = ProcedureAssistedLifecycleBinding(input_provider, residual_provider)
    input_provider.binding = binding
    session = create_procedure_execution_session(entry, registry)

    with pytest.raises(ProcedureExecutionError, match="assisted provider changed"):
        session.execute(evidence_bindings={specification.source_key: binding})

    assert session.state is ProcedureExecutionSessionState.READY


def test_manual_provider_mutation_of_live_evaluator_aborts_authority(tmp_path) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle="manual",
    )
    specification = entry.plan.run.lifecycle_evaluations[0]

    def provider(request):
        object.__setattr__(specification.evaluator, "input_revisions", ("changed",))
        return ProcedureLifecycleManualJudgmentSubmission(
            request, "changed", {"conclusion": "satisfied"}
        )

    transcript = create_procedure_execution_session(entry, registry).execute(
        evidence_bindings={
            specification.source_key: ProcedureManualLifecycleBinding(provider)
        }
    )

    assert (
        transcript.adjudication_disposition
        is ProcedureAdjudicationDisposition.AUTHORITY_ABORTED
    )
    assert transcript.failure is not None
    assert transcript.failure.stage is ProcedureFailureStage.AUTHORITY


def test_manual_evidence_traversal_mutation_of_detached_schema_aborts_authority(
    tmp_path,
) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle="manual",
    )
    specification = entry.plan.run.lifecycle_evaluations[0]

    class MutatingEvidence(Mapping):
        def __init__(self, evaluator):
            self.evaluator = evaluator

        def __getitem__(self, key):
            if key == "conclusion":
                return "satisfied"
            raise KeyError(key)

        def __iter__(self):
            return iter(("conclusion",))

        def __len__(self):
            return 1

        def items(self):
            object.__setattr__(self.evaluator, "evidence_schema", {})
            return (("conclusion", "satisfied"),)

    def provider(request):
        return ProcedureLifecycleManualJudgmentSubmission(
            request,
            request.evaluator.input_revisions[0],
            MutatingEvidence(request.evaluator),
        )

    transcript = create_procedure_execution_session(entry, registry).execute(
        evidence_bindings={
            specification.source_key: ProcedureManualLifecycleBinding(provider)
        }
    )

    assert (
        transcript.adjudication_disposition
        is ProcedureAdjudicationDisposition.AUTHORITY_ABORTED
    )
    assert transcript.failure is not None
    assert transcript.failure.stage is ProcedureFailureStage.AUTHORITY


@pytest.mark.parametrize("raised", [RuntimeError, KeyboardInterrupt])
def test_failing_manual_evidence_traversal_preserves_authority_precedence(
    tmp_path, raised
) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle="manual",
    )
    specification = entry.plan.run.lifecycle_evaluations[0]

    class MutatingEvidence(Mapping):
        def __init__(self, evaluator):
            self.evaluator = evaluator

        def __getitem__(self, key):
            raise KeyError(key)

        def __iter__(self):
            return iter(("conclusion",))

        def __len__(self):
            return 1

        def items(self):
            object.__setattr__(self.evaluator, "evidence_schema", {})
            raise raised("mapping traversal failed")

    def provider(request):
        return ProcedureLifecycleManualJudgmentSubmission(
            request,
            request.evaluator.input_revisions[0],
            MutatingEvidence(request.evaluator),
        )

    session = create_procedure_execution_session(entry, registry)
    execute = lambda: session.execute(
        evidence_bindings={
            specification.source_key: ProcedureManualLifecycleBinding(provider)
        }
    )
    if raised is KeyboardInterrupt:
        with pytest.raises(KeyboardInterrupt):
            execute()
        transcript = session.transcript
        assert transcript is not None
    else:
        transcript = execute()

    assert session.state is ProcedureExecutionSessionState.TERMINAL
    assert (
        transcript.adjudication_disposition
        is ProcedureAdjudicationDisposition.AUTHORITY_ABORTED
    )
    assert transcript.failure is not None
    assert transcript.failure.stage is ProcedureFailureStage.AUTHORITY
    evidence = transcript.boundaries[0].evidence
    assert evidence is not None and not evidence.complete
    assert len(evidence.records) == 1


def test_manual_revision_requires_exact_string_type(tmp_path) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle="manual",
    )
    specification = entry.plan.run.lifecycle_evaluations[0]

    class Revision(str):
        pass

    def provider(request):
        return ProcedureLifecycleManualJudgmentSubmission(
            request,
            Revision(specification.evaluator.input_revisions[0]),
            {"conclusion": "satisfied"},
        )

    transcript = create_procedure_execution_session(entry, registry).execute(
        evidence_bindings={
            specification.source_key: ProcedureManualLifecycleBinding(provider)
        }
    )

    assert transcript.failure is not None
    assert transcript.failure.stage is ProcedureFailureStage.MANUAL


def test_residual_schema_version_rejects_boolean(tmp_path) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle=True,
    )
    specification = entry.plan.run.lifecycle_evaluations[0]

    def input_provider(request):
        return EvaluatorInput(
            specification.invocation.input_revision,
            specification.invocation.input_data,
        )

    def residual_provider(request):
        return ProcedureLifecycleResidualJudgmentSubmission(
            True, request, EvaluationState.SATISFIED, "Satisfied."
        )

    transcript = create_procedure_execution_session(entry, registry).execute(
        evidence_bindings={
            specification.source_key: ProcedureAssistedLifecycleBinding(
                input_provider, residual_provider
            )
        }
    )

    assert transcript.failure is not None
    assert transcript.failure.stage is ProcedureFailureStage.RESIDUAL


def test_malformed_binding_mapping_item_is_a_located_pre_run_error(tmp_path) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle="manual",
    )

    class MalformedMapping(Mapping):
        def __getitem__(self, key):
            raise KeyError(key)

        def __iter__(self):
            return iter(())

        def __len__(self):
            return 1

        def items(self):
            return ((object(),),)

    session = create_procedure_execution_session(entry, registry)

    with pytest.raises(ProcedureExecutionError) as captured:
        session.execute(evidence_bindings=cast(Mapping, MalformedMapping()))

    assert captured.value.location == "$.evidence-bindings[0]"
    assert session.state is ProcedureExecutionSessionState.READY


def test_authority_revalidation_base_exception_publishes_authority_stage(
    tmp_path, monkeypatch
) -> None:
    module = importlib.import_module("eutaxis.declarations.procedure_execution")
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle="manual",
    )
    specification = entry.plan.run.lifecycle_evaluations[0]

    def interrupted(_control):
        raise KeyboardInterrupt

    def provider(request):
        monkeypatch.setattr(module, "_require_control_authority", interrupted)
        return ProcedureLifecycleManualJudgmentSubmission(
            request,
            specification.evaluator.input_revisions[0],
            {"conclusion": "satisfied"},
        )

    session = create_procedure_execution_session(entry, registry)
    with pytest.raises(KeyboardInterrupt):
        session.execute(
            evidence_bindings={
                specification.source_key: ProcedureManualLifecycleBinding(provider)
            }
        )

    transcript = session.transcript
    assert transcript is not None
    assert transcript.failure is not None
    assert transcript.failure.stage is ProcedureFailureStage.AUTHORITY
    assert (
        transcript.adjudication_disposition
        is ProcedureAdjudicationDisposition.AUTHORITY_ABORTED
    )


def test_stateful_dataclass_callables_do_not_invalidate_execution_authority(
    tmp_path,
) -> None:
    @dataclass
    class StatefulDetector:
        calls: int = 0

        def __call__(self, input_data):
            self.calls += 1
            return _detector_result()

    @dataclass
    class StatefulOperation:
        calls: int = 0

        def __call__(self, input_data):
            self.calls += 1
            return OperationSuccess(WRITE, {"written": True})

    detector = StatefulDetector()
    operation = StatefulOperation()
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle=True,
        detector_runner=detector,
        operation_runner=operation,
    )
    specification = entry.plan.run.lifecycle_evaluations[0]

    @dataclass
    class StatefulInputProvider:
        calls: int = 0

        def __call__(self, request):
            self.calls += 1
            return EvaluatorInput(
                specification.invocation.input_revision,
                specification.invocation.input_data,
            )

    @dataclass
    class StatefulResidualProvider:
        calls: int = 0

        def __call__(self, request):
            self.calls += 1
            return ProcedureLifecycleResidualJudgmentSubmission(
                1, request, EvaluationState.SATISFIED, "Satisfied."
            )

    input_provider = StatefulInputProvider()
    residual_provider = StatefulResidualProvider()
    transcript = create_procedure_execution_session(entry, registry).execute(
        evidence_bindings={
            specification.source_key: ProcedureAssistedLifecycleBinding(
                input_provider, residual_provider
            )
        }
    )

    assert transcript.successful
    assert detector.calls == 3  # one entry check and two lifecycle boundaries
    assert input_provider.calls == residual_provider.calls == 2
    assert operation.calls == 1
    assert _is_issued_procedure_execution_transcript(transcript)
    detector.calls += 1
    assert _is_issued_procedure_execution_transcript(transcript)
    execution = next(
        record.execution
        for boundary in transcript.boundaries
        if boundary.evidence is not None
        for record in boundary.evidence.records
        if isinstance(record, ProcedureAssistedBoundaryEvidence)
        and record.execution is not None
    )
    detector_binding = next(iter(execution.registry.bindings.values()))
    object.__setattr__(
        detector_binding, "runner", lambda input_data: _detector_result()
    )
    assert not _is_issued_procedure_execution_transcript(transcript)


def test_stateful_manual_provider_and_binding_mutation_have_distinct_authority(
    tmp_path,
) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle="manual",
    )
    specification = entry.plan.run.lifecycle_evaluations[0]

    @dataclass
    class StatefulProvider:
        calls: int = 0

        def __call__(self, request):
            self.calls += 1
            return ProcedureLifecycleManualJudgmentSubmission(
                request,
                specification.evaluator.input_revisions[0],
                {"conclusion": "satisfied"},
            )

    provider = StatefulProvider()
    binding = ProcedureManualLifecycleBinding(provider)
    transcript = create_procedure_execution_session(entry, registry).execute(
        evidence_bindings={specification.source_key: binding}
    )

    assert (
        transcript.adjudication_disposition is ProcedureAdjudicationDisposition.ACCEPTED
    )
    assert provider.calls == 2
    assert _is_issued_procedure_execution_transcript(transcript)
    object.__setattr__(binding, "provider", lambda request: None)
    assert not _is_issued_procedure_execution_transcript(transcript)


@pytest.mark.parametrize("first_success", [True, False])
def test_multi_action_ordinals_and_convergent_failure_continuation(
    tmp_path, first_success
) -> None:
    invocations = 0

    def runner(input_data):
        nonlocal invocations
        invocations += 1
        if invocations == 1 and not first_success:
            return OperationFailure(WRITE, "write-failed")
        return OperationSuccess(WRITE, {"written": True})

    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        operation_runner=runner,
        two_actions=True,
    )

    transcript = create_procedure_execution_session(entry, registry).execute()

    assert tuple(item.coordinate.occurrence for item in transcript.actions) == (0, 1)
    assert tuple(len(item.requirements) for item in transcript.boundaries) == (2, 2, 2)
    assert all(
        len({id(requirement) for requirement in item.requirements})
        == len(item.requirements)
        for item in transcript.boundaries
    )
    assert transcript.actions[0].transition == "write-second"
    assert transcript.actions[1].transition == "written"
    assert transcript.boundaries[-1].coordinate.occurrence == 2
    assert transcript.boundaries[-1].coordinate.predecessor_action == "write-second"
    assert transcript.graph_disposition is ProcedureGraphDisposition.SUCCESS_TERMINAL
    assert transcript.successful


def test_provider_exception_is_normalized_without_escaping(tmp_path) -> None:
    entry, entry_registry = _entry_evidence(
        tmp_path, lambda request: {facet: True for facet in request.facets}
    )
    from eutaxis.declarations import build_observation_provider_registry

    def provider(request):
        raise RuntimeError("observation-broke")

    registry = build_observation_provider_registry(
        entry_registry.declarations,
        entry_registry.facets,
        cast(ObservationProvider, provider),
    )

    transcript = create_procedure_execution_session(entry, registry).execute()

    assert (
        transcript.adjudication_disposition
        is ProcedureAdjudicationDisposition.EVIDENCE_ABORTED
    )
    assert transcript.failure is not None
    assert transcript.failure.stage.value == "observation"
    assert "observation-broke" in cast(str, transcript.failure.diagnostic)


def test_live_lifecycle_mutation_aborts_against_detached_factory_authority(
    tmp_path,
) -> None:
    entry, entry_registry = _entry_evidence(
        tmp_path, lambda request: {facet: True for facet in request.facets}
    )
    from eutaxis.declarations import build_observation_provider_registry

    def provider(request):
        requirement = entry.plan.run.requirements[-1]
        object.__setattr__(requirement, "enforcement", "changed")
        return {facet: True for facet in request.facets}

    lifecycle_registry = build_observation_provider_registry(
        entry_registry.declarations,
        entry_registry.facets,
        cast(ObservationProvider, provider),
    )
    transcript = create_procedure_execution_session(entry, lifecycle_registry).execute()

    assert (
        transcript.adjudication_disposition
        is ProcedureAdjudicationDisposition.AUTHORITY_ABORTED
    )
    assert transcript.boundaries[0].requirements[0].enforcement is None
    assert _is_issued_procedure_execution_transcript(transcript)


def test_abort_after_executed_prefix_preserves_prefix_and_unchecked_suffix(
    tmp_path,
) -> None:
    action_boundaries = 0

    def provider(request):
        nonlocal action_boundaries
        if getattr(request, "kind", None) is ProcedureBoundaryKind.ACTION:
            action_boundaries += 1
            if action_boundaries == 2:
                return {}
        return {facet: True for facet in request.facets}

    entry, registry = _entry_evidence(
        tmp_path,
        provider,
        operation_runner=lambda input_data: OperationSuccess(WRITE, {"written": True}),
        two_actions=True,
    )

    transcript = create_procedure_execution_session(entry, registry).execute()

    assert len(transcript.actions) == 1
    assert tuple(item.coordinate.occurrence for item in transcript.boundaries) == (0, 1)
    assert transcript.graph_disposition is ProcedureGraphDisposition.NO_TERMINAL
    assert (
        transcript.adjudication_disposition
        is ProcedureAdjudicationDisposition.AUTHORIZATION_ABORTED
    )
    assert any(
        item.state is ProcedureRequirementApplicabilityState.UNCHECKED
        for item in transcript.applicability
    )


def test_concurrent_execute_admits_one_caller_and_rejects_the_other(tmp_path) -> None:
    from threading import Event

    entered = Event()
    release = Event()

    def provider(request):
        entered.set()
        assert release.wait(timeout=5)
        return {facet: True for facet in request.facets}

    entry, entry_registry = _entry_evidence(
        tmp_path, lambda request: {facet: True for facet in request.facets}
    )
    from eutaxis.declarations import build_observation_provider_registry

    registry = build_observation_provider_registry(
        entry_registry.declarations,
        entry_registry.facets,
        cast(ObservationProvider, provider),
    )
    session = create_procedure_execution_session(entry, registry)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(session.execute)
        assert entered.wait(timeout=5)
        with pytest.raises(ProcedureExecutionError, match="not ready"):
            session.execute()
        release.set()
        transcript = future.result(timeout=5)

    assert session.transcript is transcript
    assert session.state is ProcedureExecutionSessionState.TERMINAL


def test_second_action_observation_resets_active_failure_stage(tmp_path) -> None:
    action_boundaries = 0

    def provider(request):
        nonlocal action_boundaries
        if getattr(request, "kind", None) is ProcedureBoundaryKind.ACTION:
            action_boundaries += 1
            if action_boundaries == 2:
                raise KeyboardInterrupt
        return {facet: True for facet in request.facets}

    entry, registry = _entry_evidence(
        tmp_path,
        provider,
        operation_runner=lambda input_data: OperationSuccess(WRITE, {"written": True}),
        two_actions=True,
    )
    session = create_procedure_execution_session(entry, registry)

    with pytest.raises(KeyboardInterrupt):
        session.execute()

    transcript = session.transcript
    assert transcript is not None and transcript.failure is not None
    assert transcript.failure.stage.value == "observation"
    assert transcript.failure.coordinate.occurrence == 1


def test_publication_compensates_one_interruption_from_error_handler(
    tmp_path, monkeypatch
) -> None:
    module = importlib.import_module("eutaxis.declarations.procedure_execution")
    original_require = module._require_control_authority
    checks = 0

    def require(control):
        nonlocal checks
        checks += 1
        if checks == 3:
            raise ProcedureExecutionError("$.run", "forced authority failure")
        original_require(control)

    class InterruptingRegistry(WeakKeyDictionary):
        interrupted = False

        def __setitem__(self, key, value):
            if not self.interrupted:
                self.interrupted = True
                raise KeyboardInterrupt
            super().__setitem__(key, value)

    monkeypatch.setattr(module, "_require_control_authority", require)
    monkeypatch.setattr(module, "_TRANSCRIPT_STATES", InterruptingRegistry())
    entry, registry = _entry_evidence(
        tmp_path, lambda request: {facet: True for facet in request.facets}
    )
    session = create_procedure_execution_session(entry, registry)

    with pytest.raises(KeyboardInterrupt):
        session.execute()

    transcript = session.transcript
    assert session.state is ProcedureExecutionSessionState.TERMINAL
    assert transcript is not None
    assert (
        transcript.adjudication_disposition
        is ProcedureAdjudicationDisposition.AUTHORITY_ABORTED
    )
    assert _is_issued_procedure_execution_transcript(transcript)


def test_factory_rejects_detached_action_not_correlated_with_final_live_state(
    tmp_path, monkeypatch
) -> None:
    module = importlib.import_module("eutaxis.declarations.procedure_execution")
    original_detach = module._detach

    def corrupt_detach(value):
        detached = original_detach(value)
        if type(value) is PreparedProcedureAction:
            object.__setattr__(detached.node, "on_success", "forged-terminal")
        return detached

    entry, registry = _entry_evidence(
        tmp_path, lambda request: {facet: True for facet in request.facets}
    )
    monkeypatch.setattr(module, "_detach", corrupt_detach)
    with pytest.raises(
        ProcedureExecutionError, match="changed during session preparation"
    ):
        create_procedure_execution_session(entry, registry)
    monkeypatch.setattr(module, "_detach", original_detach)

    assert (
        create_procedure_execution_session(entry, registry).state
        is ProcedureExecutionSessionState.READY
    )


def test_publication_rebuilds_after_transcript_capture_interruption(
    tmp_path, monkeypatch
) -> None:
    module = importlib.import_module("eutaxis.declarations.procedure_execution")
    original_require = module._require_control_authority
    original_capture = module._capture_transcript_state
    checks = 0
    interrupted = False

    def require(control):
        nonlocal checks
        checks += 1
        if checks == 3:
            raise ProcedureExecutionError("$.run", "forced authority failure")
        original_require(control)

    def capture(transcript):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise KeyboardInterrupt
        return original_capture(transcript)

    monkeypatch.setattr(module, "_require_control_authority", require)
    monkeypatch.setattr(module, "_capture_transcript_state", capture)
    entry, registry = _entry_evidence(
        tmp_path, lambda request: {facet: True for facet in request.facets}
    )
    session = create_procedure_execution_session(entry, registry)

    with pytest.raises(KeyboardInterrupt):
        session.execute()

    transcript = session.transcript
    assert session.state is ProcedureExecutionSessionState.TERMINAL
    assert transcript is not None
    assert _is_issued_procedure_execution_transcript(transcript)


def test_transient_live_runner_swap_cannot_change_captured_invocation(tmp_path) -> None:
    from types import MappingProxyType

    legitimate_calls = 0
    malicious_calls = 0

    def legitimate(input_data):
        nonlocal legitimate_calls
        legitimate_calls += 1
        return OperationSuccess(WRITE, {"written": True})

    entry, entry_registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        operation_runner=legitimate,
    )
    from eutaxis.declarations import build_observation_provider_registry

    live_operation_registry = entry.plan.run.operation_registry
    original_bindings = live_operation_registry.bindings

    def malicious(input_data):
        nonlocal malicious_calls
        malicious_calls += 1
        return OperationFailure(WRITE, "write-failed")

    def provider(request):
        if getattr(request, "kind", None) is ProcedureBoundaryKind.ACTION:
            replacement = {
                key: OperationRunnerBinding(key, cast(OperationRunner, malicious))
                for key in original_bindings
            }
            object.__setattr__(
                live_operation_registry,
                "bindings",
                MappingProxyType(replacement),
            )
            object.__setattr__(live_operation_registry, "bindings", original_bindings)
        return {facet: True for facet in request.facets}

    registry = build_observation_provider_registry(
        entry_registry.declarations,
        entry_registry.facets,
        cast(ObservationProvider, provider),
    )

    transcript = create_procedure_execution_session(entry, registry).execute()

    assert transcript.successful
    assert legitimate_calls == 1
    assert malicious_calls == 0
