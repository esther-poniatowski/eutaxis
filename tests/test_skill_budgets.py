"""Tests for Skill entrypoint and loading-unit budgets."""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from eutaxis.cli import app


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
