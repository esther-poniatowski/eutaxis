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
    description: ""
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


def test_reference_docs_section_is_appended(tmp_path: Path) -> None:
    (tmp_path / "rules.md").write_text("# Rules\n\nAlways.\n", encoding="utf-8")
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
common_sources:
  - rules.md
reference_docs_intro: |
  Consult these authoritative docs. Local first, GitHub fallback.
reference_docs:
  - id: vitruv
    title: Vitruv
    local_path: ~/work/projects/vitruv
    github_url: https://github.com/example/vitruv
    trigger: for architecture and design tasks
    description: Design principles.
  - id: hermeneia
    title: Hermeneia
    local_path: ~/work/projects/hermeneia
    github_url: https://github.com/example/hermeneia
    trigger: for prose writing
agents:
  - name: codex
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_config(config)
    output = InstructionGenerator(loaded).generate_all()["codex"]

    assert "## Reference docs\n" in output
    assert "Consult these authoritative docs." in output
    assert (
        "- **Vitruv.** Consult for architecture and design tasks. "
        "Design principles."
    ) in output
    assert "  - Local (primary): `~/work/projects/vitruv`" in output
    assert (
        "  - GitHub (fallback): <https://github.com/example/vitruv>"
    ) in output
    assert "- **Hermeneia.** Consult for prose writing." in output


def test_reference_docs_section_omitted_when_empty(tmp_path: Path) -> None:
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
    assert "Reference docs" not in output


def test_duplicate_reference_doc_id_raises(tmp_path: Path) -> None:
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
reference_docs:
  - id: vitruv
    title: Vitruv
    local_path: ~/a
    github_url: https://example.com/a
    trigger: trig
  - id: vitruv
    title: Other
    local_path: ~/b
    github_url: https://example.com/b
    trigger: trig
agents: []
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="reference_doc"):
        load_config(config)


def test_reference_doc_missing_required_field_raises(tmp_path: Path) -> None:
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
reference_docs:
  - id: vitruv
    title: Vitruv
    local_path: ~/a
    trigger: trig
agents: []
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="github_url"):
        load_config(config)


def test_rule_index_scans_labels_and_groups_by_file(tmp_path: Path) -> None:
    (tmp_path / "globals.md").write_text(
        "# Globals\n\n**precedence**:\n\n ✓ Project wins.\n\n"
        "**re-read**:\n\n ✓ Read before edit.\n",
        encoding="utf-8",
    )
    (tmp_path / "prog.md").write_text(
        "---\ndescription: Programming labels.\n---\n\n"
        "# Programming\n\n**design-axes**:\n\n ✓ Design.\n\n"
        "**annotations**:\n\n ✓ Annotate.\n",
        encoding="utf-8",
    )
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
common_sources:
  - globals.md
task_modules:
  - id: programming
    title: Programming
    path: prog.md
    trigger: when coding
rule_index_enabled: true
rule_index_intro: |
  Use these labels for self-check.
agents:
  - name: codex
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    output = InstructionGenerator(load_config(config)).generate_all()["codex"]

    assert "## Rule index\n" in output
    assert "Use these labels for self-check." in output
    assert "- **globals**: precedence, re-read" in output
    assert "- **prog**: design-axes, annotations" in output


def test_rule_index_omitted_when_disabled(tmp_path: Path) -> None:
    (tmp_path / "globals.md").write_text(
        "# Globals\n\n**precedence**:\n\n ✓ Project wins.\n",
        encoding="utf-8",
    )
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
common_sources:
  - globals.md
agents:
  - name: codex
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    output = InstructionGenerator(load_config(config)).generate_all()["codex"]
    assert "Rule index" not in output


def test_rule_index_omitted_when_no_labels_found(tmp_path: Path) -> None:
    (tmp_path / "globals.md").write_text(
        "# Globals\n\nJust prose, no labels.\n",
        encoding="utf-8",
    )
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
common_sources:
  - globals.md
rule_index_enabled: true
agents:
  - name: codex
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    output = InstructionGenerator(load_config(config)).generate_all()["codex"]
    assert "Rule index" not in output


