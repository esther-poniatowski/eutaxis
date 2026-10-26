"""Exercise migration-baseline loading, selection, and stable digests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from types import MappingProxyType
from typing import cast

import pytest

from eutaxis.declarations import (
    CheckerResult,
    CompletionLedgerError,
    CompletionState,
    EvaluationState,
    VersionedReference,
    build_completion_ledger,
    create_rule_evidence_session,
    derive_attention_requirements,
    execute_known_failure_fixtures,
    plan_attention,
)
from eutaxis.declarations.exceptions import MigrationBaselineError
from eutaxis.declarations.migration_baselines import (
    _eligible_finding_canonical_bytes,
    _is_issued_migration_baseline_registry,
    _is_issued_migration_baseline_selection,
    _jcs,
    eligible_finding_digest,
    load_migration_baseline_registry,
    select_migration_baselines,
)
from eutaxis.declarations.completion import (
    _apply_baselines,
    _is_issued_completion_ledger,
    _materialize_records,
    _provisional,
)

from tests.test_attention import (
    CHECKER,
    _fixture_index,
    _inputs as evaluator_inputs,
    _prepare_registry,
)
from tests.test_rule_evidence import _inputs, _plan
from tests.test_completion import _procedure_bundle

NOW = datetime(2026, 10, 26, 11, 30, tzinfo=timezone.utc)
CANONICAL_FIXTURES = Path(__file__).parent / "fixtures" / "migration-baseline-canonical"


class _EqualitySpoofingText(str):
    def __eq__(self, _other: object) -> bool:
        return True

    def __ne__(self, _other: object) -> bool:
        return False

    __hash__ = str.__hash__


def _equal_private_carrier(value):
    clone = object.__new__(type(value))
    for field in fields(value):
        object.__setattr__(clone, field.name, getattr(value, field.name))
    return clone


def _violated_record(tmp_path: Path, mode: str):
    if mode == "mechanical":

        def checker(_input_data):
            return CheckerResult(
                CHECKER,
                "declaration-v1",
                EvaluationState.VIOLATED,
                {"accepted": True},
            )

        _, declarations, resolution, checker_registry, detector_registry = (
            _prepare_registry(tmp_path, mode, checker_runner=checker)
        )
        assert checker_registry is not None
        requirements = derive_attention_requirements(
            resolution,
            checker_registry=checker_registry,
            detector_registry=detector_registry,
        )
        fixtures = _fixture_index(tmp_path, checker_registry)
        assurance = execute_known_failure_fixtures(
            declarations, fixtures, checker_registry
        )
        plan = plan_attention(
            requirements,
            evaluator_inputs(requirements),
            fixture_index=fixtures,
            assurance=assurance,
        )
    else:
        plan = _plan(tmp_path, mode)
    manual, residual = _inputs(plan)
    if mode == "manual":
        key = next(iter(manual))
        manual[key] = replace(manual[key], evidence={"conclusion": "violated"})
    elif mode == "assisted":
        key = next(iter(residual))
        original = residual[key]

        def violated(request):
            return replace(
                original(request),
                state=EvaluationState.VIOLATED,
                rationale="A violating candidate remains.",
            )

        residual[key] = violated
    evidence = create_rule_evidence_session(plan).execute(
        manual=manual, residual_providers=residual
    )
    record = evidence.records[0]
    assert record.state is EvaluationState.VIOLATED
    return plan, record


def _source(digest: str, **changes: str) -> str:
    values = {
        "id": "migration/known-rule-gap",
        "owner": "registry",
        "manifest": "registry/manifest",
        "migration": "rules/v1",
        "expires": "2027-01-01T00:00:00.000000Z",
        "state": "unchecked",
        "digest": digest,
    }
    values.update(changes)
    return f"""schema-version: 1
id: {values['id']}
owner: {values['owner']}
manifest: {values['manifest']}
migration: {values['migration']}
expires-at: {values['expires']}
finding:
  key:
    kind: rule-criterion
    declaration: content/refined
    criterion: manual-check
  state: {values['state']}
  digest: {values['digest']}
"""


def _plan_source(plan, digest: str, *, state: str, **changes: str) -> str:
    requirement = plan.requirements.completion[0]
    manifest = plan.resolution.unit.manifest
    owner = plan.resolution.registry.records[manifest].declaration.owner
    values = {
        "owner": owner,
        "manifest": manifest,
        "expires": "2027-01-01T00:00:00.000000Z",
    }
    values.update(changes)
    return f"""schema-version: 1
