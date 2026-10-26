"""Reconcile authenticated rule and procedure evidence without callbacks."""

from __future__ import annotations

import inspect
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Callable, NoReturn, SupportsIndex, TypeAlias, cast

from ._authority import IdentityAuthorityStore, identity_value_state
from ._runner_support import exception_detail
from .attention import (
    AttentionObligationKey,
    AttentionPlan,
    CompletionRequirement,
    OperationPredicateKey,
    ProcedurePredicateKey,
    RuleCriterionKey,
    _is_issued_attention_plan,
)
from .enforcement import EnforcementClass
from .exceptions import CompletionLedgerError
from .models import ProcedureDeclaration, VersionedReference
from .migration_baselines import (
    AppliedMigrationBaseline,
    MigrationBaselineSelection,
    _is_issued_migration_baseline_selection,
    baseline_expiry,
    eligible_finding_digest,
)
from .pre_action_evidence import (
    AssistedPreconditionEvidence,
    MechanicalPreconditionEvidence,
    PreActionEvidence,
    PreActionEvidenceRecord,
    _issued_pre_action_evidence_snapshot,
)
from .procedure_execution import (
    ProcedureAssistedBoundaryEvidence,
    ProcedureBoundaryRecord,
    ProcedureExecutionTranscript,
    ProcedureMechanicalBoundaryEvidence,
    ProcedureRequirementApplicabilityState,
    _is_issued_procedure_execution_transcript,
)
from .results import EvaluationState
from .rule_evidence import (
    RuleAssistedEvidence,
    RuleEvidence,
    RuleEvidenceRecord,
    RuleMechanicalEvidence,
    _is_issued_rule_evidence,
)
from .source import format_document_path

_LEDGER_ISSUER = object()
_MAPPING_SNAPSHOT_ISSUER = object()
_RECONCILIATION_SNAPSHOT_ISSUER = object()
_LEDGER_AUTHORITIES: IdentityAuthorityStore[CompletionLedger] = IdentityAuthorityStore()
_MAPPING_SNAPSHOT_AUTHORITIES: IdentityAuthorityStore[_ProcedureOutcomeSnapshot] = (
    IdentityAuthorityStore()
)
_RECONCILIATION_SNAPSHOT_AUTHORITIES: IdentityAuthorityStore[
    _ReconciliationSnapshot
] = IdentityAuthorityStore()


class CompletionState(StrEnum):
    """State of one canonical completion requirement."""

    SATISFIED = "satisfied"
    VIOLATED = "violated"
    BLOCKED = "blocked"
    UNCHECKED = "unchecked"
    INAPPLICABLE = "inapplicable"


class ProcedureOutcomeState(StrEnum):
    """Completion status of one effective procedure."""

    SUCCESSFUL = "successful"
    UNSUCCESSFUL = "unsuccessful"
    UNCLEARED = "uncleared"
    UNCHECKED = "unchecked"


CompletionEvidenceSource: TypeAlias = (
    RuleEvidenceRecord | PreActionEvidenceRecord | ProcedureBoundaryRecord
)
ProcedureOutcome: TypeAlias = ProcedureExecutionTranscript | PreActionEvidence
CompletionClock: TypeAlias = Callable[[], datetime]


@dataclass(frozen=True, init=False, eq=False)
class _ProcedureOutcomeSnapshot:
    mapping_origin: object
    pairs: tuple[tuple[str, ProcedureOutcome], ...]
    _token: object
    _state: tuple[object, ...]
    _issuer: object


@dataclass(frozen=True, init=False, eq=False)
class _ReconciliationSnapshot:
    completions: tuple[ProcedureCompletion, ...]
    records: tuple[_ProvisionalRecord, ...]
    _token: object
    _state: tuple[object, ...]
    _issuer: object


@dataclass(frozen=True)
class CompletionRecord:
    """Retain one canonical obligation and all evidence occurrences for it."""

    key: AttentionObligationKey
    evaluator: VersionedReference | None
    enforcement: EnforcementClass | None
    state: CompletionState
    sources: tuple[CompletionEvidenceSource, ...]
    diagnostics: tuple[str, ...]
    finding_digest: str | None
    baseline: AppliedMigrationBaseline | None
    timestamp: str


@dataclass(frozen=True)
class ProcedureCompletion:
    """Retain one effective procedure's exact supplied outcome status."""

    procedure: str
    state: ProcedureOutcomeState
    outcome: ProcedureOutcome | None


