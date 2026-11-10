"""Tests of the ``--root`` option, its former names, and the settings lookup."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from eutaxis.cli import app
from eutaxis.instructions import ConfigurationError, find_config
from eutaxis.ops import encode_project_slug


def _write_settings(path: Path, *, root: str, target: str) -> None:
    """Write a settings file whose one agent copies ``rules.md`` to ``target``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"root: {root}\n"
        "common_sources:\n"
        "  - rules.md\n"
        "agents:\n"
        "  - name: codex\n"
        "    target:\n"
        f"      path: {target}\n",
        encoding="utf-8",
    )


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "rules.md").write_text("# Rules\n", encoding="utf-8")
    return project


# Settings lookup ----------------------------------------------------------


def test_find_config_prefers_config_tools_over_root(tmp_path: Path) -> None:
    nested = tmp_path / "config" / "tools" / "agent-instructions.yaml"
    flat = tmp_path / "agent-instructions.yaml"
    nested.parent.mkdir(parents=True)
    nested.write_text("{}\n", encoding="utf-8")
    flat.write_text("{}\n", encoding="utf-8")

    assert find_config(None, tmp_path) == nested.resolve()


def test_find_config_falls_back_to_root(tmp_path: Path) -> None:
    flat = tmp_path / "agent-instructions.yaml"
    flat.write_text("{}\n", encoding="utf-8")

    assert find_config(None, tmp_path) == flat.resolve()


def test_find_config_returns_explicit_path_without_lookup(tmp_path: Path) -> None:
    explicit = tmp_path / "elsewhere.yaml"

    assert find_config(explicit, tmp_path / "unused") == explicit.resolve()


def test_find_config_names_every_candidate_when_none_exists(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        find_config(None, tmp_path)

    message = str(excinfo.value)
    assert str(tmp_path / "config" / "tools" / "agent-instructions.yaml") in message
    assert str(tmp_path / "agent-instructions.yaml") in message


def test_generate_looks_up_config_tools_below_root_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    _write_settings(
        project / "config" / "tools" / "agent-instructions.yaml",
        root="../..",
        target="FROM_TOOLS.md",
    )
    _write_settings(
        project / "agent-instructions.yaml", root=".", target="FROM_ROOT.md"
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    _write_settings(
        elsewhere / "agent-instructions.yaml", root=".", target="FROM_CWD.md"
    )
    monkeypatch.chdir(elsewhere)

    result = CliRunner().invoke(app, ["generate", "--root", str(project)])

    assert result.exit_code == 0, result.output
    assert (project / "FROM_TOOLS.md").is_file()
    assert not (project / "FROM_ROOT.md").exists()
    assert not (elsewhere / "FROM_CWD.md").exists()


def test_generate_without_root_looks_up_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    _write_settings(
        project / "agent-instructions.yaml", root=".", target="AGENTS.md"
    )
    monkeypatch.chdir(project)

    result = CliRunner().invoke(app, ["generate"])

    assert result.exit_code == 0, result.output
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == "# Rules\n"


def test_generate_without_settings_file_fails_and_names_the_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["check"])

    assert result.exit_code == 1
    assert "config/tools/agent-instructions.yaml" in result.stderr


def _skills_project(tmp_path: Path) -> Path:
    """Create a project whose settings file sits in ``config/tools/``."""
    project = tmp_path / "project"
    module = project / "instructions" / "alpha.md"
    module.parent.mkdir(parents=True)
    module.write_text(
        "---\nname: alpha\ndescription: alpha description\n"
        "invocation: [model, user]\nfailure-mode: visible\n---\nbody\n",
        encoding="utf-8",
    )
    settings = project / "config" / "tools" / "agent-instructions.yaml"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        "root: ../..\ncommon_sources: []\nagents: []\ntask_modules:\n"
        "  - id: alpha\n    title: Alpha\n    path: instructions/alpha.md\n"
        "    trigger: on alpha\n",
        encoding="utf-8",
    )
    return project


def test_skills_list_finds_settings_below_root(tmp_path: Path) -> None:
    project = _skills_project(tmp_path)

    result = CliRunner().invoke(app, ["skills", "list", "--root", str(project)])

    assert result.exit_code == 0, result.output
    assert "alpha" in result.stdout


