"""Exercise authenticated structured rule-set Skill planning."""

from __future__ import annotations

import copy
import pickle
from pathlib import Path

import pytest

import eutaxis.declarations.registry as registry_module
import eutaxis.declarations.structured_rule_skill as rule_skill_module
from eutaxis.declarations import (
    AcquisitionContractError,
    CompositionError,
    StructuredRuleSkillPlan,
    plan_structured_rule_skill,
)
from eutaxis.declarations.structured_rule_skill import (
    _STRUCTURED_RULE_SKILL_PLAN_AUTHORITIES,
    _issued_structured_rule_skill_plan_state,
    _projection_state,
)
from eutaxis.declarations.exceptions import DeclarationCatalogError
from eutaxis.skill_placement import SkillPlacementError
from tests.test_structured_skill import _base, _manifest, _pipeline, _yaml


def _rule(
    identifier: str,
    *,
    failure_mode: str = "visible",
    required_visibility: str | None = None,
    relations: list[dict[str, str]] | None = None,
    applicable: bool = True,
) -> dict[str, object]:
    document = {
        **_base(identifier, "rule"),
        "relations": relations or [],
        "applicability": {
            "facet": "oikos.enabled",
            "operator": "equals",
            "value": applicable,
        },
        "axis": "reasoning-target",
        "failure-mode": failure_mode,
        "norms": [
            {
                "id": "preserve-boundary",
                "modality": "must",
                "subject": "agent",
                "action": {"verb": "preserve", "object": "the boundary"},
            }
        ],
        "criteria": [
            {
                "id": "boundary-preserved",
                "norms": ["preserve-boundary"],
                "evaluator": {"id": "eutaxis/manual-judgment", "version": 1},
                "statement": "The boundary is preserved",
            }
        ],
    }
    if required_visibility is not None:
        document["required-visibility"] = required_visibility
    return document


def _rule_set(
    *,
    purpose: str = "Test code behavior at the boundary",
    rules: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        **_base("oikos/testing", "rule-set"),
        "purpose": purpose,
        "rules": rules
        or [
            _rule("oikos/test-design"),
            _rule("oikos/test-coverage"),
        ],
    }


def _rule_pipeline(
    tmp_path: Path,
    *,
    rule_set: dict[str, object] | None = None,
    manifest: dict[str, object] | None = None,
    extra: tuple[tuple[str, bytes], ...] = (),
):
    selected_manifest = manifest or _manifest(
        target="testing", selected=["oikos/testing"]
    )
    return _pipeline(
        tmp_path,
        manifest=selected_manifest,
        extra_declarations=(
            ("declarations/testing.yaml", _yaml(rule_set or _rule_set())),
            *extra,
        ),
    )


def test_plan_retains_exact_members_and_projections(tmp_path: Path) -> None:
    _acquisition, resolution = _rule_pipeline(tmp_path)

    plan = plan_structured_rule_skill(resolution)

    assert plan.name == "testing"
    assert plan.scope == "project"
    assert plan.invocation == ("model", "user")
    assert plan.rule_set.id == "oikos/testing"
    assert tuple(rule.id for rule in plan.rules) == (
        "oikos/test-design",
        "oikos/test-coverage",
    )
    assert tuple(projection.declaration for projection in plan.projections) == (
        "oikos/test-design",
        "oikos/test-coverage",
    )


def test_plan_rejects_non_rule_set_root(tmp_path: Path) -> None:
    _acquisition, resolution = _pipeline(tmp_path)
    with pytest.raises(CompositionError, match="is not a rule set"):
        plan_structured_rule_skill(resolution)


def test_plan_rejects_multiple_roots(tmp_path: Path) -> None:
    manifest = _manifest(
        target="testing",
        selected=["oikos/testing", "oikos/complete-module"],
    )
    _acquisition, resolution = _rule_pipeline(tmp_path, manifest=manifest)
    with pytest.raises(CompositionError, match="exactly one root rule set"):
        plan_structured_rule_skill(resolution)


@pytest.mark.parametrize("purpose", [" padded", "two\nlines", "x" * 1025])
def test_plan_rejects_invalid_description(tmp_path: Path, purpose: str) -> None:
    _acquisition, resolution = _rule_pipeline(
        tmp_path, rule_set=_rule_set(purpose=purpose)
    )
    with pytest.raises(CompositionError, match="one-line Skill description"):
        plan_structured_rule_skill(resolution)


def test_plan_rejects_incomplete_effective_membership(tmp_path: Path) -> None:
    rules = [_rule("oikos/active"), _rule("oikos/inactive", applicable=False)]
    _acquisition, resolution = _rule_pipeline(tmp_path, rule_set=_rule_set(rules=rules))
    with pytest.raises(CompositionError, match="must equal"):
        plan_structured_rule_skill(resolution)


def test_plan_rejects_external_dependency_closure(tmp_path: Path) -> None:
    rules = [
        _rule(
            "oikos/member",
            relations=[{"type": "requires", "target": "oikos/external"}],
        )
    ]
    external = _rule("oikos/external")
    _acquisition, resolution = _rule_pipeline(
        tmp_path,
        rule_set=_rule_set(rules=rules),
        extra=(("declarations/external.yaml", _yaml(external)),),
    )
    with pytest.raises(CompositionError, match="must equal"):
        plan_structured_rule_skill(resolution)


def test_plan_rejects_dependency_reordering(tmp_path: Path) -> None:
    rules = [
        _rule(
            "oikos/dependant",
            relations=[{"type": "requires", "target": "oikos/prerequisite"}],
        ),
        _rule("oikos/prerequisite"),
    ]
    _acquisition, resolution = _rule_pipeline(tmp_path, rule_set=_rule_set(rules=rules))
    with pytest.raises(CompositionError, match="must equal rule-set authored order"):
        plan_structured_rule_skill(resolution)


