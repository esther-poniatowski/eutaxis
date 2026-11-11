"""Exercise private workspace and vendored lock-generation observations."""

from __future__ import annotations

import copy
import hashlib
import pickle
import shutil
from pathlib import Path
from typing import cast

import pytest

import eutaxis.declarations.byte_carriers as carrier_module
import eutaxis.declarations.generation_sources as generation_module
from eutaxis.declarations._authority import identity_value_state
from eutaxis.declarations.acquisition_contract import (
    AcquisitionManifest,
    FacetConstituentLock,
    LockedFile,
    LockedResource,
    parse_acquisition_manifest,
    source_content_revision,
)
from eutaxis.declarations.byte_carriers import (
    RetainedDirectory,
    _trusted_directory_from_workspace_path,
)
from eutaxis.declarations.canonical_json import jcs_bytes
from eutaxis.declarations.exceptions import AcquisitionContractError, ByteCarrierError


def _digest(source: bytes) -> str:
    return "sha256:" + hashlib.sha256(source).hexdigest()


def _revision(value: object) -> str:
    return _digest(jcs_bytes(value))


def _write_workspace(
    root: Path,
    *,
    kind: str = "workspace",
    source_root: str = ".",
    resource_bytes: bytes | None = None,
) -> tuple[AcquisitionManifest, Path, Path]:
    source = root if source_root == "." else root / source_root
    declarations = source / "declarations"
    declarations.mkdir(parents=True)
    facet = declarations / "context-facets.yaml"
    facet.write_text(
        "\n".join(
            (
                "_schema: eutaxis:context-facets@1",
                "id: oikos/context-facets",
                "owner: oikos",
                "source-revision: v1",
                "facets:",
                "  - id: oikos.reviewed",
                "    value-schema: {type: boolean}",
                "",
            )
        )
    )
    declaration = declarations / "process-core.yaml"
    declaration.write_text(
        "\n".join(
            (
                "_schema: eutaxis:declaration@1",
                "id: oikos/process-core",
                "kind: rule",
                "owner: oikos",
                "status: active",
                "source-revision: fixture-1",
                "applicability: {facet: oikos.reviewed, operator: equals, value: true}",
                "relations: []",
                "axis: reasoning-target",
                "failure-mode: visible",
                "norms:",
                "  - id: state-purpose",
                "    modality: must",
                "    subject: agent",
                "    action: {verb: state, object: the reader-facing purpose}",
                "criteria:",
                "  - id: purpose-is-explicit",
                "    norms: [state-purpose]",
                "    evaluator: {id: eutaxis/manual-judgment, version: 1}",
                "    statement: The artifact states a reader-facing purpose",
                "",
            )
        )
    )
    resources: list[dict[str, str]] = []
    if resource_bytes is not None:
        resource = declarations / "resources" / "publish-index.py"
        resource.parent.mkdir()
        resource.write_bytes(resource_bytes)
        resources.append(
            {
                "id": "oikos/publish-index",
                "path": "declarations/resources/publish-index.py",
                "media-type": "text/x-python; charset=utf-8",
            }
        )
    manifest = parse_acquisition_manifest(
        {
            "schema-version": 1,
            "facet-extensions": [
                {
                    "namespace": "oikos",
                    "kind": kind,
                    "root": source_root,
                    "path": "declarations/context-facets.yaml",
                }
            ],
            "internal-source": {"namespace": "eutaxis", "kind": "packaged"},
            "sources": [
                {
                    "namespace": "oikos",
                    "kind": kind,
                    "root": source_root,
                    "files": ["declarations/process-core.yaml"],
                    **({"resources": resources} if resources else {}),
                }
            ],
        }
    )
    return manifest, facet, declaration


def _expected_source_lock(
    manifest: AcquisitionManifest,
    declaration: Path,
) -> tuple[str, str, tuple[LockedFile, ...]]:
    source = manifest.sources[0]
    files = (LockedFile(source.files[0], _digest(declaration.read_bytes())),)
    content = _revision(
        {
            "namespace": source.namespace,
            "files": [{"path": files[0].path, "sha256": files[0].sha256}],
        }
    )
    acquisition = _revision(
        {
            "schema-version": 1,
            "namespace": source.namespace,
            "kind": source.kind.value,
            "root": source.root,
            "content-revision": content,
        }
    )
    return acquisition, content, files


