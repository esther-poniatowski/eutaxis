"""Exercise the private, repeatable Git-submodule transport proof."""

from __future__ import annotations

import copy
import hashlib
import os
import pickle
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Iterator

import pytest

import eutaxis.declarations.git_transport as git_transport_module
from eutaxis.declarations.acquisition_contract import (
    PACKAGED_DECLARATION_PATHS,
    AcquisitionKind,
    AcquisitionLock,
    AcquisitionManifest,
    ExternalSourceLock,
    ExternalSourceManifest,
    FacetConstituentLock,
    FacetExtensionManifest,
    FacetRegistryLock,
    GitLock,
    InternalSourceLock,
    LockedFile,
    composite_facet_content_revision,
    facet_content_revision,
    source_content_revision,
)
from eutaxis.declarations.byte_carriers import TrustedDirectory
from eutaxis.declarations.canonical_json import jcs_bytes
from eutaxis.declarations.exceptions import AcquisitionContractError, ByteCarrierError
from eutaxis.declarations.git_transport import (
    _GitSubmoduleSession,
    _GitTransportEvidence,
    _issued_git_transport_state,
    _open_git_submodule_session,
)


def _git(directory: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ("/usr/bin/git", "-C", str(directory), *arguments),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={
            "HOME": str(directory),
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": "/usr/bin:/bin",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
        },
    ).stdout


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _revision(value: object) -> str:
    return "sha256:" + hashlib.sha256(jcs_bytes(value)).hexdigest()


def _trusted(path: Path) -> Iterator[TrustedDirectory]:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        trusted = TrustedDirectory.from_fd(descriptor, label="workspace")
    finally:
        os.close(descriptor)
    with trusted:
        yield trusted


@pytest.fixture
def git_workspace(tmp_path: Path) -> tuple[Path, GitLock, tuple[tuple[str, str], ...]]:
    return _build_workspace(tmp_path, "sha1")


def _build_workspace(
    tmp_path: Path, object_format: str
) -> tuple[Path, GitLock, tuple[tuple[str, str], ...]]:
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", f"--object-format={object_format}", "-b", "main")
    _git(seed, "config", "user.name", "Test")
    _git(seed, "config", "user.email", "test@example.invalid")
    (seed / "rules").mkdir()
    (seed / "rules" / "main.yaml").write_bytes(b"kind: rule\n")
    (seed / "facets").mkdir()
    (seed / "facets" / "extension.yaml").write_bytes(b"facets: []\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "seed")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", f"--object-format={object_format}", "-b", "main")
    _git(workspace, "config", "user.name", "Test")
    _git(workspace, "config", "user.email", "test@example.invalid")
    _git(
        workspace,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "--name",
        "vendor/library",
        str(seed),
        "vendor/library",
    )
    _git(workspace / "vendor/library", "config", "user.name", "Test")
    _git(
        workspace / "vendor/library",
        "config",
        "user.email",
        "test@example.invalid",
    )
    _git(workspace, "commit", "-m", "register submodule")

    source = workspace / "vendor" / "library"
    commit = _git(source, "rev-parse", "HEAD").decode().strip()
    gitmodules = (workspace / ".gitmodules").read_bytes()
    lock = GitLock(
        object_format=object_format,
        commit=commit,
        gitmodules_path=".gitmodules",
        gitmodules_sha256=_digest(gitmodules),
        registered_name="vendor/library",
        registered_path="vendor/library",
        parent_index_mode="160000",
        parent_index_gitlink=commit,
    )
    files = (
        ("facets/extension.yaml", _digest(b"facets: []\n")),
        ("rules/main.yaml", _digest(b"kind: rule\n")),
    )
    return workspace, lock, files


def _acquire(
    workspace: Path,
    lock: GitLock,
    files: tuple[tuple[str, str], ...],
) -> _GitTransportEvidence:
    manifest, acquisition_lock = _contracts(lock, files)
    for trusted in _trusted(workspace):
        with trusted.retain_directory(lock.registered_path) as source:
            carriers = tuple(source.read_authoritative(path) for path, _digest in files)
            session = _open_git_submodule_session(
                trusted, manifest, acquisition_lock, 0
            )
            session.bind_worktree_carriers(carriers)
            return session.finish()
    raise AssertionError("trusted workspace did not yield")


