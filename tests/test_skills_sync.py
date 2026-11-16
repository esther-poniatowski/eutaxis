"""Tests that preview and apply the complete configured Skill set."""

from __future__ import annotations

import json
import stat
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from eutaxis.cli import app
from eutaxis.commands import (
    CommandError,
    CommandSource,
    OwnershipError,
    PreparedSkillSync,
    Registry,
    get_adapter,
    verify_artifact,
)
from eutaxis.commands import synchronization as synchronization_module
from eutaxis.commands.models import TargetsSpec
from eutaxis.commands.synchronization import (
    SkillSyncManifest,
    apply_prepared_skill_sync,
    prepare_skill_sync,
)


def _write_module(path: Path, name: str, body: str = "rule body\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {name} description\n"
        "invocation: [model, user]\n"
        "failure-mode: visible\n"
        "---\n"
        f"{body}",
        encoding="utf-8",
    )


def _write_config(path: Path, names: tuple[str, ...]) -> None:
    modules = [
        {
            "id": name,
            "title": name.title(),
            "path": f"instructions/{name}.md",
            "trigger": f"on {name}",
        }
        for name in names
    ]
    path.write_text(
        yaml.safe_dump(
            {
                "_schema": "eutaxis:configuration@1",
                "common_sources": [],
                "task_modules": modules,
                "agents": [],
            }
        ),
        encoding="utf-8",
    )


def _skills(home: Path, *arguments: str):
    return CliRunner().invoke(
        app,
        ["skills", *arguments, "--agent", "claude"],
        env={"HOME": str(home)},
    )


def _source(name: str, body: str) -> CommandSource:
    """Return one direct source for prepared-publication tests."""
    return CommandSource(
        name=name,
        description=f"{name} description",
        invocation=("model", "user"),
        failure_mode="visible",
        scope_default="user",
        targets=TargetsSpec(),
        action=None,
        body=body,
    )


def _prepare(sources: list[CommandSource], *, home: Path, project_root: Path):
    """Prepare user-scope Claude actions against one isolated home."""
    return prepare_skill_sync(
        sources,
        [get_adapter("claude")],
        scope="user",
        project_root=project_root,
        home=home,
    )


