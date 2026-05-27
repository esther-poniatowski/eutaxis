from __future__ import annotations

from pathlib import Path

import yaml

from eutaxis.commands import get_adapter, load_sources, render_command
from eutaxis.commands.rendering import (
    ENTRYPOINT_FILENAME,
    OWNED_FRONTMATTER_KEY,
    SIDECAR_FILENAME,
)


def _files_by_path(artifact) -> dict[str, str]:
    return {f.relative_path: f.content for f in artifact.files}


def _skill_md_frontmatter(content: str) -> dict[str, object]:
    assert content.startswith("---\n")
    end = content.index("\n---\n", 4)
    return yaml.safe_load(content[4:end])


def test_clean_memory_renders_for_claude_skill(tmp_path: Path) -> None:
    sources = load_sources(home=tmp_path, project_root=tmp_path)
    src = next(s for s in sources if s.name == "clean-memory")

    project = Path("/Users/eresther/oikos")
    home = Path("/Users/eresther")

    artifact = render_command(src, get_adapter("claude"), project_root=project, home=home)
    files = _files_by_path(artifact)

    # Claude artifact: SKILL.md and sidecar; no agents/openai.yaml.
    assert ENTRYPOINT_FILENAME in files
    assert SIDECAR_FILENAME in files
    assert "agents/openai.yaml" not in files

    skill = files[ENTRYPOINT_FILENAME]
    front = _skill_md_frontmatter(skill)
    assert front["name"] == "clean-memory"
    assert front["disable-model-invocation"] is True
    assert front["allowed-tools"] == "Bash(eutaxis ops clean-memory*)"
    assert front["argument-hint"] == "[--all] [--backup] [--dry-run]"
    assert front[OWNED_FRONTMATTER_KEY] == artifact.content_hash

    # Body templating substituted.
    assert "eutaxis ops clean-memory --agent claude" in skill
    assert "{{ agent }}" not in skill
    assert "{{ action.template }}" not in skill


def test_clean_memory_renders_for_codex_skill(tmp_path: Path) -> None:
    sources = load_sources(home=tmp_path, project_root=tmp_path)
    src = next(s for s in sources if s.name == "clean-memory")

    project = Path("/Users/eresther/oikos")
    home = Path("/Users/eresther")

    artifact = render_command(src, get_adapter("codex"), project_root=project, home=home)
    files = _files_by_path(artifact)

    assert ENTRYPOINT_FILENAME in files
    assert "agents/openai.yaml" in files
    assert SIDECAR_FILENAME in files

    skill = files[ENTRYPOINT_FILENAME]
    front = _skill_md_frontmatter(skill)
    # Codex does NOT receive `disable-model-invocation` or `allowed-tools`.
    assert "disable-model-invocation" not in front
    assert "allowed-tools" not in front
    assert front["name"] == "clean-memory"

    openai = yaml.safe_load(files["agents/openai.yaml"])
    # Regime-derived policy + passthrough dependencies merged.
    assert openai["policy"]["allow_implicit_invocation"] is False
    assert openai["dependencies"]["tools"][0]["value"] == "eutaxis"

    assert "eutaxis ops clean-memory --agent codex" in skill


def test_override_replaces_action_template(tmp_path: Path) -> None:
    src_path = tmp_path / ".eutaxis" / "commands" / "demo.md"
    src_path.parent.mkdir(parents=True)
    src_path.write_text(
        "---\nname: demo\ndescription: d\ninvocation: [user]\n"
        "failure-mode: visible\n"
        "action:\n  kind: shell\n  template: 'base {{ agent }}'\n"
        "overrides:\n  codex:\n    action:\n      template: 'codex-special {{ agent }}'\n"
        "---\nrun {{ action.template }}\n",
        encoding="utf-8",
    )
    sources = load_sources(home=tmp_path, project_root=tmp_path)
    src = next(s for s in sources if s.name == "demo")

    claude = render_command(src, get_adapter("claude"), project_root=tmp_path, home=tmp_path)
    codex = render_command(src, get_adapter("codex"), project_root=tmp_path, home=tmp_path)

    claude_skill = _files_by_path(claude)[ENTRYPOINT_FILENAME]
    codex_skill = _files_by_path(codex)[ENTRYPOINT_FILENAME]
    assert "base claude" in claude_skill
    assert "codex-special codex" in codex_skill


def test_codex_refuses_allowed_tools_passthrough(tmp_path: Path) -> None:
    """Author tried to put `allowed-tools` into Codex frontmatter — not a permission grant."""
    src_path = tmp_path / ".eutaxis" / "commands" / "demo.md"
    src_path.parent.mkdir(parents=True)
    src_path.write_text(
        "---\nname: demo\ndescription: d\ninvocation: [user]\n"
        "failure-mode: visible\n"
        "adapters:\n  codex:\n    frontmatter:\n      allowed-tools: 'Bash(foo*)'\n"
        "---\nbody\n",
        encoding="utf-8",
    )
    sources = load_sources(home=tmp_path, project_root=tmp_path)
    src = next(s for s in sources if s.name == "demo")
    import pytest

    from eutaxis.commands import CommandError

    with pytest.raises(CommandError):
        render_command(src, get_adapter("codex"), project_root=tmp_path, home=tmp_path)


def test_sidecar_lists_all_files_with_hashes(tmp_path: Path) -> None:
    import hashlib
    import json as _json

    sources = load_sources(home=tmp_path, project_root=tmp_path)
    src = next(s for s in sources if s.name == "clean-memory")
    artifact = render_command(
        src, get_adapter("codex"), project_root=tmp_path, home=tmp_path
    )
    files = _files_by_path(artifact)

    sidecar = _json.loads(files[SIDECAR_FILENAME])
    paths = {entry["path"] for entry in sidecar["files"]}
    assert ENTRYPOINT_FILENAME in paths
    assert "agents/openai.yaml" in paths
    assert sidecar["content_hash"] == artifact.content_hash

    # Each entry's hash matches the file contents.
    for entry in sidecar["files"]:
        expected = hashlib.sha256(files[entry["path"]].encode("utf-8")).hexdigest()
        assert entry["sha256"] == expected
