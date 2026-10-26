"""Adversarial tests for the single-use rule-evidence transaction."""

from __future__ import annotations

import copy
import pickle
from collections.abc import Mapping
from dataclasses import replace
from inspect import Parameter, Signature
from pathlib import Path
from threading import Event, Thread
from typing import cast

import pytest

from eutaxis.declarations import (
    EvaluationState,
    RuleAssistedEvidence,
    RuleCriterionKey,
    RuleEvidence,
    RuleEvidenceError,
    RuleEvidenceSessionState,
    RuleManualEvidence,
    RuleManualJudgmentSubmission,
    RuleMechanicalEvidence,
    RuleResidualJudgmentSubmission,
    VersionedReference,
    create_rule_evidence_session,
    derive_attention_requirements,
    execute_known_failure_fixtures,
    plan_attention,
)
from eutaxis.declarations.rule_evidence import (
    _SESSION_CONTROLS,
    _capture_manual_submission,
    _capture_evidence_state,
    _is_issued_rule_evidence,
    _require_manual_captures,
)

from tests.test_attention import (
    Mode,
    _SingleTraversalInputs,
    _fixture_index,
    _inputs as evaluator_inputs,
    _mixed_plan,
    _prepare_registry,
)


class _EqualitySpoofingText(str):
    def __eq__(self, other: object) -> bool:
        return True


def _inputs(plan):
    manual = {}
    for entry in plan.deliberative.entries:
        if type(entry.obligation.key) is RuleCriterionKey:
            evaluator = entry.evaluator
            manual[entry.obligation.key] = RuleManualJudgmentSubmission(
                entry.obligation.key,
                VersionedReference(evaluator.id, evaluator.version),
                evaluator.input_revisions[0],
                {"conclusion": "satisfied"},
            )
    residual = {}
    for entry in plan.assisted.entries:
        if type(entry.obligation.key) is RuleCriterionKey:
            key = entry.obligation.key

            def provider(request, *, expected=key):
                assert request.requirement.key is expected
                return RuleResidualJudgmentSubmission(
                    1,
                    request,
                    EvaluationState.SATISFIED,
                    "The detector evidence leaves no violating candidate.",
                )

            residual[key] = provider
    return manual, residual


def _plan(tmp_path: Path, mode: Mode):
    _, declarations, resolution, checker, detector = _prepare_registry(tmp_path, mode)
    requirements = derive_attention_requirements(
        resolution,
        checker_registry=checker,
        detector_registry=detector,
    )
    fixtures = None
    assurance = None
    if checker is not None:
        fixtures = _fixture_index(tmp_path, checker)
        assurance = execute_known_failure_fixtures(declarations, fixtures, checker)
    return plan_attention(
        requirements,
        evaluator_inputs(requirements),
        fixture_index=fixtures,
        assurance=assurance,
    )


@pytest.mark.parametrize(
    "mode,record_types",
    [
        ("none", ()),
        ("manual", (RuleManualEvidence,)),
        ("assisted", (RuleAssistedEvidence,)),
        ("mechanical", (RuleMechanicalEvidence,)),
    ],
)
def test_rule_evidence_supports_empty_and_single_class_plans(
    tmp_path: Path, mode: Mode, record_types: tuple[type, ...]
) -> None:
    plan = _plan(tmp_path, mode)
    manual, residual = _inputs(plan)

    evidence = create_rule_evidence_session(plan).execute(
        manual=manual, residual_providers=residual
    )

    assert tuple(type(record) for record in evidence.records) == record_types
    assert _is_issued_rule_evidence(evidence)


def test_mixed_rule_evidence_preserves_canonical_rule_order(tmp_path: Path) -> None:
    _, _, _, _, plan = _mixed_plan(tmp_path)
    manual, residual = _inputs(plan)

    evidence = create_rule_evidence_session(plan).execute(
        manual=manual, residual_providers=residual
    )

    assert _is_issued_rule_evidence(evidence)
    assert tuple(type(record) for record in evidence.records) == (
        RuleManualEvidence,
        RuleAssistedEvidence,
        RuleMechanicalEvidence,
    )
    assert all(
        type(record.requirement.key) is RuleCriterionKey for record in evidence.records
    )
    assert all(record.state is EvaluationState.SATISFIED for record in evidence.records)


