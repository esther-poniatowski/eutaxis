"""Tests for generated targets and cumulative instruction-chain budgets."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from eutaxis.cli import app
from eutaxis.generate import (
    BudgetExceededError,
    ConfigurationError,
    InstructionGenerator,
    SourceNotFoundError,
    load_config,
)
from eutaxis.instructions import InstructionChainBudgetExceededError


def test_budget_exceeded_blocks_generation(tmp_path: Path) -> None:
    (tmp_path / "rules.md").write_text("# Rules\n\n" + "x" * 200 + "\n", encoding="utf-8")
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
common_sources:
  - rules.md
agents:
  - name: codex
    max_bytes: 50
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_config(config)
    with pytest.raises(BudgetExceededError) as exc_info:
        InstructionGenerator(loaded).generate_all()

    assert exc_info.value.agent_name == "codex"
    assert exc_info.value.limit == 50
    assert exc_info.value.size > 50


def test_budget_enforced_per_agent_default_applies(tmp_path: Path) -> None:
    (tmp_path / "rules.md").write_text("# Rules\n\n" + "x" * 200 + "\n", encoding="utf-8")
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
max_bytes: 80
common_sources:
  - rules.md
agents:
  - name: codex
    target: AGENTS.md
  - name: lax
    max_bytes: 10000
    target: LAX.md
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_config(config)
    generator = InstructionGenerator(loaded)

    with pytest.raises(BudgetExceededError) as exc_info:
        generator.generate_all(agent_name="codex")
    assert exc_info.value.limit == 80

    output = generator.generate_all(agent_name="lax")["lax"]
    assert "Rules" in output


def test_budget_report_yields_size_and_limit(tmp_path: Path) -> None:
    (tmp_path / "rules.md").write_text("# Rules\n\nAlways.\n", encoding="utf-8")
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
common_sources:
  - rules.md
agents:
  - name: codex
    max_bytes: 32768
    target: AGENTS.md
  - name: free
    target: FREE.md
""".lstrip(),
        encoding="utf-8",
    )

    reports = list(InstructionGenerator(load_config(config)).budget_report())
    by_name = {entry[0].name: entry for entry in reports}

    assert by_name["codex"][2] == 32768
    assert by_name["codex"][1] > 0
    assert by_name["free"][2] is None


def test_budget_can_be_disabled(tmp_path: Path) -> None:
    (tmp_path / "rules.md").write_text("# Rules\n\n" + "x" * 200 + "\n", encoding="utf-8")
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
common_sources:
  - rules.md
agents:
  - name: codex
    max_bytes: 50
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    output = InstructionGenerator(load_config(config)).generate_all(
        enforce_budget=False
    )
    assert "Rules" in output["codex"]


def _write_instruction_chain_config(tmp_path: Path, limit: int) -> Path:
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        f"""
common_sources:
  - rules.md
instruction_chains:
  - name: codex-project
    agent: codex
    sources:
      - project/AGENTS.md
    max_bytes: {limit}
agents:
  - name: codex
    target: generated/AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )
    return config


def test_instruction_chain_budget_accepts_exact_limit_and_rejects_next_byte(
    tmp_path: Path,
) -> None:
    (tmp_path / "rules.md").write_text("# Rules\n\nAlways.\n", encoding="utf-8")
    (tmp_path / "project").mkdir()
    (tmp_path / "project" / "AGENTS.md").write_text(
        "# Project\n\nSpecialize.\n", encoding="utf-8"
    )
    config = _write_instruction_chain_config(tmp_path, 10000)
    measured = list(
        InstructionGenerator(load_config(config)).instruction_chain_budget_report()
    )[0][1]
    rendered_size = len(
        InstructionGenerator(load_config(config))
        .generate_all(enforce_budget=False)["codex"]
        .encode("utf-8")
    )
    project_size = len((tmp_path / "project" / "AGENTS.md").read_bytes())
    assert measured == rendered_size + 2 + project_size

    config = _write_instruction_chain_config(tmp_path, measured)
    exact = InstructionGenerator(load_config(config))
    assert exact.generate_all()["codex"].startswith("# Rules")

    config = _write_instruction_chain_config(tmp_path, measured - 1)
    with pytest.raises(InstructionChainBudgetExceededError) as exc_info:
        InstructionGenerator(load_config(config)).write_all()
    assert exc_info.value.chain_name == "codex-project"
    assert exc_info.value.size == measured
    assert exc_info.value.limit == measured - 1
    assert not (tmp_path / "generated" / "AGENTS.md").exists()


def test_check_cli_reports_instruction_chain_budget(tmp_path: Path) -> None:
    (tmp_path / "rules.md").write_text("# Rules\n\nAlways.\n", encoding="utf-8")
    (tmp_path / "project").mkdir()
    (tmp_path / "project" / "AGENTS.md").write_text(
        "# Project\n\nSpecialize.\n", encoding="utf-8"
    )
    config = _write_instruction_chain_config(tmp_path, 10000)
    InstructionGenerator(load_config(config)).write_all()

    result = CliRunner().invoke(app, ["check", "-c", str(config)])

    assert result.exit_code == 0, result.output
    assert "[CHAIN   ] codex-project" in result.output
    assert "codex + 1 project file(s)" in result.output


def test_instruction_chain_budget_reports_missing_project_source(
    tmp_path: Path,
) -> None:
    (tmp_path / "rules.md").write_text("# Rules\n\nAlways.\n", encoding="utf-8")
    config = _write_instruction_chain_config(tmp_path, 10000)

    with pytest.raises(SourceNotFoundError, match="project/AGENTS.md"):
        InstructionGenerator(load_config(config)).generate_all()


def test_non_positive_max_bytes_raises(tmp_path: Path) -> None:
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
agents:
  - name: codex
    max_bytes: 0
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="max_bytes"):
        load_config(config)
