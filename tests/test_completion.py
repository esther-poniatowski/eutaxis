"""Adversarial tests for callback-free completion reconciliation."""

from __future__ import annotations

import copy
import inspect
import pickle
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from types import MappingProxyType
from typing import cast

import pytest

from eutaxis.declarations import (
    CompletionLedger,
    CompletionLedgerError,
    CompletionState,
    EvaluationState,
    ManualJudgmentSubmission,
    OperationSuccess,
    ProcedureOutcomeState,
    RuleEvidence,
    build_completion_ledger,
    create_pre_action_evidence_session,
    create_procedure_execution_session,
    create_rule_evidence_session,
)
from eutaxis.declarations.completion import _is_issued_completion_ledger
from eutaxis.declarations.pre_action_evidence import (
    _capture_evidence_state as _capture_preaction_state,
)
from eutaxis.declarations.pre_action_evidence import (
    _capture_record_state,
    _is_issued_pre_action_evidence,
)
from eutaxis.declarations.procedure_execution import (
    _is_issued_procedure_execution_transcript,
)

from tests.test_attention import WRITE, _pre_action_authorities
from tests.test_rule_evidence import _inputs as rule_inputs
from tests.test_rule_evidence import _plan as rule_plan

NOW = datetime(2026, 10, 26, 11, 30, tzinfo=timezone.utc)


def _rule_evidence(plan) -> RuleEvidence:
    manual, residual = rule_inputs(plan)
    return create_rule_evidence_session(plan).execute(
        manual=manual, residual_providers=residual
    )


def _procedure_bundle(tmp_path: Path, *, success: bool = True, uncleared: bool = False):
    operation_runner = (
        (lambda input_data: OperationSuccess(WRITE, {"written": True}))
        if success
        else None
    )
    plan, observation, manual, residual = _pre_action_authorities(
        tmp_path,
        **({} if operation_runner is None else {"operation_runner": operation_runner}),
    )
    if uncleared:
        key = next(iter(manual))
        submission = manual[key]
        manual[key] = replace(submission, evidence={"conclusion": "violated"})
    entry = create_pre_action_evidence_session(plan, observation).execute(
        manual=manual,
        residual_providers=residual,
    )
    attention = plan.run.attention
    rules = _rule_evidence(attention)
    if uncleared:
        return attention, rules, entry
    transcript = create_procedure_execution_session(
        entry, observation.registry
    ).execute()
    return attention, rules, transcript


def test_rule_only_satisfied_plan_completes(tmp_path: Path) -> None:
    plan = rule_plan(tmp_path, "manual")
    evidence = _rule_evidence(plan)

    ledger = build_completion_ledger(plan, evidence, {}, clock=lambda: NOW)

    assert _is_issued_completion_ledger(ledger)
    assert ledger.successful
    assert ledger.timestamp == "2026-10-26T11:30:00.000000Z"
    assert tuple(record.state for record in ledger.records) == (
        CompletionState.SATISFIED,
    )


def test_missing_rule_evidence_is_unchecked(tmp_path: Path) -> None:
    plan = rule_plan(tmp_path, "manual")

    ledger = build_completion_ledger(plan, None, {}, clock=lambda: NOW)

    assert not ledger.successful
    assert ledger.records[0].state is CompletionState.UNCHECKED
    assert ledger.records[0].sources == ()


def test_successful_procedure_and_rule_evidence_complete(tmp_path: Path) -> None:
    plan, rules, transcript = _procedure_bundle(tmp_path)

    ledger = build_completion_ledger(
        plan, rules, {"content/write": transcript}, clock=lambda: NOW
    )

    assert ledger.successful
    assert ledger.procedure_outcomes[0].state is ProcedureOutcomeState.SUCCESSFUL
    assert all(
        record.state in {CompletionState.SATISFIED, CompletionState.INAPPLICABLE}
        for record in ledger.records
    )
    assert all(record.timestamp == ledger.timestamp for record in ledger.records)


def test_missing_procedure_outcome_is_incomplete(tmp_path: Path) -> None:
    plan, rules, _ = _procedure_bundle(tmp_path)

    ledger = build_completion_ledger(plan, rules, {}, clock=lambda: NOW)

    assert not ledger.successful
    assert ledger.procedure_outcomes[0].state is ProcedureOutcomeState.UNCHECKED
    assert any(record.state is CompletionState.UNCHECKED for record in ledger.records)


