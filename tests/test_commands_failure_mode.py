"""Tests for the failure-mode gate (ADR failure-mode-as-source-field)."""

from __future__ import annotations

from pathlib import Path

import pytest

from eutaxis.commands import (
    FailureModeError,
    check_failure_mode,
    get_adapter,
    load_sources,
    render_command,
)
from eutaxis.commands.models import CommandSource, TargetsSpec
from eutaxis.commands.rendering import ENTRYPOINT_FILENAME


def _make_source(
    *,
    regime: str,
    failure_mode: str,
    required_visibility: str | None = None,
) -> CommandSource:
    return CommandSource(
        name="rs",
        description="test rule set",
        regime=regime,
        failure_mode=failure_mode,
        required_visibility=required_visibility,
        scope_default="user",
        targets=TargetsSpec(),
        action=None,
        body="body\n",
    )


def test_check_failure_mode_rejects_silent_model_invoked() -> None:
    src = _make_source(
        regime="model-invoked",
        failure_mode="silent",
        required_visibility="pre-action",
    )
    with pytest.raises(FailureModeError, match="model-invoked"):
        check_failure_mode(src)


def test_check_failure_mode_rejects_pre_invocation_user_invoked() -> None:
    src = _make_source(
        regime="user-invoked",
        failure_mode="silent",
        required_visibility="pre-invocation",
    )
    with pytest.raises(FailureModeError, match="pre-invocation"):
        check_failure_mode(src)


def test_check_failure_mode_allows_silent_user_invoked_pre_action() -> None:
    src = _make_source(
        regime="user-invoked",
        failure_mode="silent",
        required_visibility="pre-action",
    )
    check_failure_mode(src)  # no raise


def test_check_failure_mode_allows_visible_anywhere() -> None:
    for regime in ("user-invoked", "model-invoked"):
        src = _make_source(regime=regime, failure_mode="visible")
        check_failure_mode(src)  # no raise


def test_render_command_refuses_silent_model_invoked(tmp_path: Path) -> None:
    src = _make_source(
        regime="model-invoked",
        failure_mode="silent",
        required_visibility="pre-action",
    )
    with pytest.raises(FailureModeError):
        render_command(
            src, get_adapter("claude"), project_root=tmp_path, home=tmp_path
        )


def test_model_invoked_rule_set_renders_without_disable_invocation(
    tmp_path: Path,
) -> None:
    src_path = tmp_path / ".eutaxis" / "commands" / "rs.md"
    src_path.parent.mkdir(parents=True)
    src_path.write_text(
        "---\nname: rs\ndescription: d\nregime: model-invoked\n"
        "failure-mode: visible\n---\nbody\n",
        encoding="utf-8",
    )
    sources = load_sources(home=tmp_path, project_root=tmp_path)
    src = next(s for s in sources if s.name == "rs")

    artifact = render_command(
        src, get_adapter("claude"), project_root=tmp_path, home=tmp_path
    )
    skill = next(
        f.content for f in artifact.files if f.relative_path == ENTRYPOINT_FILENAME
    )
    assert "disable-model-invocation" not in skill


def test_model_invoked_rule_set_codex_omits_policy(tmp_path: Path) -> None:
    src_path = tmp_path / ".eutaxis" / "commands" / "rs.md"
    src_path.parent.mkdir(parents=True)
    src_path.write_text(
        "---\nname: rs\ndescription: d\nregime: model-invoked\n"
        "failure-mode: visible\n---\nbody\n",
        encoding="utf-8",
    )
    sources = load_sources(home=tmp_path, project_root=tmp_path)
    src = next(s for s in sources if s.name == "rs")

    artifact = render_command(
        src, get_adapter("codex"), project_root=tmp_path, home=tmp_path
    )
    paths = {f.relative_path for f in artifact.files}
    # No derived policy file when the regime is model-invoked.
    assert "agents/openai.yaml" not in paths
