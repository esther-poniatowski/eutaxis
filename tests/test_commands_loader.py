from __future__ import annotations

from pathlib import Path

import pytest

from eutaxis.commands.exceptions import CommandRenderError
from eutaxis.commands.loader import load_sources


def _write_source(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_loads_builtin_clean_memory_source(tmp_path: Path) -> None:
    sources = load_sources(home=tmp_path, project_root=tmp_path)
    names = [src.name for src in sources]
    assert "clean-memory" in names
    src = next(s for s in sources if s.name == "clean-memory")
    assert src.layer == "builtin"
    assert src.action is not None
    assert "{{ agent }}" in src.action.template
    assert src.argument_hint == "[--all] [--backup] [--dry-run]"
    assert "claude" in src.adapters
    assert src.adapters["claude"].frontmatter["allowed-tools"] == "Bash(eutaxis ops clean-memory*)"
    assert "codex" in src.adapters
    assert "agents/openai.yaml" in src.adapters["codex"].files


def test_project_overrides_user_overrides_builtin(tmp_path: Path) -> None:
    user_root = tmp_path / "home"
    project_root = tmp_path / "proj"

    _write_source(
        user_root / ".eutaxis" / "commands" / "clean-memory.md",
        "---\nname: clean-memory\ndescription: USER\ninvocation: [user]\n"
        "failure-mode: visible\n---\nbody\n",
    )
    _write_source(
        project_root / ".eutaxis" / "commands" / "clean-memory.md",
        "---\nname: clean-memory\ndescription: PROJECT\ninvocation: [user]\n"
        "failure-mode: visible\n---\nbody\n",
    )

    sources = load_sources(home=user_root, project_root=project_root)
    src = next(s for s in sources if s.name == "clean-memory")
    assert src.layer == "project"
    assert src.description == "PROJECT"


def test_missing_frontmatter_raises(tmp_path: Path) -> None:
    _write_source(
        tmp_path / ".eutaxis" / "commands" / "broken.md",
        "no frontmatter here\n",
    )
    with pytest.raises(CommandRenderError):
        load_sources(home=tmp_path, project_root=tmp_path)


def test_unsupported_invocation_value_raises(tmp_path: Path) -> None:
    _write_source(
        tmp_path / ".eutaxis" / "commands" / "weird.md",
        "---\nname: weird\ndescription: x\ninvocation: [robot]\n"
        "failure-mode: visible\n---\nbody\n",
    )
    with pytest.raises(CommandRenderError, match="Unsupported invocation"):
        load_sources(home=tmp_path, project_root=tmp_path)


def test_invocation_must_be_a_list(tmp_path: Path) -> None:
    _write_source(
        tmp_path / ".eutaxis" / "commands" / "weird.md",
        "---\nname: weird\ndescription: x\ninvocation: user\n"
        "failure-mode: visible\n---\nbody\n",
    )
    with pytest.raises(CommandRenderError, match="must be a list"):
        load_sources(home=tmp_path, project_root=tmp_path)


def test_invocation_rejects_duplicates(tmp_path: Path) -> None:
    _write_source(
        tmp_path / ".eutaxis" / "commands" / "weird.md",
        "---\nname: weird\ndescription: x\ninvocation: [user, user]\n"
        "failure-mode: visible\n---\nbody\n",
    )
    with pytest.raises(CommandRenderError, match="duplicate"):
        load_sources(home=tmp_path, project_root=tmp_path)


def test_invocation_model_and_user_accepted(tmp_path: Path) -> None:
    _write_source(
        tmp_path / ".eutaxis" / "commands" / "rs.md",
        "---\nname: rs\ndescription: x\ninvocation: [model, user]\n"
        "failure-mode: visible\n---\nbody\n",
    )
    sources = load_sources(home=tmp_path, project_root=tmp_path)
    src = next(s for s in sources if s.name == "rs")
    assert set(src.invocation) == {"model", "user"}
    assert src.failure_mode == "visible"


def test_missing_failure_mode_raises(tmp_path: Path) -> None:
    _write_source(
        tmp_path / ".eutaxis" / "commands" / "weird.md",
        "---\nname: weird\ndescription: x\ninvocation: [user]\n---\nbody\n",
    )
    with pytest.raises(CommandRenderError, match="failure-mode"):
        load_sources(home=tmp_path, project_root=tmp_path)


def test_silent_failure_requires_required_visibility(tmp_path: Path) -> None:
    _write_source(
        tmp_path / ".eutaxis" / "commands" / "silent.md",
        "---\nname: silent\ndescription: x\ninvocation: [user]\n"
        "failure-mode: silent\n---\nbody\n",
    )
    with pytest.raises(CommandRenderError, match="required-visibility is mandatory"):
        load_sources(home=tmp_path, project_root=tmp_path)


def test_visible_failure_rejects_required_visibility(tmp_path: Path) -> None:
    _write_source(
        tmp_path / ".eutaxis" / "commands" / "visible.md",
        "---\nname: visible\ndescription: x\ninvocation: [user]\n"
        "failure-mode: visible\nrequired-visibility: pre-action\n---\nbody\n",
    )
    with pytest.raises(CommandRenderError, match="must be unset"):
        load_sources(home=tmp_path, project_root=tmp_path)


def test_unsupported_required_visibility_raises(tmp_path: Path) -> None:
    _write_source(
        tmp_path / ".eutaxis" / "commands" / "silent.md",
        "---\nname: silent\ndescription: x\ninvocation: [user]\n"
        "failure-mode: silent\nrequired-visibility: maybe\n---\nbody\n",
    )
    with pytest.raises(CommandRenderError, match="Unsupported required-visibility"):
        load_sources(home=tmp_path, project_root=tmp_path)


def test_action_kind_other_than_shell_raises(tmp_path: Path) -> None:
    _write_source(
        tmp_path / ".eutaxis" / "commands" / "weird.md",
        "---\nname: weird\ndescription: x\ninvocation: [user]\n"
        "failure-mode: visible\n"
        "action:\n  kind: http\n  template: 'GET /'\n---\nbody\n",
    )
    with pytest.raises(CommandRenderError):
        load_sources(home=tmp_path, project_root=tmp_path)


def test_adapters_passthrough_parses(tmp_path: Path) -> None:
    _write_source(
        tmp_path / ".eutaxis" / "commands" / "demo.md",
        "---\n"
        "name: demo\ndescription: d\ninvocation: [user]\n"
        "failure-mode: visible\n"
        "adapters:\n"
        "  claude:\n"
        "    frontmatter:\n"
        "      allowed-tools: Bash(foo*)\n"
        "  codex:\n"
        "    files:\n"
        "      \"agents/openai.yaml\": \"policy:\\n  allow_implicit_invocation: false\\n\"\n"
        "---\nbody\n",
    )
    sources = load_sources(home=tmp_path, project_root=tmp_path)
    src = next(s for s in sources if s.name == "demo")
    assert src.adapters["claude"].frontmatter == {"allowed-tools": "Bash(foo*)"}
    assert "agents/openai.yaml" in src.adapters["codex"].files


def test_adapters_files_value_must_be_string(tmp_path: Path) -> None:
    _write_source(
        tmp_path / ".eutaxis" / "commands" / "bad.md",
        "---\n"
        "name: bad\ndescription: d\ninvocation: [user]\n"
        "failure-mode: visible\n"
        "adapters:\n"
        "  codex:\n"
        "    files:\n"
        "      \"agents/openai.yaml\": 42\n"
        "---\nbody\n",
    )
    with pytest.raises(CommandRenderError):
        load_sources(home=tmp_path, project_root=tmp_path)
