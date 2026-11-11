from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

import pytest
import yaml

from eutaxis.commands import (
    ArtifactFile,
    CommandRenderError,
    SkillRenderInput,
    assemble_skill,
    get_adapter,
    load_sources,
    render_command,
)
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

    artifact = render_command(
        src, get_adapter("claude"), project_root=project, home=home
    )
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

    artifact = render_command(
        src, get_adapter("codex"), project_root=project, home=home
    )
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

    claude = render_command(
        src, get_adapter("claude"), project_root=tmp_path, home=tmp_path
    )
    codex = render_command(
        src, get_adapter("codex"), project_root=tmp_path, home=tmp_path
    )

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
    from eutaxis.commands import CommandError

    with pytest.raises(CommandError):
        render_command(src, get_adapter("codex"), project_root=tmp_path, home=tmp_path)


@pytest.mark.parametrize("path", ("SKILL.md/payload", "agents"))
def test_shared_assembler_rejects_generated_path_prefix_collisions(path: str) -> None:
    source = SkillRenderInput(
        name="demo",
        description="Demonstrate assembly",
        scope="project",
        invocation=("user",),
        entrypoint_body="# Demo\n",
        contract_file=None,
        resources=(ArtifactFile(path, "content\n"),),
        adapter_passthrough=MappingProxyType({}),
    )

    with pytest.raises(CommandRenderError, match="reserved artifact path|collide"):
        assemble_skill(source, get_adapter("codex"))


def test_command_renderer_calls_adapter_siblings_once(tmp_path: Path) -> None:
    source = next(
        item
        for item in load_sources(home=tmp_path, project_root=tmp_path)
        if item.name == "clean-memory"
    )

    class OneShotAdapter:
        name = "one-shot"

        def __init__(self) -> None:
            self.calls = 0

        def supports_scope(self, scope: str) -> bool:
            return scope in {"user", "project"}

        def sibling_files(self, render_input):
            self.calls += 1
            if self.calls > 1:
                raise AssertionError("sibling_files called more than once")
            return (ArtifactFile("support.md", "support\n"),)

        def skill_frontmatter(self, render_input, *, rendered_body: str):
            return {
                "name": render_input.name,
                "description": render_input.description,
            }

    adapter = OneShotAdapter()

    artifact = render_command(
        source, adapter, project_root=tmp_path, home=tmp_path  # type: ignore[arg-type]
    )

    assert adapter.calls == 1
    assert "support.md" in _files_by_path(artifact)


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
    assert next(iter(sidecar)) == "_schema"
    assert sidecar["_schema"] == "eutaxis:skill-ownership@1"
    paths = {entry["path"] for entry in sidecar["files"]}
    assert ENTRYPOINT_FILENAME in paths
    assert "agents/openai.yaml" in paths
    assert sidecar["content_hash"] == artifact.content_hash

    # Each entry's hash matches the file contents.
    for entry in sidecar["files"]:
        expected = hashlib.sha256(files[entry["path"]].encode("utf-8")).hexdigest()
        assert entry["sha256"] == expected