def _expected_extension_lock(
    manifest: AcquisitionManifest,
    facet: Path,
) -> FacetConstituentLock:
    extension = manifest.facet_extensions[0]
    sha256 = _digest(facet.read_bytes())
    content = _revision(
        {
            "id": "oikos/context-facets",
            "namespace": "oikos",
            "owner": "oikos",
            "path": extension.path,
            "sha256": sha256,
        }
    )
    acquisition = _revision(
        {
            "schema-version": 1,
            "namespace": "oikos",
            "kind": extension.kind.value,
            "root": extension.root,
            "path": extension.path,
            "content-revision": content,
        }
    )
    return FacetConstituentLock(
        acquisition,
        content,
        "oikos/context-facets",
        extension.kind.value,
        "oikos",
        "oikos",
        extension.path,
        sha256,
    )


@pytest.mark.parametrize("kind", ["workspace", "vendored"])
def test_workspace_generation_observer_derives_exact_non_git_locks(
    tmp_path: Path,
    kind: str,
) -> None:
    manifest, facet, declaration = _write_workspace(tmp_path, kind=kind)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        observation = generation_module._observe_workspace_generation(
            workspace,
            manifest,
        )
        try:
            sources, extensions = generation_module._workspace_generation_components(
                observation
            )
            acquisition, content, files = _expected_source_lock(
                manifest,
                declaration,
            )
            assert sources[0].acquisition_revision == acquisition
            assert sources[0].content_revision == content
            assert sources[0].files == files
            assert sources[0].kind.value == kind
            assert sources[0].git is None
            assert extensions == (_expected_extension_lock(manifest, facet),)
        finally:
            generation_module._retire_workspace_generation_observation(observation)
    finally:
        workspace.close()


@pytest.mark.parametrize("kind", ["workspace", "vendored"])
def test_workspace_generation_retains_exact_resource_lock(
    tmp_path: Path,
    kind: str,
) -> None:
    resource_bytes = b'print("guarded index")\n'
    manifest, _facet, declaration = _write_workspace(
        tmp_path,
        kind=kind,
        resource_bytes=resource_bytes,
    )
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        observation = generation_module._observe_workspace_generation(
            workspace,
            manifest,
        )
        try:
            sources, _extensions = generation_module._workspace_generation_components(
                observation
            )
            resource = manifest.sources[0].resources[0]
            expected = LockedResource(
                resource.id,
                resource.path,
                resource.media_type,
                _digest(resource_bytes),
            )
            files = (
                LockedFile(
                    manifest.sources[0].files[0],
                    _digest(declaration.read_bytes()),
                ),
            )

            assert sources[0].resources == (expected,)
            assert sources[0].content_revision == source_content_revision(
                "oikos", files, (expected,)
            )
        finally:
            generation_module._retire_workspace_generation_observation(observation)
    finally:
        workspace.close()


def test_workspace_generation_reads_resources_before_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _facet, _declaration = _write_workspace(
        tmp_path,
        resource_bytes=b"pass\n",
    )
    events: list[tuple[str, str]] = []
    original_read = RetainedDirectory.read_authoritative
    original_verify = RetainedDirectory.verify

    def recording_read(self: RetainedDirectory, path: str):
        events.append(("read", path))
        return original_read(self, path)

    def recording_verify(self: RetainedDirectory, carrier):
        events.append(("verify", carrier.path))
        return original_verify(self, carrier)

    monkeypatch.setattr(RetainedDirectory, "read_authoritative", recording_read)
    monkeypatch.setattr(RetainedDirectory, "verify", recording_verify)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        observation = generation_module._observe_workspace_generation(
            workspace,
            manifest,
        )
        generation_module._retire_workspace_generation_observation(observation)
    finally:
        workspace.close()

    paths = (
        "declarations/context-facets.yaml",
        "declarations/process-core.yaml",
        "declarations/resources/publish-index.py",
    )
    assert events == [("read", path) for path in paths] + [
        ("verify", path) for path in paths
    ]