@dataclass(frozen=True, init=False, eq=False)
class CompletionLedger:
    """Retain the complete canonical completion reconciliation."""

    plan: AttentionPlan
    rule_evidence: RuleEvidence | None
    baseline_selection: MigrationBaselineSelection | None
    procedure_mapping_origin: object
    procedure_outcomes: tuple[ProcedureCompletion, ...]
    records: tuple[CompletionRecord, ...]
    timestamp: str
    successful: bool
    _procedure_mapping_snapshot: _ProcedureOutcomeSnapshot
    _reconciliation_snapshot: _ReconciliationSnapshot
    _token: object
    _state: tuple[object, ...]
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("CompletionLedger instances must be issued by reconciliation")

    def __copy__(self) -> NoReturn:
        raise TypeError("CompletionLedger instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("CompletionLedger instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("CompletionLedger instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("CompletionLedger instances cannot be serialized")


def build_completion_ledger(
    plan: AttentionPlan,
    rule_evidence: RuleEvidence | None,
    procedure_outcomes: Mapping[str, ProcedureOutcome],
    *,
    clock: CompletionClock,
    baselines: MigrationBaselineSelection | None = None,
) -> CompletionLedger:
    """Reconcile every canonical obligation without executing an evaluator."""
    _require_plan_and_rule_evidence(plan, rule_evidence)
    _require_baseline_selection(baselines)
    procedure_ids = _effective_procedure_ids(plan)
    try:
        supplied, outcome_snapshot = _snapshot_outcomes(
            plan, procedure_ids, procedure_outcomes
        )
    except BaseException as exc:
        _raise_after_authority(exc, plan, rule_evidence, baselines=baselines)
    completions = tuple(
        _procedure_completion(identifier, supplied.get(identifier))
        for identifier in procedure_ids
    )
    _require_transaction_sources(
        plan, rule_evidence, completions, outcome_snapshot, baselines=baselines
    )
    provisional = tuple(
        _reconcile_requirement(requirement, rule_evidence, completions)
        for requirement in plan.requirements.completion
    )
    reconciliation = _issue_reconciliation_snapshot(completions, provisional)
    _require_transaction_sources(
        plan,
        rule_evidence,
        completions,
        outcome_snapshot,
        reconciliation,
        baselines,
    )
    try:
        _require_clock(clock)
    except BaseException as exc:
        _raise_after_authority(
            exc,
            plan,
            rule_evidence,
            completions,
            outcome_snapshot,
            reconciliation,
            baselines,
        )
    _require_transaction_sources(
        plan,
        rule_evidence,
        completions,
        outcome_snapshot,
        reconciliation,
        baselines,
    )
    try:
        observed = clock()
    except BaseException as exc:
        _raise_after_authority(
            exc,
            plan,
            rule_evidence,
            completions,
            outcome_snapshot,
            reconciliation,
            baselines,
            clock_failure=True,
        )
    _require_transaction_sources(
        plan,
        rule_evidence,
        completions,
        outcome_snapshot,
        reconciliation,
        baselines,
    )
    try:
        timestamp = _canonical_timestamp(observed)
    except BaseException as exc:
        _raise_after_authority(
            exc,
            plan,
            rule_evidence,
            completions,
            outcome_snapshot,
            reconciliation,
            baselines,
        )
    _require_transaction_sources(
        plan,
        rule_evidence,
        completions,
        outcome_snapshot,
        reconciliation,
        baselines,
    )
    records = _apply_baselines(
        plan,
        _materialize_records(reconciliation.records, timestamp),
        baselines,
        datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        ),
    )
    successful = all(
        item.state is ProcedureOutcomeState.SUCCESSFUL for item in completions
    ) and all(
        item.state in {CompletionState.SATISFIED, CompletionState.INAPPLICABLE}
        or item.baseline is not None
        for item in records
    )
    ledger = object.__new__(CompletionLedger)
    object.__setattr__(ledger, "plan", plan)
    object.__setattr__(ledger, "rule_evidence", rule_evidence)
    object.__setattr__(ledger, "baseline_selection", baselines)
    object.__setattr__(ledger, "procedure_mapping_origin", procedure_outcomes)
    object.__setattr__(ledger, "procedure_outcomes", completions)
    object.__setattr__(ledger, "records", records)
    object.__setattr__(ledger, "timestamp", timestamp)
    object.__setattr__(ledger, "successful", successful)
    object.__setattr__(ledger, "_procedure_mapping_snapshot", outcome_snapshot)
    object.__setattr__(ledger, "_reconciliation_snapshot", reconciliation)
    object.__setattr__(ledger, "_issuer", _LEDGER_ISSUER)
    state = _capture_ledger_state(ledger)
    token = _LEDGER_AUTHORITIES.issue(ledger, state)
    object.__setattr__(ledger, "_token", token)
    object.__setattr__(ledger, "_state", state)
    if not _is_issued_completion_ledger(ledger):
        _fail(("ledger",), "issued ledger failed its authority check")
    return ledger


@dataclass(frozen=True)
class _ProvisionalRecord:
    key: AttentionObligationKey
    evaluator: VersionedReference | None
    enforcement: EnforcementClass | None
    state: CompletionState
    sources: tuple[CompletionEvidenceSource, ...]
    diagnostics: tuple[str, ...]
    finding_digest: str | None


def _effective_procedure_ids(plan: AttentionPlan) -> tuple[str, ...]:
    identifiers: list[str] = []
    for component in plan.resolution.unit.components:
        registered = plan.resolution.registry.records[component.declaration]
        if type(registered.declaration) is ProcedureDeclaration:
            identifiers.append(component.declaration)
    return tuple(identifiers)


def _snapshot_outcomes(
    plan: AttentionPlan,
    procedure_ids: tuple[str, ...],
    supplied: Mapping[str, ProcedureOutcome],
) -> tuple[dict[str, ProcedureOutcome], _ProcedureOutcomeSnapshot]:
    if not isinstance(supplied, Mapping):
        _fail(("procedure-outcomes",), "value must be a mapping")
    try:
        pairs = tuple(supplied.items())
    except Exception as exc:
        _fail(
            ("procedure-outcomes",),
            f"mapping could not be read: {exception_detail(exc)}",
            exc,
        )
    result: dict[str, ProcedureOutcome] = {}
    for index, pair in enumerate(pairs):
        try:
            key, outcome = pair
        except Exception as exc:
            _fail(("procedure-outcomes", index), "item is not a key-value pair", exc)
        if type(key) is not str or key not in procedure_ids or key in result:
            _fail(
                ("procedure-outcomes", index, "key"),
                "key is not one effective procedure identifier",
            )
        _require_outcome(plan, key, outcome, ("procedure-outcomes", index))
        result[key] = outcome
    snapshot = object.__new__(_ProcedureOutcomeSnapshot)
    object.__setattr__(snapshot, "mapping_origin", supplied)
    object.__setattr__(snapshot, "pairs", tuple(result.items()))
    object.__setattr__(snapshot, "_issuer", _MAPPING_SNAPSHOT_ISSUER)
    state = _capture_mapping_snapshot_state(snapshot)
    token = _MAPPING_SNAPSHOT_AUTHORITIES.issue(snapshot, state)
    object.__setattr__(snapshot, "_token", token)
    object.__setattr__(snapshot, "_state", state)
    return result, snapshot


def _require_outcome(
    plan: AttentionPlan,
    procedure: str,
    outcome: object,
    path: tuple[str | int, ...],
) -> None:
    if type(procedure) is not str:
        _fail(path, "procedure correlation is not exact text")
    if type(outcome) is PreActionEvidence:
        evidence = cast(PreActionEvidence, outcome)
        authority = _issued_pre_action_evidence_snapshot(evidence)
        if authority is None:
            _fail(path, "pre-action evidence is not authoritative")
        run = authority.plan.run
        if (
            run.attention is not plan
            or type(run.procedure.id) is not str
            or run.procedure.id != procedure
        ):
            _fail(path, "pre-action evidence correlation differs")
        if authority.cleared:
            _fail(path, "cleared pre-action evidence requires a terminal transcript")
        return
    if type(outcome) is ProcedureExecutionTranscript:
        transcript = cast(ProcedureExecutionTranscript, outcome)
        if not _is_issued_procedure_execution_transcript(transcript):
            _fail(path, "procedure transcript is not authoritative")
        if (
            transcript.authority.entry_attention_plan_origin is not plan
            or type(transcript.authority.procedure_id) is not str
            or transcript.authority.procedure_id != procedure
        ):
            _fail(path, "procedure transcript correlation differs")
        return
    _fail(path, "outcome carrier is invalid")


def _procedure_completion(
    procedure: str, outcome: ProcedureOutcome | None
) -> ProcedureCompletion:
    if outcome is None:
        return ProcedureCompletion(procedure, ProcedureOutcomeState.UNCHECKED, None)
    if type(outcome) is PreActionEvidence:
        return ProcedureCompletion(procedure, ProcedureOutcomeState.UNCLEARED, outcome)
    transcript = cast(ProcedureExecutionTranscript, outcome)
    return ProcedureCompletion(
        procedure,
        (
            ProcedureOutcomeState.SUCCESSFUL
            if transcript.successful
            else ProcedureOutcomeState.UNSUCCESSFUL
        ),
        transcript,
    )


def _reconcile_requirement(
    requirement: CompletionRequirement,
    rule_evidence: RuleEvidence | None,
    completions: tuple[ProcedureCompletion, ...],
) -> _ProvisionalRecord:
    evaluator = (
        None
        if requirement.evaluator is None
        else VersionedReference(requirement.evaluator.id, requirement.evaluator.version)
    )
    if type(requirement.key) is RuleCriterionKey:
        if rule_evidence is None:
            return _provisional(requirement, evaluator, CompletionState.UNCHECKED)
        record = next(
            item for item in rule_evidence.records if item.requirement is requirement
        )
        return _provisional(
            requirement,
            evaluator,
            _completion_state(record.state),
            (record,),
            _diagnostics(record),
        )
    procedure = (
        requirement.key.declaration
        if type(requirement.key) is ProcedurePredicateKey
        else cast(OperationPredicateKey, requirement.key).procedure
    )
    completion = next(
        item
        for item in completions
        if type(item.procedure) is str and item.procedure == procedure
    )
    if completion.outcome is None:
        return _provisional(requirement, evaluator, CompletionState.UNCHECKED)
    if type(completion.outcome) is PreActionEvidence:
        authority = _issued_pre_action_evidence_snapshot(completion.outcome)
        if authority is None:
            _fail(("procedure-outcomes",), "pre-action evidence is not authoritative")
        preaction_record = _record_with_key(authority.records, requirement.key)
        if preaction_record is None:
            return _provisional(requirement, evaluator, CompletionState.UNCHECKED)
        return _provisional(
            requirement,
            evaluator,
            _completion_state(preaction_record.state),
            (preaction_record,),
            _diagnostics(preaction_record),
        )
    return _reconcile_transcript_requirement(
        requirement, evaluator, cast(ProcedureExecutionTranscript, completion.outcome)
    )


def _reconcile_transcript_requirement(
    requirement: CompletionRequirement,
    evaluator: VersionedReference | None,
    transcript: ProcedureExecutionTranscript,
) -> _ProvisionalRecord:
    sources: list[CompletionEvidenceSource] = []
    states: list[CompletionState] = []
    diagnostics: list[str] = []
    entry_record = _record_with_key(
        transcript.authority.entry_evidence_records, requirement.key
    )
    if entry_record is not None:
        sources.append(entry_record)
        states.append(_completion_state(entry_record.state))
        diagnostics.extend(_diagnostics(entry_record))
    for attempt in transcript.boundaries:
        if not any(
            _key_signature(item.key) == _key_signature(requirement.key)
            for item in attempt.requirements
        ):
            continue
        record = (
            None
            if attempt.evidence is None
            else _record_with_key(attempt.evidence.records, requirement.key)
        )
        if record is None:
            states.append(CompletionState.UNCHECKED)
            continue
        sources.append(record)
        states.append(_completion_state(record.state))
        diagnostics.extend(_diagnostics(record))
    applicability = tuple(
        item.state
        for item in transcript.applicability
        if _key_signature(item.requirement.key) == _key_signature(requirement.key)
    )
    if len(applicability) > 1:
        _fail(("procedure-outcomes",), "transcript applicability is incomplete")
    applicability_state = None if not applicability else applicability[0]
    if not states:
        state = (
            CompletionState.INAPPLICABLE
            if applicability_state
            is ProcedureRequirementApplicabilityState.INAPPLICABLE
            else CompletionState.UNCHECKED
        )
    else:
        if applicability_state is ProcedureRequirementApplicabilityState.INAPPLICABLE:
            _fail(("procedure-outcomes",), "inapplicable requirement has evidence")
        state = _aggregate_states(states)
    return _provisional(
        requirement,
        evaluator,
        state,
        tuple(sources),
        tuple(diagnostics),
    )


def _provisional(
    requirement: CompletionRequirement,
    evaluator: VersionedReference | None,
    state: CompletionState,
    sources: tuple[CompletionEvidenceSource, ...] = (),
    diagnostics: tuple[str, ...] = (),
) -> _ProvisionalRecord:
    digest = eligible_finding_digest(
        requirement,
        state.value,
        cast(tuple[object, ...], sources),
        diagnostics,
    )
    return _ProvisionalRecord(
        requirement.key,
        evaluator,
        requirement.enforcement,
        state,
        sources,
        diagnostics,
        digest,
    )


def _materialize_records(
    provisional: tuple[_ProvisionalRecord, ...], timestamp: str
) -> tuple[CompletionRecord, ...]:
    return tuple(
        CompletionRecord(
            item.key,
            item.evaluator,
            item.enforcement,
            item.state,
            item.sources,
            item.diagnostics,
            item.finding_digest,
            None,
            timestamp,
        )
        for item in provisional
    )


def _apply_baselines(
    plan: AttentionPlan,
    records: tuple[CompletionRecord, ...],
    selection: MigrationBaselineSelection | None,
    observed: datetime,
) -> tuple[CompletionRecord, ...]:
    if selection is None:
        return records
    _require_baseline_selection(selection)
    manifest = plan.resolution.unit.manifest
    registered = plan.resolution.manifest_record
    owner = registered.declaration.owner
    if type(manifest) is not str or type(owner) is not str:
        _fail(("baselines", "manifest"), "resolved manifest identity is not exact text")
    applied = list(records)
    claimed: set[int] = set()
    for baseline_index, baseline in enumerate(selection.baselines):
        path = ("baselines", baseline_index)
        if baseline.manifest != manifest:
            _fail(path + ("manifest",), "baseline targets another manifest")
        if baseline.owner != owner:
            _fail(path + ("owner",), "baseline owner differs from manifest owner")
        if observed >= baseline_expiry(baseline.expires_at):
            _fail(path + ("expires-at",), "baseline has expired")
        matches = tuple(
            index
            for index, record in enumerate(applied)
            if type(record.key) is RuleCriterionKey
            and _key_signature(record.key) == _key_signature(baseline.finding.key)
            and record.state.value == baseline.finding.state
            and record.finding_digest == baseline.finding.digest
        )
        if len(matches) != 1:
            _fail(path + ("finding",), "baseline does not match exactly one record")
        record_index = matches[0]
        if record_index in claimed:
            _fail(path + ("finding",), "record already has a selected baseline")
        claimed.add(record_index)
        applied_baseline = AppliedMigrationBaseline(
            baseline, baseline.source_path, baseline.source_sha256
        )
        applied[record_index] = replace(
            applied[record_index], baseline=applied_baseline
        )
    return tuple(applied)


def _require_baseline_selection(
    selection: MigrationBaselineSelection | None,
) -> None:
    if selection is not None and not _is_issued_migration_baseline_selection(selection):
        _fail(("baselines",), "baseline selection is not authoritative")


def _record_with_key(
    records: Iterable[CompletionEvidenceSource], key: AttentionObligationKey
) -> CompletionEvidenceSource | None:
    matches = tuple(
        item
        for item in records
        if _key_signature(item.requirement.key) == _key_signature(key)
    )
    if len(matches) > 1:
        _fail(("records",), "outcome contains duplicate requirement evidence")
    return None if not matches else cast(CompletionEvidenceSource, matches[0])


def _key_signature(key: AttentionObligationKey) -> tuple[object, ...]:
    if type(key) is RuleCriterionKey:
        return (RuleCriterionKey, key.declaration, key.criterion)
    if type(key) is ProcedurePredicateKey:
        return (
            ProcedurePredicateKey,
            key.declaration,
            key.phase.value,
            key.predicate,
        )
    operation = cast(OperationPredicateKey, key)
    return (
        OperationPredicateKey,
        operation.procedure,
        operation.action,
        operation.subject_operation.id,
        operation.subject_operation.version,
        operation.predicate,
    )


def _completion_state(state: EvaluationState) -> CompletionState:
    return CompletionState(state.value)


def _aggregate_states(states: list[CompletionState]) -> CompletionState:
    for state in (
        CompletionState.VIOLATED,
        CompletionState.BLOCKED,
        CompletionState.UNCHECKED,
        CompletionState.SATISFIED,
    ):
        if state in states:
            return state
    _fail(("records",), "evidence state is invalid")


def _diagnostics(record: object) -> tuple[str, ...]:
    if isinstance(
        record,
        (
            RuleAssistedEvidence,
            RuleMechanicalEvidence,
            AssistedPreconditionEvidence,
            MechanicalPreconditionEvidence,
            ProcedureAssistedBoundaryEvidence,
            ProcedureMechanicalBoundaryEvidence,
        ),
    ):
        diagnostic = record.diagnostic
        return () if diagnostic is None else (diagnostic,)
    return ()


def _require_clock(clock: object) -> None:
    if not callable(clock):
        _fail(("clock",), "clock must be a synchronous zero-argument callable")
    try:
        call_method = getattr(clock, "__call__", None)
        if (
            inspect.iscoroutinefunction(clock)
            or inspect.iscoroutinefunction(call_method)
            or inspect.isasyncgenfunction(clock)
            or inspect.isasyncgenfunction(call_method)
        ):
            _fail(("clock",), "clock must be synchronous")
        signature = inspect.signature(clock)
        if signature.parameters:
            _fail(("clock",), "clock must accept exactly zero arguments")
    except CompletionLedgerError:
        raise
    except Exception as exc:
        _fail(("clock",), "clock callable could not be inspected", exc)


def _canonical_timestamp(value: object) -> str:
    if type(value) is not datetime:
        _fail(("clock", "result"), "clock must return an exact datetime")
    observed = cast(datetime, value)
    try:
        offset = observed.utcoffset()
        if (
            observed.tzinfo is None
            or type(offset) is not timedelta
            or offset != timedelta(0)
        ):
            _fail(("clock", "result"), "clock datetime must be UTC-aware")
        return observed.replace(tzinfo=None).isoformat(timespec="microseconds") + "Z"
    except CompletionLedgerError:
        raise
    except Exception as exc:
        _fail(("clock", "result"), "clock datetime could not be normalized", exc)


def _require_plan_and_rule_evidence(
    plan: AttentionPlan, rule_evidence: RuleEvidence | None
) -> None:
    if not _is_issued_attention_plan(plan):
        _fail(("plan",), "attention plan is not authoritative")
    if rule_evidence is not None and (
        not _is_issued_rule_evidence(rule_evidence) or rule_evidence.plan is not plan
    ):
        _fail(("rule-evidence",), "rule evidence is not authoritative for this plan")


def _require_sources(
    plan: AttentionPlan,
    rule_evidence: RuleEvidence | None,
    completions: tuple[ProcedureCompletion, ...],
) -> None:
    _require_plan_and_rule_evidence(plan, rule_evidence)
    for index, completion in enumerate(completions):
        if completion.outcome is not None:
            _require_outcome(
                plan,
                completion.procedure,
                completion.outcome,
                ("procedure-outcomes", index),
            )


def _capture_mapping_snapshot_state(
    snapshot: _ProcedureOutcomeSnapshot,
) -> tuple[object, ...]:
    return (
        id(snapshot.mapping_origin),
        id(snapshot.pairs),
        tuple((key, id(outcome)) for key, outcome in snapshot.pairs),
        id(snapshot._issuer),
    )


def _is_issued_mapping_snapshot(snapshot: object) -> bool:
    if (
        type(snapshot) is not _ProcedureOutcomeSnapshot
        or getattr(snapshot, "_issuer", None) is not _MAPPING_SNAPSHOT_ISSUER
        or type(getattr(snapshot, "_state", None)) is not tuple
    ):
        return False
    candidate = cast(_ProcedureOutcomeSnapshot, snapshot)
    issued = _MAPPING_SNAPSHOT_AUTHORITIES.lookup(candidate)
    return (
        issued is not None
        and candidate._token is issued[0]
        and candidate._state == issued[1]
        and candidate._state == _capture_mapping_snapshot_state(candidate)
    )


def _require_transaction_sources(
    plan: AttentionPlan,
    rule_evidence: RuleEvidence | None,
    completions: tuple[ProcedureCompletion, ...],
    mapping_snapshot: _ProcedureOutcomeSnapshot,
    reconciliation: _ReconciliationSnapshot | None = None,
    baselines: MigrationBaselineSelection | None = None,
) -> None:
    _require_baseline_selection(baselines)
    if not _is_issued_mapping_snapshot(
        mapping_snapshot
    ) or not _snapshot_matches_completions(mapping_snapshot, completions):
        _fail(("procedure-outcomes",), "captured mapping authority changed")
    if reconciliation is not None and (
        not _is_issued_reconciliation_snapshot(reconciliation)
        or reconciliation.completions is not completions
    ):
        _fail(("records",), "captured reconciliation authority changed")
    _require_sources(plan, rule_evidence, completions)


def _snapshot_matches_completions(
    snapshot: _ProcedureOutcomeSnapshot,
    completions: tuple[ProcedureCompletion, ...],
) -> bool:
    if any(type(completion.procedure) is not str for completion in completions):
        return False
    if any(
        completion.state is not _expected_procedure_state(completion.outcome)
        for completion in completions
    ):
        return False
    supplied = tuple(item for item in completions if item.outcome is not None)
    if len(snapshot.pairs) != len(supplied):
        return False
    return all(
        any(
            type(key) is str
            and key == completion.procedure
            and outcome is completion.outcome
            for key, outcome in snapshot.pairs
        )
        for completion in supplied
    )


def _expected_procedure_state(
    outcome: ProcedureOutcome | None,
) -> ProcedureOutcomeState:
    if outcome is None:
        return ProcedureOutcomeState.UNCHECKED
    if type(outcome) is PreActionEvidence:
        return ProcedureOutcomeState.UNCLEARED
    return (
        ProcedureOutcomeState.SUCCESSFUL
        if cast(ProcedureExecutionTranscript, outcome).successful
        else ProcedureOutcomeState.UNSUCCESSFUL
    )


def _issue_reconciliation_snapshot(
    completions: tuple[ProcedureCompletion, ...],
    records: tuple[_ProvisionalRecord, ...],
) -> _ReconciliationSnapshot:
    snapshot = object.__new__(_ReconciliationSnapshot)
    object.__setattr__(snapshot, "completions", completions)
    object.__setattr__(snapshot, "records", records)
    object.__setattr__(snapshot, "_issuer", _RECONCILIATION_SNAPSHOT_ISSUER)
    state = _capture_reconciliation_snapshot_state(snapshot)
    token = _RECONCILIATION_SNAPSHOT_AUTHORITIES.issue(snapshot, state)
    object.__setattr__(snapshot, "_token", token)
    object.__setattr__(snapshot, "_state", state)
    return snapshot


def _capture_reconciliation_snapshot_state(
    snapshot: _ReconciliationSnapshot,
) -> tuple[object, ...]:
    return (
        id(snapshot.completions),
        tuple(_completion_authority_state(item) for item in snapshot.completions),
        id(snapshot.records),
        tuple(_provisional_authority_state(item) for item in snapshot.records),
        id(snapshot._issuer),
    )


def _completion_authority_state(item: ProcedureCompletion) -> tuple[object, ...]:
    return (
        id(item),
        identity_value_state(item.procedure),
        item.state.value,
        id(item.outcome),
    )


def _provisional_authority_state(item: _ProvisionalRecord) -> tuple[object, ...]:
    return (
        id(item),
        _key_signature(item.key),
        identity_value_state(item.evaluator),
        None if item.enforcement is None else item.enforcement.value,
        item.state.value,
        id(item.sources),
        tuple(id(source) for source in item.sources),
        id(item.diagnostics),
        item.diagnostics,
        identity_value_state(item.finding_digest),
    )


def _is_issued_reconciliation_snapshot(snapshot: object) -> bool:
    if (
        type(snapshot) is not _ReconciliationSnapshot
        or getattr(snapshot, "_issuer", None) is not _RECONCILIATION_SNAPSHOT_ISSUER
        or type(getattr(snapshot, "_state", None)) is not tuple
    ):
        return False
    candidate = cast(_ReconciliationSnapshot, snapshot)
    issued = _RECONCILIATION_SNAPSHOT_AUTHORITIES.lookup(candidate)
    return (
        issued is not None
        and candidate._token is issued[0]
        and candidate._state == issued[1]
        and candidate._state == _capture_reconciliation_snapshot_state(candidate)
    )


def _raise_after_authority(
    exc: BaseException,
    plan: AttentionPlan,
    rule_evidence: RuleEvidence | None,
    completions: tuple[ProcedureCompletion, ...] = (),
    mapping_snapshot: _ProcedureOutcomeSnapshot | None = None,
    reconciliation: _ReconciliationSnapshot | None = None,
    baselines: MigrationBaselineSelection | None = None,
    *,
    clock_failure: bool = False,
) -> NoReturn:
    try:
        if mapping_snapshot is None:
            _require_plan_and_rule_evidence(plan, rule_evidence)
            _require_baseline_selection(baselines)
        else:
            _require_transaction_sources(
                plan,
                rule_evidence,
                completions,
                mapping_snapshot,
                reconciliation,
                baselines,
            )
    except CompletionLedgerError as authority:
        raise authority from exc
    if isinstance(exc, CompletionLedgerError):
        raise exc
    if isinstance(exc, Exception):
        message = (
            f"clock raised {exception_detail(exc)}"
            if clock_failure
            else f"callback raised {exception_detail(exc)}"
        )
        _fail(("clock",), message, exc)
    raise exc


def _records_match_expected(
    records: tuple[CompletionRecord, ...],
    expected: tuple[CompletionRecord, ...],
) -> bool:
    if len(records) != len(expected):
        return False
    for record, source in zip(records, expected):
        if (
            type(record.timestamp) is not str
            or type(source.timestamp) is not str
            or record.timestamp != source.timestamp
            or not _optional_exact_text_matches(
                record.finding_digest, source.finding_digest
            )
        ):
            return False
        if (
            record.key is not source.key
            or record.enforcement is not source.enforcement
            or record.state is not source.state
            or record.diagnostics != source.diagnostics
            or len(record.sources) != len(source.sources)
            or any(
                actual is not canonical
                for actual, canonical in zip(record.sources, source.sources)
            )
        ):
            return False
        if record.baseline is None or source.baseline is None:
            if record.baseline is not source.baseline:
                return False
        elif (
            record.baseline.baseline is not source.baseline.baseline
            or type(record.baseline.source_path) is not str
            or type(record.baseline.source_sha256) is not str
            or record.baseline.source_path != source.baseline.source_path
            or record.baseline.source_sha256 != source.baseline.source_sha256
        ):
            return False
        if record.evaluator is None or source.evaluator is None:
            if record.evaluator is not source.evaluator:
                return False
        elif (
            type(record.evaluator) is not VersionedReference
            or type(source.evaluator) is not VersionedReference
            or type(record.evaluator.id) is not str
            or type(source.evaluator.id) is not str
            or type(record.evaluator.version) is not int
            or type(source.evaluator.version) is not int
            or record.evaluator.id != source.evaluator.id
            or record.evaluator.version != source.evaluator.version
        ):
            return False
    return True


def _optional_exact_text_matches(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return left is right
    return type(left) is str and type(right) is str and left == right


def _capture_ledger_state(ledger: CompletionLedger) -> tuple[object, ...]:
    return (
        id(ledger.plan),
        id(ledger.rule_evidence),
        id(ledger.baseline_selection),
        id(ledger.procedure_mapping_origin),
        id(ledger._procedure_mapping_snapshot),
        _capture_mapping_snapshot_state(ledger._procedure_mapping_snapshot),
        id(ledger._reconciliation_snapshot),
        _capture_reconciliation_snapshot_state(ledger._reconciliation_snapshot),
        id(ledger.procedure_outcomes),
        tuple(
            (
                id(item),
                identity_value_state(item.procedure),
                item.state.value,
                id(item.outcome),
            )
            for item in ledger.procedure_outcomes
        ),
        id(ledger.records),
        tuple(
            (
                id(item),
                identity_value_state(item.key),
                identity_value_state(item.evaluator),
                None if item.enforcement is None else item.enforcement.value,
                item.state.value,
                id(item.sources),
                tuple(id(source) for source in item.sources),
                id(item.diagnostics),
                item.diagnostics,
                identity_value_state(item.finding_digest),
                id(item.baseline),
                identity_value_state(item.baseline),
                identity_value_state(item.timestamp),
            )
            for item in ledger.records
        ),
        identity_value_state(ledger.timestamp),
        ledger.successful,
        id(ledger._issuer),
    )


def _is_issued_completion_ledger(ledger: object) -> bool:
    """Return whether a completion ledger retains every source authority."""
    if (
        type(ledger) is not CompletionLedger
        or getattr(ledger, "_issuer", None) is not _LEDGER_ISSUER
        or type(getattr(ledger, "_state", None)) is not tuple
    ):
        return False
    candidate = cast(CompletionLedger, ledger)
    try:
        if (
            not isinstance(candidate.procedure_mapping_origin, Mapping)
            or candidate._procedure_mapping_snapshot.mapping_origin
            is not candidate.procedure_mapping_origin
        ):
            return False
        if type(candidate.timestamp) is not str or any(
            type(record.timestamp) is not str for record in candidate.records
        ):
            return False
        _require_transaction_sources(
            candidate.plan,
            candidate.rule_evidence,
            candidate.procedure_outcomes,
            candidate._procedure_mapping_snapshot,
            candidate._reconciliation_snapshot,
            candidate.baseline_selection,
        )
        if (
            candidate._reconciliation_snapshot.completions
            is not candidate.procedure_outcomes
        ):
            return False
        expected = candidate.plan.requirements.completion
        if len(candidate.records) != len(expected) or any(
            record.key is not requirement.key
            for record, requirement in zip(candidate.records, expected)
        ):
            return False
        if any(record.timestamp != candidate.timestamp for record in candidate.records):
            return False
        expected_records = tuple(
            _reconcile_requirement(
                requirement,
                candidate.rule_evidence,
                candidate.procedure_outcomes,
            )
            for requirement in expected
        )
        observed = datetime.strptime(
            candidate.timestamp, "%Y-%m-%dT%H:%M:%S.%fZ"
        ).replace(tzinfo=timezone.utc)
        materialized = _materialize_records(expected_records, candidate.timestamp)
        expected_with_baselines = _apply_baselines(
            candidate.plan,
            materialized,
            candidate.baseline_selection,
            observed,
        )
        if not _records_match_expected(candidate.records, expected_with_baselines):
            return False
        successful = all(
            item.state is ProcedureOutcomeState.SUCCESSFUL
            for item in candidate.procedure_outcomes
        ) and all(
            item.state in {CompletionState.SATISFIED, CompletionState.INAPPLICABLE}
            or item.baseline is not None
            for item in candidate.records
        )
        issued = _LEDGER_AUTHORITIES.lookup(candidate)
        return (
            type(candidate.successful) is bool
            and candidate.successful is successful
            and issued is not None
            and candidate._token is issued[0]
            and candidate._state == issued[1]
            and candidate._state == _capture_ledger_state(candidate)
        )
    except Exception:
        return False


def _fail(
    path: tuple[str | int, ...], message: str, cause: BaseException | None = None
) -> NoReturn:
    error = CompletionLedgerError(format_document_path(path), message)
    if cause is None:
        raise error
    raise error from cause
