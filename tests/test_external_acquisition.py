"""Exercise the private external acquisition boundary."""

from __future__ import annotations

import copy
import hashlib
import os
import pickle
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

import eutaxis.declarations.external_acquisition as acquisition_module
import eutaxis.declarations.composite_facets as composite_module
import eutaxis.declarations as declarations_api
from eutaxis import data_path
from eutaxis.declarations.acquisition_contract import (
    PACKAGED_DECLARATION_PATHS,
    AcquisitionKind,
    AcquisitionLock,
    ExternalSourceLock,
    FacetConstituentLock,
    FacetRegistryLock,
    GitLock,
    LockedFile,
    LockedResource,
    _lock_document,
    composite_facet_content_revision,
    facet_content_revision,
    source_content_revision,
)
from eutaxis.declarations.canonical_json import jcs_bytes
from eutaxis.declarations.byte_carriers import RetainedDirectory, TrustedDirectory
from eutaxis.declarations.exceptions import (
    AcquisitionContractError,
    ByteCarrierError,
    DeclarationSemanticError,
)
from eutaxis.declarations.git_transport import _issued_git_transport_state
from eutaxis.declarations.external_acquisition import (
    _EVIDENCE_AUTHORITIES,
    _FinalEvidenceState,
    _ExternalAcquisitionStage,
    _acquire_external_stage_from_path,
    _issued_external_stage_state,
)
from tests.test_packaged_source import _valid_lock


def _digest(source: bytes) -> str:
    return "sha256:" + hashlib.sha256(source).hexdigest()


def _revision(value: object) -> str:
    return "sha256:" + hashlib.sha256(jcs_bytes(value)).hexdigest()


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


def _facet_source(namespace: str) -> bytes:
    return (
        "_schema: eutaxis:context-facets@1\n"
        f"id: {namespace}/context-facets\n"
        f"owner: {namespace}\n"
        "source-revision: fixture-1\n"
        "facets:\n"
        f"  - id: {namespace}.enabled\n"
        "    value-schema: {type: boolean}\n"
    ).encode()


def _declaration_source(namespace: str, *, facet: str | None = None) -> bytes:
    facet_id = facet or f"{namespace}.enabled"
    return (
        "_schema: eutaxis:declaration@1\n"
        f"id: {namespace}/reader-purpose\n"
        "kind: rule\n"
        f"owner: {namespace}\n"
        "status: active\n"
        "source-revision: fixture-1\n"
        f"applicability: {{facet: {facet_id}, operator: equals, value: true}}\n"
        "relations: []\n"
        "axis: reasoning-target\n"
        "failure-mode: visible\n"
        "norms:\n"
        "  - id: state-purpose\n"
        "    modality: must\n"
        "    subject: agent\n"
        "    action: {verb: state, object: the reader-facing purpose}\n"
        "criteria:\n"
        "  - id: purpose-is-explicit\n"
        "    norms: [state-purpose]\n"
        "    evaluator: {id: eutaxis/manual-judgment, version: 1}\n"
        "    statement: The artifact states a reader-facing purpose\n"
    ).encode()