def test_workspace_generation_rejects_non_utf8_resource(tmp_path: Path) -> None:
    manifest, _facet, _declaration = _write_workspace(
        tmp_path,
        resource_bytes=b"\xff",
    )
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        with pytest.raises(AcquisitionContractError) as error:
            generation_module._observe_workspace_generation(workspace, manifest)
    finally:
        workspace.close()

    assert error.value.location == "$.sources[0].resources[0].path"


def test_workspace_generation_rejects_resource_mutation_before_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _facet, _declaration = _write_workspace(
        tmp_path,
        resource_bytes=b"pass\n",
    )
    resource_path = tmp_path / "declarations" / "resources" / "publish-index.py"
    original_read = RetainedDirectory.read_authoritative

    def mutating_read(self: RetainedDirectory, path: str):
        carrier = original_read(self, path)
        if path == "declarations/resources/publish-index.py":
            resource_path.write_bytes(b"changed = True\n")
        return carrier

    monkeypatch.setattr(RetainedDirectory, "read_authoritative", mutating_read)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        with pytest.raises(ByteCarrierError, match="verification"):
            generation_module._observe_workspace_generation(workspace, manifest)
    finally:
        workspace.close()


def test_workspace_generation_rejects_symlinked_resource(tmp_path: Path) -> None:
    manifest, _facet, _declaration = _write_workspace(
        tmp_path,
        resource_bytes=b"pass\n",
    )
    resource = tmp_path / "declarations" / "resources" / "publish-index.py"
    actual = tmp_path / "actual.py"
    resource.rename(actual)
    resource.symlink_to(actual)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        with pytest.raises(ByteCarrierError):
            generation_module._observe_workspace_generation(workspace, manifest)
    finally:
        workspace.close()


def test_workspace_generation_reads_all_paths_before_any_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _facet, _declaration = _write_workspace(tmp_path)
    events: list[tuple[str, str]] = []
    original_read = RetainedDirectory.read_authoritative
    original_verify = RetainedDirectory.verify

    def recording_read(self: RetainedDirectory, path: str):
        events.append(("read", path))
        return original_read(self, path)

    def recording_verify(self: RetainedDirectory, carrier):
        events.append(("verify", carrier.path))
        return original_verify(self, carrier)

    monkeypatch.setattr(RetainedDirectory, "read_authoritative", recording_read)
    monkeypatch.setattr(RetainedDirectory, "verify", recording_verify)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        observation = generation_module._observe_workspace_generation(
            workspace,
            manifest,
        )
        generation_module._retire_workspace_generation_observation(observation)
    finally:
        workspace.close()

    paths = (
        "declarations/context-facets.yaml",
        "declarations/process-core.yaml",
    )
    assert events == [("read", path) for path in paths] + [
        ("verify", path) for path in paths
    ]


def test_workspace_generation_rejects_mutation_before_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, facet, _declaration = _write_workspace(tmp_path)
    original_read = RetainedDirectory.read_authoritative

    def mutating_read(self: RetainedDirectory, path: str):
        carrier = original_read(self, path)
        if path == "declarations/process-core.yaml":
            facet.write_bytes(facet.read_bytes() + b"\n")
        return carrier

    monkeypatch.setattr(RetainedDirectory, "read_authoritative", mutating_read)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        with pytest.raises(ByteCarrierError, match="verification"):
            generation_module._observe_workspace_generation(workspace, manifest)
    finally:
        workspace.close()


def test_workspace_generation_rejects_source_root_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _facet, _declaration = _write_workspace(
        tmp_path,
        source_root="sources/oikos",
    )
    source = tmp_path / "sources" / "oikos"
    retained = tmp_path / "retained-oikos"
    original_read = RetainedDirectory.read_authoritative
    replaced = False

    def replacing_read(self: RetainedDirectory, path: str):
        nonlocal replaced
        carrier = original_read(self, path)
        if path == "declarations/process-core.yaml" and not replaced:
            replaced = True
            source.rename(retained)
            shutil.copytree(retained, source)
        return carrier

    monkeypatch.setattr(RetainedDirectory, "read_authoritative", replacing_read)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        with pytest.raises(ByteCarrierError, match="source root identity changed"):
            generation_module._observe_workspace_generation(workspace, manifest)
    finally:
        workspace.close()


