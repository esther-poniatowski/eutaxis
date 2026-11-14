from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

import eutaxis.cli as cli_module
from eutaxis.cli import app
from eutaxis.generate import (
    ConfigurationError,
    InstructionGenerator,
    MarkdownAssembler,
    SourceFile,
    SourceNotFoundError,
    load_config,
)
from eutaxis.instructions import DeclarationResolutionError, RejectedLabelError
from tests.test_external_acquisition import _write_contract
from tests.test_external_resolution import MANIFEST, RULE, _context


def test_load_config_supports_existing_agent_instructions_shape(tmp_path: Path) -> None:
    source = tmp_path / "docs" / "rules.md"
    source.parent.mkdir()
    source.write_text("# Rules\n\nUse the project style.\n", encoding="utf-8")

    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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


def test_explicit_root_supports_global_instruction_outputs(tmp_path: Path) -> None:
    project = tmp_path / "project"
    codex_home = tmp_path / ".codex"
    project.mkdir()
    codex_home.mkdir()
    (project / "shared.md").write_text("# Shared\n\nRead current files.\n", encoding="utf-8")

    config = tmp_path / "global-instructions.yml"
    config.write_text(
        f"""
_schema: eutaxis:configuration@1
common_sources:
  - shared.md
agents:
  - name: global-codex
    target: {codex_home / "AGENTS.md"}
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_config(config, root=project)
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
    (tmp_path / "eutaxis.yml").write_text(
        """
_schema: eutaxis:configuration@1
common_sources:
  - rules.md
agents:
  - name: codex
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_config(tmp_path / "eutaxis.yml")
    report = list(InstructionGenerator(loaded).diff_report())

    assert len(report) == 1
    assert report[0][0].name == "codex"
    assert report[0][2] is True


def test_missing_source_raises(tmp_path: Path) -> None:
    (tmp_path / "eutaxis.yml").write_text(
        """
_schema: eutaxis:configuration@1
common_sources:
  - missing.md
agents:
  - name: codex
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_config(tmp_path / "eutaxis.yml")

    with pytest.raises(SourceNotFoundError):
        InstructionGenerator(loaded).generate_all()


def test_duplicate_agent_names_raise(tmp_path: Path) -> None:
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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


def test_task_modules_router_disabled_by_flag(tmp_path: Path) -> None:
    """The list is still parsed (for `eutaxis skills`) but the router section is omitted."""
    (tmp_path / "rules.md").write_text("# Rules\n\nAlways.\n", encoding="utf-8")
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
common_sources:
  - rules.md
task_modules_router_enabled: false
task_modules:
  - id: programming
    title: Programming
    path: /modules/programming.md
    trigger: when writing source code
    description: Covers typed code.
agents:
  - name: codex
    target: AGENTS.md
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_config(config)
    output = InstructionGenerator(loaded).generate_all()["codex"]
    # Cumulative file: no router section.
    assert "Task modules" not in output
    assert "/modules/programming.md" not in output
    # Config object: list is still populated for downstream consumers.
    assert [m.id for m in loaded.task_modules] == ["programming"]


def test_duplicate_task_module_id_raises(tmp_path: Path) -> None:
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
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
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        """
_schema: eutaxis:configuration@1
common_sources:
  - path: docs/rules.md
    heading_offset: -1
agents: []
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="heading_offset"):
        load_config(config)


def _rejected_label_workspace(tmp_path: Path, *, strict: bool | None) -> Path:
    (tmp_path / "rules.md").write_text(
        "# Rules\n\n**keep**:\n\n✓ Keep.\n\n**3d-plots**:\n\n✓ Plot.\n\n"
        "```\n**Fenced**:\n```\n",
        encoding="utf-8",
    )
    strict_line = "" if strict is None else f"strict_rule_labels: {str(strict).lower()}\n"
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        "_schema: eutaxis:configuration@1\n"
        f"common_sources:\n  - rules.md\n{strict_line}"
        "agents:\n  - name: codex\n    target: AGENTS.md\n",
        encoding="utf-8",
    )
    return config


def test_rejected_labels_lists_each_rejected_line(tmp_path: Path) -> None:
    config = _rejected_label_workspace(tmp_path, strict=None)

    rejected = InstructionGenerator(load_config(config)).rejected_labels()

    assert [(path.name, item.line_number) for path, item in rejected] == [
        ("rules.md", 7)
    ]
    assert rejected[0][1].message == (
        "rejected label line '**3d-plots**:': a label must start with a lowercase letter"
    )


