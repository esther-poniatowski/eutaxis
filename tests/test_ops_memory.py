from __future__ import annotations

from pathlib import Path

import pytest

from eutaxis.ops import clean_memory, encode_project_slug
from eutaxis.ops.exceptions import OpsError


def test_encode_project_slug_matches_observed_pattern() -> None:
    assert (
        encode_project_slug(Path("/Users/eresther/oikos"))
        == "-Users-eresther-oikos"
    )


def _seed(home: Path, project: Path) -> tuple[Path, Path]:
    slug = encode_project_slug(project)
    claude_mem = home / ".claude" / "projects" / slug / "memory"
    codex_mem = home / ".codex" / "memories"
    for d in (claude_mem, codex_mem):
        d.mkdir(parents=True)
        (d / "a.md").write_text("a", encoding="utf-8")
        (d / "b.md").write_text("b", encoding="utf-8")
    return claude_mem, codex_mem


def test_clean_memory_claude_only_for_current_project(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "proj"
    home.mkdir(); project.mkdir()
    claude_mem, codex_mem = _seed(home, project)

    result = clean_memory(agent="claude", project_root=project, home=home)
    assert sorted(p.name for p in result.removed) == ["a.md", "b.md"]
    assert not list(claude_mem.iterdir())
    # codex memory untouched
    assert {p.name for p in codex_mem.iterdir()} == {"a.md", "b.md"}


def test_clean_memory_all_wipes_every_claude_project(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "proj"
    home.mkdir(); project.mkdir()
    _seed(home, project)
    other_mem = home / ".claude" / "projects" / "-other" / "memory"
    other_mem.mkdir(parents=True)
    (other_mem / "x.md").write_text("x", encoding="utf-8")

    result = clean_memory(agent="claude", wipe_all=True, home=home, project_root=project)
    names = sorted(p.name for p in result.removed)
    assert names == ["a.md", "b.md", "x.md"]


def test_clean_memory_codex(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "proj"
    home.mkdir(); project.mkdir()
    _, codex_mem = _seed(home, project)

    result = clean_memory(agent="codex", home=home, project_root=project)
    assert sorted(p.name for p in result.removed) == ["a.md", "b.md"]
    assert not list(codex_mem.iterdir())


def test_dry_run_reports_without_deleting(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "proj"
    home.mkdir(); project.mkdir()
    claude_mem, _ = _seed(home, project)

    result = clean_memory(
        agent="claude", project_root=project, home=home, dry_run=True
    )
    assert sorted(p.name for p in result.removed) == ["a.md", "b.md"]
    # files still on disk
    assert {p.name for p in claude_mem.iterdir()} == {"a.md", "b.md"}


def test_backup_creates_sibling_directory(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "proj"
    home.mkdir(); project.mkdir()
    claude_mem, _ = _seed(home, project)

    result = clean_memory(
        agent="claude", project_root=project, home=home, backup=True
    )
    assert len(result.backup_paths) == 1
    backup = result.backup_paths[0]
    assert backup.is_dir()
    assert {p.name for p in backup.iterdir()} == {"a.md", "b.md"}
    assert not list(claude_mem.iterdir())


def test_missing_directory_is_skipped_not_error(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "proj"
    home.mkdir(); project.mkdir()
    result = clean_memory(agent="all", project_root=project, home=home)
    assert result.removed == []
    assert result.skipped  # both targets reported missing


def test_unknown_agent_raises(tmp_path: Path) -> None:
    with pytest.raises(OpsError):
        clean_memory(agent="bogus", home=tmp_path, project_root=tmp_path)
