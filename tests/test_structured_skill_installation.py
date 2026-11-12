"""Exercise structured Skills through the shared installation boundary."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from eutaxis.commands import (
    CommandError,
    CommandRenderError,
    ArtifactFile,
    OwnershipError,
    Registry,
    diff_artifact,
    get_adapter,
    install_artifact,
    install_artifacts,
    uninstall_command,
)
from eutaxis.declarations import plan_structured_skill, render_structured_skill
from tests.test_structured_skill import _manifest, _pipeline, _procedure


def _rendered_skill(
    tmp_path: Path,
    adapter_name: str,
    *,
    purpose: str | None = None,
    scope: str = "project",
):
    manifest = _manifest()
    manifest["invocation"] = ["user"]
    manifest["scope"] = scope
    procedure = _procedure()
    if purpose is not None:
        procedure["purpose"] = purpose
    _acquisition, resolution = _pipeline(
        tmp_path,
        manifest=manifest,
        procedure=procedure,
    )
    adapter = get_adapter(adapter_name)
    return adapter, render_structured_skill(
        plan_structured_skill(resolution),
        adapter,
        entrypoint_max_bytes=100_000,
        artifact_max_bytes=1_000_000,
    )


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("adapter_name", ("claude", "codex"))
def test_structured_skill_uses_shared_install_diff_and_removal(
    tmp_path: Path,
    adapter_name: str,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    adapter, artifact = _rendered_skill(tmp_path / "source", adapter_name)
    registry = Registry(home / ".eutaxis" / "state")
    target = adapter.artifact_dir(
        artifact.name,
        "project",
        home=home,
        project_root=project,
    )

    created = install_artifact(
        artifact,
        adapter,
        scope="project",
        project_root=project,
        home=home,
        registry=registry,
    )
    assert created.action == "created"
    assert _tree_bytes(target) == {
        file.relative_path: file.content.encode("utf-8") for file in artifact.files
    }

    unchanged = install_artifact(
        artifact,
        adapter,
        scope="project",
        project_root=project,
        home=home,
        registry=registry,
    )
    assert unchanged.action == "unchanged"
    assert (
        diff_artifact(
            artifact,
            adapter,
            scope="project",
            project_root=project,
            home=home,
        )[2]
        == ""
    )

    contract = target / "references" / "contract.md"
    contract.write_text(
        contract.read_text(encoding="utf-8") + "\nlocal drift\n",
        encoding="utf-8",
    )
    assert (
        "local drift"
        in diff_artifact(
            artifact,
            adapter,
            scope="project",
            project_root=project,
            home=home,
        )[2]
    )

    repaired = install_artifact(
        artifact,
        adapter,
        scope="project",
        project_root=project,
        home=home,
        registry=registry,
    )
    assert repaired.action == "updated"

    removed = uninstall_command(
        name=artifact.name,
        adapter=adapter,
        scope="project",
        project_root=project,
        home=home,
        registry=registry,
    )
    assert removed.action == "removed"
    assert not target.exists()
    assert (
        registry.find(
            name=artifact.name,
            adapter=adapter.name,
            scope="project",
            path=target,
        )
        is None
    )


def test_failed_structured_publication_restores_artifact_and_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    adapter, initial = _rendered_skill(tmp_path / "initial", "codex")
    _same_adapter, changed = _rendered_skill(
        tmp_path / "changed",
        "codex",
        purpose="Changed publication purpose.",
    )
    registry = Registry(home / ".eutaxis" / "state")
    target = adapter.artifact_dir(
        initial.name,
        "project",
        home=home,
        project_root=project,
    )
    install_artifact(
        initial,
        adapter,
        scope="project",
        project_root=project,
        home=home,
        registry=registry,
    )
    artifact_before = _tree_bytes(target)
    registry_before = registry.path.read_bytes()

    working_upsert = registry.upsert

    def fail_after_registry_change(record) -> None:
        working_upsert(record)
        raise CommandError("planted publication failure")

    monkeypatch.setattr(registry, "upsert", fail_after_registry_change)

    with pytest.raises(CommandError, match="planted publication failure"):
        install_artifact(
            changed,
            adapter,
            scope="project",
            project_root=project,
            home=home,
            registry=registry,
        )

    assert _tree_bytes(target) == artifact_before
    assert registry.path.read_bytes() == registry_before


def test_structured_batch_install_is_atomic_across_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    initial = tuple(
        _rendered_skill(tmp_path / f"initial-{name}", name)
        for name in ("claude", "codex")
    )
    changed = tuple(
        _rendered_skill(
            tmp_path / f"changed-{name}",
            name,
            purpose="Changed publication purpose.",
        )
        for name in ("claude", "codex")
    )
    registry = Registry(home / ".eutaxis" / "state")
    install_artifacts(
        tuple((artifact, adapter) for adapter, artifact in initial),
        project_root=project,
        home=home,
        registry=registry,
    )
    targets = tuple(
        adapter.artifact_dir(
            artifact.name,
            artifact.scope,
            home=home,
            project_root=project,
        )
        for adapter, artifact in initial
    )
    trees_before = tuple(_tree_bytes(target) for target in targets)
    registry_before = registry.path.read_bytes()
    working_upsert = registry.upsert

    def fail_on_codex(record) -> None:
        working_upsert(record)
        if record.adapter == "codex":
            raise CommandError("planted second-host failure")

    monkeypatch.setattr(registry, "upsert", fail_on_codex)

    with pytest.raises(CommandError, match="planted second-host failure"):
        install_artifacts(
            tuple((artifact, adapter) for adapter, artifact in changed),
            project_root=project,
            home=home,
            registry=registry,
        )

    assert tuple(_tree_bytes(target) for target in targets) == trees_before
    assert registry.path.read_bytes() == registry_before


def test_structured_batch_install_rolls_back_finalized_state(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    batch = tuple(
        (artifact, adapter)
        for adapter, artifact in (
            _rendered_skill(tmp_path / name, name) for name in ("claude", "codex")
        )
    )
    registry = Registry(home / ".eutaxis" / "state")
    state = tmp_path / "sync-manifest.json"
    state.write_text("baseline\n", encoding="utf-8")

    def fail_after_state_write() -> None:
        state.write_text("candidate\n", encoding="utf-8")
        raise CommandError("planted finalization failure")

    with pytest.raises(CommandError, match="planted finalization failure"):
        install_artifacts(
            batch,
            project_root=project,
            home=home,
            registry=registry,
            finalize=fail_after_state_write,
            rollback_files=(state,),
        )

    assert state.read_text(encoding="utf-8") == "baseline\n"
    assert registry.load() == []
    for artifact, adapter in batch:
        assert not adapter.artifact_dir(
            artifact.name,
            artifact.scope,
            home=home,
            project_root=project,
        ).exists()


def test_structured_batch_install_rejects_a_repeated_target(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    adapter, artifact = _rendered_skill(tmp_path / "source", "claude")
    registry = Registry(home / ".eutaxis" / "state")

    with pytest.raises(CommandRenderError, match="repeats target"):
        install_artifacts(
            ((artifact, adapter), (artifact, adapter)),
            project_root=project,
            home=home,
            registry=registry,
        )

    assert registry.load() == []


def test_structured_batch_install_rejects_aliased_adapter_roots(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    codex_root = home / ".agents" / "skills"
    codex_root.mkdir(parents=True)
    claude_parent = home / ".claude"
    claude_parent.mkdir()
    (claude_parent / "skills").symlink_to(codex_root, target_is_directory=True)
    batch = tuple(
        (artifact, adapter)
        for adapter, artifact in (
            _rendered_skill(tmp_path / name, name, scope="personal")
            for name in ("claude", "codex")
        )
    )
    registry = Registry(home / ".eutaxis" / "state")

    with pytest.raises(OwnershipError, match="aliased or overlapping"):
        install_artifacts(
            batch,
            project_root=project,
            home=home,
            registry=registry,
        )

    assert registry.load() == []
    assert not (codex_root / "test-procedure").exists()


def test_failed_structured_removal_restores_artifact_and_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    adapter, artifact = _rendered_skill(tmp_path / "source", "codex")
    registry = Registry(home / ".eutaxis" / "state")
    installed = install_artifact(
        artifact,
        adapter,
        scope="project",
        project_root=project,
        home=home,
        registry=registry,
    )
    artifact_before = _tree_bytes(installed.path)
    registry_before = registry.path.read_bytes()
    working_remove = registry.remove

    def fail_after_registry_change(**kwargs):
        working_remove(**kwargs)
        raise CommandError("planted removal failure")

    monkeypatch.setattr(registry, "remove", fail_after_registry_change)

    with pytest.raises(CommandError, match="planted removal failure"):
        uninstall_command(
            name=artifact.name,
            adapter=adapter,
            scope="project",
            project_root=project,
            home=home,
            registry=registry,
        )

    assert _tree_bytes(installed.path) == artifact_before
    assert registry.path.read_bytes() == registry_before


def test_structured_install_rejects_an_adapter_mismatch(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    _adapter, artifact = _rendered_skill(tmp_path / "source", "claude")

    with pytest.raises(CommandRenderError, match="targets adapter 'claude'"):
        install_artifact(
            artifact,
            get_adapter("codex"),
            scope="project",
            project_root=project,
            home=home,
            registry=Registry(home / ".eutaxis" / "state"),
        )

    assert not (project / ".agents" / "skills" / artifact.name).exists()


@pytest.mark.parametrize(
    ("manifest_scope", "publication_scope"),
    (("project", "user"), ("personal", "project")),
)
def test_structured_install_and_diff_reject_a_scope_mismatch(
    tmp_path: Path,
    manifest_scope: str,
    publication_scope: str,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    adapter, artifact = _rendered_skill(
        tmp_path / "source",
        "claude",
        scope=manifest_scope,
    )
    registry = Registry(home / ".eutaxis" / "state")

    with pytest.raises(CommandRenderError, match="targets scope"):
        install_artifact(
            artifact,
            adapter,
            scope=publication_scope,
            project_root=project,
            home=home,
            registry=registry,
        )
    with pytest.raises(CommandRenderError, match="targets scope"):
        diff_artifact(
            artifact,
            adapter,
            scope=publication_scope,
            project_root=project,
            home=home,
        )

    wrong_target = adapter.artifact_dir(
        artifact.name,
        publication_scope,
        home=home,
        project_root=project,
    )
    assert not wrong_target.exists()
    assert registry.load() == []


def test_personal_structured_skill_publishes_to_user_scope(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    adapter, artifact = _rendered_skill(
        tmp_path / "source",
        "claude",
        scope="personal",
    )

    outcome = install_artifact(
        artifact,
        adapter,
        scope="user",
        project_root=project,
        home=home,
        registry=Registry(home / ".eutaxis" / "state"),
    )

    assert artifact.scope == "user"
    assert outcome.path == home / ".claude" / "skills" / artifact.name


@pytest.mark.parametrize(
    "extra_file",
    (
        ArtifactFile("../../outside.txt", "unsafe\n"),
        ArtifactFile("SKILL.md", "duplicate\n"),
        ArtifactFile("references", "prefix collision\n"),
    ),
)
def test_direct_artifact_paths_are_validated_before_install_and_diff(
    tmp_path: Path,
    extra_file: ArtifactFile,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    adapter, artifact = _rendered_skill(tmp_path / "source", "claude")
    forged = replace(artifact, files=(*artifact.files, extra_file))
    registry = Registry(home / ".eutaxis" / "state")
    outside = tmp_path / "outside.txt"
    outside.write_text("private outside content\n", encoding="utf-8")

    with pytest.raises((CommandRenderError, OwnershipError)):
        diff_artifact(
            forged,
            adapter,
            scope="project",
            project_root=project,
            home=home,
        )
    with pytest.raises((CommandRenderError, OwnershipError)):
        install_artifact(
            forged,
            adapter,
            scope="project",
            project_root=project,
            home=home,
            registry=registry,
        )

    assert not (project / ".claude" / "skills" / artifact.name).exists()
    assert registry.load() == []


def test_direct_artifact_diff_rejects_a_symlink_file(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    adapter, artifact = _rendered_skill(tmp_path / "source", "claude")
    registry = Registry(home / ".eutaxis" / "state")
    outcome = install_artifact(
        artifact,
        adapter,
        scope="project",
        project_root=project,
        home=home,
        registry=registry,
    )
    outside = tmp_path / "outside.txt"
    outside.write_text("private outside content\n", encoding="utf-8")
    contract = outcome.path / "references" / "contract.md"
    contract.unlink()
    contract.symlink_to(outside)

    with pytest.raises(OwnershipError, match="symbolic link"):
        diff_artifact(
            artifact,
            adapter,
            scope="project",
            project_root=project,
            home=home,
        )


def test_direct_artifact_diff_rejects_a_stale_owned_symlink(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    adapter, artifact = _rendered_skill(tmp_path / "source", "claude")
    installed = install_artifact(
        artifact,
        adapter,
        scope="project",
        project_root=project,
        home=home,
        registry=Registry(home / ".eutaxis" / "state"),
    )
    sidecar_path = installed.path / ".eutaxis-owned.json"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["files"].append({"path": "obsolete.md", "sha256": "retired"})
    sidecar_path.write_text(
        json.dumps(sidecar, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    outside = tmp_path / "outside.txt"
    outside.write_text("private outside content\n", encoding="utf-8")
    (installed.path / "obsolete.md").symlink_to(outside)

    with pytest.raises(OwnershipError, match="symbolic link"):
        diff_artifact(
            artifact,
            adapter,
            scope="project",
            project_root=project,
            home=home,
        )
