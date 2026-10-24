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
    fm.setdefault("invocation", "[model, user]")
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


def _add_budget_config(
    path: Path, *, entrypoint_max: int, unit_max: int, rule: str = "alpha-rule"
) -> None:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["skill_entrypoint_max_bytes"] = entrypoint_max
    payload["skill_loading_units"] = [
        {
            "name": "alpha-task",
            "max_bytes": unit_max,
            "members": [{"module": "alpha", "rules": [rule]}],
        }
    ]
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
    assert all(set(s.invocation) == {"model", "user"} for s in sources)


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
        "---\nname: incomplete\ndescription: x\ninvocation: [model, user]\n---\nbody\n",
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
        invocation="[user]",
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
    # alpha defaults to invocation: [model, user]; beta is user-only.
    assert "invocation: model/user" in result.output
    assert "invocation: user" in result.output


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
    # invocation includes 'model': no disable-model-invocation in the rendered SKILL.md.
    assert "disable-model-invocation" not in result.output


def test_skills_budget_reports_entrypoints_and_declared_loading_units(
    tmp_path: Path,
) -> None:
    root = tmp_path
    _write_module(
        root / "instructions" / "rules" / "alpha.md",
        name="alpha",
        body="**alpha-rule**:\n\n✓ Apply alpha.\n",
        disclosure="progressive",
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
                "trigger": "on alpha",
            }
        ],
    )
    _add_budget_config(config_path, entrypoint_max=4096, unit_max=8192)

    result = CliRunner().invoke(
        app,
        ["skills", "budget", "-c", str(config_path), "--agent", "codex"],
    )

    assert result.exit_code == 0, result.output
    assert "entrypoint alpha@codex" in result.output
    assert "loading-unit alpha-task@codex" in result.output
    assert "alpha/rules/alpha-rule.md" in result.output


def test_skills_budget_exits_one_when_an_entrypoint_exceeds_its_limit(
    tmp_path: Path,
) -> None:
    root = tmp_path
    _write_module(
        root / "instructions" / "rules" / "alpha.md",
        name="alpha",
        body="**alpha-rule**:\n\n✓ Apply alpha.\n",
        disclosure="progressive",
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
                "trigger": "on alpha",
            }
        ],
    )
    _add_budget_config(config_path, entrypoint_max=10, unit_max=8192)

    result = CliRunner().invoke(
        app,
        ["skills", "budget", "-c", str(config_path), "--agent", "codex"],
    )

    assert result.exit_code == 1
    assert "[OVER] entrypoint alpha@codex" in result.output


def test_skills_budget_exits_one_when_a_loading_unit_exceeds_its_limit(
    tmp_path: Path,
) -> None:
    root = tmp_path
    _write_module(
        root / "instructions" / "rules" / "alpha.md",
        name="alpha",
        body="**alpha-rule**:\n\n✓ Apply alpha.\n",
        disclosure="progressive",
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
                "trigger": "on alpha",
            }
        ],
    )
    _add_budget_config(config_path, entrypoint_max=4096, unit_max=10)

    result = CliRunner().invoke(
        app,
        ["skills", "budget", "-c", str(config_path), "--agent", "codex"],
    )

    assert result.exit_code == 1
    assert "[OVER] loading-unit alpha-task@codex" in result.output


def test_skills_budget_fails_when_passing_batches_exceed_composite_route(
    tmp_path: Path,
) -> None:
    root = tmp_path
    modules = []
    for name in ("alpha", "beta"):
        _write_module(
            root / "instructions" / "rules" / f"{name}.md",
            name=name,
            body=f"**{name}-rule**:\n\n✓ Apply {name}.\n",
            disclosure="progressive",
        )
        modules.append(
            {
                "id": name,
                "title": name.title(),
                "path": f"instructions/rules/{name}.md",
                "trigger": f"on {name}",
            }
        )
    config_path = tmp_path / "agent-instructions.yaml"
    _write_config(config_path, root=root, modules=modules)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    payload["skill_entrypoint_max_bytes"] = 4096
    payload["skill_loading_units"] = [
        {
            "name": f"{name}-batch",
            "max_bytes": 8192,
            "members": [{"module": name, "rules": [f"{name}-rule"]}],
        }
        for name in ("alpha", "beta")
    ]
    payload["skill_loading_units"].append(
        {
            "name": "combined-route",
            "max_bytes": 10,
            "includes": ["alpha-batch", "beta-batch"],
        }
    )
    config_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["skills", "budget", "-c", str(config_path), "--agent", "codex"],
    )

    assert result.exit_code == 1
    assert "[OK  ] loading-unit alpha-batch@codex" in result.output
    assert "[OK  ] loading-unit beta-batch@codex" in result.output
    assert "[OVER] loading-unit combined-route@codex" in result.output