def test_workspace_generation_rejects_symlinked_manifest_file(tmp_path: Path) -> None:
    manifest, _facet, declaration = _write_workspace(tmp_path)
    actual = tmp_path / "actual.yaml"
    declaration.rename(actual)
    declaration.symlink_to(actual)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        with pytest.raises(ByteCarrierError):
            generation_module._observe_workspace_generation(workspace, manifest)
    finally:
        workspace.close()


def test_workspace_generation_rejects_missing_manifest_file(tmp_path: Path) -> None:
    manifest, _facet, declaration = _write_workspace(tmp_path)
    declaration.unlink()
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        with pytest.raises(ByteCarrierError):
            generation_module._observe_workspace_generation(workspace, manifest)
    finally:
        workspace.close()


def test_workspace_generation_rejects_manifest_mutation_during_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _facet, _declaration = _write_workspace(tmp_path)
    source = manifest.sources[0]
    original_read = RetainedDirectory.read_authoritative

    def mutating_read(self: RetainedDirectory, path: str):
        carrier = original_read(self, path)
        if path == "declarations/process-core.yaml":
            object.__setattr__(source, "root", "changed-root")
        return carrier

    monkeypatch.setattr(RetainedDirectory, "read_authoritative", mutating_read)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        with pytest.raises(AcquisitionContractError, match="manifest state changed"):
            generation_module._observe_workspace_generation(workspace, manifest)
    finally:
        workspace.close()


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("oikos/context-facets", "other/context-facets", "id namespace"),
        ("owner: oikos", "owner: other", "owner differs"),
    ],
)
def test_workspace_generation_rejects_wrong_extension_identity(
    tmp_path: Path,
    old: str,
    new: str,
    message: str,
) -> None:
    manifest, facet, _declaration = _write_workspace(tmp_path)
    facet.write_text(facet.read_text().replace(old, new, 1))
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        with pytest.raises(AcquisitionContractError, match=message):
            generation_module._observe_workspace_generation(workspace, manifest)
    finally:
        workspace.close()


def test_workspace_generation_rejects_git_before_reading(tmp_path: Path) -> None:
    manifest, _facet, _declaration = _write_workspace(
        tmp_path,
        kind="git-submodule",
    )
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        with pytest.raises(AcquisitionContractError, match="Git observer"):
            generation_module._observe_workspace_generation(workspace, manifest)
    finally:
        workspace.close()


def test_workspace_generation_observation_rejects_forgery_copy_and_retirement(
    tmp_path: Path,
) -> None:
    manifest, _facet, _declaration = _write_workspace(tmp_path)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        observation = generation_module._observe_workspace_generation(
            workspace,
            manifest,
        )
        with pytest.raises(TypeError, match="must be issued"):
            generation_module._WorkspaceGenerationObservation()
        with pytest.raises(TypeError, match="cannot be copied"):
            copy.copy(observation)
        with pytest.raises(TypeError, match="cannot be copied"):
            copy.deepcopy(observation)
        with pytest.raises(TypeError, match="cannot be serialized"):
            pickle.dumps(observation)
        forged = object.__new__(generation_module._WorkspaceGenerationObservation)
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            generation_module._workspace_generation_components(forged)

        generation_module._retire_workspace_generation_observation(observation)
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            generation_module._workspace_generation_components(observation)
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            generation_module._retire_workspace_generation_observation(observation)
    finally:
        workspace.close()


def test_workspace_generation_observation_requires_live_workspace(
    tmp_path: Path,
) -> None:
    manifest, _facet, _declaration = _write_workspace(tmp_path)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    observation = generation_module._observe_workspace_generation(workspace, manifest)
    workspace.close()

    try:
        with pytest.raises(ByteCarrierError, match="closed"):
            generation_module._workspace_generation_components(observation)
    finally:
        generation_module._retire_workspace_generation_observation(observation)