def _contracts(
    git: GitLock,
    files: tuple[tuple[str, str], ...],
) -> tuple[AcquisitionManifest, AcquisitionLock]:
    extensions = tuple(item for item in files if item[0].startswith("facets/"))
    declarations = tuple(item for item in files if item not in extensions)
    namespace = "library"
    source_manifest = ExternalSourceManifest(
        namespace,
        AcquisitionKind.GIT_SUBMODULE,
        git.registered_path,
        tuple(path for path, _digest_value in declarations),
    )
    extension_manifests = tuple(
        FacetExtensionManifest(
            namespace,
            AcquisitionKind.GIT_SUBMODULE,
            git.registered_path,
            path,
        )
        for path, _digest_value in extensions
    )
    manifest = AcquisitionManifest(1, extension_manifests, (source_manifest,))

    locked_files = tuple(LockedFile(path, digest) for path, digest in declarations)
    source_content = source_content_revision(namespace, locked_files)
    source_acquisition = _revision(
        {
            "schema-version": 1,
            "namespace": namespace,
            "kind": AcquisitionKind.GIT_SUBMODULE.value,
            "root": git.registered_path,
            "content-revision": source_content,
            "git": _git_document(git),
        }
    )
    source_lock = ExternalSourceLock(
        source_acquisition,
        source_content,
        locked_files,
        AcquisitionKind.GIT_SUBMODULE,
        namespace,
        git,
    )
    extension_locks: list[FacetConstituentLock] = []
    for index, (path, digest) in enumerate(extensions):
        identifier = f"{namespace}/context-facets-{index}"
        content = facet_content_revision(
            identifier,
            namespace,
            namespace,
            path,
            digest,
        )
        acquisition = _revision(
            {
                "schema-version": 1,
                "namespace": namespace,
                "kind": AcquisitionKind.GIT_SUBMODULE.value,
                "root": git.registered_path,
                "path": path,
                "content-revision": content,
                "git": _git_document(git),
            }
        )
        extension_locks.append(
            FacetConstituentLock(
                acquisition,
                content,
                identifier,
                AcquisitionKind.GIT_SUBMODULE.value,
                namespace,
                namespace,
                path,
                digest,
            )
        )

    base_sha = _digest(b"base facets")
    base_content = facet_content_revision(
        "eutaxis/context-facets",
        "eutaxis",
        "eutaxis",
        "registries/context-facets-v1.yaml",
        base_sha,
    )
    base_acquisition = _revision(
        {
            "schema-version": 1,
            "namespace": "eutaxis",
            "kind": "packaged",
            "distribution": "eutaxis",
            "resource-root": "data",
            "path": "registries/context-facets-v1.yaml",
            "content-revision": base_content,
        }
    )
    base = FacetConstituentLock(
        base_acquisition,
        base_content,
        "eutaxis/context-facets",
        "packaged",
        "eutaxis",
        "eutaxis",
        "registries/context-facets-v1.yaml",
        base_sha,
    )
    internal_files = tuple(
        LockedFile(path, _digest(("internal:" + path).encode()))
        for path in PACKAGED_DECLARATION_PATHS
    )
    internal_content = source_content_revision("eutaxis", internal_files)
    internal_acquisition = _revision(
        {
            "schema-version": 1,
            "namespace": "eutaxis",
            "kind": "packaged",
            "distribution": "eutaxis",
            "resource-root": "data/declarations/v1",
            "content-revision": internal_content,
        }
    )
    internal = InternalSourceLock(
        internal_acquisition,
        internal_content,
        internal_files,
        "packaged",
        "eutaxis",
    )
    extension_tuple = tuple(extension_locks)
    registry = FacetRegistryLock(
        base,
        composite_facet_content_revision(
            base_content,
            tuple(item.content_revision for item in extension_tuple),
        ),
        extension_tuple,
    )
    return manifest, AcquisitionLock(registry, internal, 1, (source_lock,))


