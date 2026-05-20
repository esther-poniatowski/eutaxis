from __future__ import annotations

from pathlib import Path

import pytest

from eutaxis.scaffold import ScaffoldError, scaffold_workspace


def test_scaffold_workspace_copies_codex_project_template(tmp_path: Path) -> None:
    written = scaffold_workspace(tmp_path, template="codex-project")

    expected = {
        tmp_path / "AGENTS.md",
        tmp_path / "agent-instructions.yaml",
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