def _write_contract(
    workspace: Path,
    *,
    kind: AcquisitionKind = AcquisitionKind.WORKSPACE,
    root: str = ".",
    namespace: str = "oikos",
    git: GitLock | None = None,
    declaration_bytes: bytes | None = None,
    declaration_files: tuple[tuple[str, bytes], ...] | None = None,
    resource_files: tuple[tuple[str, str, str, bytes], ...] = (),
    facet_bytes: bytes | None = None,
) -> tuple[str, str]:
    source_root = workspace if root == "." else workspace / root
    (source_root / "declarations").mkdir(parents=True, exist_ok=True)
    facet_path = "declarations/context-facets.yaml"
    facet_bytes = facet_bytes or _facet_source(namespace)
    if declaration_files is None:
        declaration_files = (
            (
                "declarations/process-core.yaml",
                (
                    declaration_bytes
                    if declaration_bytes is not None
                    else _declaration_source(namespace)
                ),
            ),
        )
    (source_root / facet_path).write_bytes(facet_bytes)
    for declaration_path, source in declaration_files:
        (source_root / declaration_path).parent.mkdir(parents=True, exist_ok=True)
        (source_root / declaration_path).write_bytes(source)
    for _resource_id, resource_path, _media_type, source in resource_files:
        (source_root / resource_path).parent.mkdir(parents=True, exist_ok=True)
        (source_root / resource_path).write_bytes(source)

    facet_sha = _digest(facet_bytes)
    facet_content = facet_content_revision(
        f"{namespace}/context-facets",
        namespace,
        namespace,
        facet_path,
        facet_sha,
    )
    facet_payload: dict[str, object] = {
        "schema-version": 1,
        "namespace": namespace,
        "kind": kind.value,
        "root": root,
        "path": facet_path,
        "content-revision": facet_content,
    }
    if git is not None:
        facet_payload["git"] = _git_document(git)
    facet_acquisition = _revision(facet_payload)
    extension = FacetConstituentLock(
        facet_acquisition,
        facet_content,
        f"{namespace}/context-facets",
        kind.value,
        namespace,
        namespace,
        facet_path,
        facet_sha,
    )
    locked_files = tuple(
        LockedFile(declaration_path, _digest(source))
        for declaration_path, source in declaration_files
    )
    locked_resources = tuple(
        LockedResource(resource_id, path, media_type, _digest(source))
        for resource_id, path, media_type, source in resource_files
    )
    source_content = source_content_revision(
        namespace,
        locked_files,
        locked_resources,
    )
    source_payload: dict[str, object] = {
        "schema-version": 1,
        "namespace": namespace,
        "kind": kind.value,
        "root": root,
        "content-revision": source_content,
    }
    if git is not None:
        source_payload["git"] = _git_document(git)
    source_acquisition = _revision(source_payload)
    external = ExternalSourceLock(
        source_acquisition,
        source_content,
        locked_files,
        kind,
        namespace,
        git,
        locked_resources,
    )
    packaged = _valid_lock(data_path())
    lock = AcquisitionLock(
        FacetRegistryLock(
            packaged.facet_registry.base,
            composite_facet_content_revision(
                packaged.facet_registry.base.content_revision,
                (facet_content,),
            ),
            (extension,),
        ),
        packaged.internal_source,
        1,
        (external,),
    )
    manifest = {
        "schema-version": 1,
        "facet-extensions": [
            {
                "namespace": namespace,
                "kind": kind.value,
                "root": root,
                "path": facet_path,
            }
        ],
        "internal-source": {"namespace": "eutaxis", "kind": "packaged"},
        "sources": [
            {
                "namespace": namespace,
                "kind": kind.value,
                "root": root,
                "files": [path for path, _source in declaration_files],
                **(
                    {
                        "resources": [
                            {
                                "id": resource_id,
                                "path": path,
                                "media-type": media_type,
                            }
                            for resource_id, path, media_type, _source in resource_files
                        ]
                    }
                    if resource_files
                    else {}
                ),
            }
        ],
    }
    manifest_path = "acquisition.yaml"
    lock_path = "acquisition.lock.json"
    (workspace / manifest_path).write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    (workspace / lock_path).write_bytes(jcs_bytes(_lock_document(lock)))
    return manifest_path, lock_path


