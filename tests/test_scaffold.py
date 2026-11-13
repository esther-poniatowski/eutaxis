from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from eutaxis.scaffold import ScaffoldError, available_templates, scaffold_workspace


def test_scaffold_workspace_copies_codex_project_template(tmp_path: Path) -> None:
    written = scaffold_workspace(tmp_path, template="codex-project")

    expected = {
        tmp_path / "AGENTS.md",
        tmp_path / "eutaxis.yml",
        tmp_path / "docs" / "instructions" / "project-overview.md",
        tmp_path / "docs" / "instructions" / "repository-layout.md",
        tmp_path / "docs" / "instructions" / "tasks" / "programming.md",
    }

    assert set(written) == expected
    assert (tmp_path / "AGENTS.md").is_file()


def test_scaffold_workspace_refuses_overwrite_without_force(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("existing\n", encoding="utf-8")

    with pytest.raises(ScaffoldError, match="Refusing to overwrite"):
        scaffold_workspace(tmp_path, template="codex-project")

    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "existing\n"


def test_scaffold_workspace_force_overwrites_existing_files(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("existing\n", encoding="utf-8")

    scaffold_workspace(tmp_path, template="codex-project", force=True)

    assert "Project Agent Instructions" in (
        tmp_path / "AGENTS.md"
    ).read_text(encoding="utf-8")


def test_scaffold_workspace_copies_multi_agent_template(tmp_path: Path) -> None:
    scaffold_workspace(tmp_path, template="multi-agent-project")

    config = (tmp_path / "eutaxis.yml").read_text(encoding="utf-8")

    assert "path: AGENTS.md" in config
    assert "path: .claude/CLAUDE.md" in config


@pytest.mark.parametrize("template", available_templates())
def test_scaffolded_configuration_declares_its_format_first(
    tmp_path: Path, template: str
) -> None:
    scaffold_workspace(tmp_path, template=template)

    raw = yaml.safe_load((tmp_path / "eutaxis.yml").read_text(encoding="utf-8"))

    assert list(raw)[0] == "_schema"
    assert raw["_schema"] == "eutaxis:configuration@2"