def test_rule_input_mappings_are_traversed_once(tmp_path: Path) -> None:
    _, _, _, _, plan = _mixed_plan(tmp_path)
    manual, residual = _inputs(plan)
    hostile_manual = _SingleTraversalInputs(manual)
    hostile_residual = _SingleTraversalInputs(residual)

    evidence = create_rule_evidence_session(plan).execute(
        manual=cast(Mapping, hostile_manual),
        residual_providers=cast(Mapping, hostile_residual),
    )

    assert _is_issued_rule_evidence(evidence)
    assert hostile_manual.traversals == 1
    assert hostile_residual.traversals == 1


def test_missing_rule_input_fails_the_claimed_session(tmp_path: Path) -> None:
    _, _, _, _, plan = _mixed_plan(tmp_path)
    manual, residual = _inputs(plan)
    session = create_rule_evidence_session(plan)

    with pytest.raises(RuleEvidenceError, match="exact required keys"):
        session.execute(manual={}, residual_providers=residual)

    assert session.state is RuleEvidenceSessionState.FAILED_AFTER_EXECUTION
    assert session.evidence is None
    with pytest.raises(RuleEvidenceError, match="not ready"):
        session.execute(manual=manual, residual_providers=residual)


def test_residual_provider_failure_publishes_terminal_state(tmp_path: Path) -> None:
    _, _, _, _, plan = _mixed_plan(tmp_path)
    manual, residual = _inputs(plan)
    key = next(iter(residual))

    def failure(request):
        raise RuntimeError("residual failed")

    residual[key] = failure
    session = create_rule_evidence_session(plan)

    with pytest.raises(RuleEvidenceError, match="provider raised"):
        session.execute(manual=manual, residual_providers=residual)

    assert session.state is RuleEvidenceSessionState.FAILED_AFTER_EXECUTION


def test_residual_provider_interruption_is_re_raised_after_publication(
    tmp_path: Path,
) -> None:
    _, _, _, _, plan = _mixed_plan(tmp_path)
    manual, residual = _inputs(plan)
    key = next(iter(residual))

    def interrupt(request):
        raise KeyboardInterrupt("stop")

    residual[key] = interrupt
    session = create_rule_evidence_session(plan)

    with pytest.raises(KeyboardInterrupt):
        session.execute(manual=manual, residual_providers=residual)

    assert session.state is RuleEvidenceSessionState.FAILED_AFTER_EXECUTION
    assert session.evidence is None


def test_stale_fixture_prevents_rule_evidence(tmp_path: Path) -> None:
    _, _, fixtures, _, plan = _mixed_plan(tmp_path)
    manual, residual = _inputs(plan)
    fixture = next(iter(fixtures.fixtures.values()))
    source = next(digest.path for digest in fixture.digests if digest.role == "source")
    source.write_text("changed: true\n", encoding="utf-8")
    session = create_rule_evidence_session(plan)

    with pytest.raises(RuleEvidenceError, match="source file changed"):
        session.execute(manual=manual, residual_providers=residual)

    assert session.state is RuleEvidenceSessionState.FAILED_AFTER_EXECUTION


def test_canonical_manual_record_isolated_from_caller_mutation(tmp_path: Path) -> None:
    _, _, _, _, plan = _mixed_plan(tmp_path)
    manual, residual = _inputs(plan)
    source = next(iter(manual.values()))
    evidence = create_rule_evidence_session(plan).execute(
        manual=manual, residual_providers=residual
    )
    record = cast(RuleManualEvidence, evidence.records[0])

    object.__setattr__(source, "input_revision", "changed")

    assert record.submission is not source
    assert record.submission.input_revision != source.input_revision
    assert _is_issued_rule_evidence(evidence)