def _git_document(git: GitLock) -> dict[str, str]:
    return {
        "object-format": git.object_format,
        "commit": git.commit,
        "gitmodules-path": git.gitmodules_path,
        "gitmodules-sha256": git.gitmodules_sha256,
        "registered-name": git.registered_name,
        "registered-path": git.registered_path,
        "parent-index-mode": git.parent_index_mode,
        "parent-index-gitlink": git.parent_index_gitlink,
    }


def _open(
    trusted: TrustedDirectory,
    git: GitLock,
    files: tuple[tuple[str, str], ...],
) -> _GitSubmoduleSession:
    manifest, acquisition_lock = _contracts(git, files)
    return _open_git_submodule_session(trusted, manifest, acquisition_lock, 0)


def test_session_issues_verified_evidence_after_symbolic_head_and_cleanup(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
) -> None:
    workspace, lock, files = git_workspace
    baseline = _fd_count()

    evidence = _acquire(workspace, lock, files)

    state = _issued_git_transport_state(evidence)
    assert state.observation.head_commit == lock.commit
    assert tuple(blob.path for blob in state.observation.blobs) == tuple(
        path for path, _digest in files
    )
    assert len(state.worktree) == len(files)
    assert _fd_count() == baseline


def test_linked_parent_worktree_is_rejected_before_git_queries(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
    tmp_path: Path,
) -> None:
    workspace, lock, files = git_workspace
    linked = tmp_path / "linked"
    _git(workspace, "worktree", "add", "--detach", str(linked), "HEAD")
    (linked / lock.registered_path).mkdir(parents=True, exist_ok=True)

    for trusted in _trusted(linked):
        with pytest.raises(ByteCarrierError):
            _open(trusted, lock, files)


def test_detached_head_and_hostile_inherited_git_environment_are_admitted(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, lock, files = git_workspace
    _git(workspace / "vendor/library", "checkout", "--detach", lock.commit)
    monkeypatch.setenv("GIT_DIR", "/tmp/hostile")
    monkeypatch.setenv("GIT_OBJECT_DIRECTORY", "/tmp/objects")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "include.path")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "/tmp/hostile")

    evidence = _acquire(workspace, lock, files)

    assert _issued_git_transport_state(evidence).observation.head_commit == lock.commit


def test_sha256_repositories_and_real_v4_parent_index_are_admitted(
    tmp_path: Path,
) -> None:
    workspace, lock, files = _build_workspace(tmp_path, "sha256")
    _git(workspace, "update-index", "--index-version=4")

    evidence = _acquire(workspace, lock, files)

    state = _issued_git_transport_state(evidence)
    assert state.observation.parent_index.version == 4
    assert state.observation.parent_config.object_format == "sha256"


def test_staged_parent_gitlink_update_is_admitted_without_parent_commit(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
) -> None:
    workspace, lock, files = git_workspace
    source = workspace / "vendor/library"
    changed = b"kind: rule\nsummary: staged\n"
    (source / "rules/main.yaml").write_bytes(changed)
    _git(source, "add", "rules/main.yaml")
    _git(source, "commit", "-m", "update declaration")
    commit = _git(source, "rev-parse", "HEAD").decode().strip()
    _git(workspace, "add", "vendor/library")
    lock = replace(lock, commit=commit, parent_index_gitlink=commit)
    files = (files[0], ("rules/main.yaml", _digest(changed)))

    evidence = _acquire(workspace, lock, files)

    assert _issued_git_transport_state(evidence).observation.head_commit == commit


def test_dirty_listed_worktree_file_is_rejected_at_binding(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
) -> None:
    workspace, lock, files = git_workspace
    (workspace / "vendor/library/rules/main.yaml").write_bytes(b"changed\n")

    for trusted in _trusted(workspace):
        with trusted.retain_directory(lock.registered_path) as source:
            carriers = tuple(source.read_authoritative(path) for path, _digest in files)
            session = _open(trusted, lock, files)
            with pytest.raises(AcquisitionContractError, match="locked file"):
                session.bind_worktree_carriers(carriers)
            session.close()


