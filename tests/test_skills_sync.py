"""Tests that preview and apply the complete configured Skill set."""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from eutaxis.cli import app
from eutaxis.commands.synchronization import SkillSyncManifest


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


def _write_config(path: Path, root: Path, names: tuple[str, ...]) -> None:
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
                "root": str(root),
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


def test_skills_sync_previews_without_writing(tmp_path: Path) -> None:
    _write_module(tmp_path / "instructions" / "alpha.md", "alpha")
    config = tmp_path / "agent-instructions.yaml"
    _write_config(config, tmp_path, ("alpha",))
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
    config = tmp_path / "agent-instructions.yaml"
    _write_config(config, tmp_path, ("alpha", "retired"))
    home = tmp_path / "home"
    home.mkdir()
    first_apply = _skills(home, "sync", "-c", str(config), "--apply")
    assert first_apply.exit_code == 0, first_apply.output

    _write_module(
        tmp_path / "instructions" / "alpha.md",
        "alpha",
        body="updated body\n",
    )
    _write_config(config, tmp_path, ("alpha",))

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
    config = tmp_path / "agent-instructions.yaml"
    _write_config(config, tmp_path, ("alpha",))
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
    _write_config(config_a, tmp_path, ("alpha",))
    _write_config(config_b, tmp_path, ("beta",))
    home = tmp_path / "home"
    home.mkdir()

    first = _skills(home, "sync", "-c", str(config_a), "--apply")
    second = _skills(home, "sync", "-c", str(config_b), "--apply")

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert (home / ".claude" / "skills" / "alpha").is_dir()
    assert (home / ".claude" / "skills" / "beta").is_dir()

    _write_config(config_a, tmp_path, ())
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
    _write_config(config_a, tmp_path, ("shared",))
    _write_config(config_b, tmp_path, ("shared",))
    home = tmp_path / "home"
    home.mkdir()
    assert _skills(
        home, "sync", "-c", str(config_a), "--apply"
    ).exit_code == 0
    assert _skills(
        home, "sync", "-c", str(config_b), "--apply"
    ).exit_code == 0

    _write_config(config_a, tmp_path, ())
    first_retirement = _skills(
        home, "sync", "-c", str(config_a), "--apply"
    )

    assert first_retirement.exit_code == 0, first_retirement.output
    assert (home / ".claude" / "skills" / "shared").is_dir()

    _write_config(config_b, tmp_path, ())
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
    _write_config(legacy_config, tmp_path, ("legacy",))
    _write_config(active_config, tmp_path, ())
    home = tmp_path / "home"
    home.mkdir()
    installed = _skills(home, "install", "all", "-c", str(legacy_config))
    assert installed.exit_code == 0, installed.output

    result = _skills(home, "sync", "-c", str(active_config), "--apply")

    assert result.exit_code == 0, result.output
    assert (home / ".claude" / "skills" / "legacy").is_dir()


def test_project_sync_tracks_each_project_root_independently(tmp_path: Path) -> None:
    _write_module(tmp_path / "instructions" / "alpha.md", "alpha")
    config = tmp_path / "agent-instructions.yaml"
    _write_config(config, tmp_path, ("alpha",))
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
            "--project",
            str(project),
            "--apply",
        )
        assert result.exit_code == 0, result.output

    _write_config(config, tmp_path, ())
    for retired, retained in ((first, second), (second, None)):
        result = _skills(
            home,
            "sync",
            "-c",
            str(config),
            "--scope",
            "project",
            "--project",
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
    config = tmp_path / "agent-instructions.yaml"
    _write_config(config, tmp_path, ("alpha", "blocked"))
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
    config = tmp_path / "agent-instructions.yaml"
    _write_config(config, tmp_path, ("alpha",))
    home = tmp_path / "home"
    registry = home / ".eutaxis" / "state" / "installed-commands.json"
    registry.parent.mkdir(parents=True)
    registry.write_text("not json\n", encoding="utf-8")

    result = _skills(home, "sync", "-c", str(config), "--apply")

    assert result.exit_code == 1, result.output
    assert "Registry" in result.output
    assert not (home / ".claude" / "skills" / "alpha").exists()


def test_skills_sync_preflights_manifest_before_writing(tmp_path: Path) -> None:
    _write_module(tmp_path / "instructions" / "alpha.md", "alpha")
    config = tmp_path / "agent-instructions.yaml"
    _write_config(config, tmp_path, ("alpha",))
    home = tmp_path / "home"
    manifest = SkillSyncManifest(home / ".eutaxis" / "state", config)
    manifest.path.parent.mkdir(parents=True)
    manifest.path.write_text("not json\n", encoding="utf-8")

    result = _skills(home, "sync", "-c", str(config), "--apply")

    assert result.exit_code == 1, result.output
    assert "manifest" in result.output
    assert not (home / ".claude" / "skills" / "alpha").exists()


def test_skills_sync_rejects_unsafe_name_in_manifest(tmp_path: Path) -> None:
    config = tmp_path / "agent-instructions.yaml"
    _write_config(config, tmp_path, ())
    home = tmp_path / "home"
    manifest = SkillSyncManifest(home / ".eutaxis" / "state", config)
    manifest.path.parent.mkdir(parents=True)
    manifest.path.write_text(
        '{"config": "'
        + str(config.resolve())
        + '", "deployments": {"user:claude": ["../../../escape"]}}\n',
        encoding="utf-8",
    )

    result = _skills(home, "sync", "-c", str(config), "--apply")

    assert result.exit_code == 1, result.output
    assert "invalid deployments" in result.output