def _tree_state(root: Path) -> tuple[tuple[str, bytes, int, int], ...]:
    """Capture file bytes, modes, and modification times below one target."""
    return tuple(
        (
            path.relative_to(root).as_posix(),
            path.read_bytes(),
            path.stat().st_mode,
            path.stat().st_mtime_ns,
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def test_skills_sync_previews_without_writing(tmp_path: Path) -> None:
    _write_module(tmp_path / "instructions" / "alpha.md", "alpha")
    config = tmp_path / "eutaxis.yml"
    _write_config(config, ("alpha",))
    home = tmp_path / "home"
    home.mkdir()

    result = _skills(home, "sync", "-c", str(config))

    assert result.exit_code == 0, result.output
    assert "[CREATE   ] alpha@claude" in result.output
    assert "Preview only" in result.output
    assert not (home / ".claude" / "skills" / "alpha").exists()
    assert not (home / ".eutaxis").exists()


def test_skills_sync_applies_updates_and_owned_orphan_removals(
    tmp_path: Path,
) -> None:
    for name in ("alpha", "retired"):
        _write_module(tmp_path / "instructions" / f"{name}.md", name)
    config = tmp_path / "eutaxis.yml"
    _write_config(config, ("alpha", "retired"))
    home = tmp_path / "home"
    home.mkdir()
    first_apply = _skills(home, "sync", "-c", str(config), "--apply")
    assert first_apply.exit_code == 0, first_apply.output
    manifest = SkillSyncManifest(home / ".eutaxis" / "state", config)
    payload = json.loads(manifest.path.read_text(encoding="utf-8"))
    assert next(iter(payload)) == "_schema"
    assert payload["_schema"] == "eutaxis:skill-sync-manifest@1"

    _write_module(
        tmp_path / "instructions" / "alpha.md",
        "alpha",
        body="updated body\n",
    )
    _write_config(config, ("alpha",))

    preview = _skills(home, "sync", "-c", str(config))
    assert preview.exit_code == 0, preview.output
    assert "[UPDATE   ] alpha@claude" in preview.output
    assert "[REMOVE   ] retired@claude" in preview.output
    assert (home / ".claude" / "skills" / "retired").is_dir()

    applied = _skills(home, "sync", "-c", str(config), "--apply")
    assert applied.exit_code == 0, applied.output
    assert "[UPDATED  ] alpha@claude" in applied.output
    assert "[REMOVED  ] retired@claude" in applied.output
    assert "updated body" in (
        home / ".claude" / "skills" / "alpha" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert not (home / ".claude" / "skills" / "retired").exists()


def test_skills_sync_preserves_non_eutaxis_orphans(tmp_path: Path) -> None:
    _write_module(tmp_path / "instructions" / "alpha.md", "alpha")
    config = tmp_path / "eutaxis.yml"
    _write_config(config, ("alpha",))
    home = tmp_path / "home"
    foreign = home / ".claude" / "skills" / "foreign"
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text("user owned\n", encoding="utf-8")

    result = _skills(home, "sync", "-c", str(config), "--apply")

    assert result.exit_code == 0, result.output
    assert foreign.is_dir()
    assert "foreign" not in result.output


def test_skills_sync_preserves_artifacts_managed_by_another_config(
    tmp_path: Path,
) -> None:
    for name in ("alpha", "beta"):
        _write_module(tmp_path / "instructions" / f"{name}.md", name)
    config_a = tmp_path / "config-a.yaml"
    config_b = tmp_path / "config-b.yaml"
    _write_config(config_a, ("alpha",))
    _write_config(config_b, ("beta",))
    home = tmp_path / "home"
    home.mkdir()

    first = _skills(home, "sync", "-c", str(config_a), "--apply")
    second = _skills(home, "sync", "-c", str(config_b), "--apply")

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert (home / ".claude" / "skills" / "alpha").is_dir()
    assert (home / ".claude" / "skills" / "beta").is_dir()

    _write_config(config_a, ())
    retired = _skills(home, "sync", "-c", str(config_a), "--apply")

    assert retired.exit_code == 0, retired.output
    assert not (home / ".claude" / "skills" / "alpha").exists()
    assert (home / ".claude" / "skills" / "beta").is_dir()


def test_skills_sync_preserves_a_name_claimed_by_another_config(
    tmp_path: Path,
) -> None:
    _write_module(tmp_path / "instructions" / "shared.md", "shared")
    config_a = tmp_path / "config-a.yaml"
    config_b = tmp_path / "config-b.yaml"
    _write_config(config_a, ("shared",))
    _write_config(config_b, ("shared",))
    home = tmp_path / "home"
    home.mkdir()
    assert _skills(
        home, "sync", "-c", str(config_a), "--apply"
    ).exit_code == 0
    assert _skills(
        home, "sync", "-c", str(config_b), "--apply"
    ).exit_code == 0

    _write_config(config_a, ())
    first_retirement = _skills(
        home, "sync", "-c", str(config_a), "--apply"
    )

    assert first_retirement.exit_code == 0, first_retirement.output
    assert (home / ".claude" / "skills" / "shared").is_dir()

    _write_config(config_b, ())
    final_retirement = _skills(
        home, "sync", "-c", str(config_b), "--apply"
    )

    assert final_retirement.exit_code == 0, final_retirement.output
    assert not (home / ".claude" / "skills" / "shared").exists()


def test_skills_sync_preserves_owned_artifact_without_config_manifest(
    tmp_path: Path,
) -> None:
    _write_module(tmp_path / "instructions" / "legacy.md", "legacy")
    legacy_config = tmp_path / "legacy.yaml"
    active_config = tmp_path / "active.yaml"
    _write_config(legacy_config, ("legacy",))
    _write_config(active_config, ())
    home = tmp_path / "home"
    home.mkdir()
    installed = _skills(home, "install", "all", "-c", str(legacy_config))
    assert installed.exit_code == 0, installed.output

    result = _skills(home, "sync", "-c", str(active_config), "--apply")

    assert result.exit_code == 0, result.output
    assert (home / ".claude" / "skills" / "legacy").is_dir()


def test_project_sync_tracks_each_project_root_independently(tmp_path: Path) -> None:
    _write_module(tmp_path / "instructions" / "alpha.md", "alpha")
    config = tmp_path / "eutaxis.yml"
    _write_config(config, ("alpha",))
    home = tmp_path / "home"
    home.mkdir()
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    for project in (first, second):
        result = _skills(
            home,
            "sync",
            "-c",
            str(config),
            "--scope",
            "project",
            "--target-project",
            str(project),
            "--apply",
        )
        assert result.exit_code == 0, result.output

    _write_config(config, ())
    for retired, retained in ((first, second), (second, None)):
        result = _skills(
            home,
            "sync",
            "-c",
            str(config),
            "--scope",
            "project",
            "--target-project",
            str(retired),
            "--apply",
        )
        assert result.exit_code == 0, result.output
        assert not (retired / ".claude" / "skills" / "alpha").exists()
        if retained is not None:
            assert (retained / ".claude" / "skills" / "alpha").is_dir()


def test_skills_sync_blocks_a_configured_non_eutaxis_target(
    tmp_path: Path,
) -> None:
    for name in ("alpha", "blocked"):
        _write_module(tmp_path / "instructions" / f"{name}.md", name)
    config = tmp_path / "eutaxis.yml"
    _write_config(config, ("alpha", "blocked"))
    home = tmp_path / "home"
    blocked = home / ".claude" / "skills" / "blocked"
    blocked.mkdir(parents=True)
    (blocked / "SKILL.md").write_text("user owned\n", encoding="utf-8")

    result = _skills(home, "sync", "-c", str(config), "--apply")

    assert result.exit_code == 2, result.output
    assert "non-eutaxis directory" in result.output
    assert not (home / ".claude" / "skills" / "alpha").exists()


def test_skills_sync_preflights_registry_before_writing(tmp_path: Path) -> None:
    _write_module(tmp_path / "instructions" / "alpha.md", "alpha")
    config = tmp_path / "eutaxis.yml"
    _write_config(config, ("alpha",))
    home = tmp_path / "home"
    registry = home / ".eutaxis" / "state" / "installed-commands.json"
    registry.parent.mkdir(parents=True)
    registry.write_text("not json\n", encoding="utf-8")

    result = _skills(home, "sync", "-c", str(config), "--apply")

    assert result.exit_code == 2, result.output
    assert "Registry" in result.output
    assert not (home / ".claude" / "skills" / "alpha").exists()


def test_skills_sync_preflights_manifest_before_writing(tmp_path: Path) -> None:
    _write_module(tmp_path / "instructions" / "alpha.md", "alpha")
    config = tmp_path / "eutaxis.yml"
    _write_config(config, ("alpha",))
    home = tmp_path / "home"
    manifest = SkillSyncManifest(home / ".eutaxis" / "state", config)
    manifest.path.parent.mkdir(parents=True)
    manifest.path.write_text("not json\n", encoding="utf-8")

    result = _skills(home, "sync", "-c", str(config), "--apply")

    assert result.exit_code == 2, result.output
    assert "manifest" in result.output
    assert not (home / ".claude" / "skills" / "alpha").exists()


def test_skills_sync_rejects_retired_manifest_schema_key(tmp_path: Path) -> None:
    config = tmp_path / "eutaxis.yml"
    _write_config(config, ())
    home = tmp_path / "home"
    manifest = SkillSyncManifest(home / ".eutaxis" / "state", config)
    manifest.path.parent.mkdir(parents=True)
    manifest.path.write_text(
        '{"schema_version": 1, "config": "'
        + str(config.resolve())
        + '", "deployments": {}}\n',
        encoding="utf-8",
    )

    result = _skills(home, "sync", "-c", str(config), "--apply")

    assert result.exit_code == 2, result.output
    assert "_schema: eutaxis:skill-sync-manifest@1" in result.output


def test_skills_sync_rejects_unsafe_name_in_manifest(tmp_path: Path) -> None:
    config = tmp_path / "eutaxis.yml"
    _write_config(config, ())
    home = tmp_path / "home"
    manifest = SkillSyncManifest(home / ".eutaxis" / "state", config)
    manifest.path.parent.mkdir(parents=True)
    manifest.path.write_text(
        '{"_schema": "eutaxis:skill-sync-manifest@1", "config": "'
        + str(config.resolve())
        + '", "deployments": {"user:claude": ["../../../escape"]}}\n',
        encoding="utf-8",
    )

    result = _skills(home, "sync", "-c", str(config), "--apply")

    assert result.exit_code == 2, result.output
    assert "invalid deployments" in result.output


def test_prepared_sync_writes_only_selected_exact_artifact(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    sources = [_source("alpha", "alpha body\n"), _source("beta", "beta body\n")]
    prepared = _prepare(sources, home=home, project_root=tmp_path)
    alpha, beta = prepared.actions
    registry = Registry(home / ".eutaxis" / "state")

    outcomes = apply_prepared_skill_sync(
        prepared,
        selected=(alpha,),
        project_root=tmp_path,
        home=home,
        registry=registry,
    )

    assert [outcome.name for outcome in outcomes] == ["alpha"]
    assert alpha.artifact is not None
    verify_artifact(
        alpha.artifact,
        alpha.adapter,
        scope=alpha.scope,
        project_root=tmp_path,
        home=home,
    )
    assert not beta.path.exists()


def test_prepared_sync_preserves_unselected_target_bytes_and_metadata(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    sources = [_source("alpha", "alpha body\n"), _source("beta", "beta body\n")]
    registry = Registry(home / ".eutaxis" / "state")
    initial = _prepare(sources, home=home, project_root=tmp_path)
    apply_prepared_skill_sync(
        initial,
        selected=(initial.actions[0],),
        project_root=tmp_path,
        home=home,
        registry=registry,
    )
    alpha_path = initial.actions[0].path
    before = _tree_state(alpha_path)
    prepared = _prepare(sources, home=home, project_root=tmp_path)
    alpha, beta = prepared.actions

    assert alpha.action == "unchanged"
    apply_prepared_skill_sync(
        prepared,
        selected=(beta,),
        project_root=tmp_path,
        home=home,
        registry=registry,
    )

    assert _tree_state(alpha_path) == before


def test_prepared_sync_rejects_target_drift_before_any_write(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    prepared = _prepare(
        [_source("alpha", "alpha body\n")], home=home, project_root=tmp_path
    )
    action = prepared.actions[0]
    action.path.mkdir(parents=True)
    marker = action.path / "concurrent.txt"
    marker.write_text("concurrent content\n", encoding="utf-8")

    with pytest.raises(CommandError, match="changed after preparation"):
        apply_prepared_skill_sync(
            prepared,
            selected=(action,),
            project_root=tmp_path,
            home=home,
            registry=Registry(home / ".eutaxis" / "state"),
        )

    assert marker.read_text(encoding="utf-8") == "concurrent content\n"
    assert not (action.path / "SKILL.md").exists()


def test_prepared_sync_rejects_changed_plan_and_foreign_selection(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    prepared = _prepare(
        [_source("alpha", "alpha body\n")], home=home, project_root=tmp_path
    )
    registry = Registry(home / ".eutaxis" / "state")

    object.__setattr__(prepared, "digest", "0" * 64)
    with pytest.raises(CommandError, match="plan has changed"):
        apply_prepared_skill_sync(
            prepared,
            selected=(prepared.actions[0],),
            project_root=tmp_path,
            home=home,
            registry=registry,
        )

    prepared = _prepare(
        [_source("alpha", "alpha body\n")], home=home, project_root=tmp_path
    )
    foreign = replace(prepared.actions[0])
    with pytest.raises(CommandError, match="does not belong"):
        apply_prepared_skill_sync(
            prepared,
            selected=(foreign,),
            project_root=tmp_path,
            home=home,
            registry=registry,
        )
    assert not prepared.actions[0].path.exists()


def test_prepared_sync_binds_the_apply_home_and_complete_plan(tmp_path: Path) -> None:
    first_home = tmp_path / "first-home"
    second_home = tmp_path / "second-home"
    first_home.mkdir()
    second_home.mkdir()
    prepared = _prepare(
        [_source("alpha", "alpha body\n"), _source("beta", "beta body\n")],
        home=first_home,
        project_root=tmp_path,
    )

    with pytest.raises(CommandError, match="does not match the apply context"):
        apply_prepared_skill_sync(
            prepared,
            selected=(prepared.actions[0],),
            project_root=tmp_path,
            home=second_home,
            registry=Registry(second_home / ".eutaxis" / "state"),
        )

    beta_marker = prepared.actions[1].path
    beta_marker.mkdir(parents=True)
    (beta_marker / "concurrent.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(CommandError, match="changed after preparation"):
        apply_prepared_skill_sync(
            prepared,
            selected=(prepared.actions[0],),
            project_root=tmp_path,
            home=first_home,
            registry=Registry(first_home / ".eutaxis" / "state"),
        )

    assert not prepared.actions[0].path.exists()
    assert not (second_home / ".claude" / "skills" / "alpha").exists()


def test_prepared_project_sync_binds_the_apply_root(tmp_path: Path) -> None:
    home = tmp_path / "home"
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    for path in (home, first_root, second_root):
        path.mkdir()
    prepared = prepare_skill_sync(
        [_source("alpha", "alpha body\n")],
        [get_adapter("claude")],
        scope="project",
        project_root=first_root,
        home=home,
    )

    with pytest.raises(CommandError, match="does not match the apply context"):
        apply_prepared_skill_sync(
            prepared,
            selected=prepared.actions,
            project_root=second_root,
            home=home,
            registry=Registry(home / ".eutaxis" / "state"),
        )

    assert not (first_root / ".claude" / "skills" / "alpha").exists()
    assert not (second_root / ".claude" / "skills" / "alpha").exists()


def test_legacy_sync_reconciles_unchanged_registry_without_rewriting(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    sources = [_source("alpha", "alpha body\n")]
    registry = Registry(home / ".eutaxis" / "state")
    initial = _prepare(sources, home=home, project_root=tmp_path)
    apply_prepared_skill_sync(
        initial,
        selected=initial.actions,
        project_root=tmp_path,
        home=home,
        registry=registry,
    )
    prepared = _prepare(sources, home=home, project_root=tmp_path)
    assert prepared.actions[0].action == "unchanged"
    before = _tree_state(prepared.actions[0].path)
    registry.path.write_text("[]\n", encoding="utf-8")

    synchronization_module.apply_skill_sync(
        prepared.actions,
        project_root=tmp_path,
        home=home,
        registry=registry,
    )

    assert _tree_state(prepared.actions[0].path) == before
    assert (
        registry.find(
            name="alpha",
            adapter="claude",
            scope="user",
            path=prepared.actions[0].path,
        )
        is not None
    )


def test_prepared_sync_final_verification_rolls_back_late_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    prepared = _prepare(
        [_source("alpha", "alpha body\n"), _source("beta", "beta body\n")],
        home=home,
        project_root=tmp_path,
    )
    original_install = synchronization_module._install_artifact

    def mutate_first_after_install(*args, **kwargs):
        outcome = original_install(*args, **kwargs)
        if args[0].name == "beta":
            alpha = prepared.actions[0].path / "SKILL.md"
            alpha.write_text("concurrent replacement\n", encoding="utf-8")
        return outcome

    monkeypatch.setattr(
        synchronization_module, "_install_artifact", mutate_first_after_install
    )

    with pytest.raises(
        synchronization_module.OwnershipError,
        match="differs from the rendered artifact",
    ):
        apply_prepared_skill_sync(
            prepared,
            selected=prepared.actions,
            project_root=tmp_path,
            home=home,
            registry=Registry(home / ".eutaxis" / "state"),
        )

    assert (prepared.actions[0].path / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "concurrent replacement\n"
    assert not prepared.actions[1].path.exists()


def test_prepared_sync_preserves_concurrent_change_to_unwritten_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    prepared = _prepare(
        [_source("alpha", "alpha body\n"), _source("beta", "beta body\n")],
        home=home,
        project_root=tmp_path,
    )
    alpha, beta = prepared.actions
    original_install = synchronization_module._install_artifact

    def change_second_after_first_write(*args, **kwargs):
        outcome = original_install(*args, **kwargs)
        if args[0].name == "alpha":
            beta.path.mkdir(parents=True)
            (beta.path / "concurrent.txt").write_text(
                "concurrent content\n", encoding="utf-8"
            )
        return outcome

    monkeypatch.setattr(
        synchronization_module, "_install_artifact", change_second_after_first_write
    )

    with pytest.raises(CommandError, match="changed during publication"):
        apply_prepared_skill_sync(
            prepared,
            selected=prepared.actions,
            project_root=tmp_path,
            home=home,
            registry=Registry(home / ".eutaxis" / "state"),
        )

    assert not alpha.path.exists()
    assert (beta.path / "concurrent.txt").read_text(
        encoding="utf-8"
    ) == "concurrent content\n"


def test_prepared_sync_rejects_finalize_registry_drift_and_rolls_back(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    prepared = _prepare(
        [_source("alpha", "alpha body\n")], home=home, project_root=tmp_path
    )
    action = prepared.actions[0]
    registry = Registry(home / ".eutaxis" / "state")

    def remove_pending_row() -> None:
        registry.remove(
            name=action.name,
            adapter=action.adapter.name,
            scope=action.scope,
            path=action.path,
        )

    with pytest.raises(OwnershipError, match="registry row differs"):
        apply_prepared_skill_sync(
            prepared,
            selected=prepared.actions,
            project_root=tmp_path,
            home=home,
            registry=registry,
            finalize=remove_pending_row,
        )

    assert not action.path.exists()
    assert (
        registry.find(
            name=action.name,
            adapter=action.adapter.name,
            scope=action.scope,
            path=action.path,
        )
        is None
    )


def test_atomic_publish_keeps_original_after_staging_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    registry = Registry(home / ".eutaxis" / "state")
    initial = _prepare(
        [_source("alpha", "original body\n")], home=home, project_root=tmp_path
    )
    apply_prepared_skill_sync(
        initial,
        selected=initial.actions,
        project_root=tmp_path,
        home=home,
        registry=registry,
    )
    prepared = _prepare(
        [_source("alpha", "updated body\n")], home=home, project_root=tmp_path
    )
    action = prepared.actions[0]
    tree_before = _tree_state(action.path)
    registry_before = registry.path.read_bytes()
    original_write = synchronization_module._write_artifact_file
    calls = 0

    def fail_after_first_file(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected staging failure")
        return original_write(*args, **kwargs)

    monkeypatch.setattr(
        synchronization_module, "_write_artifact_file", fail_after_first_file
    )

    with pytest.raises(OSError, match="injected staging failure"):
        apply_prepared_skill_sync(
            prepared,
            selected=prepared.actions,
            project_root=tmp_path,
            home=home,
            registry=registry,
        )

    assert _tree_state(action.path) == tree_before
    assert registry.path.read_bytes() == registry_before


def test_atomic_remove_restores_original_after_registry_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    registry = Registry(home / ".eutaxis" / "state")
    initial = _prepare(
        [_source("alpha", "original body\n")], home=home, project_root=tmp_path
    )
    apply_prepared_skill_sync(
        initial,
        selected=initial.actions,
        project_root=tmp_path,
        home=home,
        registry=registry,
    )
    action = initial.actions[0]
    tree_before = _tree_state(action.path)
    registry_before = registry.path.read_bytes()
    prepared = prepare_skill_sync(
        [],
        [get_adapter("claude")],
        scope="user",
        project_root=tmp_path,
        home=home,
        managed_names_by_adapter={"claude": {"alpha"}},
    )
    original_uninstall = synchronization_module._uninstall_command

    def fail_after_registry_removal(*args, **kwargs):
        original_uninstall(*args, **kwargs)
        raise OSError("injected removal failure")

    monkeypatch.setattr(
        synchronization_module, "_uninstall_command", fail_after_registry_removal
    )

    with pytest.raises(OSError, match="injected removal failure"):
        apply_prepared_skill_sync(
            prepared,
            selected=prepared.actions,
            project_root=tmp_path,
            home=home,
            registry=registry,
        )

    assert _tree_state(action.path) == tree_before
    assert registry.path.read_bytes() == registry_before


def test_atomic_update_restores_after_post_exchange_observation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    registry = Registry(home / ".eutaxis" / "state")
    initial = _prepare(
        [_source("alpha", "original body\n")], home=home, project_root=tmp_path
    )
    apply_prepared_skill_sync(
        initial,
        selected=initial.actions,
        project_root=tmp_path,
        home=home,
        registry=registry,
    )
    prepared = _prepare(
        [_source("alpha", "updated body\n")], home=home, project_root=tmp_path
    )
    target = prepared.actions[0].path
    tree_before = _tree_state(target)
    original_exchange = synchronization_module._atomic_exchange
    original_observe = synchronization_module._observe_skill_target
    exchanged = False
    failed = False

    def mark_exchange(first: Path, second: Path) -> None:
        nonlocal exchanged
        original_exchange(first, second)
        exchanged = True

    def fail_first_target_observation(path: Path):
        nonlocal failed
        if exchanged and not failed and path == target:
            failed = True
            raise OSError("injected post-exchange observation failure")
        return original_observe(path)

    monkeypatch.setattr(synchronization_module, "_atomic_exchange", mark_exchange)
    monkeypatch.setattr(
        synchronization_module,
        "_observe_skill_target",
        fail_first_target_observation,
    )

    with pytest.raises(OSError, match="post-exchange observation failure"):
        apply_prepared_skill_sync(
            prepared,
            selected=prepared.actions,
            project_root=tmp_path,
            home=home,
            registry=registry,
        )

    assert _tree_state(target) == tree_before
    assert not tuple(target.parent.glob(".alpha.eutaxis-stage-*"))


def test_atomic_remove_restores_after_post_rename_observation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    registry = Registry(home / ".eutaxis" / "state")
    initial = _prepare(
        [_source("alpha", "original body\n")], home=home, project_root=tmp_path
    )
    apply_prepared_skill_sync(
        initial,
        selected=initial.actions,
        project_root=tmp_path,
        home=home,
        registry=registry,
    )
    target = initial.actions[0].path
    tree_before = _tree_state(target)
    prepared = prepare_skill_sync(
        [],
        [get_adapter("claude")],
        scope="user",
        project_root=tmp_path,
        home=home,
        managed_names_by_adapter={"claude": {"alpha"}},
    )
    original_rename = synchronization_module._atomic_rename_noreplace
    original_observe = synchronization_module._observe_skill_target
    renamed = False
    failed = False

    def mark_removal_rename(source: Path, destination: Path) -> None:
        nonlocal renamed
        original_rename(source, destination)
        if source == target:
            renamed = True

    def fail_first_target_observation(path: Path):
        nonlocal failed
        if renamed and not failed and path == target:
            failed = True
            raise OSError("injected post-removal observation failure")
        return original_observe(path)

    monkeypatch.setattr(
        synchronization_module, "_atomic_rename_noreplace", mark_removal_rename
    )
    monkeypatch.setattr(
        synchronization_module,
        "_observe_skill_target",
        fail_first_target_observation,
    )

    with pytest.raises(OSError, match="post-removal observation failure"):
        apply_prepared_skill_sync(
            prepared,
            selected=prepared.actions,
            project_root=tmp_path,
            home=home,
            registry=registry,
        )

    assert _tree_state(target) == tree_before
    assert not tuple(target.parent.glob(".alpha.eutaxis-previous-*"))


def test_atomic_create_refuses_concurrent_empty_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    prepared = _prepare(
        [_source("alpha", "alpha body\n")], home=home, project_root=tmp_path
    )
    target = prepared.actions[0].path
    original_rename = synchronization_module._atomic_rename_noreplace

    def create_target_before_claim(source: Path, destination: Path) -> None:
        if destination == target:
            target.mkdir(parents=True)
            target.chmod(0o700)
        original_rename(source, destination)

    monkeypatch.setattr(
        synchronization_module,
        "_atomic_rename_noreplace",
        create_target_before_claim,
    )

    with pytest.raises(OSError):
        apply_prepared_skill_sync(
            prepared,
            selected=prepared.actions,
            project_root=tmp_path,
            home=home,
            registry=Registry(home / ".eutaxis" / "state"),
        )

    assert target.is_dir()
    assert stat.S_IMODE(target.stat().st_mode) == 0o700
    assert not (target / "SKILL.md").exists()


def test_successful_update_surfaces_retained_recovery_target(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    registry = Registry(home / ".eutaxis" / "state")
    initial = _prepare(
        [_source("alpha", "original body\n")], home=home, project_root=tmp_path
    )
    apply_prepared_skill_sync(
        initial,
        selected=initial.actions,
        project_root=tmp_path,
        home=home,
        registry=registry,
    )
    prepared = _prepare(
        [_source("alpha", "updated body\n")], home=home, project_root=tmp_path
    )

    outcomes = apply_prepared_skill_sync(
        prepared,
        selected=prepared.actions,
        project_root=tmp_path,
        home=home,
        registry=registry,
    )

    warning = next(
        item for item in outcomes[0].warnings if item.startswith("Prior Skill retained")
    )
    recovery = Path(warning.split(": ", 1)[1])
    assert recovery.is_dir()
    assert "original body" in (recovery / "SKILL.md").read_text(encoding="utf-8")
    assert "updated body" in (
        prepared.actions[0].path / "SKILL.md"
    ).read_text(encoding="utf-8")


def test_target_observation_rejects_file_and_root_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "skill"
    target.mkdir()
    entrypoint = target / "SKILL.md"
    entrypoint.write_text("content\n", encoding="utf-8")
    external = tmp_path / "external"
    external.write_text("external\n", encoding="utf-8")
    original_open = synchronization_module.os.open

    def replace_file_before_open(path, flags, *args, **kwargs):
        if path == "SKILL.md" and kwargs.get("dir_fd") is not None:
            entrypoint.unlink()
            entrypoint.symlink_to(external)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(synchronization_module.os, "open", replace_file_before_open)
    with pytest.raises(CommandError, match="changed during observation"):
        synchronization_module._observe_skill_target(target)

    monkeypatch.setattr(synchronization_module.os, "open", original_open)
    entrypoint.unlink()
    entrypoint.write_text("content\n", encoding="utf-8")
    displaced = tmp_path / "displaced"
    original_stat = synchronization_module.os.stat

    def replace_root_before_final_stat(path, *args, **kwargs):
        if Path(path) == target and kwargs.get("follow_symlinks") is False:
            target.rename(displaced)
            target.mkdir()
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(
        synchronization_module.os, "stat", replace_root_before_final_stat
    )
    with pytest.raises(CommandError, match="changed during observation"):
        synchronization_module._observe_skill_target(target)


def test_prepared_sync_rejects_unissued_plan_and_defines_empty_selection(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    prepared = _prepare(
        [_source("alpha", "alpha body\n")], home=home, project_root=tmp_path
    )
    forged = object.__new__(PreparedSkillSync)
    for name, value in prepared.__dict__.items():
        object.__setattr__(forged, name, value)

    with pytest.raises(CommandError, match="was not issued here"):
        apply_prepared_skill_sync(
            forged,
            selected=(),
            project_root=tmp_path,
            home=home,
            registry=Registry(home / ".eutaxis" / "state"),
        )

    finalized: list[str] = []
    outcomes = apply_prepared_skill_sync(
        prepared,
        selected=(),
        project_root=tmp_path,
        home=home,
        registry=Registry(home / ".eutaxis" / "state"),
        finalize=lambda: finalized.append("done"),
    )

    assert outcomes == ()
    assert finalized == ["done"]
    assert not prepared.actions[0].path.exists()