def test_generate_cli_warns_on_rejected_label_and_writes(tmp_path: Path) -> None:
    config = _rejected_label_workspace(tmp_path, strict=None)

    result = CliRunner().invoke(app, ["generate", "-c", str(config)])

    assert result.exit_code == 0, result.output
    assert f"warning: {tmp_path / 'rules.md'}:7: rejected label line" in result.stderr
    assert "**Fenced**" not in result.stderr
    assert (tmp_path / "AGENTS.md").is_file()


def test_generate_plan_reports_drift_and_cumulative_budgets(tmp_path: Path) -> None:
    (tmp_path / "rules.md").write_text(
        "# Rules\n\n**purpose**:\n\nNew.\n",
        encoding="utf-8",
    )
    (tmp_path / "project.md").write_text("# Project\n", encoding="utf-8")
    target = tmp_path / "AGENTS.md"
    target.write_text("# Rules\n\nOld.\n", encoding="utf-8")
    index_target = tmp_path / "rule-index.md"
    index_target.write_text("# Old index\n", encoding="utf-8")
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        "_schema: eutaxis:configuration@1\n"
        "common_sources:\n  - rules.md\n"
        "instruction_chains:\n"
        "  - name: codex-project\n"
        "    agent: codex\n"
        "    sources: [project.md]\n"
        "    max_bytes: 10000\n"
        "rule_index_enabled: true\n"
        "rule_index_target:\n"
        "  path: rule-index.md\n"
        "agents:\n"
        "  - name: codex\n"
        "    max_bytes: 10000\n"
        "    target: AGENTS.md\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["generate", "-c", str(config), "--dry-run", "--plan"],
    )

    assert result.exit_code == 0, result.output
    assert "[UPDATE   ] codex" in result.output
    assert "+3/-1 lines" in result.output
    assert "[UPDATE   ] rule-index" in result.output
    assert "[CHAIN    ] codex-project" in result.output
    assert target.read_text(encoding="utf-8") == "# Rules\n\nOld.\n"
    assert index_target.read_text(encoding="utf-8") == "# Old index\n"
    assert result.output.rstrip().endswith("[COMMAND  ] complete")


def test_plan_and_check_report_resolved_records_and_completion(
    tmp_path: Path,
) -> None:
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="resolution",
        declaration_files=(
            ("declarations/rule.yaml", RULE),
            ("declarations/manifest.yaml", MANIFEST),
        ),
    )
    config = tmp_path / "eutaxis.yml"
    context = _context()
    config.write_text(
        "_schema: eutaxis:configuration@2\n"
        "common_sources:\n"
        "  - declaration:\n"
        "      module: purpose\n"
        f"      acquisition_manifest: {manifest_path}\n"
        f"      acquisition_lock: {lock_path}\n"
        "      composition_manifest: resolution/manifest\n"
        "      context:\n"
        f"        context.available: {str(context['context.available']).lower()}\n"
        f"        resolution.enabled: {str(context['resolution.enabled']).lower()}\n"
        "agents:\n"
        "  - name: codex\n"
        "    target: AGENTS.md\n",
        encoding="utf-8",
    )
    runner = CliRunner()

    plan = runner.invoke(
        app,
        [
            "generate",
            "--root",
            str(tmp_path),
            "-c",
            str(config),
            "--dry-run",
            "--plan",
        ],
    )

    assert plan.exit_code == 0, plan.output
    assert (
        "[SELECT   ] purpose <= resolution/manifest [cumulative, project, "
        "AGENTS.md, sha256:"
        in plan.output
    )
    assert "  - resolution/purpose" in plan.output
    assert "**purpose**:" in InstructionGenerator(load_config(config)).generate_all()[
        "codex"
    ]
    assert plan.output.rstrip().endswith("[COMMAND  ] complete")
    assert not (tmp_path / "AGENTS.md").exists()

    generated = runner.invoke(
        app,
        ["generate", "--root", str(tmp_path), "-c", str(config)],
    )
    assert generated.exit_code == 0, generated.output
    checked = runner.invoke(
        app,
        ["check", "--root", str(tmp_path), "-c", str(config)],
    )

    assert checked.exit_code == 0, checked.output
    assert "  - resolution/purpose" in checked.output
    assert checked.output.rstrip().endswith("[COMMAND  ] complete")


