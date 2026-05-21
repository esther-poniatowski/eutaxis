from __future__ import annotations

from pathlib import Path

import pytest

from eutaxis.generate import (
    BudgetExceededError,
    ConfigurationError,
    InstructionGenerator,
    MarkdownAssembler,
    SourceFile,
    SourceNotFoundError,
    load_config,
)


def test_load_config_supports_existing_agent_instructions_shape(tmp_path: Path) -> None:
    source = tmp_path / "docs" / "rules.md"
    source.parent.mkdir()
    source.write_text("# Rules\n\nUse the project style.\n", encoding="utf-8")

    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
common_sources:
  - path: docs/rules.md
agents:
  - name: codex
    target:
      path: AGENTS.md
      header: |
        # AI Agent Instructions
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_config(config)
    generator = InstructionGenerator(loaded)

    assert generator.generate_all()["codex"] == (
        "# AI Agent Instructions\n\n# Rules\n\nUse the project style.\n"
    )


def test_config_root_supports_global_instruction_outputs(tmp_path: Path) -> None:
    project = tmp_path / "project"
    codex_home = tmp_path / ".codex"
    project.mkdir()
    codex_home.mkdir()
    (project / "shared.md").write_text("# Shared\n\nRead current files.\n", encoding="utf-8")

    config = tmp_path / "global-instructions.yaml"
    config.write_text(
        f"""
root: {project}
common_sources:
  - shared.md
agents:
  - name: global-codex
    target: {codex_home / "AGENTS.md"}
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_config(config)
    paths = InstructionGenerator(loaded).write_all()

    assert paths == [codex_home / "AGENTS.md"]
    assert (codex_home / "AGENTS.md").read_text(encoding="utf-8") == (
        "# Shared\n\nRead current files.\n"
    )


def test_sections_keep_nested_content_and_strip_frontmatter() -> None:
    content = """---
tags:
  - instructions
---
# Title

Ignore this.

## Keep

Keep this.

### Child

Keep child.

## Drop

Drop this.
"""

    processed = MarkdownAssembler().process(
        content,
        SourceFile(path=Path("source.md"), sections=("Keep",), heading_offset=1),
    )

    assert processed == "### Keep\n\nKeep this.\n\n#### Child\n\nKeep child."


def test_exclude_sections_removes_nested_content() -> None:
    content = """# A

Keep.

## Secret

Drop.

### Nested

Drop nested.

## Public

Keep public.
"""

    processed = MarkdownAssembler().process(
        content,
        SourceFile(path=Path("source.md"), exclude_sections=("Secret",)),
    )

    assert "Secret" not in processed
    assert "Nested" not in processed
    assert "Public" in processed


def test_diff_report_detects_stale_output(tmp_path: Path) -> None:
    (tmp_path / "rules.md").write_text("# Rules\n\nNew.\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nOld.\n", encoding="utf-8")
    (tmp_path / "agent-instructions.yaml").write_text(
        """
common_sources:
  - rules.md
agents:
  - name: codex
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_config(tmp_path / "agent-instructions.yaml")
    report = list(InstructionGenerator(loaded).diff_report())

    assert len(report) == 1
    assert report[0][0].name == "codex"
    assert report[0][2] is True


def test_missing_source_raises(tmp_path: Path) -> None:
    (tmp_path / "agent-instructions.yaml").write_text(
        """
common_sources:
  - missing.md
agents:
  - name: codex
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_config(tmp_path / "agent-instructions.yaml")

    with pytest.raises(SourceNotFoundError):
        InstructionGenerator(loaded).generate_all()


def test_duplicate_agent_names_raise(tmp_path: Path) -> None:
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
agents:
  - name: codex
    target: AGENTS.md
  - name: codex
    target: OTHER.md
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError):
        load_config(config)


def test_string_boolean_values_raise(tmp_path: Path) -> None:
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
agents:
  - name: codex
    enabled: "false"
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="enabled"):
        load_config(config)


def test_task_modules_router_section_is_appended(tmp_path: Path) -> None:
    (tmp_path / "rules.md").write_text("# Rules\n\nAlways.\n", encoding="utf-8")
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
common_sources:
  - rules.md
task_modules_intro: |
  Load the matching task module before doing the work.
task_modules:
  - id: programming
    title: Programming
    path: /modules/programming.md
    trigger: when writing or modifying source code
    description: Covers typed code and module boundaries.
  - id: prose
    title: Prose writing
    path: /modules/prose.md
    trigger: when drafting or revising prose
agents:
  - name: codex
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_config(config)
    output = InstructionGenerator(loaded).generate_all()["codex"]

    assert "## Task modules\n" in output
    assert "Load the matching task module" in output
    assert (
        "- **Programming.** Load `/modules/programming.md` when writing or "
        "modifying source code. Covers typed code and module boundaries."
    ) in output
    assert (
        "- **Prose writing.** Load `/modules/prose.md` when drafting or "
        "revising prose."
    ) in output


def test_task_modules_router_omitted_when_empty(tmp_path: Path) -> None:
    (tmp_path / "rules.md").write_text("# Rules\n\nAlways.\n", encoding="utf-8")
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
common_sources:
  - rules.md
agents:
  - name: codex
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    output = InstructionGenerator(load_config(config)).generate_all()["codex"]
    assert "Task modules" not in output


def test_duplicate_task_module_id_raises(tmp_path: Path) -> None:
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
task_modules:
  - id: programming
    title: Programming
    path: /a.md
    trigger: trig
  - id: programming
    title: Other
    path: /b.md
    trigger: trig
agents: []
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="task_module"):
        load_config(config)


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


def test_negative_heading_offset_raises(tmp_path: Path) -> None:
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
common_sources:
  - path: docs/rules.md
    heading_offset: -1
agents: []
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="heading_offset"):
        load_config(config)
