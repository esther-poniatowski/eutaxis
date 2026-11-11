"""Tests of the command-line conventions: root, settings file, paths, exit
statuses, confirmations and retired names."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from eutaxis import _cli_options
from eutaxis.cli import app
from eutaxis.commands.cli_errors import exit_with_error
from eutaxis.instructions import (
    ConfigurationError,
    find_config,
    load_config,
    resolve_root,
    settings_root,
)
from eutaxis.ops import encode_project_slug


def _write_settings(path: Path, *, target: str, extra: str = "") -> Path:
    """Write a settings file whose one agent copies ``rules.md`` to ``target``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"{extra}"
        "common_sources:\n"
        "  - rules.md\n"
        "agents:\n"
        "  - name: codex\n"
        "    target:\n"
        f"      path: {target}\n",
        encoding="utf-8",
    )
    return path


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "rules.md").write_text("# Rules\n", encoding="utf-8")
    return project


# Settings lookup ----------------------------------------------------------


def test_find_config_reads_config_tools(tmp_path: Path) -> None:
    nested = tmp_path / "config" / "tools" / "eutaxis.yml"
    nested.parent.mkdir(parents=True)
    nested.write_text("{}\n", encoding="utf-8")

    assert find_config(None, tmp_path) == nested.resolve()


def test_find_config_reads_the_root(tmp_path: Path) -> None:
    flat = tmp_path / "eutaxis.yml"
    flat.write_text("{}\n", encoding="utf-8")

    assert find_config(None, tmp_path) == flat.resolve()


def test_find_config_refuses_two_settings_files_and_names_both(tmp_path: Path) -> None:
    nested = tmp_path / "config" / "tools" / "eutaxis.yml"
    flat = tmp_path / "eutaxis.yml"
    nested.parent.mkdir(parents=True)
    nested.write_text("{}\n", encoding="utf-8")
    flat.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError) as excinfo:
        find_config(None, tmp_path)

    assert str(nested.resolve()) in str(excinfo.value)
    assert str(flat.resolve()) in str(excinfo.value)
    assert excinfo.value.exit_code == 2


def test_find_config_returns_explicit_path_without_lookup(tmp_path: Path) -> None:
    explicit = tmp_path / "elsewhere.yml"

    assert find_config(explicit, tmp_path / "unused") == explicit.resolve()


