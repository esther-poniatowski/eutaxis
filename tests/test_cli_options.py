"""Tests of the command-line conventions: root, configuration file, paths, exit
statuses, confirmations and retired names.

Hodegos locates the root and the configuration file. The root is the folder
given by ``--root``, else by ``EUTAXIS_ROOT``, else the nearest folder, from the
current one upward, holding ``eutaxis.yml`` at one of its places, else the
current folder. The places of a folder are the folder itself, its ``.config/``,
and the folders that its ``hodegos.yml`` declares; two places holding a file
is an error. A named ``--config`` is read from the current folder.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from eutaxis import _cli_options
from eutaxis.cli import app
from eutaxis.commands.cli_errors import exit_with_error
from eutaxis.instructions import (
    CONFIG_SCHEMA,
    ConfigurationError,
    discover_configuration,
    discover_root,
    load_config,
)
from eutaxis.ops import encode_project_slug

SHARED = Path("shared") / "eutaxis.yml"
"""Configuration file kept in a folder that the declaration of the root lists."""

DECLARATION = "_schema: hodegos:configuration@1\nfolders:\n  - shared\n"
"""Declaration ``hodegos.yml`` of a project keeping its configuration in ``shared/``."""


def _write_settings(path: Path, *, target: str, extra: str = "") -> Path:
    """Write a configuration file whose one agent copies ``rules.md`` to ``target``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "_schema: eutaxis:configuration@1\n"
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


def _declare_shared(project: Path) -> None:
    """Write the declaration ``hodegos.yml`` that lists ``shared/``."""
    project.mkdir(parents=True, exist_ok=True)
    (project / "hodegos.yml").write_text(DECLARATION, encoding="utf-8")


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "rules.md").write_text("# Rules\n", encoding="utf-8")
    return project


# Settings lookup ----------------------------------------------------------


def test_discovery_reads_the_root_and_dot_config(tmp_path: Path) -> None:
    flat = tmp_path / "a" / "eutaxis.yml"
    hidden = tmp_path / "b" / ".config" / "eutaxis.yml"
    for path in (flat, hidden):
        path.parent.mkdir(parents=True)
        path.write_text("{}\n", encoding="utf-8")

    assert discover_configuration(tmp_path / "a") == (flat.parent, flat)
    assert discover_configuration(tmp_path / "b") == (tmp_path / "b", hidden)


def test_discovery_reads_a_folder_that_the_root_declares(tmp_path: Path) -> None:
    _declare_shared(tmp_path)
    (tmp_path / SHARED).parent.mkdir()
    (tmp_path / SHARED).write_text("{}\n", encoding="utf-8")

    assert discover_configuration(tmp_path) == (tmp_path, tmp_path / SHARED)


def test_discovery_ignores_an_undeclared_folder(tmp_path: Path) -> None:
    (tmp_path / SHARED).parent.mkdir()
    (tmp_path / SHARED).write_text("{}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="no configuration"):
        discover_configuration(tmp_path)


def test_discovery_refuses_two_places_and_names_both(tmp_path: Path) -> None:
    _declare_shared(tmp_path)
    shared = tmp_path / SHARED
    flat = tmp_path / "eutaxis.yml"
    shared.parent.mkdir()
    shared.write_text("{}\n", encoding="utf-8")
    flat.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError) as excinfo:
        discover_configuration(tmp_path)

    assert str(shared) in str(excinfo.value)
    assert str(flat) in str(excinfo.value)
    assert excinfo.value.exit_code == 2


def test_discovery_returns_a_named_file_without_lookup(tmp_path: Path) -> None:
    (tmp_path / "eutaxis.yml").write_text("{}\n", encoding="utf-8")
    explicit = tmp_path / "elsewhere.yml"
    explicit.write_text("{}\n", encoding="utf-8")

    assert discover_configuration(tmp_path, explicit)[1] == explicit


def test_discovery_rejects_a_named_file_that_does_not_exist(tmp_path: Path) -> None:
    (tmp_path / "eutaxis.yml").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="absent.yml"):
        discover_configuration(tmp_path, tmp_path / "absent.yml")


def test_discovery_names_the_places_when_none_holds_a_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        discover_configuration(tmp_path)

    message = str(excinfo.value)
    assert str(tmp_path) in message
    assert "write eutaxis.yml at the root, in .config/, or in a folder that " in message
    assert "hodegos.yml declares" in message