def test_rule_evidence_rejects_equal_record_self_attestation(tmp_path: Path) -> None:
    _, _, _, _, plan = _mixed_plan(tmp_path)
    manual, residual = _inputs(plan)
    evidence = create_rule_evidence_session(plan).execute(
        manual=manual, residual_providers=residual
    )
    records = list(evidence.records)
    records[0] = replace(records[0])
    object.__setattr__(evidence, "records", tuple(records))
    object.__setattr__(evidence, "_state", _capture_evidence_state(evidence))

    assert not _is_issued_rule_evidence(evidence)


def test_rule_evidence_aggregate_rejects_reconstruction(tmp_path: Path) -> None:
    _, _, _, _, plan = _mixed_plan(tmp_path)
    manual, residual = _inputs(plan)
    evidence = create_rule_evidence_session(plan).execute(
        manual=manual, residual_providers=residual
    )

    with pytest.raises(TypeError, match="issued by execution"):
        RuleEvidence()
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(evidence)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.deepcopy(evidence)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(evidence)


def test_attention_plan_can_own_only_one_rule_evidence_session(tmp_path: Path) -> None:
    _, _, _, _, plan = _mixed_plan(tmp_path)
    create_rule_evidence_session(plan)

    with pytest.raises(RuleEvidenceError, match="already owns"):
        create_rule_evidence_session(plan)


def test_reentrant_rejection_does_not_corrupt_active_transaction(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path, "assisted")
    manual, residual = _inputs(plan)
    key = next(iter(residual))
    session = create_rule_evidence_session(plan)

    def provider(request):
        with pytest.raises(RuleEvidenceError, match="not ready"):
            session.execute(manual=manual, residual_providers=residual)
        assert session.state is RuleEvidenceSessionState.RUNNING
        return RuleResidualJudgmentSubmission(
            1, request, EvaluationState.SATISFIED, "Residual review completed."
        )

    residual[key] = provider

    evidence = session.execute(manual=manual, residual_providers=residual)

    assert session.state is RuleEvidenceSessionState.COMPLETED
    assert session.evidence is evidence


def test_concurrent_rejection_does_not_corrupt_active_transaction(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path, "assisted")
    manual, residual = _inputs(plan)
    key = next(iter(residual))
    entered = Event()
    release = Event()
    outcome: list[RuleEvidence | BaseException] = []
    session = create_rule_evidence_session(plan)

    def provider(request):
        entered.set()
        assert release.wait(timeout=5)
        return RuleResidualJudgmentSubmission(
            1, request, EvaluationState.SATISFIED, "Residual review completed."
        )

    def execute() -> None:
        try:
            outcome.append(session.execute(manual=manual, residual_providers=residual))
        except BaseException as exc:  # pragma: no cover - assertion reports content
            outcome.append(exc)

    residual[key] = provider
    thread = Thread(target=execute)
    thread.start()
    assert entered.wait(timeout=5)

    with pytest.raises(RuleEvidenceError, match="not ready"):
        session.execute(manual=manual, residual_providers=residual)
    assert session.state is RuleEvidenceSessionState.RUNNING

    release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(outcome) == 1 and type(outcome[0]) is RuleEvidence
    assert session.state is RuleEvidenceSessionState.COMPLETED


