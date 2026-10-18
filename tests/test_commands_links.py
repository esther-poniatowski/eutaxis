"""Tests for the rewrite of relative links in compiled skills."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
import yaml
from typer.testing import CliRunner

from eutaxis.cli import app
from eutaxis.commands import get_adapter, load_from_instruction_config, render_command
from eutaxis.commands.links import LinkResolver, iter_links

ALPHA_BODY = dedent("""\
    # Alpha

    Read [beta](beta.md), [its anchor](beta.md#^anchor) and [the guard](../global/guard.md).
    Ask [the site](https://example.org/a.md), [mail](mailto:a@b.org) or [here](#^local).
    Keep `[code](beta.md)` and [the gap](missing.md).

    ```
    [fenced](beta.md)
    ```

    **apply**:

    ✓ Apply [beta](beta.md).
    """)


def _module(path: Path, name: str, body: str, **fm: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = "".join(f"{key}: {value}\n" for key, value in fm.items())
    path.write_text(
        f"---\nname: {name}\ndescription: {name}.\ninvocation: [model, user]\n"
        f"failure-mode: visible\n{extra}---\n\n{body}",
        encoding="utf-8",
    )


@pytest.fixture
def workspace(tmp_path: Path):
    def build(
        *, alpha_fm: dict[str, str] | None = None, beta_fm: dict[str, str] | None = None
    ):
        root = tmp_path / "src"
        _module(root / "tasks" / "alpha.md", "alpha", ALPHA_BODY, **(alpha_fm or {}))
        _module(
            root / "tasks" / "beta.md",
            "beta",
            "# Beta\n\nText. ^anchor\n",
            **(beta_fm or {}),
        )
        (root / "global").mkdir(exist_ok=True)
        (root / "global" / "guard.md").write_text("# Guard\n", encoding="utf-8")
        config = tmp_path / "agent-instructions.yaml"
        config.write_text(
            yaml.safe_dump(
                {
                    "root": str(root),
                    "task_modules": [
                        {"id": n, "title": n, "path": f"tasks/{n}.md", "trigger": "t"}
                        for n in ("alpha", "beta")
                    ],
                    "agents": [],
                }
            ),
            encoding="utf-8",
        )
        return root, config

    return build


def _render(config: Path, name: str, adapter: str = "claude", home: Path = Path("/h")):
    source = next(s for s in load_from_instruction_config(config) if s.name == name)
    return render_command(source, get_adapter(adapter), project_root=home, home=home)


def _files(rendered) -> dict[str, str]:
    return {f.relative_path: f.content for f in rendered.files}


def test_iter_links_skips_code_and_reads_wrapped_targets() -> None:
    text = '[a](x.md) `[b](y.md)` ``[c](`z`)`` ![d](<w v.png> "t")\n[e]: ref.md\n```\n[f](g.md)\n```\n'
    assert [link.target for link in iter_links(text)] == ["x.md", "w v.png", "ref.md"]


def test_rewrite_targets_sibling_skills_and_existing_files(workspace) -> None:
    root, config = workspace()

    rendered = _render(config, "alpha")
    skill = _files(rendered)["SKILL.md"]

    assert "[beta](../beta/SKILL.md)" in skill
    assert "[its anchor](../beta/SKILL.md#^anchor)" in skill
    assert f"[the guard]({(root / 'global' / 'guard.md').as_posix()})" in skill
    assert "[the site](https://example.org/a.md)" in skill
    assert "[mail](mailto:a@b.org)" in skill
    assert "[here](#^local)" in skill
    assert "`[code](beta.md)`" in skill
    assert "[fenced](beta.md)" in skill
    assert "[the gap](missing.md)" in skill
    assert rendered.warnings == (
        f"{root / 'tasks' / 'alpha.md'}:12: link target 'missing.md' resolves to "
        f"{root / 'tasks' / 'missing.md'}, which does not exist",
    )


def test_rewrite_in_split_skill_targets_rule_files_one_level_deeper(workspace) -> None:
    _, config = workspace(alpha_fm={"disclosure": "progressive"})

    files = _files(_render(config, "alpha"))

    assert (
        files["rules/apply.md"]
        == "**apply**:\n\n✓ Apply [beta](../../beta/SKILL.md).\n"
    )
    assert (
        "- [`apply`](rules/apply.md): Apply [beta](../beta/SKILL.md)."
        in files["SKILL.md"]
    )


def test_link_to_a_skill_absent_from_the_adapter_becomes_absolute(workspace) -> None:
    root, config = workspace(beta_fm={"targets": "{exclude: [codex]}"})

    claude = _files(_render(config, "alpha", "claude"))["SKILL.md"]
    codex = _files(_render(config, "alpha", "codex"))["SKILL.md"]

    assert "[beta](../beta/SKILL.md)" in claude
    assert f"[beta]({(root / 'tasks' / 'beta.md').as_posix()})" in codex


def test_rewritten_target_with_a_space_is_wrapped() -> None:
    resolver = LinkResolver(source_dir=Path("/a b"), exists=lambda path: True)
    assert (
        resolver.rewrite("[x](c.md)", emitter="SKILL.md", artifact_paths=frozenset())
        == "[x](</a b/c.md>)"
    )


def test_install_warns_once_and_diff_stays_ok(workspace, tmp_path: Path) -> None:
    _, config = workspace(alpha_fm={"disclosure": "progressive"})
    home = tmp_path / "home"
    home.mkdir()
    runner = CliRunner()

    install = runner.invoke(
        app, ["skills", "install", "all", "-c", str(config)], env={"HOME": str(home)}
    )
    diff = runner.invoke(
        app, ["skills", "diff", "-c", str(config)], env={"HOME": str(home)}
    )

    assert install.exit_code == 0, install.output
    assert install.stderr.count("link target 'missing.md'") == 1
    assert diff.exit_code == 0, diff.output
    assert "OUTDATED" not in diff.stdout
    assert "link target 'missing.md'" in diff.stderr
    installed = home / ".claude" / "skills" / "alpha" / "rules" / "apply.md"
    assert "../../beta/SKILL.md" in installed.read_text(encoding="utf-8")


def test_show_reports_missing_link_targets(workspace) -> None:
    _, config = workspace()

    result = CliRunner().invoke(app, ["skills", "show", "alpha", "-c", str(config)])

    assert result.exit_code == 0, result.output
    assert "alpha.md:12: link target 'missing.md'" in result.stderr
    assert "[beta](../beta/SKILL.md)" in result.stdout