def test_uncleared_preaction_imports_entry_and_leaves_later_unchecked(
    tmp_path: Path,
) -> None:
    plan, rules, entry = _procedure_bundle(tmp_path, uncleared=True)

    ledger = build_completion_ledger(
        plan, rules, {"content/write": entry}, clock=lambda: NOW
    )

    assert not ledger.successful
    assert ledger.procedure_outcomes[0].state is ProcedureOutcomeState.UNCLEARED
    assert any(record.state is CompletionState.VIOLATED for record in ledger.records)
    assert any(record.state is CompletionState.UNCHECKED for record in ledger.records)


def test_failure_terminal_is_not_success(tmp_path: Path) -> None:
    plan, rules, transcript = _procedure_bundle(tmp_path, success=False)

    ledger = build_completion_ledger(
        plan, rules, {"content/write": transcript}, clock=lambda: NOW
    )

    assert not ledger.successful
    assert ledger.procedure_outcomes[0].state is ProcedureOutcomeState.UNSUCCESSFUL


def test_cleared_preaction_requires_transcript(tmp_path: Path) -> None:
    plan, observation, manual, residual = _pre_action_authorities(tmp_path)
    entry = create_pre_action_evidence_session(plan, observation).execute(
        manual=manual, residual_providers=residual
    )
    attention = plan.run.attention

    with pytest.raises(CompletionLedgerError, match="requires a terminal transcript"):
        build_completion_ledger(
            attention,
            _rule_evidence(attention),
            {"content/write": entry},
            clock=lambda: NOW,
        )


def test_outcome_mapping_is_traversed_once(tmp_path: Path) -> None:
    plan, rules, transcript = _procedure_bundle(tmp_path)

    class SingleTraversal(Mapping):
        def __init__(self) -> None:
            self.traversals = 0

        def __getitem__(self, key):
            if key == "content/write":
                return transcript
            raise KeyError(key)

        def __iter__(self):
            self.traversals += 1
            if self.traversals > 1:
                raise RuntimeError("mapping traversed twice")
            return iter(("content/write",))

        def __len__(self):
            return 1

    supplied = SingleTraversal()

    ledger = build_completion_ledger(
        plan, rules, cast(Mapping, supplied), clock=lambda: NOW
    )

    assert ledger.successful
    assert supplied.traversals == 1


@pytest.mark.parametrize(
    "clock,message",
    [
        (lambda value=None: NOW, "exactly zero"),
        (lambda *, value=None: NOW, "exactly zero"),
        (lambda **kwargs: NOW, "exactly zero"),
        (lambda: datetime(2026, 10, 26, 11, 30), "UTC-aware"),
        (
            lambda: datetime(2026, 10, 26, 12, 30, tzinfo=timezone(timedelta(hours=1))),
            "UTC-aware",
        ),
        (lambda: "now", "exact datetime"),
    ],
)
def test_clock_contract_is_exact(tmp_path: Path, clock, message: str) -> None:
    plan = rule_plan(tmp_path, "manual")

    with pytest.raises(CompletionLedgerError, match=message):
        build_completion_ledger(plan, _rule_evidence(plan), {}, clock=clock)


def test_clock_runs_once_after_reconciliation(tmp_path: Path) -> None:
    plan = rule_plan(tmp_path, "manual")
    calls = 0

    def clock() -> datetime:
        nonlocal calls
        calls += 1
        return NOW

    build_completion_ledger(plan, _rule_evidence(plan), {}, clock=clock)

    assert calls == 1


def test_clock_cannot_forge_unsuccessful_procedure_state(tmp_path: Path) -> None:
    plan, rules, transcript = _procedure_bundle(tmp_path, success=False)

    def clock() -> datetime:
        frame = inspect.currentframe()
        assert frame is not None and frame.f_back is not None
        reconciliation = frame.f_back.f_locals["reconciliation"]
        object.__setattr__(
            reconciliation.completions[0],
            "state",
            ProcedureOutcomeState.SUCCESSFUL,
        )
        return NOW

    with pytest.raises(
        CompletionLedgerError, match="captured mapping authority changed"
    ):
        build_completion_ledger(
            plan,
            rules,
            {"content/write": transcript},
            clock=clock,
        )


def test_clock_cannot_forge_unchecked_requirement_state(tmp_path: Path) -> None:
    plan = rule_plan(tmp_path, "manual")

    def clock() -> datetime:
        frame = inspect.currentframe()
        assert frame is not None and frame.f_back is not None
        reconciliation = frame.f_back.f_locals["reconciliation"]
        object.__setattr__(
            reconciliation.records[0], "state", CompletionState.SATISFIED
        )
        return NOW

    with pytest.raises(
        CompletionLedgerError, match="captured reconciliation authority changed"
    ):
        build_completion_ledger(plan, None, {}, clock=clock)