@pytest.mark.parametrize(
    "mutation",
    [
        "request-requirement",
        "request-question",
        "request-execution",
        "request-issuer",
        "execution-registry",
        "execution-evaluator",
        "execution-revision",
        "execution-input",
        "execution-evidence",
    ],
)
def test_residual_provider_cannot_mutate_request_or_execution(
    tmp_path: Path, mutation: str
) -> None:
    plan = _plan(tmp_path, "assisted")
    manual, residual = _inputs(plan)
    key = next(iter(residual))

    def provider(request):
        execution = request.execution
        if mutation == "request-requirement":
            object.__setattr__(request, "requirement", object())
        elif mutation == "request-question":
            object.__setattr__(request, "residual_question", "changed")
        elif mutation == "request-execution":
            object.__setattr__(request, "execution", object())
        elif mutation == "request-issuer":
            object.__setattr__(request, "_issuer", object())
        elif mutation == "execution-registry":
            object.__setattr__(execution, "registry", object())
        elif mutation == "execution-evaluator":
            object.__setattr__(execution, "evaluator", VersionedReference("x", 1))
        elif mutation == "execution-revision":
            object.__setattr__(execution, "input_revision", "changed")
        elif mutation == "execution-input":
            object.__setattr__(execution, "input_data", {"changed": True})
        else:
            object.__setattr__(execution, "evidence", {"changed": True})
        return RuleResidualJudgmentSubmission(
            1, request, EvaluationState.SATISFIED, "Residual review completed."
        )

    residual[key] = provider
    session = create_rule_evidence_session(plan)

    with pytest.raises(RuleEvidenceError, match="(authority|carrier|content)"):
        session.execute(manual=manual, residual_providers=residual)

    assert session.state is RuleEvidenceSessionState.FAILED_AFTER_EXECUTION
    assert session.evidence is None


def test_interrupting_mapping_authority_failure_takes_precedence(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path, "manual")

    class InterruptingMapping(Mapping):
        def __getitem__(self, key):
            raise KeyError(key)

        def __iter__(self):
            object.__setattr__(plan, "_state", ())
            raise KeyboardInterrupt("stop")

        def __len__(self):
            return 1

    session = create_rule_evidence_session(plan)

    with pytest.raises(RuleEvidenceError, match="no longer authoritative"):
        session.execute(manual=InterruptingMapping(), residual_providers={})

    assert session.state is RuleEvidenceSessionState.FAILED_AFTER_EXECUTION


def test_interrupting_signature_authority_failure_takes_precedence(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path, "assisted")
    manual, residual = _inputs(plan)
    key = next(iter(residual))

    class InterruptingProvider:
        @property
        def __signature__(self):
            object.__setattr__(plan, "_state", ())
            raise KeyboardInterrupt("stop")

        def __call__(self, request):
            raise AssertionError("provider must not run")

    residual[key] = InterruptingProvider()
    session = create_rule_evidence_session(plan)

    with pytest.raises(RuleEvidenceError, match="no longer authoritative"):
        session.execute(manual=manual, residual_providers=residual)

    assert session.state is RuleEvidenceSessionState.FAILED_AFTER_EXECUTION


def test_invalid_manual_evaluator_carrier_is_rejected(tmp_path: Path) -> None:
    plan = _plan(tmp_path, "manual")
    manual, residual = _inputs(plan)
    key = next(iter(manual))
    submission = manual[key]

    class HostileEvaluator:
        def __eq__(self, other):
            raise RuntimeError("escaped equality")

    object.__setattr__(submission, "evaluator", HostileEvaluator())
    session = create_rule_evidence_session(plan)

    with pytest.raises(RuleEvidenceError, match="evaluator reference is invalid"):
        session.execute(manual=manual, residual_providers=residual)

    assert session.state is RuleEvidenceSessionState.FAILED_AFTER_EXECUTION


def test_manual_submission_is_canonical_before_provider_signature_inspection(
    tmp_path: Path,
) -> None:
    _, _, _, _, plan = _mixed_plan(tmp_path)
    manual, residual = _inputs(plan)
    manual_source = next(iter(manual.values()))
    residual_key = next(iter(residual))

    class MutatingSignatureProvider:
        @property
        def __signature__(self):
            object.__setattr__(manual_source, "input_revision", "changed")
            return Signature([Parameter("request", Parameter.POSITIONAL_ONLY)])

        def __call__(self, request):
            return RuleResidualJudgmentSubmission(
                1,
                request,
                EvaluationState.SATISFIED,
                "Residual review completed.",
            )

    residual[residual_key] = MutatingSignatureProvider()

    evidence = create_rule_evidence_session(plan).execute(
        manual=manual, residual_providers=residual
    )

    record = cast(RuleManualEvidence, evidence.records[0])
    assert manual_source.input_revision == "changed"
    assert record.submission.input_revision == "declaration-v1"
    assert _is_issued_rule_evidence(evidence)