def test_plan_reports_failed_command_without_selected_records(tmp_path: Path) -> None:
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="resolution",
        declaration_files=(
            ("declarations/rule.yaml", RULE),
            ("declarations/manifest.yaml", MANIFEST),
        ),
    )
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        "_schema: eutaxis:configuration@2\n"
        "common_sources:\n"
        "  - declaration:\n"
        "      module: purpose\n"
        f"      acquisition_manifest: {manifest_path}\n"
        f"      acquisition_lock: {lock_path}\n"
        "      composition_manifest: resolution/manifest\n"
        "      context:\n"
        "        context.available: true\n"
        "        resolution.enabled: false\n"
        "agents:\n"
        "  - name: codex\n"
        "    target: AGENTS.md\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "generate",
            "--root",
            str(tmp_path),
            "-c",
            str(config),
            "--dry-run",
            "--plan",
        ],
    )

    assert result.exit_code == 1
    assert "Declaration resolution 'resolution/manifest' failed" in result.stderr
    assert "[COMMAND  ] failed" in result.stderr
    assert "[SELECT" not in result.output


def test_version_one_rejects_declaration_sources(tmp_path: Path) -> None:
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        "_schema: eutaxis:configuration@1\n"
        "common_sources:\n"
        "  - declaration:\n"
        "      module: core\n"
        "      acquisition_manifest: declarations/acquisition.yaml\n"
        "      acquisition_lock: declarations/acquisition.lock.json\n"
        "      composition_manifest: example/core\n"
        "      context: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="configuration@2"):
        load_config(config)


@pytest.mark.parametrize(
    "replacement, message",
    [
        ("      module: 3\n", "non-empty string"),
        ("      acquisition_manifest: ../acquisition.yaml\n", "command root"),
        ("      misspelled: true\n", "unknown fields"),
    ],
)
def test_declaration_source_rejects_malformed_fields(
    tmp_path: Path,
    replacement: str,
    message: str,
) -> None:
    config = tmp_path / "eutaxis.yml"
    fields = (
        "      module: core\n"
        "      acquisition_manifest: declarations/acquisition.yaml\n"
        "      acquisition_lock: declarations/acquisition.lock.json\n"
        "      composition_manifest: example/core\n"
        "      context: {}\n"
    )
    if "module:" in replacement:
        fields = fields.replace("      module: core\n", replacement)
    elif "acquisition_manifest:" in replacement:
        fields = fields.replace(
            "      acquisition_manifest: declarations/acquisition.yaml\n",
            replacement,
        )
    else:
        fields += replacement
    config.write_text(
        "_schema: eutaxis:configuration@2\n"
        "common_sources:\n"
        "  - declaration:\n"
        + fields,
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match=message):
        load_config(config)


def test_unfiltered_report_excludes_sources_of_disabled_agents(tmp_path: Path) -> None:
    (tmp_path / "rules.md").write_text("# Rules\n", encoding="utf-8")
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        "_schema: eutaxis:configuration@2\n"
        "common_sources: [rules.md]\n"
        "agents:\n"
        "  - name: enabled\n"
        "    target: AGENTS.md\n"
        "  - name: disabled\n"
        "    enabled: false\n"
        "    target: DISABLED.md\n"
        "    sources:\n"
        "      - declaration:\n"
        "          module: hidden\n"
        "          acquisition_manifest: absent.yaml\n"
        "          acquisition_lock: absent.lock.json\n"
        "          composition_manifest: hidden/manifest\n"
        "          context: {}\n",
        encoding="utf-8",
    )

    generator = InstructionGenerator(load_config(config))

    assert generator.declaration_resolution_report() == []
    assert generator.generate_all() == {"enabled": "# Rules\n"}


def test_report_excludes_common_source_without_selected_artifact(
    tmp_path: Path,
) -> None:
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        "_schema: eutaxis:configuration@2\n"
        "common_sources:\n"
        "  - declaration:\n"
        "      module: unused\n"
        "      acquisition_manifest: absent.yaml\n"
        "      acquisition_lock: absent.lock.json\n"
        "      composition_manifest: unused/manifest\n"
        "      context: {}\n"
        "agents: []\n",
        encoding="utf-8",
    )

    generator = InstructionGenerator(load_config(config))

    assert generator.declaration_resolution_report() == []