def test_cross_plan_and_additional_outcomes_are_rejected(tmp_path: Path) -> None:
    first_plan, first_rules, transcript = _procedure_bundle(tmp_path / "first")
    second_plan, second_rules, _ = _procedure_bundle(tmp_path / "second")

    with pytest.raises(CompletionLedgerError, match="correlation differs"):
        build_completion_ledger(
            second_plan,
            second_rules,
            {"content/write": transcript},
            clock=lambda: NOW,
        )
    with pytest.raises(CompletionLedgerError, match="effective procedure"):
        build_completion_ledger(
            first_plan,
            first_rules,
            {"content/write": transcript, "not/effective": transcript},
            clock=lambda: NOW,
        )


def test_completion_ledger_rejects_reconstruction_and_mutation(
    tmp_path: Path,
) -> None:
    plan = rule_plan(tmp_path, "manual")
    ledger = build_completion_ledger(plan, _rule_evidence(plan), {}, clock=lambda: NOW)

    with pytest.raises(TypeError, match="issued by reconciliation"):
        CompletionLedger()
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(ledger)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.deepcopy(ledger)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(ledger)

    object.__setattr__(ledger.records[0], "state", CompletionState.BLOCKED)
    assert not _is_issued_completion_ledger(ledger)


def test_uncleared_preaction_cannot_self_attest_forged_records(
    tmp_path: Path,
) -> None:
    plan, observation, manual, residual = _pre_action_authorities(tmp_path)
    entry = create_pre_action_evidence_session(plan, observation).execute(
        manual=manual, residual_providers=residual
    )
    records = list(entry.records)
    records[0] = replace(
        records[0],
        state=EvaluationState.BLOCKED,
        evidence=MappingProxyType({"conclusion": "blocked"}),
    )
    object.__setattr__(entry, "records", tuple(records))
    object.__setattr__(entry, "cleared", False)
    object.__setattr__(entry, "_record_state", _capture_record_state(entry.records))
    object.__setattr__(entry, "_state", _capture_preaction_state(entry))

    assert not _is_issued_pre_action_evidence(entry)
    with pytest.raises(CompletionLedgerError, match="not authoritative"):
        build_completion_ledger(
            plan.run.attention,
            _rule_evidence(plan.run.attention),
            {"content/write": entry},
            clock=lambda: NOW,
        )


def test_clock_mapping_mutation_does_not_change_captured_outcomes(
    tmp_path: Path,
) -> None:
    plan, rules, transcript = _procedure_bundle(tmp_path)
    outcomes = {"content/write": transcript}

    def clock() -> datetime:
        outcomes.clear()
        return NOW

    ledger = build_completion_ledger(plan, rules, outcomes, clock=clock)

    assert ledger.successful
    assert _is_issued_completion_ledger(ledger)
    assert outcomes == {}


def test_clock_failure_does_not_hide_authority_mutation(tmp_path: Path) -> None:
    plan = rule_plan(tmp_path, "manual")
    evidence = _rule_evidence(plan)

    def clock() -> datetime:
        object.__setattr__(evidence, "records", ())
        raise RuntimeError("clock failed")

    with pytest.raises(
        CompletionLedgerError, match="rule evidence is not authoritative"
    ):
        build_completion_ledger(plan, evidence, {}, clock=clock)


def test_clock_signature_failure_does_not_hide_authority_mutation(
    tmp_path: Path,
) -> None:
    plan = rule_plan(tmp_path, "manual")
    evidence = _rule_evidence(plan)

    class HostileClock:
        @property
        def __signature__(self):
            object.__setattr__(evidence, "records", ())
            raise RuntimeError("signature failed")

        def __call__(self) -> datetime:
            return NOW

    with pytest.raises(
        CompletionLedgerError, match="rule evidence is not authoritative"
    ):
        build_completion_ledger(plan, evidence, {}, clock=HostileClock())


def test_hostile_timezone_is_normalized_to_public_error(tmp_path: Path) -> None:
    plan = rule_plan(tmp_path, "manual")

    class HostileTimezone(tzinfo):
        def utcoffset(self, dt):
            raise RuntimeError("offset unavailable")

        def dst(self, dt):
            return timedelta(0)

    with pytest.raises(CompletionLedgerError, match="could not be normalized"):
        build_completion_ledger(
            plan,
            _rule_evidence(plan),
            {},
            clock=lambda: datetime(2026, 10, 26, tzinfo=HostileTimezone()),
        )