def test_skills_budget_composes_loading_units_without_counting_a_file_twice(
    tmp_path: Path,
) -> None:
    root = tmp_path
    _write_module(
        root / "instructions" / "rules" / "alpha.md",
        name="alpha",
        body="**alpha-rule**:\n\n✓ Apply alpha.\n",
        disclosure="progressive",
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
                "trigger": "on alpha",
            }
        ],
    )
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    payload["skill_entrypoint_max_bytes"] = 4096
    payload["skill_loading_units"] = [
        {
            "name": "alpha-base",
            "max_bytes": 8192,
            "members": [{"module": "alpha", "rules": ["alpha-rule"]}],
        },
        {
            "name": "alpha-route",
            "max_bytes": 8192,
            "includes": ["alpha-base"],
            "members": [{"module": "alpha", "rules": ["alpha-rule"]}],
        },
    ]
    config_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["skills", "budget", "-c", str(config_path), "--agent", "codex"],
    )

    assert result.exit_code == 0, result.output
    lines = [
        line
        for line in result.output.splitlines()
        if "loading-unit alpha-" in line
    ]
    assert len(lines) == 2
    assert lines[0].split("[")[-1] == lines[1].split("[")[-1]


def test_skills_budget_rejects_a_loading_unit_composition_cycle(
    tmp_path: Path,
) -> None:
    root = tmp_path
    _write_module(root / "instructions" / "rules" / "alpha.md", name="alpha")
    config_path = tmp_path / "agent-instructions.yaml"
    _write_config(
        config_path,
        root=root,
        modules=[
            {
                "id": "alpha",
                "title": "Alpha",
                "path": "instructions/rules/alpha.md",
                "trigger": "on alpha",
            }
        ],
    )
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    payload["skill_loading_units"] = [
        {"name": "first", "max_bytes": 1000, "includes": ["second"]},
        {"name": "second", "max_bytes": 1000, "includes": ["first"]},
    ]
    config_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["skills", "budget", "-c", str(config_path), "--agent", "codex"],
    )

    assert result.exit_code == 1
    assert "loading units form a cycle" in result.output


def test_skills_budget_rejects_a_rule_not_emitted_by_the_skill(
    tmp_path: Path,
) -> None:
    root = tmp_path
    _write_module(
        root / "instructions" / "rules" / "alpha.md",
        name="alpha",
        body="**alpha-rule**:\n\n✓ Apply alpha.\n",
        disclosure="progressive",
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
                "trigger": "on alpha",
            }
        ],
    )
    _add_budget_config(
        config_path,
        entrypoint_max=4096,
        unit_max=8192,
        rule="missing-rule",
    )

    result = CliRunner().invoke(
        app,
        ["skills", "budget", "-c", str(config_path), "--agent", "codex"],
    )

    assert result.exit_code == 1
    assert "missing-rule" in result.output


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


def _diff_workspace(tmp_path: Path, body: str, **fm) -> tuple[Path, Path, Path]:
    """Write one module and its configuration; return config, module and HOME."""
    module = tmp_path / "instructions" / "rules" / "epsilon.md"
    _write_module(module, name="epsilon", body=body, **fm)
    config_path = tmp_path / "agent-instructions.yaml"
    _write_config(
        config_path,
        root=tmp_path,
        modules=[
            {
                "id": "epsilon",
                "title": "Epsilon",
                "path": "instructions/rules/epsilon.md",
                "trigger": "v",
            }
        ],
    )
    home = tmp_path / "home"
    home.mkdir()
    return config_path, module, home


def _skills(home: Path, *args: str):
    return CliRunner().invoke(
        app, ["skills", *args, "--agent", "claude"], env={"HOME": str(home)}
    )


def test_skills_diff_exits_zero_when_every_artifact_is_current(
    tmp_path: Path,
) -> None:
    config_path, _, home = _diff_workspace(tmp_path, "rule body\n")
    assert _skills(home, "install", "all", "-c", str(config_path)).exit_code == 0

    result = _skills(home, "diff", "-c", str(config_path))

    assert result.exit_code == 0, result.output
    assert "[OK      ] epsilon@claude" in result.output


@pytest.mark.parametrize("drift", ["outdated", "modified", "missing", "removed"])
def test_skills_diff_exits_one_on_drift(tmp_path: Path, drift: str) -> None:
    body = "# Rules\n\n**alpha**:\n\n✓ Do A.\n\n**beta**:\n\n✓ Do B.\n"
    config_path, module, home = _diff_workspace(
        tmp_path, body, disclosure="progressive"
    )
    skill_dir = home / ".claude" / "skills" / "epsilon"
    if drift != "missing":
        assert _skills(home, "install", "all", "-c", str(config_path)).exit_code == 0
    if drift == "outdated":
        module.write_text(
            module.read_text(encoding="utf-8").replace("Do A.", "Do A now."),
            encoding="utf-8",
        )
    elif drift == "modified":
        (skill_dir / "rules" / "alpha.md").write_text("edited\n", encoding="utf-8")
    elif drift == "removed":
        module.write_text(
            module.read_text(encoding="utf-8").split("**beta**")[0], encoding="utf-8"
        )

    result = _skills(home, "diff", "-c", str(config_path))

    assert result.exit_code == 1, result.output
    assert "[OUTDATED] epsilon@claude" in result.output
    if drift == "removed":
        assert "rules/beta.md (removed)" in result.output