def _write_multi_contract(
    workspace: Path,
    specs: tuple[tuple[str, AcquisitionKind, str], ...],
    *,
    extension_order: tuple[str, ...],
    git_by_namespace: dict[str, GitLock] | None = None,
) -> tuple[str, str]:
    git_by_namespace = git_by_namespace or {}
    packaged = _valid_lock(data_path())
    source_manifests: list[dict[str, object]] = []
    source_locks: list[ExternalSourceLock] = []
    extensions_by_namespace: dict[
        str, tuple[dict[str, object], FacetConstituentLock]
    ] = {}
    for namespace, kind, root in specs:
        git = git_by_namespace.get(namespace)
        source_root = workspace if root == "." else workspace / root
        (source_root / "declarations").mkdir(parents=True, exist_ok=True)
        declaration_path = "declarations/process-core.yaml"
        declaration_bytes = _declaration_source(
            namespace,
            facet=(
                f"{namespace}.enabled"
                if namespace in extension_order
                else "artifact.created"
            ),
        )
        (source_root / declaration_path).write_bytes(declaration_bytes)
        locked_file = LockedFile(declaration_path, _digest(declaration_bytes))
        source_content = source_content_revision(namespace, (locked_file,))
        source_payload: dict[str, object] = {
            "schema-version": 1,
            "namespace": namespace,
            "kind": kind.value,
            "root": root,
            "content-revision": source_content,
        }
        if git is not None:
            source_payload["git"] = _git_document(git)
        source_acquisition = _revision(source_payload)
        source_locks.append(
            ExternalSourceLock(
                source_acquisition,
                source_content,
                (locked_file,),
                kind,
                namespace,
                git,
            )
        )
        source_manifests.append(
            {
                "namespace": namespace,
                "kind": kind.value,
                "root": root,
                "files": [declaration_path],
            }
        )
        if namespace in extension_order:
            facet_path = "declarations/context-facets.yaml"
            facet_bytes = _facet_source(namespace)
            (source_root / facet_path).write_bytes(facet_bytes)
            facet_sha = _digest(facet_bytes)
            content = facet_content_revision(
                f"{namespace}/context-facets",
                namespace,
                namespace,
                facet_path,
                facet_sha,
            )
            extension_payload: dict[str, object] = {
                "schema-version": 1,
                "namespace": namespace,
                "kind": kind.value,
                "root": root,
                "path": facet_path,
                "content-revision": content,
            }
            if git is not None:
                extension_payload["git"] = _git_document(git)
            acquisition = _revision(extension_payload)
            extensions_by_namespace[namespace] = (
                {
                    "namespace": namespace,
                    "kind": kind.value,
                    "root": root,
                    "path": facet_path,
                },
                FacetConstituentLock(
                    acquisition,
                    content,
                    f"{namespace}/context-facets",
                    kind.value,
                    namespace,
                    namespace,
                    facet_path,
                    facet_sha,
                ),
            )
    extension_pairs = tuple(
        extensions_by_namespace[namespace] for namespace in extension_order
    )
    extension_locks = tuple(item[1] for item in extension_pairs)
    lock = AcquisitionLock(
        FacetRegistryLock(
            packaged.facet_registry.base,
            composite_facet_content_revision(
                packaged.facet_registry.base.content_revision,
                tuple(item.content_revision for item in extension_locks),
            ),
            extension_locks,
        ),
        packaged.internal_source,
        1,
        tuple(source_locks),
    )
    manifest = {
        "schema-version": 1,
        "facet-extensions": [item[0] for item in extension_pairs],
        "internal-source": {"namespace": "eutaxis", "kind": "packaged"},
        "sources": source_manifests,
    }
    manifest_path = "acquisition.yaml"
    lock_path = "acquisition.lock.json"
    (workspace / manifest_path).write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    (workspace / lock_path).write_bytes(jcs_bytes(_lock_document(lock)))
    return manifest_path, lock_path


