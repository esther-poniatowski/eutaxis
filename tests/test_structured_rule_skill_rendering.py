"""Exercise bounded rendering of authenticated structured rule-set Skills."""

from __future__ import annotations

from pathlib import Path

import pytest

import eutaxis.declarations.structured_rule_skill_rendering as rendering_module
from eutaxis.commands import get_adapter
from eutaxis.declarations import (
    AcquisitionContractError,
    CompositionError,
    plan_structured_rule_skill,
    render_structured_rule_skill,
)
from eutaxis.declarations.exceptions import DeclarationCatalogError
from tests.test_structured_rule_skill import _rule, _rule_pipeline, _rule_set

GOLDEN_ROOT = Path(__file__).parent / "fixtures" / "structured-rule-skill"


def _rich_rule_set() -> dict[str, object]:
    first = _rule("oikos/test-design")
    first["rationale"] = "Isolated behavior reveals the failing boundary"
    norms = first["norms"]
    assert isinstance(norms, list)
    norm = norms[0]
    assert isinstance(norm, dict)
    norm["guidance"] = "Pass every external collaborator explicitly"
    norm["rationale"] = "Ambient state prevents controlled inputs"
    norm["decision-criterion"] = "unit-runs-with-test-doubles"
    criteria = first["criteria"]
    assert isinstance(criteria, list)
    criteria.append(
        {
            "id": "unit-runs-with-test-doubles",
            "norms": ["preserve-boundary"],
            "evaluator": {"id": "eutaxis/manual-judgment", "version": 1},
            "statement": "The unit runs with test doubles",
        }
    )
    first["exceptions"] = [
        {
            "id": "generated-boundary",
            "when": {
                "facet": "artifact.created",
                "operator": "equals",
                "value": False,
            },
            "disposition": "waive",
            "affects": ["preserve-boundary"],
            "rationale": "No generated artifact exists yet",
        }
    ]
    result = _rule_set(rules=[first, _rule("oikos/test-coverage")])
    result["rationale"] = "Tests must expose behavioral regressions"
    return result


def _plan(tmp_path: Path, *, scope: str = "project"):
    manifest = None
    if scope != "project":
        from tests.test_structured_skill import _manifest

        manifest = _manifest(target="testing", selected=["oikos/testing"])
        manifest["scope"] = scope
    _acquisition, resolution = _rule_pipeline(
        tmp_path,
        rule_set=_rich_rule_set(),
        manifest=manifest,
    )
    return plan_structured_rule_skill(resolution)


def _files(artifact) -> dict[str, str]:
    return {file.relative_path: file.content for file in artifact.files}


@pytest.mark.parametrize("adapter_name", ["claude", "codex"])
def test_rule_skill_matches_reviewed_host_golden(
    tmp_path: Path, adapter_name: str
) -> None:
    plan = _plan(tmp_path)
    first = render_structured_rule_skill(
        plan,
        get_adapter(adapter_name),
        entrypoint_max_bytes=100_000,
        artifact_max_bytes=1_000_000,
    )
    second = render_structured_rule_skill(
        plan,
        get_adapter(adapter_name),
        entrypoint_max_bytes=100_000,
        artifact_max_bytes=1_000_000,
    )
    assert first == second
    assert [file.relative_path for file in first.files] == [
        "SKILL.md",
        ".eutaxis-owned.json",
    ]
    actual = _files(first)
    golden_root = GOLDEN_ROOT / adapter_name
    expected_paths = {
        path.relative_to(golden_root).as_posix()
        for path in golden_root.rglob("*")
        if path.is_file()
    }
    assert set(actual) == expected_paths
    for relative_path, content in actual.items():
        assert content.encode("utf-8") == (golden_root / relative_path).read_bytes()
    assert "The boundary is preserved" not in actual["SKILL.md"]
    assert "references/contract.md" not in actual["SKILL.md"]


