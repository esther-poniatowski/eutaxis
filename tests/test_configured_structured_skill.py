"""Exercise one configured declaration across install, route and budget commands."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from eutaxis.cli import app
from eutaxis.commands import get_adapter
from eutaxis.commands.loader import load_from_instruction_config
from eutaxis.commands.exceptions import CommandRenderError
from eutaxis.declarations import (
    plan_structured_rule_skill,
    render_structured_rule_skill,
)
from eutaxis.instructions import ConfigurationError
from tests.test_loading_unit_publication import _installed_closure_digest, _workspace
from tests.test_structured_rule_skill import _rule_pipeline


@pytest.fixture
def structured_config(tmp_path: Path):
    """Replace the Markdown dependency with an authenticated separate Skill."""
    path = _workspace(tmp_path)
    acquisition, resolution = _rule_pipeline(tmp_path)
    raw = yaml.safe_load(path.read_text())
    raw["_schema"] = "eutaxis:configuration@2"
    raw["task_modules"][1] = {
        "id": "testing",
        "title": "Testing",
        "trigger": "on testing",
        "path": "instructions/unavailable.md",
        "description": "Testing router",
        "skill_source": {
            "declaration": {
                "module": "testing",
                "acquisition_manifest": "acquisition.yaml",
                "acquisition_lock": "acquisition.lock.json",
                "composition_manifest": "oikos/complete-module-skill",
                "context": {"oikos.enabled": True, "artifact.created": True},
            }
        },
    }
    raw["skill_loading_units"][1]["members"] = [{"module": "testing"}]
    path.write_text(yaml.safe_dump(raw))
    return path, acquisition, plan_structured_rule_skill(resolution)


@pytest.mark.parametrize(
    ("host", "directory"), [("claude", ".claude"), ("codex", ".agents")]
)
def test_actual_install_route_and_budgets_share_one_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    structured_config,
    host: str,
    directory: str,
) -> None:
    """Check the installed entrypoint and route files against the CLI budget."""
    config, _, plan = structured_config
    home = tmp_path / "host"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda _cls=None: home)
    runner = CliRunner()
    options = ["-c", str(config), "--root", str(tmp_path), "--agent", host]
    install = runner.invoke(
        app, ["skills", "install", "all", *options, "--scope", "project"]
    )
    assert install.exit_code == 0, install.output
    skills = tmp_path / directory / "skills"
    expected = render_structured_rule_skill(
        plan,
        get_adapter(host),
        entrypoint_max_bytes=4096,
        artifact_max_bytes=8192,
    )
    for member in expected.files:
        assert (skills / "testing" / member.relative_path).read_text() == member.content

    for name, manifest in (
        ("style-batch", "routes/batches/style-batch.md"),
        ("section-route", "routes/section-route.md"),
    ):
        content = (skills / "workflow" / manifest).read_text()
        paths = re.findall(r"^1\. `?\[`([^`]+)`\]", content, re.M)
        assert "testing/SKILL.md" in paths
        digest = _installed_closure_digest(skills, paths)
        assert f"Closure digest: `{digest}`" in content
        report = runner.invoke(app, ["skills", "loading-unit", "show", name, *options])
        assert report.exit_code == 0, report.output
        assert f"closure-digest: {digest}" in report.output
        measured_files = [
            line.removeprefix("file: ")
            for line in report.output.splitlines()
            if line.startswith("file: ")
        ]
        byte_count = sum((skills / member).stat().st_size for member in measured_files)
        assert f"bytes: {byte_count}/" in report.output
    budget = runner.invoke(app, ["skills", "budget", *options])
    assert budget.exit_code == 0, budget.output


def test_configured_source_rejects_stale_lock(structured_config) -> None:
    """Fail closed when the selected structured source changes after locking."""
    config, _, _ = structured_config
    rule_set = config.parent / "declarations/testing.yaml"
    rule_set.write_bytes(rule_set.read_bytes() + b"\n")
    with pytest.raises(CommandRenderError, match="lock"):
        load_from_instruction_config(config)


def test_configured_source_rejects_mismatched_module(structured_config) -> None:
    """Reject a declaration bound to a different task module identifier."""
    config, _, _ = structured_config
    raw = yaml.safe_load(config.read_text())
    raw["task_modules"][1]["skill_source"]["declaration"]["module"] = "workflow"
    config.write_text(yaml.safe_dump(raw))
    with pytest.raises(ConfigurationError, match="must use the task module id"):
        load_from_instruction_config(config)


def test_configured_source_rejects_mismatched_manifest_target(structured_config) -> None:
    """Keep the installed name and loading-unit identity bound to one module."""
    config, _, _ = structured_config
    raw = yaml.safe_load(config.read_text())
    module = raw["task_modules"][1]
    module["id"] = "other-skill"
    module["skill_source"]["declaration"]["module"] = "other-skill"
    raw["skill_loading_units"][1]["members"] = [{"module": "other-skill"}]
    config.write_text(yaml.safe_dump(raw))
    with pytest.raises(CommandRenderError, match="targets 'testing'.*'other-skill'"):
        load_from_instruction_config(config)
