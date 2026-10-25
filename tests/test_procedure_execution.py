"""Exercise the high-level evaluator-less procedure execution boundary."""

from __future__ import annotations

import gc
import importlib
import pickle
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields, is_dataclass
from threading import Barrier
from typing import cast
from weakref import ref
from weakref import WeakKeyDictionary

import pytest

from eutaxis.declarations import (
    ObservationProvider,
    OperationFailure,
    OperationRunner,
    OperationRunnerBinding,
    OperationSuccess,
    PreparedProcedureAction,
    ProcedureAdjudicationDisposition,
    ProcedureBoundaryKind,
    ProcedureExecutionSessionState,
    ProcedureGraphDisposition,
    ProcedureRequirementApplicabilityState,
    create_pre_action_evidence_session,
    create_procedure_execution_session,
)
from eutaxis.declarations.exceptions import ProcedureExecutionError
from eutaxis.declarations.procedure_execution import (
    _is_issued_procedure_execution_transcript,
)

from tests.test_attention import WRITE, _pre_action_authorities


def _entry_evidence(
    tmp_path,
    provider,
    *,
    operation_runner=None,
    later_requirements=True,
    evaluator_backed_lifecycle=False,
    two_actions=False,
):
    plan, observation, manual, residual = _pre_action_authorities(
        tmp_path,
        observation_provider=cast(ObservationProvider, provider),
        later_requirements=later_requirements,
        evaluator_backed_lifecycle=evaluator_backed_lifecycle,
        two_actions=two_actions,
        **(
            {}
            if operation_runner is None
            else {"operation_runner": cast(OperationRunner, operation_runner)}
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
    assert transcript.boundaries[0].evidence is None
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


def test_evaluator_backed_lifecycle_rejection_precedes_claim_installation(
    tmp_path,
) -> None:
    entry, registry = _entry_evidence(
        tmp_path,
        lambda request: {facet: True for facet in request.facets},
        evaluator_backed_lifecycle=True,
    )

    for _ in range(2):
        with pytest.raises(ProcedureExecutionError, match="evaluator-backed"):
            create_procedure_execution_session(entry, registry)


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