def _build_git_workspace(
    tmp_path: Path,
    specs: tuple[tuple[str, str, bool], ...],
) -> tuple[Path, dict[str, GitLock]]:
    """Build a parent repository with valid declaration submodules."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "--object-format=sha1", "-b", "main")
    _git(workspace, "config", "user.name", "Test")
    _git(workspace, "config", "user.email", "test@example.invalid")
    for namespace, root, has_extension in specs:
        seed = tmp_path / f"seed-{namespace}"
        seed.mkdir()
        _git(seed, "init", "--object-format=sha1", "-b", "main")
        _git(seed, "config", "user.name", "Test")
        _git(seed, "config", "user.email", "test@example.invalid")
        declarations = seed / "declarations"
        declarations.mkdir()
        facet = f"{namespace}.enabled" if has_extension else "artifact.created"
        (declarations / "process-core.yaml").write_bytes(
            _declaration_source(namespace, facet=facet)
        )
        if has_extension:
            (declarations / "context-facets.yaml").write_bytes(_facet_source(namespace))
        _git(seed, "add", ".")
        _git(seed, "commit", "-m", "seed declarations")
        _git(
            workspace,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "--name",
            root,
            str(seed),
            root,
        )
    _git(workspace, "commit", "-m", "register declaration submodules")
    gitmodules_sha256 = _digest((workspace / ".gitmodules").read_bytes())
    locks: dict[str, GitLock] = {}
    for namespace, root, _has_extension in specs:
        commit = _git(workspace / root, "rev-parse", "HEAD").decode().strip()
        locks[namespace] = GitLock(
            object_format="sha1",
            commit=commit,
            gitmodules_path=".gitmodules",
            gitmodules_sha256=gitmodules_sha256,
            registered_name=root,
            registered_path=root,
            parent_index_mode="160000",
            parent_index_gitlink=commit,
        )
    return workspace, locks


@pytest.mark.parametrize(
    ("kind", "root"),
    [
        (AcquisitionKind.WORKSPACE, "."),
        (AcquisitionKind.VENDORED, "vendor/oikos"),
    ],
)
def test_external_stage_retains_one_verified_contract(
    tmp_path: Path,
    kind: AcquisitionKind,
    root: str,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path, kind=kind, root=root)
    baseline = len(os.listdir("/dev/fd"))

    stage = _acquire_external_stage_from_path(
        str(tmp_path),
        manifest_path,
        lock_path,
    )
    state = _issued_external_stage_state(stage)

    assert len(os.listdir("/dev/fd")) == baseline
    assert state.composite.authority_for("oikos.enabled").id == ("oikos/context-facets")
    assert len(state.declarations) == 6
    assert type(_EVIDENCE_AUTHORITIES.state(state.evidence)) is _FinalEvidenceState
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(stage)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(stage)
    with pytest.raises(TypeError, match="must be issued"):
        _ExternalAcquisitionStage()


def test_workspace_path_may_be_relative_dot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    monkeypatch.chdir(tmp_path)

    stage = _acquire_external_stage_from_path(
        ".",
        manifest_path,
        lock_path,
    )

    assert len(_issued_external_stage_state(stage).declarations) == 6


def test_acquisition_authorizes_every_packaged_and_external_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    original = acquisition_module._validate_external_declaration_semantics
    original_parse = acquisition_module.load_declaration_source_bytes
    calls: list[tuple[str, str]] = []
    events: list[str] = []

    def parse(*args, **kwargs):
        events.append("parse")
        return original_parse(*args, **kwargs)

    def record(source, namespace, location):
        events.append("authorize")
        calls.append((namespace, location))
        return original(source, namespace, location)

    monkeypatch.setattr(acquisition_module, "load_declaration_source_bytes", parse)
    monkeypatch.setattr(
        acquisition_module,
        "_validate_external_declaration_semantics",
        record,
    )

    _acquire_external_stage_from_path(str(tmp_path), manifest_path, lock_path)

    assert events == ["parse"] * len(calls) + ["authorize"] * len(calls)
    assert calls == [
        *(
            ("eutaxis", f"$.internal-source.files[{index}]")
            for index, _path in enumerate(PACKAGED_DECLARATION_PATHS)
        ),
        ("oikos", "$.sources[0].files[0]"),
    ]


def test_acquisition_rejects_external_namespace_impersonation(tmp_path: Path) -> None:
    source = _declaration_source("oikos").replace(
        b"id: oikos/reader-purpose",
        b"id: other/reader-purpose",
    )
    manifest_path, lock_path = _write_contract(
        tmp_path,
        declaration_bytes=source,
    )

    with pytest.raises(
        AcquisitionContractError,
        match="identifier namespace differs",
    ) as raised:
        _acquire_external_stage_from_path(str(tmp_path), manifest_path, lock_path)

    assert raised.value.location == "$.sources[0].files[0].id"


def test_later_intrinsic_failure_precedes_earlier_authorization_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    original_parse = acquisition_module.load_declaration_source_bytes
    parse_count = 0
    authorization_count = 0

    def parse(*args, **kwargs):
        nonlocal parse_count
        declaration = original_parse(*args, **kwargs)
        parse_count += 1
        if parse_count == 1:
            object.__setattr__(declaration.declaration, "id", "other/impersonation")
        if parse_count == len(PACKAGED_DECLARATION_PATHS) + 1:
            raise DeclarationSemanticError(
                declaration.path,
                "$.later-field",
                "injected later intrinsic failure",
            )
        return declaration

    monkeypatch.setattr(acquisition_module, "load_declaration_source_bytes", parse)
    original_authorize = acquisition_module._validate_external_declaration_semantics

    def count_authorization(*args, **kwargs):
        nonlocal authorization_count
        authorization_count += 1
        return original_authorize(*args, **kwargs)

    monkeypatch.setattr(
        acquisition_module,
        "_validate_external_declaration_semantics",
        count_authorization,
    )

    with pytest.raises(
        DeclarationSemanticError,
        match="injected later intrinsic failure",
    ):
        _acquire_external_stage_from_path(str(tmp_path), manifest_path, lock_path)

    assert parse_count == len(PACKAGED_DECLARATION_PATHS) + 1
    assert authorization_count == 0


def test_zero_extensions_preserves_the_packaged_composite(
    tmp_path: Path,
) -> None:
    manifest_path, lock_path = _write_multi_contract(
        tmp_path,
        specs=(("oikos", AcquisitionKind.WORKSPACE, "."),),
        extension_order=(),
    )

    stage = _acquire_external_stage_from_path(str(tmp_path), manifest_path, lock_path)
    state = _issued_external_stage_state(stage)

    assert state.composite.authority_for("artifact.created").id == (
        "eutaxis/context-facets"
    )
    assert len(state.composite.facets) == len(
        state.composite.authority_for("artifact.created").facets
    )


def test_source_and_extension_orders_remain_independent(
    tmp_path: Path,
) -> None:
    manifest_path, lock_path = _write_multi_contract(
        tmp_path,
        specs=(
            ("oikos", AcquisitionKind.WORKSPACE, "."),
            ("hermeneia", AcquisitionKind.VENDORED, "vendor/hermeneia"),
        ),
        extension_order=("hermeneia", "oikos"),
    )

    stage = _acquire_external_stage_from_path(str(tmp_path), manifest_path, lock_path)
    state = _issued_external_stage_state(stage)

    assert tuple(
        state.composite.authority_for(facet).id
        for facet in ("hermeneia.enabled", "oikos.enabled")
    ) == ("hermeneia/context-facets", "oikos/context-facets")
    assert tuple(item.declaration.id for item in state.declarations[-2:]) == (
        "oikos/reader-purpose",
        "hermeneia/reader-purpose",
    )


def test_global_phase_order_establishes_roots_facets_reads_and_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    events: list[tuple[str, str]] = []
    original_retain = TrustedDirectory.retain_directory
    original_read = RetainedDirectory.read_authoritative
    original_verify = RetainedDirectory.verify

    def recording_retain(self: TrustedDirectory, path: str):
        events.append(("open", path))
        return original_retain(self, path)

    def recording_read(self: RetainedDirectory, path: str):
        events.append(("read", path))
        return original_read(self, path)

    def recording_verify(self: RetainedDirectory, carrier):
        events.append(("verify", carrier.path))
        return original_verify(self, carrier)

    monkeypatch.setattr(TrustedDirectory, "retain_directory", recording_retain)
    monkeypatch.setattr(RetainedDirectory, "read_authoritative", recording_read)
    monkeypatch.setattr(RetainedDirectory, "verify", recording_verify)

    _acquire_external_stage_from_path(str(tmp_path), manifest_path, lock_path)

    base_read = events.index(("read", "registries/context-facets-v1.yaml"))
    assert ("open", "data") in events[:base_read]
    assert ("open", "data/declarations/v1") in events[:base_read]
    assert events[:base_read].count(("open", ".")) >= 2
    extension_read = events.index(("read", "declarations/context-facets.yaml"))
    external_declaration_read = events.index(("read", "declarations/process-core.yaml"))
    assert base_read < extension_read < external_declaration_read
    assert max(index for index, event in enumerate(events) if event[0] == "read") < min(
        index for index, event in enumerate(events) if event[0] == "verify"
    )


def test_provisional_composite_is_limited_to_the_parsing_view(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    original_parse = acquisition_module._parse_all_declarations
    checked = False

    def checking_parse(packaged, sources, external, parsing_view):
        nonlocal checked
        with pytest.raises(AcquisitionContractError, match="not issued"):
            parsing_view._composite.require_authority()
        parsing_view.require_authority()
        checked = True
        return original_parse(packaged, sources, external, parsing_view)

    monkeypatch.setattr(
        acquisition_module,
        "_parse_all_declarations",
        checking_parse,
    )

    stage = _acquire_external_stage_from_path(str(tmp_path), manifest_path, lock_path)

    assert checked
    _issued_external_stage_state(stage).composite.require_authority()


def test_manifest_mutation_during_later_reads_fails_final_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    manifest = tmp_path / manifest_path
    original_read = RetainedDirectory.read_authoritative
    mutated = False

    def mutating_read(self: RetainedDirectory, path: str):
        nonlocal mutated
        if path == "declarations/process-core.yaml" and not mutated:
            mutated = True
            manifest.write_bytes(manifest.read_bytes() + b"\n")
        return original_read(self, path)

    monkeypatch.setattr(RetainedDirectory, "read_authoritative", mutating_read)

    with pytest.raises(ByteCarrierError, match="verification"):
        _acquire_external_stage_from_path(str(tmp_path), manifest_path, lock_path)


def test_resource_digest_drift_fails_before_publication(tmp_path: Path) -> None:
    path = "declarations/resources/publish-index.py"
    manifest_path, lock_path = _write_contract(
        tmp_path,
        resource_files=(
            (
                "oikos/publish-index",
                path,
                "text/x-python; charset=utf-8",
                b"print('locked')\n",
            ),
        ),
    )
    (tmp_path / path).write_bytes(b"print('drifted')\n")

    with pytest.raises(AcquisitionContractError, match="digest differs") as raised:
        _acquire_external_stage_from_path(str(tmp_path), manifest_path, lock_path)

    assert raised.value.location == "$.sources[0].resources[0].sha256"


def test_resource_mutation_after_read_fails_final_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = "declarations/resources/publish-index.py"
    manifest_path, lock_path = _write_contract(
        tmp_path,
        resource_files=(
            (
                "oikos/publish-index",
                path,
                "text/x-python; charset=utf-8",
                b"print('locked')\n",
            ),
        ),
    )
    original_read = RetainedDirectory.read_authoritative
    mutated = False

    def mutating_read(self: RetainedDirectory, requested: str):
        nonlocal mutated
        carrier = original_read(self, requested)
        if requested == path and not mutated:
            mutated = True
            (tmp_path / path).write_bytes(b"print('changed after read')\n")
        return carrier

    monkeypatch.setattr(RetainedDirectory, "read_authoritative", mutating_read)

    with pytest.raises(ByteCarrierError, match="verification"):
        _acquire_external_stage_from_path(str(tmp_path), manifest_path, lock_path)


def test_resource_must_be_strict_utf8(tmp_path: Path) -> None:
    manifest_path, lock_path = _write_contract(
        tmp_path,
        resource_files=(
            (
                "oikos/publish-index",
                "declarations/resources/publish-index.py",
                "text/x-python; charset=utf-8",
                b"\xff",
            ),
        ),
    )

    with pytest.raises(AcquisitionContractError, match="not strict UTF-8") as raised:
        _acquire_external_stage_from_path(str(tmp_path), manifest_path, lock_path)

    assert raised.value.location == "$.sources[0].resources[0].path"


def test_replacing_vendored_root_during_reads_fails_final_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = "vendor/oikos"
    manifest_path, lock_path = _write_contract(
        tmp_path,
        kind=AcquisitionKind.VENDORED,
        root=root,
    )
    source_root = tmp_path / root
    retained_root = tmp_path / "retained-oikos"
    original_read = RetainedDirectory.read_authoritative
    replaced = False

    def replacing_read(self: RetainedDirectory, path: str):
        nonlocal replaced
        if path == "declarations/process-core.yaml" and not replaced:
            replaced = True
            source_root.rename(retained_root)
            shutil.copytree(retained_root, source_root)
        return original_read(self, path)

    monkeypatch.setattr(RetainedDirectory, "read_authoritative", replacing_read)

    with pytest.raises(ByteCarrierError, match="root identity changed"):
        _acquire_external_stage_from_path(str(tmp_path), manifest_path, lock_path)


def test_stage_authority_rejects_external_registry_mutation(tmp_path: Path) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    stage = _acquire_external_stage_from_path(str(tmp_path), manifest_path, lock_path)
    state = _issued_external_stage_state(stage)
    external = state.composite.authority_for("oikos.enabled")
    object.__setattr__(external, "source_revision", "changed")

    with pytest.raises(AcquisitionContractError, match="registry state changed"):
        _issued_external_stage_state(stage)


def test_stage_rejects_forgery_and_is_not_public() -> None:
    assert not hasattr(declarations_api, "ExternalAcquisitionStage")
    assert not hasattr(declarations_api, "acquire_external_stage")
    forged = object.__new__(_ExternalAcquisitionStage)
    with pytest.raises(AcquisitionContractError, match="not issued"):
        _issued_external_stage_state(forged)


def test_interrupted_composite_publication_retires_every_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    original_issue = composite_module._COMPOSITE_AUTHORITIES.issue
    attempted_composites = []
    attempted_provenances = []
    attempted_evidence = []

    def interrupt(value, state):
        original_issue(value, state)
        attempted_composites.append(value)
        attempted_provenances.append(state.provenance)
        provenance_state = composite_module._FACET_PROVENANCE_AUTHORITIES.state(
            state.provenance
        )
        attempted_evidence.append(provenance_state.evidence)
        raise KeyboardInterrupt("injected composite publication interruption")

    monkeypatch.setattr(composite_module._COMPOSITE_AUTHORITIES, "issue", interrupt)

    with pytest.raises(KeyboardInterrupt, match="publication interruption"):
        _acquire_external_stage_from_path(str(tmp_path), manifest_path, lock_path)

    assert len(attempted_composites) == 1
    assert len(attempted_provenances) == 1
    assert (
        composite_module._COMPOSITE_AUTHORITIES.state(attempted_composites[0]) is None
    )
    provenance = attempted_provenances[0]
    provenance_state = composite_module._FACET_PROVENANCE_AUTHORITIES.state(provenance)
    assert provenance_state is None
    assert _EVIDENCE_AUTHORITIES.state(attempted_evidence[0]) is None


def test_interrupted_stage_publication_retires_every_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    original_issue = acquisition_module._STAGE_AUTHORITIES.issue
    attempted: list[_ExternalAcquisitionStage] = []
    attempted_composites = []
    attempted_provenances = []
    attempted_evidence = []

    def interrupt(value, state):
        original_issue(value, state)
        attempted.append(value)
        attempted_composites.append(state.composite)
        composite_state = composite_module._COMPOSITE_AUTHORITIES.state(state.composite)
        attempted_provenances.append(composite_state.provenance)
        attempted_evidence.append(state.evidence)
        raise KeyboardInterrupt("injected stage publication interruption")

    monkeypatch.setattr(acquisition_module._STAGE_AUTHORITIES, "issue", interrupt)
    baseline = len(os.listdir("/dev/fd"))

    with pytest.raises(KeyboardInterrupt, match="publication interruption"):
        _acquire_external_stage_from_path(str(tmp_path), manifest_path, lock_path)

    assert len(os.listdir("/dev/fd")) == baseline
    assert len(attempted) == 1
    assert acquisition_module._STAGE_AUTHORITIES.state(attempted[0]) is None
    assert (
        composite_module._COMPOSITE_AUTHORITIES.state(attempted_composites[0]) is None
    )
    assert (
        composite_module._FACET_PROVENANCE_AUTHORITIES.state(attempted_provenances[0])
        is None
    )
    assert _EVIDENCE_AUTHORITIES.state(attempted_evidence[0]) is None


def test_git_stage_retains_verified_transport_evidence(tmp_path: Path) -> None:
    workspace, git_locks = _build_git_workspace(
        tmp_path,
        (("oikos", "vendor/oikos", True),),
    )
    manifest_path, lock_path = _write_contract(
        workspace,
        kind=AcquisitionKind.GIT_SUBMODULE,
        root="vendor/oikos",
        git=git_locks["oikos"],
    )
    baseline = len(os.listdir("/dev/fd"))

    stage = _acquire_external_stage_from_path(str(workspace), manifest_path, lock_path)
    state = _issued_external_stage_state(stage)
    evidence = _EVIDENCE_AUTHORITIES.state(state.evidence)

    assert len(os.listdir("/dev/fd")) == baseline
    assert type(evidence) is _FinalEvidenceState
    git_evidence = evidence.sources[0].git_evidence
    git_state = _issued_git_transport_state(git_evidence)
    assert git_state.source_position == 0
    assert git_state.acquisition_manifest is evidence.manifest
    assert git_state.acquisition_lock is evidence.lock


def test_mixed_transports_preserve_source_and_extension_orders(tmp_path: Path) -> None:
    workspace, git_locks = _build_git_workspace(
        tmp_path,
        (("gitlib", "vendor/gitlib", True),),
    )
    manifest_path, lock_path = _write_multi_contract(
        workspace,
        specs=(
            ("gitlib", AcquisitionKind.GIT_SUBMODULE, "vendor/gitlib"),
            ("local", AcquisitionKind.VENDORED, "vendor/local"),
        ),
        extension_order=("local", "gitlib"),
        git_by_namespace=git_locks,
    )

    stage = _acquire_external_stage_from_path(str(workspace), manifest_path, lock_path)
    state = _issued_external_stage_state(stage)
    evidence = _EVIDENCE_AUTHORITIES.state(state.evidence)

    assert type(evidence) is _FinalEvidenceState
    assert tuple(item.declaration.id for item in state.declarations[-2:]) == (
        "gitlib/reader-purpose",
        "local/reader-purpose",
    )
    assert tuple(
        state.composite.authority_for(f"{namespace}.enabled").owner
        for namespace in ("local", "gitlib")
    ) == ("local", "gitlib")
    assert evidence.sources[0].git_evidence is not None
    assert evidence.sources[1].git_evidence is None


def test_multiple_git_sources_retain_independent_proofs(tmp_path: Path) -> None:
    workspace, git_locks = _build_git_workspace(
        tmp_path,
        (
            ("alpha", "vendor/alpha", True),
            ("beta", "vendor/beta", True),
        ),
    )
    manifest_path, lock_path = _write_multi_contract(
        workspace,
        specs=(
            ("alpha", AcquisitionKind.GIT_SUBMODULE, "vendor/alpha"),
            ("beta", AcquisitionKind.GIT_SUBMODULE, "vendor/beta"),
        ),
        extension_order=("beta", "alpha"),
        git_by_namespace=git_locks,
    )

    state = _issued_external_stage_state(
        _acquire_external_stage_from_path(str(workspace), manifest_path, lock_path)
    )
    evidence = _EVIDENCE_AUTHORITIES.state(state.evidence)

    assert type(evidence) is _FinalEvidenceState
    proofs = tuple(source.git_evidence for source in evidence.sources)
    assert all(proof is not None for proof in proofs)
    assert tuple(
        _issued_git_transport_state(proof).source_position for proof in proofs
    ) == (
        0,
        1,
    )


def test_git_carrier_splicing_fails_and_closes_every_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, git_locks = _build_git_workspace(
        tmp_path,
        (("oikos", "vendor/oikos", True),),
    )
    manifest_path, lock_path = _write_contract(
        workspace,
        kind=AcquisitionKind.GIT_SUBMODULE,
        root="vendor/oikos",
        git=git_locks["oikos"],
    )

    def splice(sessions, extensions, declarations, resources):
        sessions[0].bind_worktree_carriers(
            (declarations[0][0], extensions[0].authoritative)
        )

    monkeypatch.setattr(acquisition_module, "_bind_git_carriers", splice)
    baseline = len(os.listdir("/dev/fd"))

    with pytest.raises(AcquisitionContractError, match="worktree carrier differs"):
        _acquire_external_stage_from_path(str(workspace), manifest_path, lock_path)

    assert len(os.listdir("/dev/fd")) == baseline