def test_workspace_generation_observation_rejects_mutated_lock(
    tmp_path: Path,
) -> None:
    manifest, _facet, _declaration = _write_workspace(tmp_path)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        observation = generation_module._observe_workspace_generation(
            workspace,
            manifest,
        )
        state = generation_module._issued_workspace_generation_state(observation)
        object.__setattr__(
            state.sources[0].lock,
            "content_revision",
            "sha256:" + "0" * 64,
        )
        with pytest.raises(AcquisitionContractError, match="lock state changed"):
            generation_module._workspace_generation_components(observation)
        generation_module._retire_workspace_generation_observation(observation)
    finally:
        workspace.close()


def test_workspace_generation_observation_reauthenticates_verified_evidence(
    tmp_path: Path,
) -> None:
    manifest, _facet, _declaration = _write_workspace(tmp_path)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        observation = generation_module._observe_workspace_generation(
            workspace,
            manifest,
        )
        state = generation_module._issued_workspace_generation_state(observation)
        evidence = state.sources[0].evidence[0]
        verified_state = carrier_module._VERIFIED_AUTHORITIES.retire(evidence)
        assert verified_state is not None
        verification_snapshot = cast(
            tuple[str, bytes, str, object, object],
            verified_state[6],
        )
        corrupted = (
            verification_snapshot[0],
            verification_snapshot[1],
            "sha256:" + "0" * 64,
            verification_snapshot[3],
            verification_snapshot[4],
        )
        carrier_module._VERIFIED_AUTHORITIES.issue(
            evidence,
            (*verified_state[:6], corrupted),
        )
        with pytest.raises(ByteCarrierError, match="verified carrier state is invalid"):
            generation_module._workspace_generation_components(observation)
        generation_module._retire_workspace_generation_observation(observation)
    finally:
        workspace.close()


def test_workspace_generation_reauthenticates_resource_evidence(
    tmp_path: Path,
) -> None:
    manifest, _facet, _declaration = _write_workspace(
        tmp_path,
        resource_bytes=b"pass\n",
    )
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        observation = generation_module._observe_workspace_generation(
            workspace,
            manifest,
        )
        state = generation_module._issued_workspace_generation_state(observation)
        evidence = state.sources[0].resource_evidence[0]
        verified_state = carrier_module._VERIFIED_AUTHORITIES.retire(evidence)
        assert verified_state is not None
        verification_snapshot = cast(
            tuple[str, bytes, str, object, object],
            verified_state[6],
        )
        corrupted = (
            verification_snapshot[0],
            verification_snapshot[1],
            "sha256:" + "0" * 64,
            verification_snapshot[3],
            verification_snapshot[4],
        )
        carrier_module._VERIFIED_AUTHORITIES.issue(
            evidence,
            (*verified_state[:6], corrupted),
        )
        with pytest.raises(ByteCarrierError, match="verified carrier state is invalid"):
            generation_module._workspace_generation_components(observation)
        generation_module._retire_workspace_generation_observation(observation)
    finally:
        workspace.close()