def test_skills_sync_former_project_option_works_and_warns(tmp_path: Path) -> None:
    project = _skills_project(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    result = CliRunner().invoke(
        app,
        ["skills", "sync", "--agent", "claude", "--scope", "project",
         "--project", str(project), "--apply"],
        env={"HOME": str(home)},
    )

    assert result.exit_code == 0, result.output
    assert (project / ".claude" / "skills" / "alpha" / "SKILL.md").is_file()
    assert "--project is deprecated" in result.stderr


# Former names of --root ----------------------------------------------------


def _seed_memory(home: Path, project: Path) -> Path:
    memory = home / ".claude" / "projects" / encode_project_slug(project) / "memory"
    memory.mkdir(parents=True)
    (memory / "note.md").write_text("note\n", encoding="utf-8")
    return memory


@pytest.mark.parametrize("flag", ["--root", "-r"])
def test_clean_memory_dry_run_with_root_writes_nothing(
    tmp_path: Path, flag: str
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    memory = _seed_memory(home, project)

    result = CliRunner().invoke(
        app,
        ["ops", "clean-memory", "--agent", "claude", flag, str(project), "--dry-run"],
        env={"HOME": str(home)},
    )

    assert result.exit_code == 0, result.output
    assert "Would remove 1 file(s)" in result.stdout
    assert (memory / "note.md").is_file()
    assert "deprecated" not in result.stderr


def test_clean_memory_former_project_option_works_and_warns(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    memory = _seed_memory(home, project)

    result = CliRunner().invoke(
        app,
        [
            "ops", "clean-memory", "--agent", "claude",
            "--project", str(project), "--yes",
        ],
        env={"HOME": str(home)},
    )

    assert result.exit_code == 0, result.output
    assert not (memory / "note.md").exists()
    assert "--project is deprecated" in result.stderr
    assert "--root" in result.stderr


def test_root_and_its_former_name_together_are_refused(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["commands", "list", "--root", str(tmp_path), "--project", str(tmp_path)],
    )

    assert result.exit_code == 2
    assert "give the root once" in result.stderr


def test_commands_list_reads_project_layer_with_root_and_former_name(
    tmp_path: Path,
) -> None:
    source = tmp_path / ".eutaxis" / "commands" / "local-only.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "---\nname: local-only\ndescription: Project command.\n"
        "invocation: [user]\nfailure-mode: visible\n"
        "action:\n  kind: shell\n  template: \"true\"\n---\nbody\n",
        encoding="utf-8",
    )
    home = tmp_path / "home"
    home.mkdir()

    new = CliRunner().invoke(
        app, ["commands", "list", "--root", str(tmp_path)], env={"HOME": str(home)}
    )
    former = CliRunner().invoke(
        app, ["commands", "list", "--project", str(tmp_path)], env={"HOME": str(home)}
    )

    assert new.exit_code == 0, new.output
    assert former.exit_code == 0, former.output
    assert "local-only (project)" in new.stdout
    assert new.stdout == former.stdout
    assert "--project is deprecated" in former.stderr


@pytest.mark.parametrize(
    ("flags", "warns"),
    [(("--root",), False), (("--target",), True), (("-t",), True)],
)
def test_init_scaffolds_into_root_or_former_target(
    tmp_path: Path, flags: tuple[str, ...], warns: bool
) -> None:
    result = CliRunner().invoke(
        app, ["init", "--template", "codex-project", *flags, str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "agent-instructions.yaml").is_file()
    assert ("--target is deprecated" in result.stderr) is warns


def test_former_names_are_hidden_from_help() -> None:
    for arguments in (
        ["init", "--help"],
        ["ops", "clean-memory", "--help"],
        ["skills", "sync", "--help"],
        ["commands", "install", "--help"],
    ):
        result = CliRunner().invoke(app, arguments)
        assert result.exit_code == 0, result.output
        assert "--root" in result.stdout
        assert "--project" not in result.stdout
        assert "--target" not in result.stdout