def test_find_config_names_every_place_when_none_exists(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        find_config(None, tmp_path)

    message = str(excinfo.value)
    assert str(tmp_path / "config" / "tools" / "eutaxis.yml") in message
    assert str(tmp_path / "eutaxis.yml") in message


def test_former_settings_file_name_is_not_read(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_settings(project / "agent-instructions.yaml", target="AGENTS.md")

    result = CliRunner().invoke(app, ["generate", "--root", str(project)])

    assert result.exit_code == 2
    assert "eutaxis.yml" in result.stderr
    assert not (project / "AGENTS.md").exists()


def test_two_settings_files_fail_the_command_with_status_2(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_settings(project / "config" / "tools" / "eutaxis.yml", target="A.md")
    _write_settings(project / "eutaxis.yml", target="B.md")

    result = CliRunner().invoke(app, ["generate", "--root", str(project)])

    assert result.exit_code == 2
    assert "Two settings files compete" in result.stderr
    assert not (project / "A.md").exists()
    assert not (project / "B.md").exists()


def test_missing_settings_file_fails_with_status_2() -> None:
    result = CliRunner().invoke(app, ["check"])

    assert result.exit_code == 2
    assert "config/tools/eutaxis.yml" in result.stderr


def test_absent_explicit_config_fails_with_status_2(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["list", "-c", "absent.yml"])

    assert result.exit_code == 2
    assert str(tmp_path / "absent.yml") in result.stderr


# Root resolution -----------------------------------------------------------


def test_resolve_root_prefers_option_then_variable_then_ancestor(tmp_path: Path) -> None:
    project = tmp_path / "project"
    nested = project / "a" / "b"
    nested.mkdir(parents=True)
    (project / "config" / "tools").mkdir(parents=True)
    (project / "config" / "tools" / "eutaxis.yml").write_text("{}\n", encoding="utf-8")
    other = tmp_path / "other"
    other.mkdir()

    environ = {"EUTAXIS_ROOT": str(other)}
    assert resolve_root(Path("x"), cwd=nested, environ=environ) == nested / "x"
    assert resolve_root(None, cwd=nested, environ=environ) == other.resolve()
    assert resolve_root(None, cwd=nested, environ={}) == project.resolve()
    assert resolve_root(None, cwd=other, environ={}) == other.resolve()
    assert resolve_root(None, cwd=nested, environ={"EUTAXIS_ROOT": ""}) == (
        project.resolve()
    )


def test_settings_root_is_the_project_of_a_file_in_config_tools(tmp_path: Path) -> None:
    assert settings_root(tmp_path / "config" / "tools" / "eutaxis.yml") == tmp_path
    assert settings_root(tmp_path / "eutaxis.yml") == tmp_path


def test_generate_runs_from_a_subfolder_of_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    _write_settings(project / "config" / "tools" / "eutaxis.yml", target="AGENTS.md")
    subfolder = project / "docs" / "deep"
    subfolder.mkdir(parents=True)
    monkeypatch.chdir(subfolder)

    result = CliRunner().invoke(app, ["generate"])

    assert result.exit_code == 0, result.output
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == "# Rules\n"


def test_root_variable_names_the_project(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_settings(project / "eutaxis.yml", target="AGENTS.md")

    result = CliRunner().invoke(app, ["generate"], env={"EUTAXIS_ROOT": str(project)})

    assert result.exit_code == 0, result.output
    assert (project / "AGENTS.md").is_file()


def test_root_option_overrides_the_variable(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_settings(project / "eutaxis.yml", target="AGENTS.md")
    decoy = tmp_path / "decoy"
    decoy.mkdir()

    result = CliRunner().invoke(
        app,
        ["generate", "--root", str(project)],
        env={"EUTAXIS_ROOT": str(decoy)},
    )

    assert result.exit_code == 0, result.output
    assert (project / "AGENTS.md").is_file()


# Paths ------------------------------------------------------------------------


def test_paths_of_an_explicit_settings_file_resolve_against_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    settings = _write_settings(tmp_path / "shared" / "settings.yml", target="AGENTS.md")
    monkeypatch.chdir(project)

    result = CliRunner().invoke(app, ["generate", "-c", "../shared/settings.yml"])

    assert result.exit_code == 0, result.output
    assert (project / "AGENTS.md").is_file()
    assert not (settings.parent / "AGENTS.md").exists()


def test_settings_file_moves_to_config_tools_without_an_edit(tmp_path: Path) -> None:
    project = _project(tmp_path)
    flat = _write_settings(project / "eutaxis.yml", target="AGENTS.md")
    nested = project / "config" / "tools" / "eutaxis.yml"
    nested.parent.mkdir(parents=True)
    flat.rename(nested)

    result = CliRunner().invoke(app, ["generate", "--root", str(project)])

    assert result.exit_code == 0, result.output
    assert (project / "AGENTS.md").is_file()


def test_retired_root_key_is_a_configuration_error(tmp_path: Path) -> None:
    project = _project(tmp_path)
    settings = _write_settings(
        project / "eutaxis.yml", target="AGENTS.md", extra="root: .\n"
    )

    result = CliRunner().invoke(app, ["generate", "--root", str(project)])

    assert result.exit_code == 2
    assert "'root', which is retired" in result.stderr
    assert "--target-project" in result.stderr
    with pytest.raises(ConfigurationError, match="retired"):
        load_config(settings)


# Skills: root and target project -------------------------------------------


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
    settings = project / "config" / "tools" / "eutaxis.yml"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        "common_sources: []\nagents: []\ntask_modules:\n"
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


def test_project_scope_install_goes_to_the_root_by_default(tmp_path: Path) -> None:
    project = _skills_project(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    result = CliRunner().invoke(
        app,
        ["skills", "install", "alpha", "--root", str(project),
         "--scope", "project", "--agent", "claude"],
        env={"HOME": str(home)},
    )

    assert result.exit_code == 0, result.output
    assert (project / ".claude" / "skills" / "alpha" / "SKILL.md").is_file()


def test_target_project_receives_project_scope_artifacts(tmp_path: Path) -> None:
    project = _skills_project(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    home = tmp_path / "home"
    home.mkdir()

    result = CliRunner().invoke(
        app,
        ["skills", "install", "alpha", "--root", str(project), "--scope", "project",
         "--agent", "claude", "--target-project", str(other)],
        env={"HOME": str(home)},
    )

    assert result.exit_code == 0, result.output
    assert (other / ".claude" / "skills" / "alpha" / "SKILL.md").is_file()
    assert not (project / ".claude").exists()


def test_unknown_skill_is_a_usage_error_without_traceback(tmp_path: Path) -> None:
    project = _skills_project(tmp_path)

    result = CliRunner().invoke(
        app, ["skills", "show", "absent", "--root", str(project)]
    )

    assert result.exit_code == 2
    assert "Unknown skill: 'absent'" in result.stderr
    assert result.exception is None or isinstance(result.exception, SystemExit)


# Commands: root -------------------------------------------------------------


def _project_command(folder: Path) -> None:
    source = folder / ".eutaxis" / "commands" / "local-only.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "---\nname: local-only\ndescription: Project command.\n"
        "invocation: [user]\nfailure-mode: visible\n"
        "action:\n  kind: shell\n  template: \"true\"\n---\nbody\n",
        encoding="utf-8",
    )


def test_commands_list_reads_the_project_layer_of_the_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _project_command(project)
    home = tmp_path / "home"
    home.mkdir()

    explicit = CliRunner().invoke(
        app, ["commands", "list", "--root", str(project)], env={"HOME": str(home)}
    )
    current = CliRunner().invoke(
        app, ["commands", "list"], env={"HOME": str(home), "EUTAXIS_ROOT": str(project)}
    )

    assert explicit.exit_code == 0, explicit.output
    assert "local-only (project)" in explicit.stdout
    assert current.stdout == explicit.stdout


# Clean memory: confirmation -------------------------------------------------


def _seed_memory(home: Path, project: Path) -> Path:
    memory = home / ".claude" / "projects" / encode_project_slug(project) / "memory"
    memory.mkdir(parents=True)
    (memory / "note.md").write_text("note\n", encoding="utf-8")
    return memory


def _clean_memory(home: Path, project: Path, *flags: str, **kwargs):
    return CliRunner().invoke(
        app,
        ["ops", "clean-memory", "--agent", "claude", "--root", str(project), *flags],
        env={"HOME": str(home)},
        **kwargs,
    )


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


def test_clean_memory_without_terminal_and_without_yes_stops(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    memory = _seed_memory(home, project)

    result = _clean_memory(home, project)

    assert result.exit_code == 2
    assert "Pass --yes" in result.stderr
    assert (memory / "note.md").is_file()


def test_clean_memory_with_yes_deletes_without_asking(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    memory = _seed_memory(home, project)

    result = _clean_memory(home, project, "--yes")

    assert result.exit_code == 0, result.output
    assert "Removed 1 file(s)" in result.stdout
    assert not (memory / "note.md").exists()


@pytest.mark.parametrize(("answer", "deleted"), [("y\n", True), ("n\n", False)])
def test_clean_memory_asks_on_a_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: str, deleted: bool
) -> None:
    monkeypatch.setattr(_cli_options, "stdin_is_terminal", lambda: True)
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    memory = _seed_memory(home, project)

    result = _clean_memory(home, project, input=answer)

    assert result.exit_code == (0 if deleted else 1), result.output
    assert "Delete these 1 file(s)?" in result.stdout
    assert (memory / "note.md").exists() is not deleted
    assert ("Nothing deleted." in result.stdout) is not deleted


# Exit statuses ----------------------------------------------------------------


def test_generate_budget_overflow_exits_1_and_dry_run_exits_0(tmp_path: Path) -> None:
    project = _project(tmp_path)
    settings = _write_settings(project / "eutaxis.yml", target="AGENTS.md")

    dry_run = CliRunner().invoke(app, ["generate", "--root", str(project), "--dry-run"])
    settings.write_text(
        settings.read_text(encoding="utf-8") + "max_bytes: 1\n", encoding="utf-8"
    )
    over = CliRunner().invoke(app, ["generate", "--root", str(project), "--dry-run"])

    assert dry_run.exit_code == 0, dry_run.output
    assert over.exit_code == 1
    assert "over the 1-byte budget" in over.stderr


def test_invalid_settings_file_exits_2(tmp_path: Path) -> None:
    (tmp_path / "eutaxis.yml").write_text("agents: 3\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["generate", "--dry-run"])

    assert result.exit_code == 2
    assert "agents must be a list" in result.stderr


def test_environment_failure_exits_3(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(typer.Exit) as excinfo:
        exit_with_error(OSError("filesystem unavailable"))

    assert excinfo.value.exit_code == 3
    assert "filesystem unavailable" in capsys.readouterr().err


def test_init_scaffolds_the_settings_file_into_the_root(tmp_path: Path) -> None:
    first = CliRunner().invoke(
        app, ["init", "--template", "codex-project", "-r", str(tmp_path)]
    )
    second = CliRunner().invoke(
        app, ["init", "--template", "codex-project", "-r", str(tmp_path)]
    )

    assert first.exit_code == 0, first.output
    assert (tmp_path / "eutaxis.yml").is_file()
    assert second.exit_code == 2
    assert "--force" in second.stderr


def test_scan_walks_the_folder_given_with_dir(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "instructions").mkdir(parents=True)
    (project / "instructions" / "rules.md").write_text("# Rules\n", encoding="utf-8")
    _write_settings(project / "eutaxis.yml", target="AGENTS.md")
    settings = project / "eutaxis.yml"
    settings.write_text(
        settings.read_text(encoding="utf-8").replace(
            "  - rules.md", "  - instructions/rules.md"
        ),
        encoding="utf-8",
    )
    (project / "drafts").mkdir()
    (project / "drafts" / "stray.md").write_text("# Stray\n", encoding="utf-8")

    default = CliRunner().invoke(app, ["scan", "--root", str(project)])
    walked = CliRunner().invoke(
        app, ["scan", "--root", str(project), "--dir", str(project / "drafts")]
    )

    assert default.exit_code == 0, default.output
    assert walked.exit_code == 1
    assert "stray.md" in walked.stdout


# Retired names ------------------------------------------------------------------


@pytest.mark.parametrize(
    "arguments",
    [
        ["commands", "list", "--project", "."],
        ["skills", "sync", "--project", "."],
        ["skills", "install", "all", "--project", "."],
        ["ops", "clean-memory", "--agent", "claude", "--project", ".", "--dry-run"],
        ["init", "--target", "."],
        ["init", "-t", "."],
        ["generate", "-n"],
    ],
)
def test_retired_option_names_are_rejected(arguments: list[str]) -> None:
    result = CliRunner().invoke(app, arguments)

    assert result.exit_code == 2
    assert "No such option" in result.output


def test_retired_names_are_absent_from_help() -> None:
    for arguments in (
        ["init", "--help"],
        ["ops", "clean-memory", "--help"],
        ["skills", "sync", "--help"],
        ["commands", "install", "--help"],
        ["generate", "--help"],
    ):
        result = CliRunner().invoke(app, arguments)
        assert result.exit_code == 0, result.output
        assert "--root" in result.stdout
        assert "--project " not in result.stdout
        assert "--target " not in result.stdout
        assert "-n " not in result.stdout