def test_carrier_from_another_root_cannot_be_spliced_into_session(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
) -> None:
    workspace, lock, files = git_workspace
    other = workspace / "other"
    (other / "facets").mkdir(parents=True)
    (other / "rules").mkdir()
    (other / "facets/extension.yaml").write_bytes(b"facets: []\n")
    (other / "rules/main.yaml").write_bytes(b"kind: rule\n")

    for trusted in _trusted(workspace):
        with trusted.retain_directory("other") as wrong_root:
            carriers = tuple(
                wrong_root.read_authoritative(path) for path, _digest_value in files
            )
            session = _open(trusted, lock, files)
            with pytest.raises(AcquisitionContractError, match="another source root"):
                session.bind_worktree_carriers(carriers)
            session.close()


def test_mutation_between_binding_and_finish_fails_and_closes_session(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
) -> None:
    workspace, lock, files = git_workspace
    baseline = _fd_count()

    for trusted in _trusted(workspace):
        with trusted.retain_directory(lock.registered_path) as source:
            carriers = tuple(source.read_authoritative(path) for path, _digest in files)
            session = _open(trusted, lock, files)
            session.bind_worktree_carriers(carriers)
            (workspace / "vendor/library/rules/main.yaml").write_bytes(b"changed\n")
            with pytest.raises(ByteCarrierError, match="verification"):
                session.finish()
            with pytest.raises(AcquisitionContractError, match="closed"):
                session.finish()

    assert _fd_count() == baseline


def test_source_contract_mutation_between_phases_retires_session(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
) -> None:
    workspace, lock, files = git_workspace
    manifest, acquisition_lock = _contracts(lock, files)
    source_lock = acquisition_lock.sources[0]

    for trusted in _trusted(workspace):
        with trusted.retain_directory(lock.registered_path) as source:
            carriers = tuple(source.read_authoritative(path) for path, _digest in files)
            session = _open_git_submodule_session(
                trusted, manifest, acquisition_lock, 0
            )
            session.bind_worktree_carriers(carriers)
            object.__setattr__(source_lock, "namespace", "changed")
            with pytest.raises(AcquisitionContractError, match="contract state"):
                session.finish()
            with pytest.raises(AcquisitionContractError, match="closed"):
                session.finish()


def test_complete_contract_prevents_partial_extension_and_wrong_source_selection(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
) -> None:
    workspace, lock, files = git_workspace
    manifest, acquisition_lock = _contracts(lock, files)
    partial = replace(manifest, facet_extensions=())

    for trusted in _trusted(workspace):
        with pytest.raises(AcquisitionContractError, match="extension count"):
            _open_git_submodule_session(trusted, partial, acquisition_lock, 0)
        with pytest.raises(AcquisitionContractError, match="source position"):
            _open_git_submodule_session(trusted, manifest, acquisition_lock, 1)


@pytest.mark.parametrize(
    "config_key, config_value",
    (
        ("core.hooksPath", "/tmp/hooks"),
        ("core.fsmonitor", "/tmp/watch"),
        ("extensions.partialClone", "origin"),
        ("remote.origin.promisor", "true"),
    ),
)
def test_active_or_redirecting_nested_config_is_rejected(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
    config_key: str,
    config_value: str,
) -> None:
    workspace, lock, files = git_workspace
    _git(workspace / "vendor/library", "config", config_key, config_value)

    for trusted in _trusted(workspace):
        with pytest.raises(AcquisitionContractError, match="forbidden"):
            _open(trusted, lock, files)


@pytest.mark.parametrize(
    "config_key, config_value",
    (
        ("alias.pwn", "!run-command"),
        ("credential.https://example.invalid.helper", "!helper"),
        ("submodule.library.update", "!run-command"),
        ("browser.tool.cmd", "run-command"),
    ),
)
def test_command_bearing_nested_config_families_are_rejected(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
    config_key: str,
    config_value: str,
) -> None:
    workspace, lock, files = git_workspace
    _git(workspace / "vendor/library", "config", config_key, config_value)

    for trusted in _trusted(workspace):
        with pytest.raises(AcquisitionContractError, match="forbidden"):
            _open(trusted, lock, files)