def test_request_mutation_precedes_simultaneous_provider_failure(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path, "assisted")
    manual, residual = _inputs(plan)
    key = next(iter(residual))

    def provider(request):
        object.__setattr__(request, "residual_question", "changed")
        raise RuntimeError("provider failed too")

    residual[key] = provider
    session = create_rule_evidence_session(plan)

    with pytest.raises(RuleEvidenceError, match="request authority changed"):
        session.execute(manual=manual, residual_providers=residual)

    assert session.state is RuleEvidenceSessionState.FAILED_AFTER_EXECUTION


def test_blocked_detector_does_not_prevent_later_mechanical_evidence(
    tmp_path: Path,
) -> None:
    def blocked_detector(input_data):
        raise RuntimeError("detector unavailable")

    _, declarations, resolution, checker, detector = _prepare_registry(
        tmp_path,
        "mixed",
        detector_runner=blocked_detector,
    )
    assert checker is not None and detector is not None
    requirements = derive_attention_requirements(
        resolution,
        checker_registry=checker,
        detector_registry=detector,
    )
    fixtures = _fixture_index(tmp_path, checker)
    assurance = execute_known_failure_fixtures(declarations, fixtures, checker)
    plan = plan_attention(
        requirements,
        evaluator_inputs(requirements),
        fixture_index=fixtures,
        assurance=assurance,
    )
    manual, residual = _inputs(plan)

    evidence = create_rule_evidence_session(plan).execute(
        manual=manual, residual_providers=residual
    )

    assisted = cast(RuleAssistedEvidence, evidence.records[1])
    mechanical = cast(RuleMechanicalEvidence, evidence.records[2])
    assert assisted.state is EvaluationState.BLOCKED
    assert assisted.execution is None and assisted.diagnostic
    assert mechanical.result is not None
    assert mechanical.state is EvaluationState.SATISFIED


def test_private_requirement_replacement_cannot_self_attest(tmp_path: Path) -> None:
    plan = _plan(tmp_path, "manual")
    manual, residual = _inputs(plan)
    session = create_rule_evidence_session(plan)

    class MutatingMapping(_SingleTraversalInputs):
        def __iter__(self):
            control = _SESSION_CONTROLS[session]
            control.requirements = ()
            return super().__iter__()

    with pytest.raises(RuleEvidenceError, match="session authority differs"):
        session.execute(
            manual=cast(Mapping, MutatingMapping(manual)),
            residual_providers=residual,
        )

    assert session.state is RuleEvidenceSessionState.FAILED_AFTER_EXECUTION
    assert session.evidence is None


def test_private_input_replacement_cannot_self_attest(tmp_path: Path) -> None:
    plan = _plan(tmp_path, "assisted")
    manual, residual = _inputs(plan)
    key = next(iter(residual))
    session = create_rule_evidence_session(plan)

    def provider(request):
        control = _SESSION_CONTROLS[session]
        assert control.inputs is not None
        control.inputs = replace(control.inputs, providers=(provider,))
        return RuleResidualJudgmentSubmission(
            1, request, EvaluationState.SATISFIED, "Residual review completed."
        )

    residual[key] = provider

    with pytest.raises(RuleEvidenceError, match="session authority differs"):
        session.execute(manual=manual, residual_providers=residual)

    assert session.state is RuleEvidenceSessionState.FAILED_AFTER_EXECUTION
    assert session.evidence is None


def test_all_manual_carriers_are_guarded_before_canonicalization() -> None:
    first_key = RuleCriterionKey("rule/one", "criterion")
    second_key = RuleCriterionKey("rule/two", "criterion")
    evaluator = VersionedReference("registry/manual", 1)
    first = RuleManualJudgmentSubmission(
        first_key, evaluator, "declaration-v1", {"conclusion": "satisfied"}
    )
    second = RuleManualJudgmentSubmission(
        second_key, evaluator, "declaration-v1", {"conclusion": "satisfied"}
    )
    captures = (
        _capture_manual_submission(first, 0),
        _capture_manual_submission(second, 1),
    )

    object.__setattr__(second, "input_revision", "changed")

    with pytest.raises(RuleEvidenceError, match="captured submission authority"):
        _require_manual_captures(captures)


