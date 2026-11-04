"""Exercise the private workspace/vendored acquisition boundary."""

from __future__ import annotations

import copy
import hashlib
import os
import pickle
import shutil
from pathlib import Path

import pytest
import yaml

import eutaxis.declarations.workspace_acquisition as workspace_module
import eutaxis.declarations.composite_facets as composite_module
import eutaxis.declarations as declarations_api
from eutaxis import data_path
from eutaxis.declarations.acquisition_contract import (
    AcquisitionKind,
    AcquisitionLock,
    ExternalSourceLock,
    FacetConstituentLock,
    FacetRegistryLock,
    LockedFile,
    _lock_document,
    composite_facet_content_revision,
    facet_content_revision,
    source_content_revision,
)
from eutaxis.declarations.canonical_json import jcs_bytes
from eutaxis.declarations.byte_carriers import RetainedDirectory, TrustedDirectory
from eutaxis.declarations.exceptions import AcquisitionContractError, ByteCarrierError
from eutaxis.declarations.workspace_acquisition import (
    _EVIDENCE_AUTHORITIES,
    _FinalEvidenceState,
    _WorkspaceVendoredAcquisitionStage,
    _acquire_workspace_vendored_stage_from_path,
    _issued_workspace_vendored_stage_state,
)
from tests.test_packaged_source import _valid_lock
from tests.test_acquisition_contract import _lock as _contract_lock
from tests.test_acquisition_contract import _manifest as _contract_manifest


def _digest(source: bytes) -> str:
    return "sha256:" + hashlib.sha256(source).hexdigest()


def _revision(value: object) -> str:
    return "sha256:" + hashlib.sha256(jcs_bytes(value)).hexdigest()