@pytest.mark.parametrize("repository", ("parent", "nested"))
def test_external_helper_urls_in_retained_repository_configs_are_rejected(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
    repository: str,
) -> None:
    workspace, lock, files = git_workspace
    target = workspace if repository == "parent" else workspace / "vendor/library"
    _git(target, "config", "remote.hostile.url", "hostile://payload")

    for trusted in _trusted(workspace):
        with pytest.raises(AcquisitionContractError, match="external-helper"):
            _open(trusted, lock, files)


def test_external_helper_url_in_gitmodules_is_rejected(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
) -> None:
    workspace, lock, files = git_workspace
    _git(
        workspace,
        "config",
        "-f",
        ".gitmodules",
        "submodule.vendor/library.url",
        "hostile://payload",
    )
    _git(workspace, "add", ".gitmodules")
    lock = replace(
        lock,
        gitmodules_sha256=_digest((workspace / ".gitmodules").read_bytes()),
    )

    for trusted in _trusted(workspace):
        with pytest.raises(AcquisitionContractError, match="external-helper"):
            _open(trusted, lock, files)


def test_alternate_object_store_is_rejected_and_failed_open_cleans_up(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
) -> None:
    workspace, lock, files = git_workspace
    alternates = workspace / ".git/modules/vendor/library/objects/info/alternates"
    alternates.write_text("/tmp/objects\n")
    baseline = _fd_count()

    for trusted in _trusted(workspace):
        with pytest.raises(AcquisitionContractError, match="redirecting metadata"):
            _open(trusted, lock, files)

    assert _fd_count() == baseline


@pytest.mark.parametrize(
    "repository, relative_path",
    (
        ("nested", "objects/aa"),
        ("nested", "objects/pack"),
        ("parent", "objects/pack"),
    ),
)
def test_symbolic_links_anywhere_in_used_object_stores_are_rejected(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
    tmp_path: Path,
    repository: str,
    relative_path: str,
) -> None:
    workspace, lock, files = git_workspace
    git_directory = (
        workspace / ".git/modules/vendor/library"
        if repository == "nested"
        else workspace / ".git"
    )
    target = git_directory / relative_path
    target.mkdir(parents=True, exist_ok=True)
    external = tmp_path / f"external-{repository}-{target.name}"
    target.rename(external)
    target.symlink_to(external, target_is_directory=True)

    for trusted in _trusted(workspace):
        with pytest.raises(AcquisitionContractError, match="symbolic links"):
            _open(trusted, lock, files)


def test_gitlink_head_and_lock_must_be_identical(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
) -> None:
    workspace, lock, files = git_workspace
    mismatched = replace(lock, commit="a" * 40, parent_index_gitlink="a" * 40)

    for trusted in _trusted(workspace):
        with pytest.raises(AcquisitionContractError, match="differ"):
            _open(trusted, mismatched, files)


def test_unstaged_gitmodules_change_is_rejected(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
) -> None:
    workspace, lock, files = git_workspace
    gitmodules = workspace / ".gitmodules"
    gitmodules.write_bytes(gitmodules.read_bytes() + b"\n")

    for trusted in _trusted(workspace):
        with pytest.raises(AcquisitionContractError, match="digest differs"):
            _open(trusted, lock, files)


def test_missing_committed_path_is_rejected_before_binding(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
) -> None:
    workspace, lock, _files = git_workspace
    files = (("rules/missing.yaml", _digest(b"missing")),)

    for trusted in _trusted(workspace):
        with pytest.raises(AcquisitionContractError, match="tree query"):
            _open(trusted, lock, files)


@pytest.mark.parametrize("detached", (False, True))
def test_malformed_present_packed_refs_is_rejected_for_every_head_form(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
    detached: bool,
) -> None:
    workspace, lock, files = git_workspace
    if detached:
        _git(workspace / "vendor/library", "checkout", "--detach", lock.commit)
    packed = workspace / ".git/modules/vendor/library/packed-refs"
    packed.write_bytes(b"# pack-refs with: unknown-trait \n")

    for trusted in _trusted(workspace):
        with pytest.raises(AcquisitionContractError, match="trait"):
            _open(trusted, lock, files)