@pytest.mark.parametrize("schema_version", [True, 1.0])
def test_residual_schema_version_requires_exact_integer(
    tmp_path: Path, schema_version: object
) -> None:
    plan = _plan(tmp_path, "assisted")
    manual, residual = _inputs(plan)
    key = next(iter(residual))

    def provider(request):
        return RuleResidualJudgmentSubmission(
            cast(int, schema_version),
            request,
            EvaluationState.SATISFIED,
            "Residual review completed.",
        )

    residual[key] = provider
    session = create_rule_evidence_session(plan)

    with pytest.raises(RuleEvidenceError, match="correlation is invalid"):
        session.execute(manual=manual, residual_providers=residual)

    assert session.state is RuleEvidenceSessionState.FAILED_AFTER_EXECUTION


def test_callback_cannot_forge_completed_publication(tmp_path: Path) -> None:
    plan = _plan(tmp_path, "assisted")
    manual, residual = _inputs(plan)
    key = next(iter(residual))
    session = create_rule_evidence_session(plan)

    def provider(request):
        control = _SESSION_CONTROLS[session]
        control.publication = (RuleEvidenceSessionState.COMPLETED, None)
        raise RuntimeError("provider failed")

    residual[key] = provider

    with pytest.raises(RuleEvidenceError, match="session authority differs"):
        session.execute(manual=manual, residual_providers=residual)

    assert session.state is RuleEvidenceSessionState.FAILED_AFTER_EXECUTION
    assert session.evidence is None


def test_callback_cannot_reopen_session_for_reentrant_execution(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path, "assisted")
    manual, residual = _inputs(plan)
    key = next(iter(residual))
    session = create_rule_evidence_session(plan)
    calls = 0

    def provider(request):
        nonlocal calls
        calls += 1
        control = _SESSION_CONTROLS[session]
        control.publication = (RuleEvidenceSessionState.READY, None)
        control.active = False
        with pytest.raises(RuleEvidenceError, match="session authority differs"):
            session.execute(manual=manual, residual_providers=residual)
        return RuleResidualJudgmentSubmission(
            1, request, EvaluationState.SATISFIED, "Residual review completed."
        )

    residual[key] = provider

    with pytest.raises(RuleEvidenceError, match="session authority differs"):
        session.execute(manual=manual, residual_providers=residual)

    assert calls == 1
    assert session.state is RuleEvidenceSessionState.FAILED_AFTER_EXECUTION
    assert session.evidence is None


def test_manual_evaluator_rejects_equality_spoof(tmp_path: Path) -> None:
    plan = _plan(tmp_path, "manual")
    manual, residual = _inputs(plan)
    submission = next(iter(manual.values()))

    class EqualToEveryReference:
        def __eq__(self, other):
            return True

    object.__setattr__(submission, "evaluator", EqualToEveryReference())
    session = create_rule_evidence_session(plan)

    with pytest.raises(RuleEvidenceError, match="evaluator reference is invalid"):
        session.execute(manual=manual, residual_providers=residual)

    assert session.state is RuleEvidenceSessionState.FAILED_AFTER_EXECUTION


@pytest.mark.parametrize(
    "reference",
    [
        VersionedReference("registry/manual", True),
        VersionedReference(_EqualitySpoofingText("wrong"), 1),
    ],
)
def test_manual_evaluator_rejects_malformed_reference_fields(
    tmp_path: Path, reference: VersionedReference
) -> None:
    plan = _plan(tmp_path, "manual")
    manual, residual = _inputs(plan)
    submission = next(iter(manual.values()))
    object.__setattr__(submission, "evaluator", reference)
    session = create_rule_evidence_session(plan)

    with pytest.raises(RuleEvidenceError, match="evaluator reference is invalid"):
        session.execute(manual=manual, residual_providers=residual)

    assert session.state is RuleEvidenceSessionState.FAILED_AFTER_EXECUTION