def _facet_source(namespace: str) -> bytes:
    return (
        "schema-version: 1\n"
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
        "schema-version: 1\n"
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
) -> tuple[str, str]:
    source_root = workspace if root == "." else workspace / root
    (source_root / "declarations").mkdir(parents=True)
    facet_path = "declarations/context-facets.yaml"
    declaration_path = "declarations/process-core.yaml"
    facet_bytes = _facet_source(namespace)
    declaration_bytes = _declaration_source(namespace)
    (source_root / facet_path).write_bytes(facet_bytes)
    (source_root / declaration_path).write_bytes(declaration_bytes)

    facet_sha = _digest(facet_bytes)
    facet_content = facet_content_revision(
        f"{namespace}/context-facets",
        namespace,
        namespace,
        facet_path,
        facet_sha,
    )
    facet_acquisition = _revision(
        {
            "schema-version": 1,
            "namespace": namespace,
            "kind": kind.value,
            "root": root,
            "path": facet_path,
            "content-revision": facet_content,
        }
    )
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
    locked_file = LockedFile(declaration_path, _digest(declaration_bytes))
    source_content = source_content_revision(namespace, (locked_file,))
    source_acquisition = _revision(
        {
            "schema-version": 1,
            "namespace": namespace,
            "kind": kind.value,
            "root": root,
            "content-revision": source_content,
        }
    )
    external = ExternalSourceLock(
        source_acquisition,
        source_content,
        (locked_file,),
        kind,
        namespace,
        None,
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
                "files": [declaration_path],
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
) -> tuple[str, str]:
    packaged = _valid_lock(data_path())
    source_manifests: list[dict[str, object]] = []
    source_locks: list[ExternalSourceLock] = []
    extensions_by_namespace: dict[
        str, tuple[dict[str, object], FacetConstituentLock]
    ] = {}
    for namespace, kind, root in specs:
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
        source_acquisition = _revision(
            {
                "schema-version": 1,
                "namespace": namespace,
                "kind": kind.value,
                "root": root,
                "content-revision": source_content,
            }
        )
        source_locks.append(
            ExternalSourceLock(
                source_acquisition,
                source_content,
                (locked_file,),
                kind,
                namespace,
                None,
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
            acquisition = _revision(
                {
                    "schema-version": 1,
                    "namespace": namespace,
                    "kind": kind.value,
                    "root": root,
                    "path": facet_path,
                    "content-revision": content,
                }
            )
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


@pytest.mark.parametrize(
    ("kind", "root"),
    [
        (AcquisitionKind.WORKSPACE, "."),
        (AcquisitionKind.VENDORED, "vendor/oikos"),
    ],
)
def test_workspace_vendored_stage_retains_one_verified_contract(
    tmp_path: Path,
    kind: AcquisitionKind,
    root: str,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path, kind=kind, root=root)
    baseline = len(os.listdir("/dev/fd"))

    stage = _acquire_workspace_vendored_stage_from_path(
        str(tmp_path),
        manifest_path,
        lock_path,
    )
    state = _issued_workspace_vendored_stage_state(stage)

    assert len(os.listdir("/dev/fd")) == baseline
    assert state.composite.authority_for("oikos.enabled").id == ("oikos/context-facets")
    assert len(state.declarations) == 6
    assert type(_EVIDENCE_AUTHORITIES.state(state.evidence)) is _FinalEvidenceState
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(stage)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(stage)
    with pytest.raises(TypeError, match="must be issued"):
        _WorkspaceVendoredAcquisitionStage()


def test_workspace_path_may_be_relative_dot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    monkeypatch.chdir(tmp_path)

    stage = _acquire_workspace_vendored_stage_from_path(
        ".",
        manifest_path,
        lock_path,
    )

    assert len(_issued_workspace_vendored_stage_state(stage).declarations) == 6


def test_zero_extensions_preserves_the_packaged_composite(
    tmp_path: Path,
) -> None:
    manifest_path, lock_path = _write_multi_contract(
        tmp_path,
        specs=(("oikos", AcquisitionKind.WORKSPACE, "."),),
        extension_order=(),
    )

    stage = _acquire_workspace_vendored_stage_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    state = _issued_workspace_vendored_stage_state(stage)

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

    stage = _acquire_workspace_vendored_stage_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    state = _issued_workspace_vendored_stage_state(stage)

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

    _acquire_workspace_vendored_stage_from_path(str(tmp_path), manifest_path, lock_path)

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
    original_parse = workspace_module._parse_all_declarations
    checked = False

    def checking_parse(packaged, sources, external, parsing_view):
        nonlocal checked
        with pytest.raises(AcquisitionContractError, match="not issued"):
            parsing_view._composite.require_authority()
        parsing_view.require_authority()
        checked = True
        return original_parse(packaged, sources, external, parsing_view)

    monkeypatch.setattr(
        workspace_module,
        "_parse_all_declarations",
        checking_parse,
    )

    stage = _acquire_workspace_vendored_stage_from_path(
        str(tmp_path), manifest_path, lock_path
    )

    assert checked
    _issued_workspace_vendored_stage_state(stage).composite.require_authority()


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
        _acquire_workspace_vendored_stage_from_path(
            str(tmp_path), manifest_path, lock_path
        )


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
        _acquire_workspace_vendored_stage_from_path(
            str(tmp_path), manifest_path, lock_path
        )


def test_stage_authority_rejects_external_registry_mutation(tmp_path: Path) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    stage = _acquire_workspace_vendored_stage_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    state = _issued_workspace_vendored_stage_state(stage)
    external = state.composite.authority_for("oikos.enabled")
    object.__setattr__(external, "source_revision", "changed")

    with pytest.raises(AcquisitionContractError, match="registry state changed"):
        _issued_workspace_vendored_stage_state(stage)


def test_stage_rejects_forgery_and_is_not_public() -> None:
    assert not hasattr(declarations_api, "WorkspaceVendoredAcquisitionStage")
    assert not hasattr(declarations_api, "acquire_workspace_vendored_stage")
    forged = object.__new__(_WorkspaceVendoredAcquisitionStage)
    with pytest.raises(AcquisitionContractError, match="not issued"):
        _issued_workspace_vendored_stage_state(forged)


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
        _acquire_workspace_vendored_stage_from_path(
            str(tmp_path), manifest_path, lock_path
        )

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
    original_issue = workspace_module._STAGE_AUTHORITIES.issue
    attempted: list[_WorkspaceVendoredAcquisitionStage] = []
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

    monkeypatch.setattr(workspace_module._STAGE_AUTHORITIES, "issue", interrupt)
    baseline = len(os.listdir("/dev/fd"))

    with pytest.raises(KeyboardInterrupt, match="publication interruption"):
        _acquire_workspace_vendored_stage_from_path(
            str(tmp_path), manifest_path, lock_path
        )

    assert len(os.listdir("/dev/fd")) == baseline
    assert len(attempted) == 1
    assert workspace_module._STAGE_AUTHORITIES.state(attempted[0]) is None
    assert (
        composite_module._COMPOSITE_AUTHORITIES.state(attempted_composites[0]) is None
    )
    assert (
        composite_module._FACET_PROVENANCE_AUTHORITIES.state(attempted_provenances[0])
        is None
    )
    assert _EVIDENCE_AUTHORITIES.state(attempted_evidence[0]) is None


def test_git_contract_fails_before_external_root_open(
    tmp_path: Path,
) -> None:
    manifest = _contract_manifest(kind="git-submodule", root="missing/source")
    lock = _contract_lock(kind="git-submodule", root="missing/source")
    manifest_path = "acquisition.yaml"
    lock_path = "acquisition.lock.json"
    (tmp_path / manifest_path).write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    (tmp_path / lock_path).write_bytes(jcs_bytes(lock))
    baseline = len(os.listdir("/dev/fd"))

    with pytest.raises(AcquisitionContractError, match="Git proof") as raised:
        _acquire_workspace_vendored_stage_from_path(
            str(tmp_path), manifest_path, lock_path
        )

    assert raised.value.location == "$.sources[0].kind"
    assert len(os.listdir("/dev/fd")) == baseline