def test_plan_rejects_forbidden_member_placement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules = [
        _rule("oikos/visible"),
        _rule(
            "oikos/silent",
            failure_mode="silent",
            required_visibility="pre-action",
        ),
    ]
    with monkeypatch.context() as bypass:
        bypass.setattr(
            registry_module,
            "validate_skill_placement",
            lambda _candidates, _invocation: None,
        )
        _acquisition, resolution = _rule_pipeline(
            tmp_path,
            rule_set=_rule_set(rules=rules),
        )
    with pytest.raises(SkillPlacementError, match="oikos/silent"):
        plan_structured_rule_skill(resolution)


def test_plan_rejects_pre_invocation_even_for_user_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest(target="testing", selected=["oikos/testing"])
    manifest["invocation"] = ["user"]
    rules = [
        _rule(
            "oikos/pre-invocation",
            failure_mode="silent",
            required_visibility="pre-invocation",
        )
    ]
    with monkeypatch.context() as bypass:
        bypass.setattr(
            registry_module,
            "validate_skill_placement",
            lambda _candidates, _invocation: None,
        )
        _acquisition, resolution = _rule_pipeline(
            tmp_path,
            rule_set=_rule_set(rules=rules),
            manifest=manifest,
        )
    with pytest.raises(SkillPlacementError, match="pre-invocation"):
        plan_structured_rule_skill(resolution)


def test_plan_reauthenticates_public_projection(tmp_path: Path) -> None:
    _acquisition, resolution = _rule_pipeline(tmp_path)
    plan = plan_structured_rule_skill(resolution)
    object.__setattr__(plan.projections[0], "norms", ())
    with pytest.raises(AcquisitionContractError):
        _issued_structured_rule_skill_plan_state(plan)


@pytest.mark.parametrize("field", ["manifest", "rule_set", "rules"])
def test_plan_reauthenticates_retained_declarations(tmp_path: Path, field: str) -> None:
    _first_acquisition, first_resolution = _rule_pipeline(tmp_path / "first")
    first = plan_structured_rule_skill(first_resolution)
    first_state = _issued_structured_rule_skill_plan_state(first)
    _second_acquisition, second_resolution = _rule_pipeline(tmp_path / "second")
    second = plan_structured_rule_skill(second_resolution)
    second_state = _issued_structured_rule_skill_plan_state(second)
    if field == "manifest":
        forged = first_state._replace(manifest=second_state.manifest)
    elif field == "rule_set":
        forged = first_state._replace(rule_set=second_state.rule_set)
    else:
        forged = first_state._replace(rules=second_state.rules)
    forged = forged._replace(
        projection_state=_projection_state(
            forged.manifest,
            forged.rule_set,
            forged.rules,
            forged.projections,
        )
    )
    token = _STRUCTURED_RULE_SKILL_PLAN_AUTHORITIES.issue(first, forged)
    object.__setattr__(first, "_token", token)

    with pytest.raises(CompositionError, match="changed"):
        _issued_structured_rule_skill_plan_state(first)


def test_plan_reauthenticates_catalog_authority(tmp_path: Path) -> None:
    _acquisition, resolution = _rule_pipeline(tmp_path)
    plan = plan_structured_rule_skill(resolution)
    state = _issued_structured_rule_skill_plan_state(plan)
    object.__setattr__(state.catalog, "revision", 99)

    with pytest.raises(
        DeclarationCatalogError, match="catalog projection state changed"
    ):
        _issued_structured_rule_skill_plan_state(plan)


def test_catalog_corruption_precedes_planning_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _acquisition, resolution = _rule_pipeline(tmp_path)

    def corrupt_catalog(*args):
        catalog = args[1]
        object.__setattr__(catalog, "revision", 99)
        raise RuntimeError("later planning failure")

    monkeypatch.setattr(rule_skill_module, "_close_members", corrupt_catalog)
    with pytest.raises(
        DeclarationCatalogError, match="catalog projection state changed"
    ) as raised:
        plan_structured_rule_skill(resolution)
    assert isinstance(raised.value.__cause__, RuntimeError)


def test_resolution_mutation_at_planning_boundary_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _acquisition, resolution = _rule_pipeline(tmp_path)
    original = rule_skill_module._plan_from_catalog

    def corrupt_resolution(*args):
        resolution_state = args[1]
        object.__setattr__(resolution_state.resolution.unit, "components", ())
        return original(*args)

    monkeypatch.setattr(rule_skill_module, "_plan_from_catalog", corrupt_resolution)
    with pytest.raises(AcquisitionContractError):
        plan_structured_rule_skill(resolution)


def test_failed_final_validation_retires_provisional_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _acquisition, resolution = _rule_pipeline(tmp_path)
    issued: list[StructuredRuleSkillPlan] = []
    original = rule_skill_module._issue_plan

    def capture(*args):
        plan = original(*args)
        issued.append(plan)
        return plan

    def fail_validation(*_args):
        raise RuntimeError("final validation failed")

    monkeypatch.setattr(rule_skill_module, "_issue_plan", capture)
    monkeypatch.setattr(rule_skill_module, "_validate_plan_success", fail_validation)
    with pytest.raises(RuntimeError, match="final validation failed"):
        plan_structured_rule_skill(resolution)
    assert len(issued) == 1
    with pytest.raises(CompositionError, match="not issued"):
        _issued_structured_rule_skill_plan_state(issued[0])


def test_plan_rejects_construction_copy_and_serialization(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="must be issued"):
        StructuredRuleSkillPlan()
    forged = object.__new__(StructuredRuleSkillPlan)
    with pytest.raises(CompositionError, match="not issued"):
        _issued_structured_rule_skill_plan_state(forged)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(forged)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(forged)