id: migration/known-rule-gap
owner: {values['owner']}
manifest: {values['manifest']}
migration: rules/v1
expires-at: {values['expires']}
finding:
  key:
    kind: rule-criterion
    declaration: {requirement.key.declaration}
    criterion: {requirement.key.criterion}
  state: {state}
  digest: {digest}
"""


def test_load_and_select_exact_baseline(tmp_path: Path) -> None:
    source = tmp_path / "baseline.yaml"
    source.write_text(_source("sha256:" + "0" * 64), encoding="utf-8")

    registry = load_migration_baseline_registry((source,), root=tmp_path)
    selection = select_migration_baselines(registry, ("migration/known-rule-gap",))

    assert _is_issued_migration_baseline_registry(registry)
    assert _is_issued_migration_baseline_selection(selection)
    assert selection.baselines[0].source_path == "baseline.yaml"
    assert len(selection.baselines[0].source_sha256) == 64


def test_path_subclass_cannot_escape_root_or_falsify_provenance(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside-baseline.yaml"
    outside.write_text(_source("sha256:" + "0" * 64), encoding="utf-8")

    class HostilePath(type(Path())):
        def resolve(self, strict=False):
            return self

        def relative_to(self, *other, **kwargs):
            return Path("reviewed.yaml")

    with pytest.raises(MigrationBaselineError, match="exact Path"):
        load_migration_baseline_registry((HostilePath(outside),), root=tmp_path)
    with pytest.raises(MigrationBaselineError, match="exact Path"):
        load_migration_baseline_registry(
            (tmp_path / "missing.yaml",), root=HostilePath(tmp_path)
        )


def test_loader_rejects_open_source_and_duplicate_identifier(tmp_path: Path) -> None:
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    first.write_text(
        _source("sha256:" + "0" * 64) + "description: forbidden\n",
        encoding="utf-8",
    )
    with pytest.raises(MigrationBaselineError, match="description"):
        load_migration_baseline_registry((first,), root=tmp_path)

    first.write_text(_source("sha256:" + "0" * 64), encoding="utf-8")
    second.write_text(_source("sha256:" + "1" * 64), encoding="utf-8")
    with pytest.raises(MigrationBaselineError, match="duplicate baseline id"):
        load_migration_baseline_registry((first, second), root=tmp_path)


def test_selection_rejects_duplicate_and_unknown_ids(tmp_path: Path) -> None:
    source = tmp_path / "baseline.yaml"
    source.write_text(_source("sha256:" + "0" * 64), encoding="utf-8")
    registry = load_migration_baseline_registry((source,), root=tmp_path)

    with pytest.raises(MigrationBaselineError, match="more than once"):
        select_migration_baselines(
            registry,
            ("migration/known-rule-gap", "migration/known-rule-gap"),
        )
    with pytest.raises(MigrationBaselineError, match="not present"):
        select_migration_baselines(registry, ("missing",))


def test_copied_registry_and_selection_carriers_have_no_authority(
    tmp_path: Path,
) -> None:
    source = tmp_path / "baseline.yaml"
    source.write_text(_source("sha256:" + "0" * 64), encoding="utf-8")
    registry = load_migration_baseline_registry((source,), root=tmp_path)
    selection = select_migration_baselines(registry, ("migration/known-rule-gap",))

    with pytest.raises(MigrationBaselineError, match="not authoritative"):
        select_migration_baselines(
            _equal_private_carrier(registry), ("migration/known-rule-gap",)
        )
    assert not _is_issued_migration_baseline_selection(
        _equal_private_carrier(selection)
    )


def test_schema_rejects_blocked_baseline(tmp_path: Path) -> None:
    source = tmp_path / "baseline.yaml"
    source.write_text(_source("sha256:" + "0" * 64, state="blocked"), encoding="utf-8")

    with pytest.raises(MigrationBaselineError, match="blocked"):
        load_migration_baseline_registry((source,), root=tmp_path)


@pytest.mark.parametrize("version", ["1.0", "true"])
def test_schema_version_requires_exact_integer(tmp_path: Path, version: str) -> None:
    source = tmp_path / "baseline.yaml"
    document = _source("sha256:" + "0" * 64).replace(
        "schema-version: 1", f"schema-version: {version}"
    )
    source.write_text(document, encoding="utf-8")

    with pytest.raises(MigrationBaselineError, match="schema-version"):
        load_migration_baseline_registry((source,), root=tmp_path)


@pytest.mark.parametrize("state", ["satisfied", "inapplicable"])
def test_schema_rejects_nonblocking_finding_states(tmp_path: Path, state: str) -> None:
    source = tmp_path / "baseline.yaml"
    source.write_text(_source("sha256:" + "0" * 64, state=state), encoding="utf-8")

    with pytest.raises(MigrationBaselineError, match=state):
        load_migration_baseline_registry((source,), root=tmp_path)


@pytest.mark.parametrize("kind", ["procedure-predicate", "operation-predicate"])
def test_schema_rejects_procedure_and_operation_targets(
    tmp_path: Path, kind: str
) -> None:
    source = tmp_path / "baseline.yaml"
    document = _source("sha256:" + "0" * 64).replace(
        "kind: rule-criterion", f"kind: {kind}"
    )
    source.write_text(document, encoding="utf-8")

    with pytest.raises(MigrationBaselineError, match="rule-criterion"):
        load_migration_baseline_registry((source,), root=tmp_path)


@pytest.mark.parametrize(
    "original,replacement",
    [
        ("id: migration/known-rule-gap", 'id: "migration/known-rule-gap\\n"'),
        ("owner: registry", 'owner: "registry\\n"'),
        ("manifest: registry/manifest", 'manifest: "registry/manifest\\n"'),
        ("migration: rules/v1", 'migration: "rules/v1\\n"'),
        (
            "    declaration: content/refined",
            '    declaration: "content/refined\\n"',
        ),
        ("    criterion: manual-check", '    criterion: "manual-check\\n"'),
    ],
)
def test_schema_rejects_final_whitespace_in_every_identifier(
    tmp_path: Path, original: str, replacement: str
) -> None:
    source = tmp_path / "baseline.yaml"
    document = _source("sha256:" + "0" * 64).replace(original, replacement)
    source.write_text(document, encoding="utf-8")

    with pytest.raises(MigrationBaselineError):
        load_migration_baseline_registry((source,), root=tmp_path)


def test_jcs_number_and_utf16_ordering_contract() -> None:
    assert _jcs({"n": -0.0}) == '{"n":0}'
    assert _jcs({"n": 1e-7}) == '{"n":1e-7}'
    assert _jcs({"n": 1e-6}) == '{"n":0.000001}'
    assert _jcs({"n": 1e20}) == '{"n":100000000000000000000}'
    assert _jcs({"n": 1e21}) == '{"n":1e+21}'
    assert _jcs({"n": 2**53 - 1}) == '{"n":9007199254740991}'
    assert _jcs({"n": -(2**53 - 1)}) == '{"n":-9007199254740991}'
    assert _jcs({"\ue000": 1, "😀": 2}) == '{"😀":2,"\ue000":1}'
    assert _jcs({"control": "\u0001"}) == '{"control":"\\u0001"}'
    with pytest.raises(ValueError, match="interoperable"):
        _jcs({"n": 2**53})
    with pytest.raises(ValueError, match="interoperable"):
        _jcs({"n": -(2**53)})
    with pytest.raises(UnicodeError, match="surrogate"):
        _jcs({"text": "\ud800"})


@pytest.mark.parametrize(
    "mode,expected_digest",
    [
        (
            "manual",
            "sha256:01156c08101d92f48e175637a765da5148b3c3d9e139ea682ca1afa42671da29",
        ),
        (
            "assisted",
            "sha256:c483afaba040660aad43df269952e5156d8720fcfce8b6ac7f8e8c9ec825fb8a",
        ),
        (
            "mechanical",
            "sha256:f087473954afd21544aa78eca3e5585172c69a2067e26686fb3dc7db1870ae04",
        ),
    ],
)
def test_violated_digest_contract_is_fixed_for_each_evidence_class(
    tmp_path: Path, mode: str, expected_digest: str
) -> None:
    plan, record = _violated_record(tmp_path, mode)
    requirement = plan.requirements.completion[0]
    canonical = _eligible_finding_canonical_bytes(
        requirement, "violated", (record,), ()
    )

    assert canonical == (CANONICAL_FIXTURES / f"{mode}.json").read_bytes().rstrip(b"\n")
    assert (
        eligible_finding_digest(requirement, "violated", (record,), ())
        == expected_digest
    )


def test_unchecked_canonical_bytes_and_digest_are_fixed(tmp_path: Path) -> None:
    plan = _plan(tmp_path, "manual")
    requirement = plan.requirements.completion[0]
    canonical = _eligible_finding_canonical_bytes(requirement, "unchecked", (), ())

    assert canonical == (
        b'{"enforcement":"deliberative","evaluator":{"id":"registry/manual","version":1},'
        b'"key":{"criterion":"manual-check","declaration":"content/base","kind":"rule-criterion"},'
        b'"obligation":{"axis":"reasoning-target","criterion":{"evaluator":{"id":"registry/manual",'
        b'"version":1},"id":"manual-check","norms":["base"],"statement":"The manual-check '
        b'obligation is satisfied"},"failure-mode":"visible","key":{"criterion":"manual-check",'
        b'"declaration":"content/base","kind":"rule-criterion"},"norms":[{"action":{"object":'
        b'"the base contract","timing":null,"verb":"preserve"},"applicability":{"all":[{"facet":'
        b'"artifact.created","operator":"equals","value":true},{"facet":"context.available","operator":'
        b'"exists"}]},"decision-criterion":null,"guidance":null,"id":"base","modality":"must",'
        b'"rationale":null,"subject":"agent"}],"rationale":null,"required-visibility":null,"title":null},'
        b'"schema-version":1,"source":null,"state":"unchecked"}'
    )
    assert eligible_finding_digest(requirement, "unchecked", (), ()) == (
        "sha256:75da8694840bbd755cc14f1314345faf572ed298b714b75d8bc76de8647eb034"
    )


def test_finding_digest_binds_obligation_and_evidence(tmp_path: Path) -> None:
    plan = _plan(tmp_path, "manual")
    requirement = plan.requirements.completion[0]
    unchecked = eligible_finding_digest(requirement, "unchecked", (), ())
    assert unchecked is not None and unchecked.startswith("sha256:")

    manual, residual = _inputs(plan)
    key = next(iter(manual))
    manual[key] = replace(manual[key], evidence={"conclusion": "violated"})
    evidence = create_rule_evidence_session(plan).execute(
        manual=manual, residual_providers=residual
    )
    record = evidence.records[0]
    violated = eligible_finding_digest(requirement, record.state.value, (record,), ())

    assert violated is not None and violated != unchecked
    changed = replace(requirement.obligation, title="changed")
    changed_requirement = replace(requirement, obligation=changed)
    assert (
        eligible_finding_digest(changed_requirement, record.state.value, (record,), ())
        != violated
    )
    changed_norm = replace(requirement.obligation.norms[0], subject="other-agent")
    changed_norms = replace(requirement.obligation, norms=(changed_norm,))
    assert (
        eligible_finding_digest(
            replace(requirement, obligation=changed_norms),
            record.state.value,
            (record,),
            (),
        )
        != violated
    )
    changed_record = replace(
        record,
        submission=replace(record.submission, evidence={"conclusion": "other"}),
    )
    assert (
        eligible_finding_digest(requirement, record.state.value, (changed_record,), ())
        != violated
    )


@pytest.mark.parametrize("state", ["unchecked", "violated"])
def test_exact_baseline_retains_finding_and_permits_rule_only_success(
    tmp_path: Path, state: str
) -> None:
    plan = _plan(tmp_path, "manual")
    evidence = None
    if state == "violated":
        manual, residual = _inputs(plan)
        key = next(iter(manual))
        manual[key] = replace(manual[key], evidence={"conclusion": "violated"})
        evidence = create_rule_evidence_session(plan).execute(
            manual=manual, residual_providers=residual
        )
    first = build_completion_ledger(plan, evidence, {}, clock=lambda: NOW)
    record = first.records[0]
    assert record.state.value == state
    assert record.finding_digest is not None
    source = tmp_path / "baseline.yaml"
    source.write_text(
        _plan_source(plan, record.finding_digest, state=state), encoding="utf-8"
    )
    registry = load_migration_baseline_registry((source,), root=tmp_path)
    selection = select_migration_baselines(registry, ("migration/known-rule-gap",))

    ledger = build_completion_ledger(
        plan, evidence, {}, clock=lambda: NOW, baselines=selection
    )

    assert ledger.successful
    assert ledger.records[0].state.value == state
    assert ledger.records[0].baseline is not None
    assert ledger.records[0].baseline.baseline is selection.baselines[0]
    assert ledger.records[0].baseline.source_path == "baseline.yaml"


@pytest.mark.parametrize(
    "change,message",
    [
        ({"owner": "other"}, "owner differs"),
        ({"manifest": "other/manifest"}, "another manifest"),
        ({"expires": "2026-10-26T11:30:00.000000Z"}, "expired"),
        ({"expires": "2026-10-26T11:29:59.999999Z"}, "expired"),
    ],
)
def test_baseline_owner_manifest_and_expiry_are_exact(
    tmp_path: Path, change: dict[str, str], message: str
) -> None:
    plan = _plan(tmp_path, "manual")
    first = build_completion_ledger(plan, None, {}, clock=lambda: NOW)
    digest = first.records[0].finding_digest
    assert digest is not None
    source = tmp_path / "baseline.yaml"
    source.write_text(
        _plan_source(plan, digest, state="unchecked", **change), encoding="utf-8"
    )
    selection = select_migration_baselines(
        load_migration_baseline_registry((source,), root=tmp_path),
        ("migration/known-rule-gap",),
    )

    with pytest.raises(CompletionLedgerError, match=message):
        build_completion_ledger(plan, None, {}, clock=lambda: NOW, baselines=selection)


@pytest.mark.parametrize(
    "expires",
    [
        "2027-01-01T00:00:00Z",
        "2027-01-01T00:00:00.00000Z",
        "2027-01-01T00:00:00.0000000Z",
        "2027-01-01T00:00:00.000000z",
        "2027-01-01T01:00:00.000000+01:00",
        "2027-02-30T00:00:00.000000Z",
    ],
)
def test_invalid_expiry_forms_are_rejected(tmp_path: Path, expires: str) -> None:
    source = tmp_path / "baseline.yaml"
    source.write_text(_source("sha256:" + "0" * 64, expires=expires), encoding="utf-8")

    with pytest.raises(MigrationBaselineError):
        load_migration_baseline_registry((source,), root=tmp_path)


def test_mutated_selection_cannot_authorize_completion(tmp_path: Path) -> None:
    plan = _plan(tmp_path, "manual")
    first = build_completion_ledger(plan, None, {}, clock=lambda: NOW)
    digest = first.records[0].finding_digest
    assert digest is not None
    source = tmp_path / "baseline.yaml"
    source.write_text(_plan_source(plan, digest, state="unchecked"), encoding="utf-8")
    selection = select_migration_baselines(
        load_migration_baseline_registry((source,), root=tmp_path),
        ("migration/known-rule-gap",),
    )
    object.__setattr__(selection, "identifiers", ())

    with pytest.raises(CompletionLedgerError, match="not authoritative"):
        build_completion_ledger(plan, None, {}, clock=lambda: NOW, baselines=selection)


@pytest.mark.parametrize(
    "attribute,value", [("source_path", "other.yaml"), ("source_sha256", "0" * 64)]
)
def test_mutated_source_provenance_cannot_authorize_completion(
    tmp_path: Path, attribute: str, value: str
) -> None:
    plan = _plan(tmp_path, "manual")
    first = build_completion_ledger(plan, None, {}, clock=lambda: NOW)
    digest = first.records[0].finding_digest
    assert digest is not None
    source = tmp_path / "baseline.yaml"
    source.write_text(_plan_source(plan, digest, state="unchecked"), encoding="utf-8")
    selection = select_migration_baselines(
        load_migration_baseline_registry((source,), root=tmp_path),
        ("migration/known-rule-gap",),
    )
    object.__setattr__(selection.baselines[0], attribute, value)

    with pytest.raises(CompletionLedgerError, match="not authoritative"):
        build_completion_ledger(plan, None, {}, clock=lambda: NOW, baselines=selection)


@pytest.mark.parametrize("mutation", ["owner", "record"])
def test_post_plan_manifest_mutation_invalidates_baseline_authority(
    tmp_path: Path, mutation: str
) -> None:
    plan = _plan(tmp_path, "manual")
    first = build_completion_ledger(plan, None, {}, clock=lambda: NOW)
    digest = first.records[0].finding_digest
    assert digest is not None
    source = tmp_path / "baseline.yaml"
    source.write_text(_plan_source(plan, digest, state="unchecked"), encoding="utf-8")
    selection = select_migration_baselines(
        load_migration_baseline_registry((source,), root=tmp_path),
        ("migration/known-rule-gap",),
    )
    manifest_id = plan.resolution.unit.manifest
    if mutation == "owner":
        manifest = plan.resolution.registry.records[manifest_id].declaration
        object.__setattr__(manifest, "owner", "forged")
    else:
        records = dict(plan.resolution.registry.records)
        records[manifest_id] = replace(records[manifest_id])
        object.__setattr__(
            plan.resolution.registry, "records", MappingProxyType(records)
        )

    with pytest.raises(CompletionLedgerError, match="plan is not authoritative"):
        build_completion_ledger(plan, None, {}, clock=lambda: NOW, baselines=selection)


@pytest.mark.parametrize("mutation", ["owner", "manifest"])
def test_equality_spoof_cannot_forge_manifest_authority(
    tmp_path: Path, mutation: str
) -> None:
    plan = _plan(tmp_path, "manual")
    first = build_completion_ledger(plan, None, {}, clock=lambda: NOW)
    digest = first.records[0].finding_digest
    assert digest is not None
    source = tmp_path / "baseline.yaml"
    changes = {mutation: f"evil/{mutation}"}
    source.write_text(
        _plan_source(plan, digest, state="unchecked", **changes), encoding="utf-8"
    )
    selection = select_migration_baselines(
        load_migration_baseline_registry((source,), root=tmp_path),
        ("migration/known-rule-gap",),
    )
    if mutation == "owner":
        manifest = plan.resolution.manifest_record.declaration
        object.__setattr__(
            manifest, "owner", _EqualitySpoofingText(str(manifest.owner))
        )
    else:
        object.__setattr__(
            plan.resolution.unit,
            "manifest",
            _EqualitySpoofingText(str(plan.resolution.unit.manifest)),
        )

    with pytest.raises(CompletionLedgerError, match="plan is not authoritative"):
        build_completion_ledger(plan, None, {}, clock=lambda: NOW, baselines=selection)


def test_equivocating_manifest_mapping_cannot_forge_owner_authority(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path, "manual")
    first = build_completion_ledger(plan, None, {}, clock=lambda: NOW)
    digest = first.records[0].finding_digest
    assert digest is not None
    manifest_id = plan.resolution.unit.manifest
    original_records = plan.resolution.registry.records
    original = original_records[manifest_id]
    forged_manifest = replace(original.declaration, owner="forged")
    forged = replace(original, declaration=forged_manifest)
    source = tmp_path / "baseline.yaml"
    source.write_text(
        _plan_source(plan, digest, state="unchecked", owner="forged"),
        encoding="utf-8",
    )
    selection = select_migration_baselines(
        load_migration_baseline_registry((source,), root=tmp_path),
        ("migration/known-rule-gap",),
    )

    class EquivocatingRecords(Mapping):
        def __getitem__(self, key):
            return original_records[key]

        def __iter__(self):
            return iter(original_records)

        def __len__(self):
            return len(original_records)

        def get(self, key, default=None):
            return forged if key == manifest_id else original_records.get(key, default)

    object.__setattr__(plan.resolution.registry, "records", EquivocatingRecords())

    with pytest.raises(CompletionLedgerError, match="plan is not authoritative"):
        build_completion_ledger(plan, None, {}, clock=lambda: NOW, baselines=selection)


def test_digest_mismatch_cannot_authorize_completion(tmp_path: Path) -> None:
    plan = _plan(tmp_path, "manual")
    source = tmp_path / "baseline.yaml"
    source.write_text(
        _plan_source(plan, "sha256:" + "0" * 64, state="unchecked"),
        encoding="utf-8",
    )
    selection = select_migration_baselines(
        load_migration_baseline_registry((source,), root=tmp_path),
        ("migration/known-rule-gap",),
    )

    with pytest.raises(CompletionLedgerError, match="exactly one record"):
        build_completion_ledger(plan, None, {}, clock=lambda: NOW, baselines=selection)


@pytest.mark.parametrize(
    "replacement",
    [
        "    declaration: content/other",
        "    criterion: other-check",
        "  state: violated",
    ],
)
def test_wrong_key_or_state_cannot_authorize_completion(
    tmp_path: Path, replacement: str
) -> None:
    plan = _plan(tmp_path, "manual")
    first = build_completion_ledger(plan, None, {}, clock=lambda: NOW)
    record = first.records[0]
    assert record.finding_digest is not None
    document = _plan_source(plan, record.finding_digest, state="unchecked")
    if "declaration:" in replacement:
        document = document.replace(
            f"    declaration: {record.key.declaration}", replacement
        )
    elif "criterion:" in replacement:
        document = document.replace(
            f"    criterion: {record.key.criterion}", replacement
        )
    else:
        document = document.replace("  state: unchecked", replacement)
    source = tmp_path / "baseline.yaml"
    source.write_text(document, encoding="utf-8")
    selection = select_migration_baselines(
        load_migration_baseline_registry((source,), root=tmp_path),
        ("migration/known-rule-gap",),
    )

    with pytest.raises(CompletionLedgerError, match="exactly one record"):
        build_completion_ledger(plan, None, {}, clock=lambda: NOW, baselines=selection)


def test_two_selected_baselines_cannot_claim_one_record(tmp_path: Path) -> None:
    plan = _plan(tmp_path, "manual")
    first = build_completion_ledger(plan, None, {}, clock=lambda: NOW)
    digest = first.records[0].finding_digest
    assert digest is not None
    first_source = tmp_path / "first.yaml"
    second_source = tmp_path / "second.yaml"
    document = _plan_source(plan, digest, state="unchecked")
    first_source.write_text(document, encoding="utf-8")
    second_source.write_text(
        document.replace("id: migration/known-rule-gap", "id: migration/second-gap"),
        encoding="utf-8",
    )
    selection = select_migration_baselines(
        load_migration_baseline_registry((first_source, second_source), root=tmp_path),
        ("migration/known-rule-gap", "migration/second-gap"),
    )

    with pytest.raises(CompletionLedgerError, match="already has"):
        build_completion_ledger(plan, None, {}, clock=lambda: NOW, baselines=selection)


def test_one_selected_baseline_cannot_match_several_records(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path, "manual")
    first = build_completion_ledger(plan, None, {}, clock=lambda: NOW)
    record = first.records[0]
    assert record.finding_digest is not None
    source = tmp_path / "baseline.yaml"
    source.write_text(
        _plan_source(plan, record.finding_digest, state="unchecked"),
        encoding="utf-8",
    )
    selection = select_migration_baselines(
        load_migration_baseline_registry((source,), root=tmp_path),
        ("migration/known-rule-gap",),
    )

    with pytest.raises(CompletionLedgerError, match="exactly one record"):
        _apply_baselines(plan, (record, replace(record)), selection, NOW)


@pytest.mark.parametrize("invalid", [2**53, "\ud800"])
def test_invalid_ijson_evidence_is_ineligible_and_stays_blocking(
    tmp_path: Path, invalid: object
) -> None:
    plan, record = _violated_record(tmp_path, "manual")
    requirement = plan.requirements.completion[0]
    invalid_record = replace(
        record,
        submission=replace(
            record.submission,
            evidence={"conclusion": "violated", "invalid": invalid},
        ),
    )

    assert (
        eligible_finding_digest(requirement, "violated", (invalid_record,), ()) is None
    )
    evaluator = requirement.evaluator
    assert evaluator is not None
    provisional = _provisional(
        requirement,
        VersionedReference(evaluator.id, evaluator.version),
        CompletionState.VIOLATED,
        (invalid_record,),
        (),
    )
    materialized = _materialize_records((provisional,), "2026-10-26T11:30:00.000000Z")[
        0
    ]

    assert materialized.state is CompletionState.VIOLATED
    assert materialized.finding_digest is None
    assert materialized.baseline is None


def test_clock_mutation_of_baseline_authority_prevents_issuance(tmp_path: Path) -> None:
    plan = _plan(tmp_path, "manual")
    first = build_completion_ledger(plan, None, {}, clock=lambda: NOW)
    digest = first.records[0].finding_digest
    assert digest is not None
    source = tmp_path / "baseline.yaml"
    source.write_text(_plan_source(plan, digest, state="unchecked"), encoding="utf-8")
    selection = select_migration_baselines(
        load_migration_baseline_registry((source,), root=tmp_path),
        ("migration/known-rule-gap",),
    )

    def hostile_clock() -> datetime:
        object.__setattr__(selection.baselines[0], "owner", "forged")
        return NOW

    with pytest.raises(CompletionLedgerError, match="not authoritative"):
        build_completion_ledger(
            plan, None, {}, clock=hostile_clock, baselines=selection
        )


@pytest.mark.parametrize("hostile_method", ["items", "get"])
def test_clock_mapping_callback_cannot_escape_baseline_authority_check(
    tmp_path: Path, hostile_method: str
) -> None:
    plan = _plan(tmp_path, "manual")
    first = build_completion_ledger(plan, None, {}, clock=lambda: NOW)
    digest = first.records[0].finding_digest
    assert digest is not None
    source = tmp_path / "baseline.yaml"
    source.write_text(_plan_source(plan, digest, state="unchecked"), encoding="utf-8")
    selection = select_migration_baselines(
        load_migration_baseline_registry((source,), root=tmp_path),
        ("migration/known-rule-gap",),
    )
    original = selection.registry.entries

    class HostileEntries(Mapping):
        def __getitem__(self, key):
            return original[key]

        def __iter__(self):
            return iter(original)

        def __len__(self):
            return len(original)

        def items(self):
            if hostile_method == "items":
                raise RuntimeError("items callback escaped")
            return original.items()

        def get(self, key, default=None):
            if hostile_method == "get":
                raise RuntimeError("get callback escaped")
            return original.get(key, default)

    def hostile_clock() -> datetime:
        object.__setattr__(selection.registry, "entries", HostileEntries())
        return NOW

    with pytest.raises(CompletionLedgerError, match="not authoritative"):
        build_completion_ledger(
            plan, None, {}, clock=hostile_clock, baselines=selection
        )


def test_baseline_expiry_uses_detached_canonical_clock_value(tmp_path: Path) -> None:
    plan = _plan(tmp_path, "manual")
    first = build_completion_ledger(plan, None, {}, clock=lambda: NOW)
    digest = first.records[0].finding_digest
    assert digest is not None
    source = tmp_path / "baseline.yaml"
    source.write_text(_plan_source(plan, digest, state="unchecked"), encoding="utf-8")
    selection = select_migration_baselines(
        load_migration_baseline_registry((source,), root=tmp_path),
        ("migration/known-rule-gap",),
    )

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
        None,
        {},
        clock=lambda: datetime(2026, 10, 26, 11, 30, tzinfo=zone),
        baselines=selection,
    )

    assert ledger.successful
    assert ledger.timestamp == "2026-10-26T11:30:00.000000Z"
    assert zone.calls == 1


def test_rule_baseline_cannot_waive_unsuccessful_procedure(tmp_path: Path) -> None:
    plan, _, transcript = _procedure_bundle(tmp_path, success=False)
    first = build_completion_ledger(
        plan, None, {"content/write": transcript}, clock=lambda: NOW
    )
    rule_record = next(
        record for record in first.records if record.finding_digest is not None
    )
    source = tmp_path / "baseline.yaml"
    source.write_text(
        _plan_source(
            plan,
            cast(str, rule_record.finding_digest),
            state=rule_record.state.value,
        ),
        encoding="utf-8",
    )
    selection = select_migration_baselines(
        load_migration_baseline_registry((source,), root=tmp_path),
        ("migration/known-rule-gap",),
    )

    ledger = build_completion_ledger(
        plan,
        None,
        {"content/write": transcript},
        clock=lambda: NOW,
        baselines=selection,
    )

    assert any(record.baseline is not None for record in ledger.records)
    assert not ledger.successful


def test_post_issuance_baseline_mutation_invalidates_ledger(tmp_path: Path) -> None:
    plan = _plan(tmp_path, "manual")
    first = build_completion_ledger(plan, None, {}, clock=lambda: NOW)
    digest = first.records[0].finding_digest
    assert digest is not None
    source = tmp_path / "baseline.yaml"
    source.write_text(_plan_source(plan, digest, state="unchecked"), encoding="utf-8")
    selection = select_migration_baselines(
        load_migration_baseline_registry((source,), root=tmp_path),
        ("migration/known-rule-gap",),
    )
    ledger = build_completion_ledger(
        plan, None, {}, clock=lambda: NOW, baselines=selection
    )
    applied = ledger.records[0].baseline
    assert applied is not None and _is_issued_completion_ledger(ledger)

    object.__setattr__(applied, "source_path", "forged.yaml")

    assert not _is_issued_completion_ledger(ledger)


@pytest.mark.parametrize("field", ["digest", "timestamp"])
def test_equality_spoofed_ledger_scalar_loses_authority(
    tmp_path: Path, field: str
) -> None:
    plan = _plan(tmp_path, "manual")
    ledger = build_completion_ledger(plan, None, {}, clock=lambda: NOW)
    record = ledger.records[0]
    assert _is_issued_completion_ledger(ledger)
    if field == "digest":
        object.__setattr__(
            record,
            "finding_digest",
            _EqualitySpoofingText("sha256:" + "0" * 64),
        )
    else:
        forged = _EqualitySpoofingText("2025-01-01T00:00:00.000000Z")
        object.__setattr__(record, "timestamp", forged)
        object.__setattr__(ledger, "timestamp", forged)

    assert not _is_issued_completion_ledger(ledger)