def test_invalid_declaration_is_a_configuration_error(tmp_path: Path) -> None:
    (tmp_path / "hodegos.yml").write_text("folders: [shared]\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="hodegos.yml"):
        discover_root(tmp_path)
    for arguments in (["generate"], ["commands", "list"], ["init"]):
        result = CliRunner().invoke(app, [*arguments, "--root", str(tmp_path)])
        assert result.exit_code == 2, (arguments, result.output)
        assert "hodegos.yml" in result.stderr
        assert result.exception is None or isinstance(result.exception, SystemExit)


def test_former_settings_file_name_is_not_read(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_settings(project / "agent-instructions.yaml", target="AGENTS.md")

    result = CliRunner().invoke(app, ["generate", "--root", str(project)])

    assert result.exit_code == 2
    assert "eutaxis.yml" in result.stderr
    assert not (project / "AGENTS.md").exists()


def test_two_settings_files_fail_the_command_with_status_2(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_settings(project / ".config" / "eutaxis.yml", target="A.md")
    _write_settings(project / "eutaxis.yml", target="B.md")

    result = CliRunner().invoke(app, ["generate", "--root", str(project)])

    assert result.exit_code == 2
    assert "two places hold a configuration" in result.stderr
    assert not (project / "A.md").exists()
    assert not (project / "B.md").exists()


def test_missing_settings_file_fails_with_status_2() -> None:
    result = CliRunner().invoke(app, ["check"])

    assert result.exit_code == 2
    assert "hodegos.yml declares" in result.stderr


def test_absent_explicit_config_fails_with_status_2(tmp_path: Path) -> None:
    (tmp_path / "eutaxis.yml").write_text("{}\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["list", "-c", "absent.yml"])

    assert result.exit_code == 2
    assert str(tmp_path / "absent.yml") in result.stderr


# Root resolution -----------------------------------------------------------


def test_discover_root_prefers_option_then_variable_then_ancestor(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    nested = project / "a" / "b"
    nested.mkdir(parents=True)
    _declare_shared(project)
    (project / SHARED).parent.mkdir()
    (project / SHARED).write_text("{}\n", encoding="utf-8")
    other = tmp_path / "other"
    other.mkdir()

    environ = {"EUTAXIS_ROOT": str(other)}
    assert discover_root(Path("x"), cwd=nested, environ=environ) == nested / "x"
    assert discover_root(None, cwd=nested, environ=environ) == other
    assert discover_root(None, cwd=nested, environ={}) == project
    assert discover_root(None, cwd=other, environ={}) == other
    assert discover_root(None, cwd=nested, environ={"EUTAXIS_ROOT": ""}) == project


def test_load_config_without_root_resolves_against_the_folder_of_the_file(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    settings = _write_settings(project / "eutaxis.yml", target="AGENTS.md")

    assert load_config(settings).root == project


def test_generate_runs_from_a_subfolder_of_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    _declare_shared(project)
    _write_settings(project / SHARED, target="AGENTS.md")
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


@pytest.mark.parametrize("place", [Path(".config") / "eutaxis.yml", SHARED])
def test_settings_file_moves_between_places_without_an_edit(
    tmp_path: Path, place: Path
) -> None:
    project = _project(tmp_path)
    _declare_shared(project)
    flat = _write_settings(project / "eutaxis.yml", target="AGENTS.md")
    (project / place).parent.mkdir(parents=True)
    flat.rename(project / place)

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


# Format identifier --------------------------------------------------------


def _write_without_schema(path: Path, *, first: str = "") -> Path:
    """Write the configuration of ``_write_settings`` with ``first`` in place of ``_schema``."""
    _write_settings(path, target="AGENTS.md")
    body = path.read_text(encoding="utf-8").split("\n", 1)[1]
    path.write_text(first + body, encoding="utf-8")
    return path


def test_configuration_declaring_its_identifier_loads(tmp_path: Path) -> None:
    project = _project(tmp_path)
    first = _write_settings(project / "eutaxis.yml", target="AGENTS.md")
    later = _write_without_schema(project / "later.yml")
    later.write_text(
        later.read_text(encoding="utf-8") + "_schema: eutaxis:configuration@1\n",
        encoding="utf-8",
    )

    assert CONFIG_SCHEMA == "eutaxis:configuration@2"
    assert [agent.name for agent in load_config(first).agents] == ["codex"]
    assert [agent.name for agent in load_config(later, root=project).agents] == [
        "codex"
    ]


def test_configuration_without_identifier_is_a_configuration_error(
    tmp_path: Path,
) -> None:
    settings = _write_without_schema(_project(tmp_path) / "eutaxis.yml")

    with pytest.raises(ConfigurationError) as excinfo:
        load_config(settings)

    assert "declares no key '_schema'" in str(excinfo.value)
    assert "_schema: eutaxis:configuration@2" in str(excinfo.value)


@pytest.mark.parametrize(
    "value",
    [
        "eutaxis:configuration@3",
        "eutaxis:configuration@10",
        "ktisma:configuration@1",
        "eutaxis:skill-sync-manifest@1",
        "1",
    ],
)
def test_configuration_with_other_identifier_is_a_configuration_error(
    tmp_path: Path, value: str
) -> None:
    settings = _write_without_schema(
        _project(tmp_path) / "eutaxis.yml", first=f"_schema: {value}\n"
    )

    with pytest.raises(ConfigurationError) as excinfo:
        load_config(settings)

    assert f"declares _schema: {value}" in str(excinfo.value)
    assert "_schema: eutaxis:configuration@2" in str(excinfo.value)


def test_generate_without_identifier_exits_2_naming_the_value(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    _write_without_schema(project / "eutaxis.yml")

    result = CliRunner().invoke(app, ["generate", "--root", str(project)])

    assert result.exit_code == 2
    assert "_schema: eutaxis:configuration@2" in result.stderr
    assert not (project / "AGENTS.md").exists()


# Skills: root and target project -------------------------------------------


def _skills_project(tmp_path: Path) -> Path:
    """Create a project whose configuration file sits in a declared ``shared/``."""
    project = tmp_path / "project"
    module = project / "instructions" / "alpha.md"
    module.parent.mkdir(parents=True)
    module.write_text(
        "---\nname: alpha\ndescription: alpha description\n"
        "invocation: [model, user]\nfailure-mode: visible\n---\nbody\n",
        encoding="utf-8",
    )
    _declare_shared(project)
    settings = project / SHARED
    settings.parent.mkdir(parents=True)
    settings.write_text(
        "_schema: eutaxis:configuration@1\n"
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
    (tmp_path / "eutaxis.yml").write_text(
        "_schema: eutaxis:configuration@1\nagents: 3\n", encoding="utf-8"
    )

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
