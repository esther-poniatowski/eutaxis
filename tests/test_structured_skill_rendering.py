"""Exercise bounded rendering of authenticated structured procedure Skills."""

from __future__ import annotations

from pathlib import Path

import pytest

import eutaxis.declarations.structured_skill_rendering as rendering_module
from eutaxis.commands import get_adapter
from eutaxis.declarations import (
    AcquisitionContractError,
    CompositionError,
    StructuredSkillPlan,
    plan_structured_skill,
    render_structured_skill,
)
from tests.test_structured_skill import (
    MEDIA_TYPE,
    _manifest,
    _operation,
    _pipeline,
    _procedure,
    _yaml,
)

GOLDEN_ROOT = Path(__file__).parent / "fixtures" / "structured-skill"


def _plan(tmp_path: Path, *, scope: str = "project"):
    manifest = _manifest()
    manifest["invocation"] = ["user"]
    manifest["scope"] = scope
    _acquisition, resolution = _pipeline(tmp_path, manifest=manifest)
    return plan_structured_skill(resolution)


def _files(artifact) -> dict[str, str]:
    return {file.relative_path: file.content for file in artifact.files}


@pytest.mark.parametrize("adapter_name", ("claude", "codex"))
def test_structured_skill_matches_reviewed_host_golden(
    tmp_path: Path, adapter_name: str
) -> None:
    plan = _plan(tmp_path)
    adapter = get_adapter(adapter_name)

    first = render_structured_skill(
        plan,
        adapter,
        entrypoint_max_bytes=100_000,
        artifact_max_bytes=1_000_000,
    )
    second = render_structured_skill(
        plan,
        adapter,
        entrypoint_max_bytes=100_000,
        artifact_max_bytes=1_000_000,
    )

    assert first == second
    expected_order = [
        "SKILL.md",
        "references/contract.md",
        "scripts/publish-index.py",
    ]
    if adapter_name == "codex":
        expected_order.append("agents/openai.yaml")
    expected_order.append(".eutaxis-owned.json")
    assert [file.relative_path for file in first.files] == expected_order
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
    assert actual["scripts/publish-index.py"].encode("utf-8") == b"print('publish')\n"


@pytest.mark.parametrize("adapter_name", ("claude", "codex"))
def test_personal_scope_translates_to_host_user_scope(
    tmp_path: Path, adapter_name: str
) -> None:
    plan = _plan(tmp_path, scope="personal")

    artifact = render_structured_skill(
        plan,
        get_adapter(adapter_name),
        entrypoint_max_bytes=100_000,
        artifact_max_bytes=1_000_000,
    )

    assert artifact.name == "complete-module"


def test_structured_skill_accepts_exact_final_byte_budgets(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    adapter = get_adapter("codex")
    artifact = render_structured_skill(
        plan,
        adapter,
        entrypoint_max_bytes=100_000,
        artifact_max_bytes=1_000_000,
    )
    files = _files(artifact)
    entrypoint_bytes = len(files["SKILL.md"].encode("utf-8"))
    artifact_bytes = sum(len(content.encode("utf-8")) for content in files.values())

    assert (
        render_structured_skill(
            plan,
            adapter,
            entrypoint_max_bytes=entrypoint_bytes,
            artifact_max_bytes=artifact_bytes,
        )
        == artifact
    )

    with pytest.raises(CompositionError, match="SKILL.md uses") as entrypoint_error:
        render_structured_skill(
            plan,
            adapter,
            entrypoint_max_bytes=entrypoint_bytes - 1,
            artifact_max_bytes=artifact_bytes,
        )
    assert entrypoint_error.value.location == "$.budgets.entrypoint-max-bytes"

    with pytest.raises(CompositionError, match="complete artifact uses") as total_error:
        render_structured_skill(
            plan,
            adapter,
            entrypoint_max_bytes=entrypoint_bytes,
            artifact_max_bytes=artifact_bytes - 1,
        )
    assert total_error.value.location == "$.budgets.artifact-max-bytes"


@pytest.mark.parametrize("value", (None, True, 0, -1, 1.5))
def test_structured_skill_rejects_invalid_budget(tmp_path: Path, value: object) -> None:
    plan = _plan(tmp_path)

    with pytest.raises(CompositionError, match="exact positive integer"):
        render_structured_skill(
            plan,
            get_adapter("claude"),
            entrypoint_max_bytes=value,  # type: ignore[arg-type]
            artifact_max_bytes=1_000_000,
        )


def test_structured_skill_reauthenticates_plan_after_assembly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan(tmp_path)
    original = rendering_module.assemble_skill

    def hostile_assembly(source, adapter):
        artifact = original(source, adapter)
        object.__setattr__(plan.procedure, "purpose", "changed")
        return artifact

    monkeypatch.setattr(rendering_module, "assemble_skill", hostile_assembly)

    with pytest.raises(AcquisitionContractError, match="state changed"):
        render_structured_skill(
            plan,
            get_adapter("claude"),
            entrypoint_max_bytes=100_000,
            artifact_max_bytes=1_000_000,
        )


def test_structured_skill_authenticates_before_budget_validation() -> None:
    forged = object.__new__(StructuredSkillPlan)

    with pytest.raises(CompositionError, match="not issued"):
        render_structured_skill(
            forged,
            get_adapter("claude"),
            entrypoint_max_bytes=0,
            artifact_max_bytes=0,
        )


def test_structured_resources_sort_and_deduplicate_exact_pairs(tmp_path: Path) -> None:
    shared = {
        "resource": "oikos/shared",
        "destination": "scripts/shared.py",
    }
    publish = _operation(
        support_resources=[
            {
                "resource": "oikos/z-resource",
                "destination": "scripts/z.py",
            },
            shared,
        ]
    )
    check = _operation(
        identifier="oikos/check-index",
        support_resources=[
            shared,
            {
                "resource": "oikos/a-resource",
                "destination": "scripts/a.py",
            },
        ],
    )
    procedure = _procedure()
    procedure["actions"] = [
        {
            "id": "publish",
            "operation": {"id": "oikos/publish-index", "version": 1},
            "with": {},
            "on-success": "check",
            "on-failure": {"publish-failed": "publish-failed"},
        },
        {
            "id": "check",
            "operation": {"id": "oikos/check-index", "version": 1},
            "with": {},
            "on-success": "published",
            "on-failure": {"publish-failed": "publish-failed"},
        },
    ]
    _acquisition, resolution = _pipeline(
        tmp_path,
        operation=publish,
        procedure=procedure,
        extra_declarations=(("declarations/check-operation.yaml", _yaml(check)),),
        resources=(
            (
                "oikos/z-resource",
                "declarations/resources/z.py",
                MEDIA_TYPE,
                b"z\n",
            ),
            (
                "oikos/shared",
                "declarations/resources/shared.py",
                MEDIA_TYPE,
                b"shared\n",
            ),
            (
                "oikos/a-resource",
                "declarations/resources/a.py",
                MEDIA_TYPE,
                b"a\n",
            ),
        ),
    )
    artifact = render_structured_skill(
        plan_structured_skill(resolution),
        get_adapter("claude"),
        entrypoint_max_bytes=100_000,
        artifact_max_bytes=1_000_000,
    )

    paths = [file.relative_path for file in artifact.files]
    assert paths[2:5] == ["scripts/a.py", "scripts/shared.py", "scripts/z.py"]
    assert paths.count("scripts/shared.py") == 1
