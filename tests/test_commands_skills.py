"""Tests for the config-driven Skill loader and the `eutaxis skills` CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from eutaxis.cli import app
from eutaxis.commands import (
    CommandRenderError,
    load_from_instruction_config,
)
from eutaxis.instructions.exceptions import ConfigurationError


def _write_module(path: Path, *, name: str, body: str = "rule body\n", **fm) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fm.setdefault("description", f"{name} description")
    fm.setdefault("regime", "model-invoked")
    fm.setdefault("failure-mode", "visible")
    fm_text = "".join(f"{k}: {v}\n" for k, v in fm.items())
    path.write_text(f"---\nname: {name}\n{fm_text}---\n{body}", encoding="utf-8")


def _write_config(path: Path, root: Path, modules: list[dict]) -> None:
    payload = {
        "root": str(root),
        "common_sources": [],
        "task_modules": modules,
        "agents": [],
    }
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


def test_load_from_instruction_config_returns_sources(tmp_path: Path) -> None:
    root = tmp_path
    _write_module(root / "instructions" / "rules" / "first.md", name="first")
    _write_module(root / "instructions" / "rules" / "second.md", name="second")

    config_path = tmp_path / "agent-instructions.yaml"
    _write_config(
        config_path,
        root=root,
        modules=[
            {
                "id": "first",
                "title": "First",
                "path": "instructions/rules/first.md",
                "trigger": "on first",
            },
            {
                "id": "second",
                "title": "Second",
                "path": "instructions/rules/second.md",
                "trigger": "on second",
            },
        ],
    )

    sources = load_from_instruction_config(config_path)
    assert [s.name for s in sources] == ["first", "second"]
    assert all(s.layer == "config" for s in sources)
    assert all(s.regime == "model-invoked" for s in sources)


def test_load_from_instruction_config_raises_on_missing_file(tmp_path: Path) -> None:
    root = tmp_path
    config_path = tmp_path / "agent-instructions.yaml"
    _write_config(
        config_path,
        root=root,
        modules=[
            {
                "id": "ghost",
                "title": "Ghost",
                "path": "instructions/rules/ghost.md",
                "trigger": "never",
            }
        ],
    )

    # Either the instruction-config loader raises while resolving
    # frontmatter descriptions for a missing file, or the Skill loader
    # raises with a "missing file" message. Both signal the same fault.
    with pytest.raises((CommandRenderError, ConfigurationError)):
        load_from_instruction_config(config_path)


def test_load_from_instruction_config_raises_on_missing_failure_mode(
    tmp_path: Path,
) -> None:
    root = tmp_path
    path = root / "instructions" / "rules" / "incomplete.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\nname: incomplete\ndescription: x\nregime: model-invoked\n---\nbody\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "agent-instructions.yaml"
    _write_config(
        config_path,
        root=root,
        modules=[
            {
                "id": "incomplete",
                "title": "Incomplete",
                "path": "instructions/rules/incomplete.md",
                "trigger": "x",
            }
        ],
    )

    with pytest.raises(CommandRenderError, match="failure-mode"):
        load_from_instruction_config(config_path)


def test_skills_list_cli_reports_each_source(tmp_path: Path) -> None:
    root = tmp_path
    _write_module(root / "instructions" / "rules" / "alpha.md", name="alpha")
    _write_module(
        root / "instructions" / "rules" / "beta.md",
        name="beta",
        regime="user-invoked",
        **{"failure-mode": "silent", "required-visibility": "pre-action"},
    )
    config_path = tmp_path / "agent-instructions.yaml"
    _write_config(
        config_path,
        root=root,
        modules=[
            {
                "id": "alpha",
                "title": "Alpha",
                "path": "instructions/rules/alpha.md",
                "trigger": "x",
            },
            {
                "id": "beta",
                "title": "Beta",
                "path": "instructions/rules/beta.md",
                "trigger": "y",
            },
        ],
    )

    runner = CliRunner()
    result = runner.invoke(app, ["skills", "list", "-c", str(config_path)])
    assert result.exit_code == 0, result.output
    assert "alpha" in result.output
    assert "beta" in result.output
    assert "model-invoked" in result.output
    assert "user-invoked" in result.output


def test_skills_show_renders_for_claude(tmp_path: Path) -> None:
    root = tmp_path
    _write_module(root / "instructions" / "rules" / "gamma.md", name="gamma")
    config_path = tmp_path / "agent-instructions.yaml"
    _write_config(
        config_path,
        root=root,
        modules=[
            {
                "id": "gamma",
                "title": "Gamma",
                "path": "instructions/rules/gamma.md",
                "trigger": "z",
            }
        ],
    )

    runner = CliRunner()
    result = runner.invoke(
        app, ["skills", "show", "gamma", "-c", str(config_path), "--agent", "claude"]
    )
    assert result.exit_code == 0, result.output
    assert "--- SKILL.md ---" in result.output
    assert "name: gamma" in result.output
    # model-invoked: no disable-model-invocation in the rendered SKILL.md.
    assert "disable-model-invocation" not in result.output


def test_skills_install_writes_artifact(tmp_path: Path) -> None:
    root = tmp_path
    _write_module(root / "instructions" / "rules" / "delta.md", name="delta")
    config_path = tmp_path / "agent-instructions.yaml"
    _write_config(
        config_path,
        root=root,
        modules=[
            {
                "id": "delta",
                "title": "Delta",
                "path": "instructions/rules/delta.md",
                "trigger": "w",
            }
        ],
    )

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    runner = CliRunner()
    # Redirect HOME so the installer writes into the test sandbox.
    result = runner.invoke(
        app,
        ["skills", "install", "delta", "-c", str(config_path), "--agent", "claude"],
        env={"HOME": str(fake_home)},
    )
    assert result.exit_code == 0, result.output
    installed = fake_home / ".claude" / "skills" / "delta" / "SKILL.md"
    assert installed.is_file()
    content = installed.read_text(encoding="utf-8")
    assert "name: delta" in content
    assert "disable-model-invocation" not in content
