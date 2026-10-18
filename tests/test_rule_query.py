"""Tests for the `eutaxis rule` query over modules and deployed skills."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
import yaml
from typer.testing import CliRunner

from eutaxis.cli import app

STYLE = dedent("""\
    ---
    name: style
    description: Style rules.
    invocation: [model, user]
    failure-mode: visible
    {extra}---

    # Style

    ## Register

    **short-sentences**:

    ✓ Keep sentences short.
    ✗ Do not chain clauses.

    *Exception.* Quoted text keeps its length.

    *Why the limit.* Long sentences hide their verb.

    ## Topic

    **topic-first**:

    ✓ Open on the topic.

    **3d-plots**:

    Text under a rejected label.
    """)

GLOBAL = dedent("""\
    # Verification

    **constraint-scan**:

    ✓ Scan the constraints before returning.

    **short-sentences**:

    ✓ A second definition of the same label.
    """)


@pytest.fixture
def workspace(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "src"
    (root / "tasks").mkdir(parents=True)
    (root / "global").mkdir()
    (root / "tasks" / "style.md").write_text(STYLE.format(extra=""), encoding="utf-8")
    (root / "global" / "verification.md").write_text(GLOBAL, encoding="utf-8")
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "root": str(root),
                "common_sources": [{"path": "global/verification.md"}],
                "task_modules": [
                    {
                        "id": "style",
                        "title": "Style",
                        "path": "tasks/style.md",
                        "trigger": "when writing",
                    }
                ],
                "agents": [],
            }
        ),
        encoding="utf-8",
    )
    home = tmp_path / "home"
    home.mkdir()
    return {"root": root, "config": config, "home": home}


def _run(*args: str, home: Path | None = None):
    env = {"HOME": str(home)} if home is not None else None
    return CliRunner().invoke(app, ["rule", *args], env=env)


def test_show_prints_whole_rule_with_location(workspace) -> None:
    result = _run("show", "topic-first", "-c", str(workspace["config"]), "-m", "style")
    assert result.exit_code == 0, result.output
    first = result.stdout.splitlines()[0]
    assert first.startswith("style > Style > Topic > topic-first (")
    assert first.endswith("style.md:23-25)")
    assert "✓ Open on the topic." in result.stdout
    assert "3d-plots" not in result.stdout


def test_show_part_prints_one_field(workspace) -> None:
    result = _run(
        "show",
        "short-sentences",
        "--part",
        "exception",
        "--module",
        "style",
        "-c",
        str(workspace["config"]),
    )
    assert result.exit_code == 0, result.output
    assert "[exception]" in result.stdout
    assert "*Exception.* Quoted text keeps its length." in result.stdout
    assert "✓ Keep sentences short." not in result.stdout


def test_show_missing_part_lists_available_parts(workspace) -> None:
    result = _run(
        "show", "topic-first", "--part", "exception", "-c", str(workspace["config"])
    )
    assert result.exit_code == 1
    assert "has no 'exception' part" in result.stderr
    assert "Available parts: valid." in result.stderr


def test_show_unknown_label_suggests_close_labels(workspace) -> None:
    result = _run("show", "topic-frst", "-c", str(workspace["config"]))
    assert result.exit_code == 1
    assert "Unknown rule label 'topic-frst'" in result.stderr
    assert "Close labels: topic-first." in result.stderr


def test_show_rejected_label_names_the_offending_line(workspace) -> None:
    result = _run("show", "3d-plots", "-c", str(workspace["config"]))
    assert result.exit_code == 1
    assert "lowercase letter" in result.stderr
    assert "style.md" in result.stderr


def test_show_ambiguous_label_requires_module(workspace) -> None:
    result = _run("show", "short-sentences", "-c", str(workspace["config"]))
    assert result.exit_code == 1
    assert "several modules (verification, style)" in result.stderr
    assert "--module" in result.stderr


def test_list_reports_rules_and_rejected_lines(workspace) -> None:
    result = _run("list", "-c", str(workspace["config"]))
    assert result.exit_code == 0, result.output
    rows = [line.split() for line in result.stdout.splitlines()]
    assert [row[:2] for row in rows] == [
        ["constraint-scan", "verification"],
        ["short-sentences", "verification"],
        ["short-sentences", "style"],
        ["topic-first", "style"],
    ]
    assert result.stdout.splitlines()[3].endswith("Open on the topic.")
    assert "rejected label line '**3d-plots**:'" in result.stderr


def test_list_filters_by_module(workspace) -> None:
    result = _run("list", "-c", str(workspace["config"]), "--module", "verification")
    assert result.exit_code == 0, result.output
    assert "topic-first" not in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize("disclosure", ["", "disclosure: progressive\n"])
def test_skills_dir_reads_inline_and_split_skills(workspace, disclosure: str) -> None:
    (workspace["root"] / "tasks" / "style.md").write_text(
        STYLE.format(extra=disclosure), encoding="utf-8"
    )
    home = workspace["home"]
    install = CliRunner().invoke(
        app,
        ["skills", "install", "all", "-c", str(workspace["config"]), "-a", "claude"],
        env={"HOME": str(home)},
    )
    assert install.exit_code == 0, install.output
    skills = home / ".claude" / "skills"
    (skills / "foreign").mkdir()
    (skills / "foreign" / "SKILL.md").write_text(
        "**foreign-rule**:\n\n✓ Not ours.\n", encoding="utf-8"
    )

    result = _run(
        "show", "short-sentences", "--part", "why", "--skills-dir", str(skills)
    )
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("style > Style > Register > short-sentences [why]")
    expected_file = "rules/short-sentences.md" if disclosure else "SKILL.md"
    assert expected_file in result.stdout.splitlines()[0]

    listing = _run("list", "--skills-dir", str(skills))
    assert listing.exit_code == 0, listing.output
    assert "foreign-rule" not in listing.stdout
    assert "3d-plots" in listing.stderr


def test_default_source_is_the_user_skills_dir_of_the_agent(workspace) -> None:
    home = workspace["home"]
    install = CliRunner().invoke(
        app,
        ["skills", "install", "all", "-c", str(workspace["config"])],
        env={"HOME": str(home)},
    )
    assert install.exit_code == 0, install.output

    claude = _run("show", "topic-first", home=home)
    codex = _run("show", "topic-first", "--agent", "codex", home=home)
    assert claude.exit_code == 0, claude.output
    assert codex.exit_code == 0, codex.output
    assert ".claude/skills/style/SKILL.md" in claude.stdout
    assert ".agents/skills/style/SKILL.md" in codex.stdout

    missing = _run("show", "constraint-scan", home=home)
    assert missing.exit_code == 1
    assert "query their rules with -c <config>" in missing.stderr


def test_missing_skills_dir_is_reported(tmp_path: Path) -> None:
    result = _run("list", "--skills-dir", str(tmp_path / "absent"))
    assert result.exit_code == 1
    assert "Skills directory not found" in result.stderr


def test_config_and_skills_dir_are_exclusive(workspace) -> None:
    result = _run(
        "list", "-c", str(workspace["config"]), "--skills-dir", str(workspace["home"])
    )
    assert result.exit_code == 1
    assert "cannot be combined" in result.stderr


def _section_config(workspace, entry: dict) -> Path:
    config = workspace["config"].with_name("sections.yaml")
    config.write_text(
        yaml.safe_dump(
            {"root": str(workspace["root"]), "common_sources": [entry], "agents": []}
        ),
        encoding="utf-8",
    )
    return config


def test_config_section_selection_keeps_only_selected_rules(workspace) -> None:
    config = _section_config(
        workspace, {"path": "tasks/style.md", "sections": ["Register"]}
    )

    listing = _run("list", "-c", str(config))
    shown = _run("show", "short-sentences", "-c", str(config))
    outside = _run("show", "topic-first", "-c", str(config))

    assert listing.exit_code == 0, listing.output
    assert [line.split()[0] for line in listing.stdout.splitlines()] == [
        "short-sentences"
    ]
    assert listing.stderr == ""
    assert shown.stdout.splitlines()[0].endswith("style.md:12-19)")
    assert outside.exit_code == 1
    assert "Unknown rule label 'topic-first'" in outside.stderr


def test_config_section_exclusion_drops_excluded_rules(workspace) -> None:
    config = _section_config(
        workspace, {"path": "tasks/style.md", "exclude_sections": ["Register"]}
    )

    listing = _run("list", "-c", str(config))

    assert [line.split()[0] for line in listing.stdout.splitlines()] == ["topic-first"]
    assert "style.md:27: rejected label line '**3d-plots**:'" in listing.stderr


def test_config_whole_module_entry_overrides_a_section_selection(workspace) -> None:
    config = workspace["config"].with_name("union.yaml")
    config.write_text(
        yaml.safe_dump(
            {
                "root": str(workspace["root"]),
                "common_sources": [{"path": "tasks/style.md", "sections": ["Topic"]}],
                "agents": [
                    {
                        "name": "codex",
                        "target": {"path": "AGENTS.md"},
                        "sources": [{"path": "tasks/style.md"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    listing = _run("list", "-c", str(config))

    assert [line.split()[0] for line in listing.stdout.splitlines()] == [
        "short-sentences",
        "topic-first",
    ]