def test_fork_failure_closes_every_borrowed_descriptor(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, lock, files = git_workspace
    baseline = _fd_count()

    def fail_fork() -> int:
        raise OSError("planted fork failure")

    monkeypatch.setattr(git_transport_module.os, "fork", fail_fork)
    for trusted in _trusted(workspace):
        with pytest.raises(OSError, match="planted fork failure"):
            _open(trusted, lock, files)

    assert _fd_count() == baseline


@pytest.mark.parametrize("failure", ("create", "write", "seek"))
def test_temporary_file_setup_failure_occurs_before_descriptor_borrow(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    workspace, lock, files = git_workspace
    baseline = _fd_count()
    original = git_transport_module.tempfile.TemporaryFile
    calls = 0

    class FailingTemporaryFile:
        def __init__(self) -> None:
            self.file = original()

        def __enter__(self) -> FailingTemporaryFile:
            return self

        def __exit__(self, *_args: object) -> None:
            self.file.close()

        def write(self, value: bytes) -> int:
            if failure == "write":
                raise OSError("planted temporary write failure")
            return self.file.write(value)

        def seek(self, offset: int) -> int:
            if failure == "seek":
                raise OSError("planted temporary seek failure")
            return self.file.seek(offset)

        def fileno(self) -> int:
            return self.file.fileno()

    def temporary_file() -> object:
        nonlocal calls
        calls += 1
        if failure == "create" and calls == 1:
            raise OSError("planted temporary create failure")
        if calls == 1:
            return FailingTemporaryFile()
        return original()

    monkeypatch.setattr(git_transport_module.tempfile, "TemporaryFile", temporary_file)
    for trusted in _trusted(workspace):
        with pytest.raises(OSError, match="planted temporary"):
            _open(trusted, lock, files)

    assert _fd_count() == baseline


def test_interrupted_wait_kills_and_reaps_child_and_closes_descriptors(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, lock, files = git_workspace
    baseline = _fd_count()

    def interrupt_wait(_process: int) -> int:
        raise KeyboardInterrupt("planted wait interruption")

    monkeypatch.setattr(git_transport_module, "_wait_for_process", interrupt_wait)
    for trusted in _trusted(workspace):
        with pytest.raises(KeyboardInterrupt, match="planted wait interruption"):
            _open(trusted, lock, files)

    with pytest.raises(ChildProcessError):
        os.waitpid(-1, os.WNOHANG)
    assert _fd_count() == baseline


def test_symlink_committed_path_is_rejected_before_worktree_binding(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
) -> None:
    workspace, lock, _files = git_workspace
    source = workspace / "vendor/library"
    (source / "rules/link.yaml").symlink_to("main.yaml")
    _git(source, "add", "rules/link.yaml")
    _git(source, "commit", "-m", "add link")
    commit = _git(source, "rev-parse", "HEAD").decode().strip()
    _git(workspace, "add", "vendor/library")
    lock = replace(lock, commit=commit, parent_index_gitlink=commit)
    files = (("rules/link.yaml", _digest(b"main.yaml")),)

    for trusted in _trusted(workspace):
        with pytest.raises(AcquisitionContractError, match="regular blob"):
            _open(trusted, lock, files)


def test_sessions_and_evidence_reject_direct_construction_copy_and_pickle(
    git_workspace: tuple[Path, GitLock, tuple[tuple[str, str], ...]],
) -> None:
    workspace, lock, files = git_workspace
    evidence = _acquire(workspace, lock, files)

    with pytest.raises(TypeError):
        _GitSubmoduleSession()
    with pytest.raises(TypeError):
        _GitTransportEvidence()
    with pytest.raises(TypeError):
        copy.copy(evidence)
    with pytest.raises(TypeError):
        copy.deepcopy(evidence)
    with pytest.raises(TypeError):
        pickle.dumps(evidence)
    with pytest.raises(AcquisitionContractError, match="not issued"):
        _issued_git_transport_state(object.__new__(_GitTransportEvidence))


def _fd_count() -> int:
    return len(os.listdir("/dev/fd"))
