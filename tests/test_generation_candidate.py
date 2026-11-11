"""Exercise private canonical lock-candidate assembly and ownership."""

from __future__ import annotations

import copy
import pickle
from pathlib import Path
from typing import cast

import pytest

import eutaxis.declarations.byte_carriers as carrier_module
import eutaxis.declarations.generation_candidate as candidate_module
import eutaxis.declarations.generation_sources as source_module
import eutaxis.declarations.packaged_source as packaged_module
from eutaxis.declarations.acquisition_contract import (
    _lock_document,
    parse_acquisition_lock_bytes,
)
from eutaxis.declarations.byte_carriers import _trusted_directory_from_workspace_path
from eutaxis.declarations.canonical_json import jcs_bytes
from eutaxis.declarations.exceptions import AcquisitionContractError, ByteCarrierError


def _write_candidate_workspace(
    root: Path, *, rule_id: str = "oikos/process-core"
) -> str:
    declarations = root / "declarations"
    declarations.mkdir(parents=True)
    (declarations / "context-facets.yaml").write_text(
        "\n".join(
            (
                "schema-version: 1",
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
    (declarations / "process-core.yaml").write_text(f"kind: rule\nid: {rule_id}\n")
    manifest_path = "declarations/acquisition.yaml"
    (root / manifest_path).write_text(
        "\n".join(
            (
                "schema-version: 1",
                "facet-extensions:",
                "  - namespace: oikos",
                "    kind: workspace",
                "    root: .",
                "    path: declarations/context-facets.yaml",
                "internal-source:",
                "  namespace: eutaxis",
                "  kind: packaged",
                "sources:",
                "  - namespace: oikos",
                "    kind: workspace",
                "    root: .",
                "    files:",
                "      - declarations/process-core.yaml",
                "",
            )
        )
    )
    return manifest_path


def test_generated_candidate_binds_exact_canonical_lock_bytes(tmp_path: Path) -> None:
    manifest_path = _write_candidate_workspace(tmp_path)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        candidate = candidate_module._generate_workspace_candidate(
            workspace,
            manifest_path,
        )
        try:
            source, manifest, lock = candidate_module._generated_candidate_payload(
                candidate
            )
            assert source == jcs_bytes(_lock_document(lock))
            assert parse_acquisition_lock_bytes(source) == lock
            assert lock.facet_registry.base.namespace == "eutaxis"
            assert lock.facet_registry.extensions[0].namespace == "oikos"
            assert lock.sources[0].namespace == "oikos"
            assert lock.sources[0].files[0].path == "declarations/process-core.yaml"
            assert manifest.sources[0].files == ("declarations/process-core.yaml",)
        finally:
            candidate_module._retire_generated_candidate(candidate)
    finally:
        workspace.close()


def test_generated_candidate_retirement_retires_owned_observations(
    tmp_path: Path,
) -> None:
    manifest_path = _write_candidate_workspace(tmp_path)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        candidate = candidate_module._generate_workspace_candidate(
            workspace,
            manifest_path,
        )
        state = candidate_module._issued_generated_candidate_state(candidate)
        packaged = state.packaged
        external = state.external
        candidate_module._retire_generated_candidate(candidate)

        with pytest.raises(AcquisitionContractError, match="not issued here"):
            candidate_module._generated_candidate_payload(candidate)
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            candidate_module._packaged_generation_components(packaged)
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            candidate_module._workspace_generation_components(external)
    finally:
        workspace.close()


def test_generated_candidate_rejects_forgery_copy_and_serialization(
    tmp_path: Path,
) -> None:
    manifest_path = _write_candidate_workspace(tmp_path)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        candidate = candidate_module._generate_workspace_candidate(
            workspace,
            manifest_path,
        )
        try:
            with pytest.raises(TypeError, match="must be issued"):
                candidate_module._GeneratedCandidate()
            with pytest.raises(TypeError, match="cannot be copied"):
                copy.copy(candidate)
            with pytest.raises(TypeError, match="cannot be copied"):
                copy.deepcopy(candidate)
            with pytest.raises(TypeError, match="cannot be serialized"):
                pickle.dumps(candidate)
            forged = object.__new__(candidate_module._GeneratedCandidate)
            with pytest.raises(AcquisitionContractError, match="not issued here"):
                candidate_module._generated_candidate_payload(forged)
        finally:
            candidate_module._retire_generated_candidate(candidate)
    finally:
        workspace.close()


def test_generated_candidate_requires_live_workspace(tmp_path: Path) -> None:
    manifest_path = _write_candidate_workspace(tmp_path)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    candidate = candidate_module._generate_workspace_candidate(workspace, manifest_path)
    workspace.close()
    try:
        with pytest.raises(ByteCarrierError, match="closed"):
            candidate_module._generated_candidate_payload(candidate)
    finally:
        candidate_module._retire_generated_candidate(candidate)


def test_generated_candidate_rejects_manifest_change_during_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = _write_candidate_workspace(tmp_path)
    manifest_file = tmp_path / manifest_path
    original_observe = candidate_module._observe_workspace_generation
    captured: list[object] = []

    def mutating_observe(workspace, manifest):
        observation = original_observe(workspace, manifest)
        captured.append(observation)
        manifest_file.write_bytes(manifest_file.read_bytes() + b"\n")
        return observation

    monkeypatch.setattr(
        candidate_module,
        "_observe_workspace_generation",
        mutating_observe,
    )
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        with pytest.raises(ByteCarrierError, match="verification"):
            candidate_module._generate_workspace_candidate(workspace, manifest_path)
        assert captured
        assert (
            source_module._WORKSPACE_GENERATION_AUTHORITIES.state(captured[0]) is None
        )
    finally:
        workspace.close()


def test_generated_candidate_rejects_mutated_constructed_lock(tmp_path: Path) -> None:
    manifest_path = _write_candidate_workspace(tmp_path)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        candidate = candidate_module._generate_workspace_candidate(
            workspace,
            manifest_path,
        )
        state = candidate_module._issued_generated_candidate_state(candidate)
        object.__setattr__(state.lock, "schema_version", 2)
        try:
            with pytest.raises(AcquisitionContractError, match="lock state changed"):
                candidate_module._generated_candidate_payload(candidate)
        finally:
            candidate_module._retire_generated_candidate(candidate)
    finally:
        workspace.close()


def test_generated_candidate_rejects_substituted_canonical_bytes(
    tmp_path: Path,
) -> None:
    manifest_path = _write_candidate_workspace(tmp_path)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        candidate = candidate_module._generate_workspace_candidate(
            workspace,
            manifest_path,
        )
        state = candidate_module._issued_generated_candidate_state(candidate)
        substituted = state._replace(canonical_bytes=b"{}")
        candidate_module._GENERATED_CANDIDATE_AUTHORITIES.retire(candidate)
        candidate_module._GENERATED_CANDIDATE_AUTHORITIES.issue(candidate, substituted)
        try:
            with pytest.raises(AcquisitionContractError, match="bytes changed"):
                candidate_module._generated_candidate_payload(candidate)
        finally:
            candidate_module._retire_generated_candidate(candidate)
    finally:
        workspace.close()


def test_generated_candidate_reauthenticates_manifest_evidence(tmp_path: Path) -> None:
    manifest_path = _write_candidate_workspace(tmp_path)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        candidate = candidate_module._generate_workspace_candidate(
            workspace,
            manifest_path,
        )
        state = candidate_module._issued_generated_candidate_state(candidate)
        evidence = state.manifest_evidence
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
        try:
            with pytest.raises(
                ByteCarrierError, match="verified carrier state is invalid"
            ):
                candidate_module._generated_candidate_payload(candidate)
        finally:
            candidate_module._retire_generated_candidate(candidate)
    finally:
        workspace.close()


def test_generated_candidate_rejects_external_observation_from_another_workspace(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_manifest_path = _write_candidate_workspace(first_root, rule_id="oikos/first")
    second_manifest_path = _write_candidate_workspace(
        second_root,
        rule_id="oikos/second",
    )
    first_workspace = _trusted_directory_from_workspace_path(str(first_root))
    second_workspace = _trusted_directory_from_workspace_path(str(second_root))
    first = candidate_module._generate_workspace_candidate(
        first_workspace,
        first_manifest_path,
    )
    second = candidate_module._generate_workspace_candidate(
        second_workspace,
        second_manifest_path,
    )
    try:
        first_state = candidate_module._issued_generated_candidate_state(first)
        second_state = candidate_module._issued_generated_candidate_state(second)
        substituted = first_state._replace(external=second_state.external)
        candidate_module._GENERATED_CANDIDATE_AUTHORITIES.retire(first)
        candidate_module._GENERATED_CANDIDATE_AUTHORITIES.issue(first, substituted)
        with pytest.raises(AcquisitionContractError, match="candidate inputs"):
            candidate_module._generated_candidate_payload(first)
    finally:
        candidate_module._GENERATED_CANDIDATE_AUTHORITIES.retire(first)
        candidate_module._retire_nested_observations(
            first_state.packaged,
            first_state.external,
        )
        candidate_module._retire_generated_candidate(second)
        first_workspace.close()
        second_workspace.close()


def test_generated_candidate_issuance_interruption_retires_nested_observations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = _write_candidate_workspace(tmp_path)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    original_issue = candidate_module._GENERATED_CANDIDATE_AUTHORITIES.issue
    issued: list[candidate_module._GeneratedCandidate] = []
    nested: list[tuple[object, object]] = []

    def interrupt_after_issue(
        value: candidate_module._GeneratedCandidate,
        state: object,
    ) -> object:
        typed_state = cast(candidate_module._GeneratedCandidateState, state)
        token = original_issue(value, typed_state)
        issued.append(value)
        nested.append((typed_state.packaged, typed_state.external))
        raise KeyboardInterrupt("injected candidate publication interruption")

    monkeypatch.setattr(
        candidate_module._GENERATED_CANDIDATE_AUTHORITIES,
        "issue",
        interrupt_after_issue,
    )
    try:
        with pytest.raises(KeyboardInterrupt, match="publication interruption"):
            candidate_module._generate_workspace_candidate(workspace, manifest_path)
        assert (
            candidate_module._GENERATED_CANDIDATE_AUTHORITIES.state(issued[0]) is None
        )
        packaged, external = nested[0]
        assert packaged_module._PACKAGED_GENERATION_AUTHORITIES.state(packaged) is None
        assert source_module._WORKSPACE_GENERATION_AUTHORITIES.state(external) is None
    finally:
        workspace.close()


def test_generation_failure_remains_primary_when_nested_cleanup_reports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = _write_candidate_workspace(tmp_path)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    original_external_retire = candidate_module._retire_workspace_generation_observation
    original_packaged_retire = candidate_module._retire_packaged_generation_observation
    retired: list[tuple[str, object]] = []

    def fail_assembly(_manifest: object, _lock: object) -> bytes:
        raise RuntimeError("injected assembly failure")

    def reporting_external_retire(observation: object) -> None:
        original_external_retire(observation)
        retired.append(("external", observation))
        raise RuntimeError("injected cleanup report")

    def recording_packaged_retire(observation: object) -> None:
        original_packaged_retire(observation)
        retired.append(("packaged", observation))

    monkeypatch.setattr(candidate_module, "acquisition_lock_json_bytes", fail_assembly)
    monkeypatch.setattr(
        candidate_module,
        "_retire_workspace_generation_observation",
        reporting_external_retire,
    )
    monkeypatch.setattr(
        candidate_module,
        "_retire_packaged_generation_observation",
        recording_packaged_retire,
    )
    try:
        with pytest.raises(RuntimeError, match="assembly failure") as raised:
            candidate_module._generate_workspace_candidate(workspace, manifest_path)
        assert isinstance(raised.value.__cause__, RuntimeError)
        assert "cleanup report" in str(raised.value.__cause__)
        assert [kind for kind, _observation in retired] == ["external", "packaged"]
        external = retired[0][1]
        packaged = retired[1][1]
        assert source_module._WORKSPACE_GENERATION_AUTHORITIES.state(external) is None
        assert packaged_module._PACKAGED_GENERATION_AUTHORITIES.state(packaged) is None
    finally:
        workspace.close()
