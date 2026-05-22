from __future__ import annotations

import json
from pathlib import Path

import pytest

from eutaxis.commands import (
    OwnershipError,
    get_adapter,
    install_command,
    load_sources,
    uninstall_command,
)
from eutaxis.commands.installer import diff_command
from eutaxis.commands.registry import Registry
from eutaxis.commands.rendering import (
    ENTRYPOINT_FILENAME,
    OWNED_FRONTMATTER_KEY,
    SIDECAR_FILENAME,
)


@pytest.fixture
def isolated(tmp_path: Path) -> tuple[Path, Path, Registry]:
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "proj"
    project.mkdir()
    registry = Registry(home / ".eutaxis" / "state")
    return home, project, registry


def _builtin_source(home: Path, project: Path):
    sources = load_sources(home=home, project_root=project)
    return next(s for s in sources if s.name == "clean-memory")


def test_install_claude_writes_skill_directory(isolated) -> None:
    home, project, registry = isolated
    src = _builtin_source(home, project)
    adapter = get_adapter("claude")

    outcome = install_command(
        src, adapter, scope="user",
        project_root=project, home=home, registry=registry,
    )
    assert outcome.action == "created"
    target = outcome.path
    assert target == home / ".claude" / "skills" / "clean-memory"
    assert target.is_dir()
    assert (target / ENTRYPOINT_FILENAME).is_file()
    assert (target / SIDECAR_FILENAME).is_file()
    # Claude artifact has no agents/openai.yaml.
    assert not (target / "agents" / "openai.yaml").exists()

    sidecar = json.loads((target / SIDECAR_FILENAME).read_text())
    assert sidecar["adapter"] == "claude"
    skill_md = (target / ENTRYPOINT_FILENAME).read_text()
    assert OWNED_FRONTMATTER_KEY in skill_md


def test_install_codex_writes_skill_directory_with_openai_yaml(isolated) -> None:
    home, project, registry = isolated
    src = _builtin_source(home, project)
    adapter = get_adapter("codex")

    outcome = install_command(
        src, adapter, scope="user",
        project_root=project, home=home, registry=registry,
    )
    assert outcome.action == "created"
    target = outcome.path
    assert target == home / ".agents" / "skills" / "clean-memory"
    assert (target / ENTRYPOINT_FILENAME).is_file()
    assert (target / "agents" / "openai.yaml").is_file()
    assert (target / SIDECAR_FILENAME).is_file()


def test_install_then_unchanged_then_uninstall(isolated) -> None:
    home, project, registry = isolated
    src = _builtin_source(home, project)
    adapter = get_adapter("claude")

    first = install_command(
        src, adapter, scope="user",
        project_root=project, home=home, registry=registry,
    )
    assert first.action == "created"

    second = install_command(
        src, adapter, scope="user",
        project_root=project, home=home, registry=registry,
    )
    assert second.action == "unchanged"

    record = registry.find(name="clean-memory", adapter="claude", scope="user")
    assert record is not None and record.path == first.path

    out = uninstall_command(
        name="clean-memory", adapter=adapter, scope="user",
        project_root=project, home=home, registry=registry,
    )
    assert out.action == "removed"
    assert not first.path.exists()
    assert registry.find(name="clean-memory", adapter="claude", scope="user") is None


def test_project_scope_installs_both_adapters(isolated) -> None:
    home, project, registry = isolated
    src = _builtin_source(home, project)

    claude_outcome = install_command(
        src, get_adapter("claude"), scope="project",
        project_root=project, home=home, registry=registry,
    )
    codex_outcome = install_command(
        src, get_adapter("codex"), scope="project",
        project_root=project, home=home, registry=registry,
    )
    assert claude_outcome.path == project / ".claude" / "skills" / "clean-memory"
    assert codex_outcome.path == project / ".agents" / "skills" / "clean-memory"


def test_refuses_to_overwrite_non_eutaxis_directory(isolated) -> None:
    home, project, registry = isolated
    src = _builtin_source(home, project)
    adapter = get_adapter("claude")

    target_dir = adapter.artifact_dir(
        "clean-memory", "user", home=home, project_root=project
    )
    target_dir.mkdir(parents=True)
    (target_dir / ENTRYPOINT_FILENAME).write_text(
        "---\nname: hand\ndescription: hand-rolled\n---\nuser content\n",
        encoding="utf-8",
    )

    with pytest.raises(OwnershipError):
        install_command(
            src, adapter, scope="user",
            project_root=project, home=home, registry=registry,
        )

    # force=True must bypass the guard.
    outcome = install_command(
        src, adapter, scope="user",
        project_root=project, home=home, registry=registry, force=True,
    )
    assert outcome.action in {"created", "updated"}


def test_ownership_via_frontmatter_marker_when_sidecar_missing(isolated) -> None:
    """If the user deletes the sidecar but leaves the marker, we still own it."""
    home, project, registry = isolated
    src = _builtin_source(home, project)
    adapter = get_adapter("claude")

    install_command(
        src, adapter, scope="user",
        project_root=project, home=home, registry=registry,
    )
    target_dir = home / ".claude" / "skills" / "clean-memory"
    (target_dir / SIDECAR_FILENAME).unlink()

    # Should not raise OwnershipError; the SKILL.md marker survives.
    outcome = install_command(
        src, adapter, scope="user",
        project_root=project, home=home, registry=registry,
    )
    # We treat marker-only as ours; install proceeds.
    assert outcome.action in {"unchanged", "updated", "created"}


def test_diff_reports_drift(isolated) -> None:
    home, project, registry = isolated
    src = _builtin_source(home, project)
    adapter = get_adapter("claude")

    _, _, diff = diff_command(
        src, adapter, scope="user",
        project_root=project, home=home,
    )
    assert diff  # directory does not exist yet -> full insertion

    install_command(
        src, adapter, scope="user",
        project_root=project, home=home, registry=registry,
    )
    _, target, diff = diff_command(
        src, adapter, scope="user",
        project_root=project, home=home,
    )
    assert diff == ""

    (target / ENTRYPOINT_FILENAME).write_text(
        (target / ENTRYPOINT_FILENAME).read_text() + "\nextra line\n",
        encoding="utf-8",
    )
    _, _, diff = diff_command(
        src, adapter, scope="user",
        project_root=project, home=home,
    )
    assert diff