def test_rule_skill_accepts_exact_final_byte_budgets(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    adapter = get_adapter("codex")
    artifact = render_structured_rule_skill(
        plan,
        adapter,
        entrypoint_max_bytes=100_000,
        artifact_max_bytes=1_000_000,
    )
    files = _files(artifact)
    entrypoint_bytes = len(files["SKILL.md"].encode())
    artifact_bytes = sum(len(content.encode()) for content in files.values())
    assert (
        render_structured_rule_skill(
            plan,
            adapter,
            entrypoint_max_bytes=entrypoint_bytes,
            artifact_max_bytes=artifact_bytes,
        )
        == artifact
    )
    with pytest.raises(CompositionError, match="SKILL.md uses"):
        render_structured_rule_skill(
            plan,
            adapter,
            entrypoint_max_bytes=entrypoint_bytes - 1,
            artifact_max_bytes=artifact_bytes,
        )
    with pytest.raises(CompositionError, match="complete artifact uses"):
        render_structured_rule_skill(
            plan,
            adapter,
            entrypoint_max_bytes=entrypoint_bytes,
            artifact_max_bytes=artifact_bytes - 1,
        )


@pytest.mark.parametrize("value", [None, True, 0, -1, 1.5])
def test_rule_skill_rejects_invalid_budget(tmp_path: Path, value: object) -> None:
    plan = _plan(tmp_path)
    with pytest.raises(CompositionError, match="exact positive integer"):
        render_structured_rule_skill(
            plan,
            get_adapter("claude"),
            entrypoint_max_bytes=value,  # type: ignore[arg-type]
            artifact_max_bytes=1_000_000,
        )


def test_rule_skill_translates_personal_scope(tmp_path: Path) -> None:
    artifact = render_structured_rule_skill(
        _plan(tmp_path, scope="personal"),
        get_adapter("claude"),
        entrypoint_max_bytes=100_000,
        artifact_max_bytes=1_000_000,
    )
    assert artifact.scope == "user"


def test_rule_skill_reauthenticates_after_assembly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan(tmp_path)
    original = rendering_module.assemble_skill

    def hostile_assembly(source, adapter):
        artifact = original(source, adapter)
        object.__setattr__(plan.rules[0], "rationale", "changed")
        return artifact

    monkeypatch.setattr(rendering_module, "assemble_skill", hostile_assembly)
    with pytest.raises(AcquisitionContractError):
        render_structured_rule_skill(
            plan,
            get_adapter("claude"),
            entrypoint_max_bytes=100_000,
            artifact_max_bytes=1_000_000,
        )


def test_rule_skill_reauthenticates_catalog_after_assembly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan(tmp_path)
    catalog = rendering_module._structured_rule_skill_plan_authority_state(plan).catalog
    original = rendering_module.assemble_skill

    def hostile_assembly(source, adapter):
        artifact = original(source, adapter)
        object.__setattr__(catalog, "revision", 99)
        return artifact

    monkeypatch.setattr(rendering_module, "assemble_skill", hostile_assembly)
    with pytest.raises(
        DeclarationCatalogError,
        match="catalog projection state changed",
    ):
        render_structured_rule_skill(
            plan,
            get_adapter("claude"),
            entrypoint_max_bytes=100_000,
            artifact_max_bytes=1_000_000,
        )


def test_catalog_corruption_precedes_later_rule_skill_rendering_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan(tmp_path)
    catalog = rendering_module._structured_rule_skill_plan_authority_state(plan).catalog

    def hostile_assembly(source, adapter):
        object.__setattr__(catalog, "revision", 99)
        raise RuntimeError("later rendering failure")

    monkeypatch.setattr(rendering_module, "assemble_skill", hostile_assembly)
    with pytest.raises(
        DeclarationCatalogError,
        match="catalog projection state changed",
    ) as raised:
        render_structured_rule_skill(
            plan,
            get_adapter("claude"),
            entrypoint_max_bytes=100_000,
            artifact_max_bytes=1_000_000,
        )

    assert isinstance(raised.value.__cause__, RuntimeError)
