"""Exercise structured rule Skills through the shared publication boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from eutaxis.commands import CommandError, Registry, get_adapter, install_artifacts
from eutaxis.declarations import (
    plan_structured_rule_skill,
    render_structured_rule_skill,
)
from tests.test_structured_rule_skill import _rule_pipeline, _rule_set


def _rendered_rule_skills(
    tmp_path: Path,
    *,
    purpose: str,
):
    """Render one authenticated rule plan for both supported adapters."""
    _acquisition, resolution = _rule_pipeline(
        tmp_path,
        rule_set=_rule_set(purpose=purpose),
    )
    plan = plan_structured_rule_skill(resolution)
    return tuple(
        (
            render_structured_rule_skill(
                plan,
                adapter,
                entrypoint_max_bytes=100_000,
                artifact_max_bytes=1_000_000,
            ),
            adapter,
        )
        for adapter in (get_adapter("claude"), get_adapter("codex"))
    )


def _tree_bytes(root: Path) -> dict[str, bytes]:
    """Return the exact regular-file tree below one installed Skill."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_failed_rule_skill_batch_restores_artifacts_and_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    initial = _rendered_rule_skills(
        tmp_path / "initial",
        purpose="Test code behavior at the boundary",
    )
    changed = _rendered_rule_skills(
        tmp_path / "changed",
        purpose="Test changed behavior at the boundary",
    )
    registry = Registry(home / ".eutaxis" / "state")
    install_artifacts(
        initial,
        project_root=project,
        home=home,
        registry=registry,
    )
    targets = tuple(
        adapter.artifact_dir(
            artifact.name,
            artifact.scope,
            home=home,
            project_root=project,
        )
        for artifact, adapter in initial
    )
    trees_before = tuple(_tree_bytes(target) for target in targets)
    registry_before = registry.path.read_bytes()
    working_upsert = registry.upsert

    def fail_on_second_registry_update(record) -> None:
        working_upsert(record)
        if record.adapter == "codex":
            raise CommandError("planted rule-Skill publication failure")

    monkeypatch.setattr(registry, "upsert", fail_on_second_registry_update)

    with pytest.raises(
        CommandError,
        match="planted rule-Skill publication failure",
    ):
        install_artifacts(
            changed,
            project_root=project,
            home=home,
            registry=registry,
        )

    assert tuple(_tree_bytes(target) for target in targets) == trees_before
    assert registry.path.read_bytes() == registry_before