def test_report_includes_common_source_used_by_standalone_rule_index(
    tmp_path: Path,
) -> None:
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="resolution",
        declaration_files=(
            ("declarations/rule.yaml", RULE),
            ("declarations/manifest.yaml", MANIFEST),
        ),
    )
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        "_schema: eutaxis:configuration@2\n"
        "common_sources:\n"
        "  - declaration:\n"
        "      module: purpose\n"
        f"      acquisition_manifest: {manifest_path}\n"
        f"      acquisition_lock: {lock_path}\n"
        "      composition_manifest: resolution/manifest\n"
        "      context:\n"
        "        context.available: true\n"
        "        resolution.enabled: true\n"
        "rule_index_enabled: true\n"
        "rule_index_target:\n"
        "  path: rule-index.md\n"
        "agents: []\n",
        encoding="utf-8",
    )

    generator = InstructionGenerator(load_config(config))

    reports = generator.declaration_resolution_report()
    assert len(reports) == 1
    assert reports[0][1].selection.records == ("resolution/purpose",)
    assert generator.render_standalone_rule_index() is not None
    assert generator.standalone_rule_index_declarations() == ("resolution/purpose",)


def test_standalone_index_excludes_agent_only_structured_records(
    tmp_path: Path,
) -> None:
    private_rule = RULE.replace(
        b"id: resolution/purpose", b"id: resolution/private"
    )
    private_manifest = MANIFEST.replace(
        b"id: resolution/manifest", b"id: resolution/private-manifest"
    ).replace(
        b"declarations: [resolution/purpose]",
        b"declarations: [resolution/private]",
    )
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="resolution",
        declaration_files=(
            ("declarations/rule.yaml", RULE),
            ("declarations/manifest.yaml", MANIFEST),
            ("declarations/private-rule.yaml", private_rule),
            ("declarations/private-manifest.yaml", private_manifest),
        ),
    )
    context = _context()
    common_source = {
        "declaration": {
            "module": "purpose",
            "acquisition_manifest": manifest_path,
            "acquisition_lock": lock_path,
            "composition_manifest": "resolution/manifest",
            "context": context,
        }
    }
    private_source = {
        "declaration": {
            "module": "private",
            "acquisition_manifest": manifest_path,
            "acquisition_lock": lock_path,
            "composition_manifest": "resolution/private-manifest",
            "context": context,
        }
    }
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        yaml.safe_dump(
            {
                "_schema": "eutaxis:configuration@2",
                "common_sources": [common_source],
                "rule_index_enabled": True,
                "rule_index_target": {"path": "rule-index.md"},
                "agents": [
                    {
                        "name": "codex",
                        "target": "AGENTS.md",
                        "sources": [private_source],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    generator = InstructionGenerator(load_config(config))

    reports = generator.declaration_resolution_report()
    rendered = generator.render_standalone_rule_index()

    assert {resolved.selection.records for _source, resolved in reports} == {
        ("resolution/purpose",),
        ("resolution/private",),
    }
    assert rendered is not None
    assert "purpose" in rendered[1]
    assert "private" not in rendered[1]
    assert generator.standalone_rule_index_declarations() == ("resolution/purpose",)


def test_one_generator_binds_report_and_output_to_one_candidate(
    tmp_path: Path,
) -> None:
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="resolution",
        declaration_files=(
            ("declarations/rule.yaml", RULE),
            ("declarations/manifest.yaml", MANIFEST),
        ),
    )
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        "_schema: eutaxis:configuration@2\n"
        "common_sources:\n"
        "  - declaration:\n"
        "      module: purpose\n"
        f"      acquisition_manifest: {manifest_path}\n"
        f"      acquisition_lock: {lock_path}\n"
        "      composition_manifest: resolution/manifest\n"
        "      context:\n"
        "        context.available: true\n"
        "        resolution.enabled: true\n"
        "agents:\n"
        "  - name: codex\n"
        "    target: AGENTS.md\n",
        encoding="utf-8",
    )
    generator = InstructionGenerator(load_config(config))
    _source, resolved = generator.declaration_resolution_report()[0]
    (tmp_path / "declarations" / "rule.yaml").write_text(
        "changed after resolution\n", encoding="utf-8"
    )

    assert generator.generate_all()["codex"].encode() == resolved.content
    with pytest.raises(DeclarationResolutionError):
        InstructionGenerator(load_config(config)).generate_all()


def test_plan_maps_operational_failure_to_failed_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "rules.md").write_text("# Rules\n", encoding="utf-8")
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        "_schema: eutaxis:configuration@1\n"
        "common_sources: [rules.md]\n"
        "agents:\n"
        "  - name: codex\n"
        "    target: AGENTS.md\n",
        encoding="utf-8",
    )

    def fail_diff(_self: InstructionGenerator, _name: str) -> str:
        raise OSError("planted diff failure")

    monkeypatch.setattr(InstructionGenerator, "unified_diff", fail_diff)
    result = CliRunner().invoke(
        app,
        ["generate", "-c", str(config), "--dry-run", "--plan"],
    )

    assert result.exit_code == 2
    assert "planted diff failure" in result.stderr
    assert "[COMMAND  ] failed" in result.stderr
    assert "[COMMAND  ] complete" not in result.output