def test_timestamp_normalization_revalidates_sources(tmp_path: Path) -> None:
    plan = rule_plan(tmp_path, "manual")
    evidence = _rule_evidence(plan)

    class MutatingTimezone(tzinfo):
        def utcoffset(self, dt):
            object.__setattr__(evidence, "records", ())
            return timedelta(0)

        def dst(self, dt):
            return timedelta(0)

    with pytest.raises(
        CompletionLedgerError, match="rule evidence is not authoritative"
    ):
        build_completion_ledger(
            plan,
            evidence,
            {},
            clock=lambda: datetime(2026, 10, 26, tzinfo=MutatingTimezone()),
        )


def test_transcript_uses_retained_entry_evidence_after_origin_mutation(
    tmp_path: Path,
) -> None:
    plan, rules, transcript = _procedure_bundle(tmp_path)
    entry = transcript.authority.entry_evidence_origin
    retained = transcript.authority.entry_evidence_records
    records = list(entry.records)
    records[0] = replace(
        records[0],
        state=EvaluationState.BLOCKED,
        evidence=MappingProxyType({"conclusion": "blocked"}),
    )
    object.__setattr__(entry, "records", tuple(records))
    object.__setattr__(entry, "cleared", False)
    object.__setattr__(entry, "_record_state", _capture_record_state(entry.records))
    object.__setattr__(entry, "_state", _capture_preaction_state(entry))

    assert not _is_issued_pre_action_evidence(entry)
    assert _is_issued_procedure_execution_transcript(transcript)
    ledger = build_completion_ledger(
        plan,
        rules,
        {"content/write": transcript},
        clock=lambda: NOW,
    )

    assert ledger.successful
    assert any(
        source is retained[0] for record in ledger.records for source in record.sources
    )


def test_timestamp_normalization_failure_preserves_authority_precedence(
    tmp_path: Path,
) -> None:
    plan = rule_plan(tmp_path, "manual")
    evidence = _rule_evidence(plan)

    class MutatingFailingTimezone(tzinfo):
        def utcoffset(self, dt):
            object.__setattr__(evidence, "records", ())
            raise RuntimeError("offset unavailable")

        def dst(self, dt):
            return timedelta(0)

    with pytest.raises(
        CompletionLedgerError, match="rule evidence is not authoritative"
    ):
        build_completion_ledger(
            plan,
            evidence,
            {},
            clock=lambda: datetime(2026, 10, 26, tzinfo=MutatingFailingTimezone()),
        )


def test_stateful_zero_timezone_still_produces_canonical_z_timestamp(
    tmp_path: Path,
) -> None:
    plan = rule_plan(tmp_path, "manual")

    class OneZeroOffsetTimezone(tzinfo):
        def __init__(self) -> None:
            self.calls = 0

        def utcoffset(self, dt):
            self.calls += 1
            return timedelta(0) if self.calls == 1 else None

        def dst(self, dt):
            return timedelta(0)

    zone = OneZeroOffsetTimezone()
    ledger = build_completion_ledger(
        plan,
        _rule_evidence(plan),
        {},
        clock=lambda: datetime(2026, 10, 26, tzinfo=zone),
    )

    assert ledger.timestamp == "2026-10-26T00:00:00.000000Z"
    assert zone.calls == 1


def test_nonzero_offset_cannot_spoof_equality_with_utc(tmp_path: Path) -> None:
    plan = rule_plan(tmp_path, "manual")

    class EqualitySpoofingOffset(timedelta):
        def __eq__(self, other: object) -> bool:
            return True

    class NonzeroSpoofingTimezone(tzinfo):
        def utcoffset(self, dt):
            return EqualitySpoofingOffset(hours=1)

        def dst(self, dt):
            return timedelta(0)

    with pytest.raises(CompletionLedgerError, match="UTC-aware"):
        build_completion_ledger(
            plan,
            _rule_evidence(plan),
            {},
            clock=lambda: datetime(2026, 10, 26, 12, tzinfo=NonzeroSpoofingTimezone()),
        )


def test_mapping_is_not_called_after_its_single_snapshot(
    tmp_path: Path,
) -> None:
    plan, rules, transcript = _procedure_bundle(tmp_path)

    class ArmedMapping(Mapping):
        def __init__(self) -> None:
            self.armed = False
            self.lookups = 0

        def __getitem__(self, key):
            self.lookups += 1
            if key != "content/write":
                raise KeyError(key)
            if self.armed:
                object.__setattr__(rules, "records", ())
            return transcript

        def __iter__(self):
            return iter(("content/write",))

        def __len__(self):
            return 1

    outcomes = ArmedMapping()

    def clock() -> datetime:
        outcomes.armed = True
        return NOW

    ledger = build_completion_ledger(plan, rules, cast(Mapping, outcomes), clock=clock)

    assert ledger.successful
    assert outcomes.lookups == 1
    assert len(rules.records) > 0
    assert _is_issued_completion_ledger(ledger)
