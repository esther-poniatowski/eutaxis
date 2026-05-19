from __future__ import annotations

from pathlib import Path

import pytest

from eutaxis.generate import (
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