def test_rule_index_externalized_when_target_set(tmp_path: Path) -> None:
    (tmp_path / "globals.md").write_text(
        "# Globals\n\n**precedence**:\n\n ✓ Project wins.\n",
        encoding="utf-8",
    )
    (tmp_path / "prog.md").write_text(
        "# Programming\n\n**design-axes**:\n\n ✓ Design.\n",
        encoding="utf-8",
    )
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
common_sources:
  - globals.md
task_modules:
  - id: programming
    title: Programming
    path: ../prog.md
    trigger: when coding
    description: ""
rule_index_enabled: true
rule_index_intro: |
  Full label listing.
rule_index_pointer: |
  See `generated/rule-index.md` for the full label index.
rule_index_target:
  path: generated/rule-index.md
  header: |
    # Rule index
    Auto-generated. Do not edit.
agents:
  - name: codex
    target: generated/AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_config(config)
    gen = InstructionGenerator(loaded)
    paths = gen.write_all()

    index_path = tmp_path / "generated" / "rule-index.md"
    agents_path = tmp_path / "generated" / "AGENTS.md"
    assert agents_path in paths
    assert index_path in paths

    agent_text = agents_path.read_text(encoding="utf-8")
    assert "## Rule index\n" in agent_text
    assert "See `generated/rule-index.md`" in agent_text
    # Full body must NOT be in the agent output
    assert "- **globals**:" not in agent_text
    assert "- **prog**:" not in agent_text
    # Intro is the full-body intro, not the pointer text — also not inline
    assert "Full label listing." not in agent_text

    index_text = index_path.read_text(encoding="utf-8")
    assert index_text.startswith("# Rule index")
    assert "## Rule index" in index_text
    assert "Full label listing." in index_text
    assert "- **globals**: precedence" in index_text
    assert "- **prog**: design-axes" in index_text


def test_rule_index_inline_when_no_target(tmp_path: Path) -> None:
    (tmp_path / "globals.md").write_text(
        "# Globals\n\n**precedence**:\n\n ✓ Project wins.\n",
        encoding="utf-8",
    )
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
common_sources:
  - globals.md
rule_index_enabled: true
rule_index_intro: |
  Inline body.
agents:
  - name: codex
    target: generated/AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_config(config)
    gen = InstructionGenerator(loaded)
    output = gen.generate_all()["codex"]

    assert "## Rule index\n" in output
    assert "Inline body." in output
    assert "- **globals**: precedence" in output


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


def test_task_module_description_falls_back_to_frontmatter(
    tmp_path: Path,
) -> None:
    (tmp_path / "prog.md").write_text(
        "---\n"
        "description: How to write source code.\n"
        "---\n\n"
        "# Programming\n",
        encoding="utf-8",
    )
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
task_modules:
  - id: programming
    title: Programming
    path: prog.md
    trigger: when coding
agents:
  - name: codex
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_config(config)
    output = InstructionGenerator(loaded).generate_all()["codex"]

    assert "How to write source code." in output


def test_config_description_overrides_frontmatter(tmp_path: Path) -> None:
    (tmp_path / "prog.md").write_text(
        "---\n"
        "description: Frontmatter wording.\n"
        "---\n\n"
        "# Programming\n",
        encoding="utf-8",
    )
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
task_modules:
  - id: programming
    title: Programming
    path: prog.md
    trigger: when coding
    description: Config wording.
agents:
  - name: codex
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    output = InstructionGenerator(load_config(config)).generate_all()["codex"]

    assert "Config wording." in output
    assert "Frontmatter wording." not in output


def test_task_module_description_missing_everywhere_raises(
    tmp_path: Path,
) -> None:
    (tmp_path / "prog.md").write_text(
        "# Programming\n\nNo frontmatter.\n",
        encoding="utf-8",
    )
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        """
task_modules:
  - id: programming
    title: Programming
    path: prog.md
    trigger: when coding
agents:
  - name: codex
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="programming"):
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