def test_workspace_generation_rejects_reordered_evidence_with_matching_lock(
    tmp_path: Path,
) -> None:
    _manifest, _facet, _declaration = _write_workspace(tmp_path)
    second = tmp_path / "declarations" / "second.yaml"
    second.write_text("kind: rule\nid: oikos/second\n")
    manifest = parse_acquisition_manifest(
        {
            "schema-version": 1,
            "facet-extensions": [
                {
                    "namespace": "oikos",
                    "kind": "workspace",
                    "root": ".",
                    "path": "declarations/context-facets.yaml",
                }
            ],
            "internal-source": {"namespace": "eutaxis", "kind": "packaged"},
            "sources": [
                {
                    "namespace": "oikos",
                    "kind": "workspace",
                    "root": ".",
                    "files": [
                        "declarations/process-core.yaml",
                        "declarations/second.yaml",
                    ],
                }
            ],
        }
    )
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        observation = generation_module._observe_workspace_generation(
            workspace,
            manifest,
        )
        state = generation_module._issued_workspace_generation_state(observation)
        source = state.sources[0]
        reversed_evidence = tuple(reversed(source.evidence))
        substituted_files = tuple(
            LockedFile(
                evidence.authoritative.path,
                evidence.authoritative.sha256,
            )
            for evidence in reversed_evidence
        )
        substituted_lock = generation_module._source_lock_from_files(
            source.manifest,
            substituted_files,
        )
        substituted_source = source._replace(
            lock=substituted_lock,
            lock_state=identity_value_state(substituted_lock),
            evidence=reversed_evidence,
        )
        substituted_state = state._replace(sources=(substituted_source,))
        generation_module._WORKSPACE_GENERATION_AUTHORITIES.retire(observation)
        generation_module._WORKSPACE_GENERATION_AUTHORITIES.issue(
            observation,
            substituted_state,
        )

        with pytest.raises(
            AcquisitionContractError,
            match="locked declaration path differs from manifest",
        ):
            generation_module._workspace_generation_components(observation)
        generation_module._retire_workspace_generation_observation(observation)
    finally:
        if "observation" in locals():
            generation_module._WORKSPACE_GENERATION_AUTHORITIES.retire(observation)
        workspace.close()


def test_workspace_generation_rejects_source_state_from_another_workspace(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    for root, identifier in ((first_root, "first"), (second_root, "second")):
        declarations = root / "declarations"
        declarations.mkdir(parents=True)
        (declarations / "rule.yaml").write_text(f"kind: rule\nid: oikos/{identifier}\n")
    manifest = parse_acquisition_manifest(
        {
            "schema-version": 1,
            "facet-extensions": [],
            "internal-source": {"namespace": "eutaxis", "kind": "packaged"},
            "sources": [
                {
                    "namespace": "oikos",
                    "kind": "workspace",
                    "root": ".",
                    "files": ["declarations/rule.yaml"],
                }
            ],
        }
    )
    first_workspace = _trusted_directory_from_workspace_path(str(first_root))
    second_workspace = _trusted_directory_from_workspace_path(str(second_root))
    first_observation = generation_module._observe_workspace_generation(
        first_workspace,
        manifest,
    )
    second_observation = generation_module._observe_workspace_generation(
        second_workspace,
        manifest,
    )
    try:
        first_state = generation_module._issued_workspace_generation_state(
            first_observation
        )
        second_state = generation_module._issued_workspace_generation_state(
            second_observation
        )
        substituted_state = first_state._replace(sources=second_state.sources)
        generation_module._WORKSPACE_GENERATION_AUTHORITIES.retire(first_observation)
        generation_module._WORKSPACE_GENERATION_AUTHORITIES.issue(
            first_observation,
            substituted_state,
        )

        with pytest.raises(
            AcquisitionContractError,
            match="source root differs from live workspace",
        ):
            generation_module._workspace_generation_components(first_observation)
    finally:
        generation_module._WORKSPACE_GENERATION_AUTHORITIES.retire(first_observation)
        generation_module._WORKSPACE_GENERATION_AUTHORITIES.retire(second_observation)
        first_workspace.close()
        second_workspace.close()


def test_workspace_generation_publication_interruption_retires_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _facet, _declaration = _write_workspace(tmp_path)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    original_issue = generation_module._WORKSPACE_GENERATION_AUTHORITIES.issue
    issued: list[generation_module._WorkspaceGenerationObservation] = []

    def interrupt_after_issue(
        value: generation_module._WorkspaceGenerationObservation,
        state: object,
    ) -> object:
        token = original_issue(value, state)  # type: ignore[arg-type]
        issued.append(value)
        raise KeyboardInterrupt("injected observation publication interruption")

    monkeypatch.setattr(
        generation_module._WORKSPACE_GENERATION_AUTHORITIES,
        "issue",
        interrupt_after_issue,
    )
    try:
        with pytest.raises(KeyboardInterrupt, match="publication interruption"):
            generation_module._observe_workspace_generation(workspace, manifest)
        provisional = issued[0]
        assert (
            generation_module._WORKSPACE_GENERATION_AUTHORITIES.state(provisional)
            is None
        )
    finally:
        workspace.close()
