"""Tests for progressive disclosure of skill bodies into rule files."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from eutaxis.commands import (
    CommandRenderError,
    get_adapter,
    install_command,
    render_command,
)
from eutaxis.commands.disclosure import READING_NOTE, disclose
from eutaxis.commands.installer import diff_command
from eutaxis.commands.loader import _load_one
from eutaxis.commands.registry import Registry
from eutaxis.commands.rendering import ENTRYPOINT_FILENAME, SIDECAR_FILENAME

BODY = dedent("""\
    # Style

    Module preamble.

    ## Core

    Section intro.

    **first-rule**:

    ✓ Do the first thing.

    *Exception.* Quoted text.

    **second-rule**:

    ✓ Do the second thing.
    ✗ Do not do the opposite.

    ## Procedure

    Steps without labels:

    1. Read.
    2. Write.

    ## Tail

    **third-rule**:

    Plain prose rule.
    """)


def _write_source(path: Path, body: str = BODY, **extra: str) -> Path:
    front = {
        "name": "style",
        "description": "Style rules.",
        "invocation": "[model, user]",
        "failure-mode": "visible",
        **extra,
    }
    text = "".join(f"{key}: {value}\n" for key, value in front.items())
    path.write_text(f"---\n{text}---\n\n{body}", encoding="utf-8")
    return path


@pytest.fixture
def env(tmp_path: Path) -> dict[str, Path]:
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "proj"
    project.mkdir()
    return {"home": home, "project": project, "src": tmp_path / "style.md"}


def _render(source_path: Path, env: dict[str, Path], adapter: str = "claude"):
    source = _load_one(source_path, layer="config")
    return render_command(
        source,
        get_adapter(adapter),
        project_root=env["project"],
        home=env["home"],
    )


def _install(source_path: Path, env: dict[str, Path], adapter: str = "claude"):
    source = _load_one(source_path, layer="config")
    return install_command(
        source,
        get_adapter(adapter),
        scope="user",
        project_root=env["project"],
        home=env["home"],
        registry=Registry(env["home"] / ".eutaxis" / "state"),
    )


def test_disclose_keeps_text_outside_rules_and_indexes_each_rule() -> None:
    result = disclose(BODY, module="style")
    body = result.entrypoint_body
    assert [f.relative_path for f in result.rule_files] == [
        "rules/first-rule.md",
        "rules/second-rule.md",
        "rules/third-rule.md",
    ]
    for kept in (
        "# Style",
        "Module preamble.",
        "## Core",
        "Section intro.",
        "1. Read.",
    ):
        assert kept in body
    assert "- [`first-rule`](rules/first-rule.md): Do the first thing." in body
    assert "- [`third-rule`](rules/third-rule.md): Plain prose rule." in body
    assert body.count(READING_NOTE) == 1
    assert "*Exception.*" not in body
    assert body.index("## Core") < body.index("first-rule") < body.index("## Procedure")


def test_disclose_rule_file_holds_the_whole_block() -> None:
    result = disclose(BODY, module="style")
    first = result.rule_files[0].content
    assert first == (
        "**first-rule**:\n\n✓ Do the first thing.\n\n*Exception.* Quoted text.\n"
    )


def test_disclose_places_every_source_line_in_one_file() -> None:
    result = disclose(BODY, module="style")
    emitted = [result.entrypoint_body, *(f.content for f in result.rule_files)]
    for line in BODY.splitlines():
        if not line.strip():
            continue
        holders = [text for text in emitted if line in text.splitlines()]
        assert len(holders) == 1, line


def test_disclose_returns_body_without_rules_unchanged() -> None:
    body = "# Procedure\n\n1. Read.\n"
    result = disclose(body, module="procedure")
    assert result.entrypoint_body == body
    assert result.rule_files == ()


def test_disclose_refuses_duplicate_labels() -> None:
    body = "**twice**:\n\n✓ One.\n\n**twice**:\n\n✓ Two.\n"
    with pytest.raises(CommandRenderError, match="twice"):
        disclose(body, module="m")


def test_default_output_is_unchanged(env: dict[str, Path], tmp_path: Path) -> None:
    default = _render(_write_source(env["src"]), env)
    explicit = _render(
        _write_source(tmp_path / "explicit.md", disclosure="inline"), env
    )
    assert [f.relative_path for f in default.files] == [
        ENTRYPOINT_FILENAME,
        SIDECAR_FILENAME,
    ]
    assert default.files == explicit.files
    skill_md = default.files[0].content
    assert skill_md.endswith("\n\n" + BODY)


def test_progressive_render_lists_every_rule_file_in_the_manifest(
    env: dict[str, Path],
) -> None:
    rendered = _render(_write_source(env["src"], disclosure="progressive"), env)
    paths = [f.relative_path for f in rendered.files]
    assert paths == [
        ENTRYPOINT_FILENAME,
        "rules/first-rule.md",
        "rules/second-rule.md",
        "rules/third-rule.md",
        SIDECAR_FILENAME,
    ]
    sidecar = json.loads(rendered.files[-1].content)
    assert sorted(entry["path"] for entry in sidecar["files"]) == sorted(paths[:-1])
    assert "x-eutaxis-owned" in rendered.files[0].content


def test_progressive_hash_covers_rule_files(
    env: dict[str, Path], tmp_path: Path
) -> None:
    before = _render(_write_source(env["src"], disclosure="progressive"), env)
    changed = BODY.replace("Quoted text.", "Quoted or cited text.")
    after = _render(
        _write_source(tmp_path / "changed.md", body=changed, disclosure="progressive"),
        env,
    )
    assert before.files[0].content.split("x-eutaxis-owned")[0] == (
        after.files[0].content.split("x-eutaxis-owned")[0]
    )
    assert before.content_hash != after.content_hash


@pytest.mark.parametrize(
    "adapter, skills_root", [("claude", ".claude"), ("codex", ".agents")]
)
def test_reinstall_removes_the_file_of_a_deleted_rule(
    env: dict[str, Path], adapter: str, skills_root: str
) -> None:
    source_path = _write_source(env["src"], disclosure="progressive")
    outcome = _install(source_path, env, adapter)
    target = env["home"] / skills_root / "skills" / "style"
    assert outcome.path == target
    assert (target / "rules" / "second-rule.md").is_file()

    trimmed = BODY.replace(
        "**second-rule**:\n\n✓ Do the second thing.\n✗ Do not do the opposite.\n\n", ""
    )
    _write_source(source_path, body=trimmed, disclosure="progressive")
    source = _load_one(source_path, layer="config")
    _, _, diff = diff_command(
        source,
        get_adapter(adapter),
        scope="user",
        project_root=env["project"],
        home=env["home"],
    )
    assert "rules/second-rule.md (removed)" in diff

    assert _install(source_path, env, adapter).action == "updated"
    assert not (target / "rules" / "second-rule.md").exists()
    assert (target / "rules" / "first-rule.md").is_file()
    sidecar = json.loads((target / SIDECAR_FILENAME).read_text(encoding="utf-8"))
    assert "rules/second-rule.md" not in {entry["path"] for entry in sidecar["files"]}


def test_switching_back_to_inline_removes_the_rules_directory(
    env: dict[str, Path],
) -> None:
    source_path = _write_source(env["src"], disclosure="progressive")
    _install(source_path, env)
    _write_source(source_path)
    assert _install(source_path, env).action == "updated"
    target = env["home"] / ".claude" / "skills" / "style"
    assert not (target / "rules").exists()


def test_hand_edited_rule_file_is_reported_and_repaired(env: dict[str, Path]) -> None:
    source_path = _write_source(env["src"], disclosure="progressive")
    _install(source_path, env)
    rule_file = env["home"] / ".claude" / "skills" / "style" / "rules" / "first-rule.md"
    original = rule_file.read_text(encoding="utf-8")
    rule_file.write_text("edited\n", encoding="utf-8")

    source = _load_one(source_path, layer="config")
    _, _, diff = diff_command(
        source,
        get_adapter("claude"),
        scope="user",
        project_root=env["project"],
        home=env["home"],
    )
    assert "first-rule.md" in diff
    assert _install(source_path, env).action == "updated"
    assert rule_file.read_text(encoding="utf-8") == original
    assert _install(source_path, env).action == "unchanged"


def test_loader_rejects_unknown_disclosure(env: dict[str, Path]) -> None:
    with pytest.raises(CommandRenderError, match="disclosure"):
        _load_one(_write_source(env["src"], disclosure="folded"), layer="config")
