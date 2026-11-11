"""Integration tests for generated Skill loading-unit manifests."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

import eutaxis.commands._skills_cli as skills_cli_module
from eutaxis.cli import app
from eutaxis.commands import CommandError
from eutaxis.commands import synchronization as synchronization_module
from eutaxis.commands.loading_unit_publication import _closure_digest
from eutaxis.commands.registry import Registry, default_state_dir
from eutaxis.commands.synchronization import SkillSyncManifest, skill_write_transaction
from eutaxis.instructions import ConfigurationError, load_config


def _write_module(
    path: Path,
    *,
    name: str,
    rule: str,
    targets: str | None = None,
    scope_default: str | None = None,
) -> None:
    target_line = f"targets: {targets}\n" if targets is not None else ""
    scope_line = (
        f"scope_default: {scope_default}\n" if scope_default is not None else ""
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {name} description\n"
        "invocation: [model, user]\n"
        "failure-mode: visible\n"
        "disclosure: progressive\n"
        f"{target_line}{scope_line}"
        "---\n"
        f"# {name.title()}\n\n"
        f"**{rule}**:\n\n"
        f"✓ Apply {name}.\n",
        encoding="utf-8",
    )


def _workspace(tmp_path: Path, *, publish: bool = True) -> Path:
    _write_module(
        tmp_path / "instructions" / "workflow.md",
        name="workflow",
        rule="workflow-rule",
    )
    _write_module(
        tmp_path / "instructions" / "style.md",
        name="style",
        rule="style-rule",
    )
    units = [
        {
            "name": "workflow-batch",
            "max_bytes": 10000,
            "members": [{"module": "workflow", "rules": ["workflow-rule"]}],
        },
        {
            "name": "style-batch",
            "max_bytes": 10000,
            "members": [{"module": "style", "rules": ["style-rule"]}],
        },
        {
            "name": "section-route",
            "max_bytes": 30000,
            "includes": ["workflow-batch", "style-batch"],
            **({"publish_to": "workflow"} if publish else {}),
        },
    ]
    config = tmp_path / "eutaxis.yml"
    config.write_text(
        yaml.safe_dump(
            {
                "_schema": "eutaxis:configuration@1",
                "common_sources": [],
                "task_modules": [
                    {
                        "id": name,
                        "title": name.title(),
                        "path": f"instructions/{name}.md",
                        "trigger": f"on {name}",
                    }
                    for name in ("workflow", "style")
                ],
                "skill_entrypoint_max_bytes": 4096,
                "skill_loading_units": units,
                "agents": [],
            }
        ),
        encoding="utf-8",
    )
    return config


def _nested_workspace(tmp_path: Path) -> Path:
    config = _workspace(tmp_path)
    workflow = tmp_path / "instructions" / "workflow.md"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(
            "disclosure: progressive\n",
            "disclosure: progressive\nscope_default: project\n",
        ),
        encoding="utf-8",
    )
    _write_module(
        tmp_path / "instructions" / "outer.md",
        name="outer",
        rule="outer-rule",
        scope_default="user",
    )
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    payload["task_modules"].append(
        {
            "id": "outer",
            "title": "Outer",
            "path": "instructions/outer.md",
            "trigger": "on outer",
        }
    )
    payload["skill_loading_units"].extend(
        [
            {
                "name": "outer-batch",
                "max_bytes": 10000,
                "members": [{"module": "outer", "rules": ["outer-rule"]}],
            },
            {
                "name": "outer-route",
                "max_bytes": 30000,
                "publish_to": "outer",
                "includes": ["outer-batch", "workflow-batch", "style-batch"],
            },
        ]
    )
    config.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return config


def _run(home: Path, *arguments: str):
    return CliRunner().invoke(
        app,
        ["skills", *arguments],
        env={"HOME": str(home)},
        catch_exceptions=False,
    )


def _installed_closure_digest(skills: Path, ordered_paths: list[str]) -> str:
    payload = []
    for selected_path in ordered_paths:
        content = (skills / selected_path).read_text(encoding="utf-8")
        if selected_path.endswith("/SKILL.md"):
            lines = content.splitlines(keepends=True)
            closing = next(
                (
                    index
                    for index, line in enumerate(lines[1:], start=1)
                    if line.rstrip("\r\n") == "---"
                ),
                None,
            )
            if lines and lines[0].rstrip("\r\n") == "---" and closing is not None:
                content = "".join(
                    line
                    for index, line in enumerate(lines)
                    if not (0 < index < closing and line.startswith("x-eutaxis-owned:"))
                )
        payload.append(
            {
                "path": selected_path,
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
        )
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def test_closure_digest_ignores_only_the_generated_frontmatter_owner_hash() -> None:
    def digest(generated: str, authored: str) -> str:
        return _closure_digest(
            {
                "skill/SKILL.md": (
                    "---\n"
                    f"x-eutaxis-owned: {generated}\n"
                    "---\n"
                    f"x-eutaxis-owned: {authored}\n"
                )
            }
        )

    assert digest("first", "authored") == digest("second", "authored")
    assert digest("first", "authored") != digest("first", "changed")


@pytest.mark.parametrize(
    ("adapter", "root"),
    (("codex", ".agents"), ("claude", ".claude")),
)
def test_published_route_is_installed_inside_its_owner_for_each_adapter(
    tmp_path: Path, adapter: str, root: str
) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    result = _run(
        home,
        "sync",
        "-c",
        str(config),
        "--agent",
        adapter,
        "--apply",
    )

    assert result.exit_code == 0, result.output
    owner = home / root / "skills" / "workflow"
    route = owner / "routes" / "section-route.md"
    workflow_batch = owner / "routes" / "batches" / "workflow-batch.md"
    style_batch = owner / "routes" / "batches" / "style-batch.md"
    assert route.is_file()
    assert workflow_batch.is_file()
    assert style_batch.is_file()
    entrypoint = (owner / "SKILL.md").read_text(encoding="utf-8")
    assert "[`section-route`](routes/section-route.md)" in entrypoint
    route_text = route.read_text(encoding="utf-8")
    assert route_text.index("workflow/SKILL.md") < route_text.index("style/SKILL.md")
    assert "../../style/rules/style-rule.md" in route_text
    sidecar = json.loads((owner / ".eutaxis-owned.json").read_text(encoding="utf-8"))
    owned = {item["path"] for item in sidecar["files"]}
    assert "routes/section-route.md" in owned
    assert "routes/batches/style-batch.md" in owned
    assert "eutaxis:published-loading-routes" not in (
        owner / "rules" / "workflow-rule.md"
    ).read_text(encoding="utf-8")


def test_manifest_digest_and_order_describe_the_installed_closure(
    tmp_path: Path,
) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    result = _run(
        home,
        "sync",
        "-c",
        str(config),
        "--agent",
        "codex",
        "--apply",
    )
    assert result.exit_code == 0, result.output
    skills = home / ".agents" / "skills"
    route = skills / "workflow" / "routes" / "section-route.md"
    route_text = route.read_text(encoding="utf-8")
    ordered_paths = re.findall(r"^1\. \[`([^`]+)`\]", route_text, flags=re.MULTILINE)
    assert ordered_paths == [
        "workflow/SKILL.md",
        "workflow/rules/workflow-rule.md",
        "style/SKILL.md",
        "style/rules/style-rule.md",
    ]
    declared_digest = re.search(
        r"^- Closure digest: `([0-9a-f]{64})`$", route_text, flags=re.MULTILINE
    )
    assert declared_digest is not None
    assert declared_digest.group(1) == _installed_closure_digest(skills, ordered_paths)


@pytest.mark.parametrize(
    ("adapter", "root"),
    (("codex", ".agents"), ("claude", ".claude")),
)
def test_installed_digest_ignores_an_indented_yaml_fence_for_each_adapter(
    tmp_path: Path,
    adapter: str,
    root: str,
) -> None:
    config = _workspace(tmp_path)
    workflow = tmp_path / "instructions" / "workflow.md"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(
            "description: workflow description\n",
            "description: |\n" "  workflow description\n" "  ---\n" "  continuation\n",
        ),
        encoding="utf-8",
    )
    home = tmp_path / "home"
    home.mkdir()

    result = _run(
        home,
        "sync",
        "-c",
        str(config),
        "--agent",
        adapter,
        "--apply",
    )

    assert result.exit_code == 0, result.output
    skills = home / root / "skills"
    route_text = (skills / "workflow" / "routes" / "section-route.md").read_text(
        encoding="utf-8"
    )
    ordered_paths = re.findall(r"^1\. \[`([^`]+)`\]", route_text, flags=re.MULTILINE)
    declared_digest = re.search(
        r"^- Closure digest: `([0-9a-f]{64})`$", route_text, flags=re.MULTILINE
    )
    assert declared_digest is not None
    assert declared_digest.group(1) == _installed_closure_digest(skills, ordered_paths)


@pytest.mark.parametrize(
    ("adapter", "root"),
    (("codex", ".agents"), ("claude", ".claude")),
)
def test_project_scope_routes_resolve_from_an_unrelated_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    adapter: str,
    root: str,
) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    project = tmp_path / "project"
    unrelated = tmp_path / "unrelated"
    home.mkdir()
    project.mkdir()
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)

    result = _run(
        home,
        "sync",
        "-c",
        str(config),
        "--agent",
        adapter,
        "--scope",
        "project",
        "--target-project",
        str(project),
        "--apply",
    )

    assert result.exit_code == 0, result.output
    route = project / root / "skills" / "workflow" / "routes" / "section-route.md"
    assert route.is_file()
    route_text = route.read_text(encoding="utf-8")
    assert "../../style/rules/style-rule.md" in route_text
    ordered_paths = re.findall(r"^1\. \[`([^`]+)`\]", route_text, flags=re.MULTILINE)
    assert ordered_paths == [
        "workflow/SKILL.md",
        "workflow/rules/workflow-rule.md",
        "style/SKILL.md",
        "style/rules/style-rule.md",
    ]
    declared_digest = re.search(
        r"^- Closure digest: `([0-9a-f]{64})`$", route_text, flags=re.MULTILINE
    )
    assert declared_digest is not None
    assert declared_digest.group(1) == _installed_closure_digest(
        project / root / "skills", ordered_paths
    )


def test_loading_unit_show_reports_publication_and_exact_files(
    tmp_path: Path,
) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    result = _run(
        home,
        "loading-unit",
        "show",
        "section-route",
        "-c",
        str(config),
        "--agent",
        "codex",
    )

    assert result.exit_code == 0, result.output
    assert "publication-owner: workflow" in result.output
    assert "route-manifest: workflow/routes/section-route.md" in result.output
    assert "file: workflow/SKILL.md" in result.output
    assert "file: style/rules/style-rule.md" in result.output
    assert "closure-digest:" in result.output


def test_budget_counts_generated_route_delivery_files(tmp_path: Path) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    result = _run(
        home,
        "budget",
        "-c",
        str(config),
        "--agent",
        "codex",
    )

    assert result.exit_code == 0, result.output
    assert "published-to: workflow" in result.output
    assert "workflow/routes/section-route.md" in result.output
    assert "workflow/routes/batches/workflow-batch.md" in result.output


def test_installing_a_route_owner_installs_dependencies_first(
    tmp_path: Path,
) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    result = _run(
        home,
        "install",
        "workflow",
        "-c",
        str(config),
        "--agent",
        "claude",
    )

    assert result.exit_code == 0, result.output
    assert result.output.index("style@claude") < result.output.index("workflow@claude")
    assert (home / ".claude" / "skills" / "style" / "SKILL.md").is_file()


def test_installing_a_route_member_refreshes_its_published_owner(
    tmp_path: Path,
) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    initial = _run(home, "install", "workflow", "-c", str(config), "--agent", "claude")
    assert initial.exit_code == 0, initial.output
    route = home / ".claude" / "skills" / "workflow" / "routes" / "section-route.md"
    before = route.read_text(encoding="utf-8")
    style = tmp_path / "instructions" / "style.md"
    style.write_text(
        style.read_text(encoding="utf-8").replace("Apply style.", "Apply new style."),
        encoding="utf-8",
    )

    refreshed = _run(home, "install", "style", "-c", str(config), "--agent", "claude")

    assert refreshed.exit_code == 0, refreshed.output
    assert refreshed.output.index("style@claude") < refreshed.output.index(
        "workflow@claude"
    )
    assert route.read_text(encoding="utf-8") != before


def test_direct_owner_install_uses_one_scope_for_the_complete_route(
    tmp_path: Path,
) -> None:
    config = _workspace(tmp_path)
    _write_module(
        tmp_path / "instructions" / "workflow.md",
        name="workflow",
        rule="workflow-rule",
        scope_default="project",
    )
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()

    result = _run(
        home,
        "install",
        "workflow",
        "-c",
        str(config),
        "--agent",
        "claude",
        "--target-project",
        str(project),
    )

    assert result.exit_code == 0, result.output
    assert (project / ".claude" / "skills" / "workflow" / "SKILL.md").is_file()
    assert (project / ".claude" / "skills" / "style" / "SKILL.md").is_file()
    assert not (home / ".claude" / "skills" / "style").exists()


def test_shared_member_refreshes_each_owner_in_that_owners_default_scope(
    tmp_path: Path,
) -> None:
    config = _workspace(tmp_path)
    _write_module(
        tmp_path / "instructions" / "project-workflow.md",
        name="project-workflow",
        rule="project-workflow-rule",
        scope_default="project",
    )
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    payload["task_modules"].append(
        {
            "id": "project-workflow",
            "title": "Project Workflow",
            "path": "instructions/project-workflow.md",
            "trigger": "on project workflow",
        }
    )
    payload["skill_loading_units"].extend(
        [
            {
                "name": "project-workflow-batch",
                "max_bytes": 10000,
                "members": [
                    {
                        "module": "project-workflow",
                        "rules": ["project-workflow-rule"],
                    }
                ],
            },
            {
                "name": "project-route",
                "max_bytes": 30000,
                "publish_to": "project-workflow",
                "includes": ["project-workflow-batch", "style-batch"],
            },
        ]
    )
    config.write_text(yaml.safe_dump(payload), encoding="utf-8")
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()

    result = _run(
        home,
        "install",
        "style",
        "-c",
        str(config),
        "--agent",
        "codex",
        "--target-project",
        str(project),
    )

    assert result.exit_code == 0, result.output
    assert (home / ".agents" / "skills" / "workflow" / "SKILL.md").is_file()
    assert (home / ".agents" / "skills" / "style" / "SKILL.md").is_file()
    assert (project / ".agents" / "skills" / "project-workflow" / "SKILL.md").is_file()
    assert (project / ".agents" / "skills" / "style" / "SKILL.md").is_file()


@pytest.mark.parametrize("requested", ("style", "all"))
def test_nested_owner_scopes_propagate_to_every_manifest_target(
    tmp_path: Path, requested: str
) -> None:
    config = _nested_workspace(tmp_path)
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()

    result = _run(
        home,
        "install",
        requested,
        "-c",
        str(config),
        "--agent",
        "codex",
        "--target-project",
        str(project),
    )

    assert result.exit_code == 0, result.output
    user_skills = home / ".agents" / "skills"
    project_skills = project / ".agents" / "skills"
    assert (user_skills / "outer" / "routes" / "outer-route.md").is_file()
    assert (user_skills / "workflow" / "SKILL.md").is_file()
    assert (user_skills / "style" / "SKILL.md").is_file()
    assert (project_skills / "workflow" / "routes" / "section-route.md").is_file()
    assert (project_skills / "style" / "SKILL.md").is_file()


def test_installed_manifest_blocks_uninstall_after_config_evolves(
    tmp_path: Path,
) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    installed = _run(
        home, "install", "workflow", "-c", str(config), "--agent", "claude"
    )
    assert installed.exit_code == 0, installed.output
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    payload["skill_loading_units"][2].pop("publish_to")
    config.write_text(yaml.safe_dump(payload), encoding="utf-8")

    result = _run(home, "uninstall", "style", "-c", str(config), "--agent", "claude")

    assert result.exit_code == 2
    assert "installed published route owner(s) require it" in result.output
    assert (home / ".claude" / "skills" / "style" / "SKILL.md").is_file()


def test_direct_uninstall_refuses_to_leave_a_dangling_route(tmp_path: Path) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    installed = _run(home, "install", "workflow", "-c", str(config), "--agent", "codex")
    assert installed.exit_code == 0, installed.output

    result = _run(home, "uninstall", "style", "-c", str(config), "--agent", "codex")

    assert result.exit_code == 2
    assert "installed published route owner(s) require it" in result.output
    assert (home / ".agents" / "skills" / "style" / "SKILL.md").is_file()


def test_sync_rolls_back_the_complete_route_after_a_late_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    initial = _run(home, "sync", "-c", str(config), "--agent", "claude", "--apply")
    assert initial.exit_code == 0, initial.output
    skills = home / ".claude" / "skills"
    workflow_before = (skills / "workflow" / "SKILL.md").read_text(encoding="utf-8")
    style_before = (skills / "style" / "SKILL.md").read_text(encoding="utf-8")
    registry = home / ".eutaxis" / "state" / "installed-commands.json"
    registry_before = registry.read_text(encoding="utf-8")
    style_source = tmp_path / "instructions" / "style.md"
    style_source.write_text(
        style_source.read_text(encoding="utf-8").replace(
            "Apply style.", "Apply changed style."
        ),
        encoding="utf-8",
    )
    original_install = synchronization_module.install_command

    def fail_after_owner_write(*args, **kwargs):
        outcome = original_install(*args, **kwargs)
        if args[0].name == "workflow":
            raise CommandError("injected late failure")
        return outcome

    monkeypatch.setattr(
        synchronization_module, "install_command", fail_after_owner_write
    )

    result = _run(home, "sync", "-c", str(config), "--agent", "claude", "--apply")

    assert result.exit_code == 2
    assert "injected late failure" in result.output
    assert (skills / "workflow" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == workflow_before
    assert (skills / "style" / "SKILL.md").read_text(encoding="utf-8") == style_before
    assert registry.read_text(encoding="utf-8") == registry_before


@pytest.mark.parametrize("failure_type", (OSError, KeyboardInterrupt))
def test_sync_manifest_failure_rolls_back_artifacts_registry_and_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_type: type[BaseException],
) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    initial = _run(home, "sync", "-c", str(config), "--agent", "codex", "--apply")
    assert initial.exit_code == 0, initial.output
    skills = home / ".agents" / "skills"
    workflow_before = (skills / "workflow" / "SKILL.md").read_bytes()
    style_before = (skills / "style" / "SKILL.md").read_bytes()
    registry_path = home / ".eutaxis" / "state" / "installed-commands.json"
    registry_before = registry_path.read_bytes()
    manifest = SkillSyncManifest(home / ".eutaxis" / "state", config)
    manifest_before = manifest.path.read_bytes()
    style_source = tmp_path / "instructions" / "style.md"
    style_source.write_text(
        style_source.read_text(encoding="utf-8").replace(
            "Apply style.", "Apply changed style."
        ),
        encoding="utf-8",
    )
    original_update = SkillSyncManifest.update

    def fail_after_manifest_write(self, **kwargs):
        original_update(self, **kwargs)
        raise failure_type("injected manifest failure")

    monkeypatch.setattr(SkillSyncManifest, "update", fail_after_manifest_write)

    result = _run(
        home,
        "sync",
        "-c",
        str(config),
        "--agent",
        "codex",
        "--apply",
    )
    if failure_type is KeyboardInterrupt:
        assert result.exit_code != 0
    else:
        assert result.exit_code == 3
        assert "injected manifest failure" in result.output

    assert (skills / "workflow" / "SKILL.md").read_bytes() == workflow_before
    assert (skills / "style" / "SKILL.md").read_bytes() == style_before
    assert registry_path.read_bytes() == registry_before
    assert manifest.path.read_bytes() == manifest_before


def test_direct_install_rolls_back_the_complete_route_after_a_late_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    initial = _run(home, "install", "workflow", "-c", str(config), "--agent", "codex")
    assert initial.exit_code == 0, initial.output
    skills = home / ".agents" / "skills"
    workflow_before = (skills / "workflow" / "SKILL.md").read_text(encoding="utf-8")
    style_before = (skills / "style" / "SKILL.md").read_text(encoding="utf-8")
    registry = home / ".eutaxis" / "state" / "installed-commands.json"
    registry_before = registry.read_text(encoding="utf-8")
    style_source = tmp_path / "instructions" / "style.md"
    style_source.write_text(
        style_source.read_text(encoding="utf-8").replace(
            "Apply style.", "Apply changed style."
        ),
        encoding="utf-8",
    )
    original_install = skills_cli_module.install_command

    def fail_after_owner_write(*args, **kwargs):
        outcome = original_install(*args, **kwargs)
        if args[0].name == "workflow":
            raise CommandError("injected direct-install failure")
        return outcome

    monkeypatch.setattr(skills_cli_module, "install_command", fail_after_owner_write)

    result = _run(home, "install", "style", "-c", str(config), "--agent", "codex")

    assert result.exit_code == 2
    assert "injected direct-install failure" in result.output
    assert not re.search(r"^\[", result.output, flags=re.MULTILINE)
    assert (skills / "workflow" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == workflow_before
    assert (skills / "style" / "SKILL.md").read_text(encoding="utf-8") == style_before
    assert registry.read_text(encoding="utf-8") == registry_before


def test_direct_install_reports_a_concise_filesystem_failure_after_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    original_install = skills_cli_module.install_command

    def fail_after_first_write(*args, **kwargs):
        outcome = original_install(*args, **kwargs)
        if args[0].name == "style":
            raise OSError("injected filesystem failure")
        return outcome

    monkeypatch.setattr(skills_cli_module, "install_command", fail_after_first_write)

    result = _run(home, "install", "all", "-c", str(config), "--agent", "codex")

    assert result.exit_code == 3
    assert "Error: injected filesystem failure" in result.output
    assert "Traceback" not in result.output
    assert not re.search(r"^\[", result.output, flags=re.MULTILINE)
    assert not (home / ".agents" / "skills" / "workflow").exists()
    assert not (home / ".agents" / "skills" / "style").exists()


@pytest.mark.parametrize("agent", ("codex", "all"))
@pytest.mark.parametrize("command", ("install", "uninstall"))
def test_direct_mutators_reject_invalid_scope_without_writes(
    tmp_path: Path,
    agent: str,
    command: str,
) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    if command == "uninstall":
        initial = _run(
            home,
            "install",
            "all",
            "-c",
            str(config),
            "--agent",
            agent,
        )
        assert initial.exit_code == 0, initial.output
    before = {
        path.relative_to(home): path.read_bytes()
        for path in home.rglob("*")
        if path.is_file()
    }

    result = _run(
        home,
        command,
        "workflow",
        "-c",
        str(config),
        "--agent",
        agent,
        "--scope",
        "invalid",
    )

    after = {
        path.relative_to(home): path.read_bytes()
        for path in home.rglob("*")
        if path.is_file()
    }
    assert result.exit_code == 2
    assert (
        "Error: Invalid scope 'invalid'; expected 'user' or 'project'." in result.output
    )
    assert "Traceback" not in result.output
    assert after == before


def test_direct_install_reports_rollback_cleanup_failure_without_hiding_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    initial = _run(home, "install", "all", "-c", str(config), "--agent", "codex")
    assert initial.exit_code == 0, initial.output
    original_install = skills_cli_module.install_command
    original_copytree = synchronization_module.shutil.copytree

    def fail_after_owner_write(*args, **kwargs):
        outcome = original_install(*args, **kwargs)
        if args[0].name == "workflow":
            calls = 0

            def fail_first_restore(*copy_args, **copy_kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError("injected restoration failure")
                return original_copytree(*copy_args, **copy_kwargs)

            monkeypatch.setattr(
                synchronization_module.shutil, "copytree", fail_first_restore
            )
            raise CommandError("primary install failure")
        return outcome

    monkeypatch.setattr(skills_cli_module, "install_command", fail_after_owner_write)

    result = _run(home, "install", "all", "-c", str(config), "--agent", "codex")

    assert result.exit_code == 2
    assert result.output.startswith("Error: primary install failure\n")
    assert "Rollback cleanup also failed:" in result.output
    assert "injected restoration failure" in result.output
    assert "workflow" in result.output
    assert "Traceback" not in result.output


def test_child_change_updates_owner_route_digest_and_diff(tmp_path: Path) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    applied = _run(
        home,
        "sync",
        "-c",
        str(config),
        "--agent",
        "claude",
        "--apply",
    )
    assert applied.exit_code == 0, applied.output
    route = home / ".claude" / "skills" / "workflow" / "routes" / "section-route.md"
    original = route.read_text(encoding="utf-8")
    style = tmp_path / "instructions" / "style.md"
    style.write_text(
        style.read_text(encoding="utf-8").replace(
            "Apply style.", "Apply revised style."
        ),
        encoding="utf-8",
    )

    diff = _run(
        home,
        "diff",
        "workflow",
        "-c",
        str(config),
        "--agent",
        "claude",
    )

    assert diff.exit_code == 1, diff.output
    assert "routes/section-route.md" in diff.output
    updated = _run(
        home,
        "sync",
        "-c",
        str(config),
        "--agent",
        "claude",
        "--apply",
    )
    assert updated.exit_code == 0, updated.output
    assert route.read_text(encoding="utf-8") != original


def test_removing_publication_retires_generated_route_files(tmp_path: Path) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    assert (
        _run(
            home,
            "sync",
            "-c",
            str(config),
            "--agent",
            "claude",
            "--apply",
        ).exit_code
        == 0
    )
    route = home / ".claude" / "skills" / "workflow" / "routes" / "section-route.md"
    assert route.is_file()
    _workspace(tmp_path, publish=False)

    result = _run(
        home,
        "sync",
        "-c",
        str(config),
        "--agent",
        "claude",
        "--apply",
    )

    assert result.exit_code == 0, result.output
    assert not route.exists()


@pytest.mark.parametrize(
    "mutation, message",
    (
        (lambda route: route.update(publish_to="missing"), "unknown task module"),
        (
            lambda route: route.update(includes=["style-batch"]),
            "must include the entrypoint",
        ),
    ),
)
def test_publication_owner_must_exist_inside_the_route(
    tmp_path: Path, mutation, message: str
) -> None:
    config = _workspace(tmp_path)
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    mutation(payload["skill_loading_units"][2])
    config.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ConfigurationError, match=message):
        load_config(config)


def test_publication_fails_before_writing_when_a_member_excludes_the_adapter(
    tmp_path: Path,
) -> None:
    config = _workspace(tmp_path)
    _write_module(
        tmp_path / "instructions" / "style.md",
        name="style",
        rule="style-rule",
        targets="{include: [claude]}",
    )
    home = tmp_path / "home"
    home.mkdir()

    result = _run(
        home,
        "sync",
        "-c",
        str(config),
        "--agent",
        "codex",
        "--apply",
    )

    assert result.exit_code == 2
    assert "does not target adapter 'codex'" in result.output
    assert not (home / ".agents").exists()


def test_owner_excluded_adapter_is_skipped_during_all_agent_sync(
    tmp_path: Path,
) -> None:
    config = _workspace(tmp_path)
    _write_module(
        tmp_path / "instructions" / "workflow.md",
        name="workflow",
        rule="workflow-rule",
        targets="{include: [claude]}",
    )
    home = tmp_path / "home"
    home.mkdir()

    result = _run(home, "sync", "-c", str(config), "--agent", "all", "--apply")

    assert result.exit_code == 0, result.output
    assert (
        home / ".claude" / "skills" / "workflow" / "routes" / "section-route.md"
    ).is_file()
    assert not (home / ".agents" / "skills" / "workflow").exists()


def test_owner_excluded_publication_does_not_block_valid_member_or_list(
    tmp_path: Path,
) -> None:
    config = _workspace(tmp_path)
    _write_module(
        tmp_path / "instructions" / "workflow.md",
        name="workflow",
        rule="workflow-rule",
        targets="{include: [claude]}",
    )
    home = tmp_path / "home"
    home.mkdir()

    installed = _run(home, "install", "style", "-c", str(config), "--agent", "codex")
    listed = _run(home, "loading-unit", "list", "-c", str(config), "--agent", "codex")

    assert installed.exit_code == 0, installed.output
    assert (home / ".agents" / "skills" / "style" / "SKILL.md").is_file()
    assert not (home / ".agents" / "skills" / "workflow").exists()
    assert listed.exit_code == 0, listed.output
    assert "style-batch@codex" in listed.output
    assert "section-route@codex" not in listed.output
    assert "workflow-batch@codex" not in listed.output


def test_generated_route_rejects_an_authored_file_collision(tmp_path: Path) -> None:
    config = _workspace(tmp_path)
    workflow = tmp_path / "instructions" / "workflow.md"
    content = workflow.read_text(encoding="utf-8")
    content = content.replace(
        "failure-mode: visible\n",
        "failure-mode: visible\n"
        "adapters:\n"
        "  codex:\n"
        "    files:\n"
        "      routes/section-route.md: authored collision\n",
    )
    workflow.write_text(content, encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()

    result = _run(
        home,
        "sync",
        "-c",
        str(config),
        "--agent",
        "codex",
        "--apply",
    )

    assert result.exit_code == 2
    assert "collide with authored files" in result.output
    assert not (home / ".agents").exists()


def test_generated_route_rejects_a_case_variant_authored_collision(
    tmp_path: Path,
) -> None:
    config = _workspace(tmp_path)
    workflow = tmp_path / "instructions" / "workflow.md"
    content = workflow.read_text(encoding="utf-8").replace(
        "failure-mode: visible\n",
        "failure-mode: visible\n"
        "adapters:\n"
        "  codex:\n"
        "    files:\n"
        "      routes/Section-Route.md: case collision\n",
    )
    workflow.write_text(content, encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()

    result = _run(
        home,
        "sync",
        "-c",
        str(config),
        "--agent",
        "codex",
        "--apply",
    )

    assert result.exit_code == 2
    assert "collide with authored files" in result.output
    assert "Section-Route.md" in result.output
    assert not (home / ".agents").exists()


@pytest.mark.parametrize("name", ("../escape", "Route", "route.md", "a](/escape"))
def test_loading_unit_names_must_be_safe_path_slugs(tmp_path: Path, name: str) -> None:
    config = _workspace(tmp_path)
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    payload["skill_loading_units"][0]["name"] = name
    config.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="safe lowercase slug"):
        load_config(config)


def test_loading_unit_names_are_casefold_unique(tmp_path: Path) -> None:
    config = _workspace(tmp_path)
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    duplicate = dict(payload["skill_loading_units"][0])
    duplicate["name"] = "Workflow-Batch"
    payload["skill_loading_units"].append(duplicate)
    config.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="Duplicate skill loading unit name"):
        load_config(config)


def test_composite_includes_emit_only_leaf_batch_manifests(tmp_path: Path) -> None:
    config = _workspace(tmp_path)
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    payload["skill_loading_units"].insert(
        2,
        {
            "name": "composite",
            "max_bytes": 20000,
            "includes": ["workflow-batch", "style-batch"],
        },
    )
    payload["skill_loading_units"][3]["includes"] = ["composite"]
    config.write_text(yaml.safe_dump(payload), encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()

    result = _run(home, "sync", "-c", str(config), "--agent", "codex", "--apply")

    assert result.exit_code == 0, result.output
    batches = home / ".agents" / "skills" / "workflow" / "routes" / "batches"
    assert (batches / "workflow-batch.md").is_file()
    assert (batches / "style-batch.md").is_file()
    assert not (batches / "composite.md").exists()


def test_batch_budget_and_diagnostic_include_delivery_manifest(tmp_path: Path) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    budget = _run(home, "budget", "-c", str(config), "--agent", "codex")
    shown = _run(
        home,
        "loading-unit",
        "show",
        "workflow-batch",
        "-c",
        str(config),
        "--agent",
        "codex",
    )

    assert budget.exit_code == 0, budget.output
    workflow_block = budget.output.split("loading-unit workflow-batch@codex", 1)[
        1
    ].split("[OK  ] loading-unit", 1)[0]
    assert "workflow/routes/batches/workflow-batch.md" in workflow_block
    assert shown.exit_code == 0, shown.output
    assert "publication-owner: workflow" in shown.output
    assert "batch-manifest: workflow/routes/batches/workflow-batch.md" in shown.output
    assert "closure-digest:" in shown.output


def test_shared_batch_reports_every_owner_and_gates_the_largest_variant(
    tmp_path: Path,
) -> None:
    config = _nested_workspace(tmp_path)
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    installed = _run(
        home,
        "install",
        "all",
        "-c",
        str(config),
        "--agent",
        "codex",
        "--target-project",
        str(project),
    )
    assert installed.exit_code == 0, installed.output

    shown = _run(
        home,
        "loading-unit",
        "show",
        "style-batch",
        "-c",
        str(config),
        "--agent",
        "codex",
        "--target-project",
        str(project),
    )
    listed = _run(
        home,
        "loading-unit",
        "list",
        "-c",
        str(config),
        "--agent",
        "codex",
        "--target-project",
        str(project),
    )

    assert shown.exit_code == 0, shown.output
    assert shown.output.count("publication-owner:") == 2
    assert "publication-owner: outer" in shown.output
    assert "publication-owner: workflow" in shown.output
    assert shown.output.count("batch-manifest:") == 2
    measured_files = re.findall(r"^file: (.+)$", shown.output, flags=re.MULTILINE)
    delivery_files = [path for path in measured_files if "/routes/batches/" in path]
    assert len(delivery_files) == 1
    declared_bytes = int(
        re.search(r"^bytes: (\d+)/", shown.output, re.MULTILINE).group(1)
    )
    roots = [home / ".agents" / "skills", project / ".agents" / "skills"]
    measured_bytes = 0
    for relative_path in measured_files:
        installed_path = next(
            root / relative_path for root in roots if (root / relative_path).is_file()
        )
        measured_bytes += len(installed_path.read_bytes())
    assert declared_bytes == measured_bytes
    assert "owner: outer, workflow" in listed.output


def test_dual_role_unit_reports_all_routes_but_gates_one_delivery_variant(
    tmp_path: Path,
) -> None:
    config = _workspace(tmp_path)
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    payload["skill_loading_units"][1]["publish_to"] = "style"
    config.write_text(yaml.safe_dump(payload), encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()

    shown = _run(
        home,
        "loading-unit",
        "show",
        "style-batch",
        "-c",
        str(config),
        "--agent",
        "codex",
    )
    listed = _run(home, "loading-unit", "list", "-c", str(config), "--agent", "codex")

    assert shown.exit_code == 0, shown.output
    assert "publication-owner: style" in shown.output
    assert "publication-owner: workflow" in shown.output
    assert "route-manifest: style/routes/style-batch.md" in shown.output
    assert "batch-manifest: workflow/routes/batches/style-batch.md" in shown.output
    measured_files = re.findall(r"^file: (.+)$", shown.output, flags=re.MULTILINE)
    delivery_files = [path for path in measured_files if "/routes/" in path]
    assert len(delivery_files) == 1
    assert "owner: style, workflow" in listed.output


def test_rollback_attempts_every_target_and_preserves_the_primary_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "value").write_text("first-before", encoding="utf-8")
    (second / "value").write_text("second-before", encoding="utf-8")
    state = tmp_path / "state.json"
    state.write_text("state-before", encoding="utf-8")
    registry = Registry(default_state_dir(tmp_path / "home"))

    with pytest.raises(CommandError, match="primary failure") as captured:
        with skill_write_transaction((first, second), registry, file_paths=(state,)):
            (first / "value").write_text("first-after", encoding="utf-8")
            (second / "value").write_text("second-after", encoding="utf-8")
            state.write_text("state-after", encoding="utf-8")
            original_copytree = synchronization_module.shutil.copytree
            calls = 0

            def fail_first_restore(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError("first restoration failed")
                return original_copytree(*args, **kwargs)

            monkeypatch.setattr(
                synchronization_module.shutil, "copytree", fail_first_restore
            )
            raise CommandError("primary failure")

    assert (first / "value").read_text(encoding="utf-8") == "first-before"
    assert state.read_text(encoding="utf-8") == "state-before"
    notes = getattr(captured.value, "__notes__", [])
    assert any("first restoration failed" in note for note in notes)


def test_loading_unit_list_and_show_fail_when_the_unit_is_over_budget(
    tmp_path: Path,
) -> None:
    config = _workspace(tmp_path)
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    payload["skill_loading_units"][0]["max_bytes"] = 1
    config.write_text(yaml.safe_dump(payload), encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()

    listed = _run(home, "loading-unit", "list", "-c", str(config), "--agent", "codex")
    shown = _run(
        home,
        "loading-unit",
        "show",
        "workflow-batch",
        "-c",
        str(config),
        "--agent",
        "codex",
    )

    assert listed.exit_code == 1
    assert "workflow-batch@codex" in listed.output
    assert shown.exit_code == 1
    assert "bytes:" in shown.output


def test_deployment_lock_prevents_rollback_from_overwriting_a_later_mutator(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    target = home / ".agents" / "skills" / "shared"
    target.mkdir(parents=True)
    entrypoint = target / "SKILL.md"
    entrypoint.write_text("initial\n", encoding="utf-8")
    registry = Registry(default_state_dir(home))
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    errors: list[BaseException] = []

    def first_mutator() -> None:
        try:
            with skill_write_transaction((target,), registry):
                entrypoint.write_text("temporary\n", encoding="utf-8")
                first_entered.set()
                assert release_first.wait(2)
                raise CommandError("rollback first mutator")
        except CommandError:
            return
        except BaseException as exc:  # pragma: no cover - thread diagnostic
            errors.append(exc)

    def second_mutator() -> None:
        try:
            assert first_entered.wait(2)
            with skill_write_transaction((target,), registry):
                second_entered.set()
                entrypoint.write_text("later\n", encoding="utf-8")
        except BaseException as exc:  # pragma: no cover - thread diagnostic
            errors.append(exc)

    first = threading.Thread(target=first_mutator)
    second = threading.Thread(target=second_mutator)
    first.start()
    assert first_entered.wait(2)
    second.start()
    assert not second_entered.wait(0.1)
    release_first.set()
    first.join(2)
    second.join(2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert entrypoint.read_text(encoding="utf-8") == "later\n"


def test_skill_list_does_not_add_route_picker_entries(tmp_path: Path) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    result = _run(home, "list", "-c", str(config))

    assert result.exit_code == 0, result.output
    assert result.output.count("\n-") + result.output.startswith("-") == 2
    assert "section-route" not in result.output


def test_unknown_skill_is_a_concise_error(tmp_path: Path) -> None:
    config = _workspace(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    result = _run(
        home,
        "show",
        "missing",
        "-c",
        str(config),
        "--agent",
        "codex",
    )

    assert result.exit_code == 2
    assert "Error: Unknown skill: 'missing'" in result.output
    assert "Traceback" not in result.output