def test_report_output_failure_uses_failed_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "rules.md").write_text("# Rules\n", encoding="utf-8")
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        "_schema: eutaxis:configuration@1\n"
        "common_sources: [rules.md]\n"
        "agents:\n"
        "  - name: codex\n"
        "    target: AGENTS.md\n",
        encoding="utf-8",
    )
    diagnostics: list[str] = []

    def fail_stdout(message: object = None, *, err: bool = False, **_kwargs) -> None:
        if err:
            diagnostics.append(str(message))
            return
        raise OSError("planted output failure")

    monkeypatch.setattr(cli_module.typer, "echo", fail_stdout)
    result = CliRunner().invoke(
        app,
        ["generate", "-c", str(config), "--dry-run", "--plan"],
    )

    assert result.exit_code == 2
    assert diagnostics == ["Error: planted output failure", "[COMMAND  ] failed"]


def test_check_fails_for_stale_standalone_rule_index(tmp_path: Path) -> None:
    (tmp_path / "rules.md").write_text(
        "# Rules\n\n**purpose**:\n\nCurrent.\n", encoding="utf-8"
    )
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        "_schema: eutaxis:configuration@1\n"
        "common_sources:\n  - rules.md\n"
        "rule_index_enabled: true\n"
        "rule_index_target:\n"
        "  path: rule-index.md\n"
        "agents:\n"
        "  - name: codex\n"
        "    target: AGENTS.md\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    generated = runner.invoke(app, ["generate", "-c", str(config)])
    assert generated.exit_code == 0, generated.output
    (tmp_path / "rule-index.md").write_text("# Stale index\n", encoding="utf-8")

    result = runner.invoke(app, ["check", "-c", str(config)])

    assert result.exit_code == 1
    assert "[OK      ] codex" in result.output
    assert "[OUTDATED] rule-index" in result.output
    assert result.output.rstrip().endswith("[COMMAND  ] complete")


def test_check_reports_current_standalone_rule_index(tmp_path: Path) -> None:
    (tmp_path / "rules.md").write_text(
        "# Rules\n\n**purpose**:\n\nCurrent.\n", encoding="utf-8"
    )
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(
        "_schema: eutaxis:configuration@1\n"
        "common_sources:\n  - rules.md\n"
        "rule_index_enabled: true\n"
        "rule_index_target:\n"
        "  path: rule-index.md\n"
        "agents:\n"
        "  - name: codex\n"
        "    target: AGENTS.md\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    generated = runner.invoke(app, ["generate", "-c", str(config)])
    assert generated.exit_code == 0, generated.output

    result = runner.invoke(app, ["check", "-c", str(config)])

    assert result.exit_code == 0, result.output
    assert "[OK      ] rule-index" in result.output


def test_strict_rule_labels_fails_generate_before_writing(tmp_path: Path) -> None:
    config = _rejected_label_workspace(tmp_path, strict=True)

    result = CliRunner().invoke(app, ["generate", "-c", str(config)])

    assert result.exit_code == 1
    assert "strict_rule_labels is set" in result.stderr
    assert f"{tmp_path / 'rules.md'}:7" in result.stderr
    assert not (tmp_path / "AGENTS.md").exists()
    with pytest.raises(RejectedLabelError):
        InstructionGenerator(load_config(config)).write_all()


def test_strict_rule_labels_fails_check(tmp_path: Path) -> None:
    config = _rejected_label_workspace(tmp_path, strict=False)
    assert CliRunner().invoke(app, ["generate", "-c", str(config)]).exit_code == 0
    assert CliRunner().invoke(app, ["check", "-c", str(config)]).exit_code == 0
    strict = _rejected_label_workspace(tmp_path, strict=True)

    result = CliRunner().invoke(app, ["check", "-c", str(strict)])

    assert result.exit_code == 1
    assert "strict_rule_labels is set" in result.stderr


def test_strict_rule_labels_must_be_boolean(tmp_path: Path) -> None:
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        '_schema: eutaxis:configuration@1\nstrict_rule_labels: "yes"\nagents: []\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="strict_rule_labels"):
        load_config(config)
