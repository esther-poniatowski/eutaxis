"""Exercise sealed semantic validation of generated lock candidates."""

from __future__ import annotations

import copy
import pickle
from pathlib import Path

import pytest

import eutaxis.declarations._external_evidence as evidence_module
import eutaxis.declarations.candidate_validation as validation_module
import eutaxis.declarations.composite_facets as composite_module
import eutaxis.declarations.external_acquisition as acquisition_module
import eutaxis.declarations.external_result as result_module
import eutaxis.declarations.generation_candidate as candidate_module
from eutaxis.declarations.byte_carriers import _trusted_directory_from_workspace_path
from eutaxis.declarations.exceptions import (
    AcquisitionContractError,
    DeclarationRegistryError,
)


def _write_workspace(
    root: Path,
    *,
    rule_id: str = "oikos/process-core",
    evaluator_id: str = "eutaxis/manual-judgment",
) -> str:
    """Write one candidate fixture and return its manifest path."""
    declarations = root / "declarations"
    declarations.mkdir(parents=True)
    (declarations / "context-facets.yaml").write_text(
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
        ),
        encoding="utf-8",
    )
    (declarations / "process-core.yaml").write_text(
        "\n".join(
            (
                "_schema: eutaxis:declaration@1",
                f"id: {rule_id}",
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
                f"    evaluator: {{id: {evaluator_id}, version: 1}}",
                "    statement: The artifact states a reader-facing purpose",
                "",
            )
        ),
        encoding="utf-8",
    )
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
        ),
        encoding="utf-8",
    )
    return manifest_path


def _candidate(root: Path, **kwargs: str):
    """Return one workspace, manifest path, and generated candidate."""
    manifest_path = _write_workspace(root, **kwargs)
    workspace = _trusted_directory_from_workspace_path(str(root))
    candidate = candidate_module._generate_workspace_candidate(
        workspace,
        manifest_path,
    )
    return workspace, manifest_path, candidate


def test_validation_consumes_only_after_semantic_acquisition(tmp_path: Path) -> None:
    workspace, _manifest_path, candidate = _candidate(tmp_path)
    try:
        expected, _manifest, _lock = candidate_module._generated_candidate_payload(
            candidate
        )
        receipt = validation_module._validate_generated_candidate(candidate)

        assert (
            validation_module._issued_validation_receipt_state(receipt).candidate
            is candidate
        )
        assert candidate_module._issued_generated_candidate_state(candidate)

        actual = validation_module._consume_validated_candidate(candidate, receipt)

        assert actual == expected
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            candidate_module._generated_candidate_payload(candidate)
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            validation_module._issued_validation_receipt_state(receipt)
    finally:
        workspace.close()


def test_validation_rejects_semantically_invalid_registry(tmp_path: Path) -> None:
    workspace, _manifest_path, candidate = _candidate(
        tmp_path,
        evaluator_id="oikos/missing-evaluator",
    )
    try:
        with pytest.raises(DeclarationRegistryError, match="missing-evaluator"):
            validation_module._validate_generated_candidate(candidate)
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            candidate_module._generated_candidate_payload(candidate)
    finally:
        workspace.close()


def test_validation_rereads_sources_and_retires_changed_candidate(
    tmp_path: Path,
) -> None:
    workspace, _manifest_path, candidate = _candidate(tmp_path)
    source = tmp_path / "declarations/process-core.yaml"
    source.write_bytes(source.read_bytes() + b"\n")
    try:
        with pytest.raises(AcquisitionContractError, match="digest differs"):
            validation_module._validate_generated_candidate(candidate)
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            candidate_module._generated_candidate_payload(candidate)
    finally:
        workspace.close()


def test_generated_stage_cannot_publish_public_result(tmp_path: Path) -> None:
    workspace, _manifest_path, candidate = _candidate(tmp_path)
    try:
        stage = acquisition_module._acquire_external_stage_from_candidate(candidate)
        with pytest.raises(AcquisitionContractError, match="cannot publish"):
            result_module._publish_external_result(stage)

        receipt = validation_module._validate_generated_candidate(candidate)
        validation_module._consume_validated_candidate(candidate, receipt)
    finally:
        workspace.close()


def test_generated_stage_cannot_bypass_lowest_result_issuer(tmp_path: Path) -> None:
    workspace, _manifest_path, candidate = _candidate(tmp_path)
    stage = acquisition_module._acquire_external_stage_from_candidate(candidate)
    registry = validation_module._issue_external_declaration_registry(stage)
    try:
        with pytest.raises(AcquisitionContractError, match="cannot publish"):
            result_module._issue_external_result(stage, registry)
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            acquisition_module._issued_external_stage_state(stage)
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            validation_module._issued_external_registry_state(registry)

        receipt = validation_module._validate_generated_candidate(candidate)
        validation_module._consume_validated_candidate(candidate, receipt)
    finally:
        workspace.close()


@pytest.mark.parametrize(
    ("module", "target"),
    (
        (validation_module, "_retire_external_registry"),
        (acquisition_module, "_retire_composite_tree"),
        (acquisition_module, "_retire_external_evidence"),
    ),
)
def test_validation_retries_interrupted_graph_retirement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module: object,
    target: str,
) -> None:
    workspace, _manifest_path, candidate = _candidate(tmp_path)
    captured: dict[str, object] = {}
    original_stage_issue = validation_module._acquire_external_stage_from_candidate
    original_registry_issue = validation_module._issue_external_declaration_registry
    original_receipt_issue = validation_module._issue_validation_receipt
    original_retire = getattr(module, target)
    calls = 0

    def capture_stage(value: object):
        stage = original_stage_issue(value)
        stage_state = acquisition_module._issued_external_stage_state(stage)
        captured.update(
            stage=stage,
            composite=stage_state.composite,
            evidence=stage_state.evidence,
        )
        return stage

    def capture_registry(stage: object):
        registry = original_registry_issue(stage)
        captured["registry"] = registry
        return registry

    def capture_receipt(value: object, state: object):
        receipt = original_receipt_issue(value, state)
        captured["receipt"] = receipt
        return receipt

    def interrupt_once(value: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError(f"injected {target} interruption")
        original_retire(value)

    monkeypatch.setattr(
        validation_module,
        "_acquire_external_stage_from_candidate",
        capture_stage,
    )
    monkeypatch.setattr(
        validation_module,
        "_issue_external_declaration_registry",
        capture_registry,
    )
    monkeypatch.setattr(
        validation_module,
        "_issue_validation_receipt",
        capture_receipt,
    )
    monkeypatch.setattr(
        module,
        target,
        interrupt_once,
    )
    try:
        with pytest.raises(RuntimeError, match=target):
            validation_module._validate_generated_candidate(candidate)
        assert calls == 2
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            candidate_module._issued_generated_candidate_state(candidate)
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            validation_module._issued_validation_receipt_state(captured["receipt"])
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            validation_module._issued_external_registry_state(captured["registry"])
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            acquisition_module._issued_external_stage_state(captured["stage"])
        assert not composite_module._has_composite_authority(
            captured["composite"],
            allow_provisional=True,
        )
        assert evidence_module._EVIDENCE_AUTHORITIES.state(captured["evidence"]) is None
    finally:
        workspace.close()


def test_cleanup_failure_preserves_existing_primary_cause() -> None:
    original_cause = ValueError("original semantic cause")
    primary = RuntimeError("primary semantic failure")
    primary.__cause__ = original_cause
    cleanup = OSError("cleanup failure")

    validation_module._attach_cleanup_cause(primary, cleanup)

    assert primary.__cause__ is cleanup
    assert cleanup.__cause__ is original_cause


def test_validation_retries_interrupted_receipt_retirement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, _manifest_path, candidate = _candidate(tmp_path)
    captured: dict[str, object] = {}
    original_receipt_issue = validation_module._issue_validation_receipt
    original_receipt_retire = validation_module._retire_validation_receipt
    original_registry_retire = validation_module._retire_external_registry
    receipt_calls = 0
    registry_calls = 0

    def capture_receipt(value: object, state: object):
        receipt = original_receipt_issue(value, state)
        captured["receipt"] = receipt
        return receipt

    def interrupt_receipt_once(receipt: object) -> None:
        nonlocal receipt_calls
        receipt_calls += 1
        if receipt_calls == 1:
            raise RuntimeError("injected receipt retirement interruption")
        original_receipt_retire(receipt)

    def interrupt_registry_once(registry: object) -> None:
        nonlocal registry_calls
        registry_calls += 1
        if registry_calls == 1:
            raise RuntimeError("injected graph retirement interruption")
        original_registry_retire(registry)

    monkeypatch.setattr(
        validation_module,
        "_issue_validation_receipt",
        capture_receipt,
    )
    monkeypatch.setattr(
        validation_module,
        "_retire_validation_receipt",
        interrupt_receipt_once,
    )
    monkeypatch.setattr(
        validation_module,
        "_retire_external_registry",
        interrupt_registry_once,
    )
    try:
        with pytest.raises(RuntimeError, match="graph retirement interruption"):
            validation_module._validate_generated_candidate(candidate)
        assert receipt_calls == 2
        assert registry_calls == 2
        assert (
            validation_module._VALIDATION_RECEIPT_AUTHORITIES.state(captured["receipt"])
            is None
        )
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            candidate_module._issued_generated_candidate_state(candidate)
    finally:
        workspace.close()


def test_cleanup_cause_attachment_rejects_cycles() -> None:
    same = RuntimeError("same failure")
    validation_module._attach_cleanup_cause(same, same)
    assert same.__cause__ is None

    original = ValueError("original cause")
    primary = RuntimeError("primary failure")
    primary.__cause__ = original
    cleanup = OSError("cleanup failure")
    cleanup.__cause__ = primary

    validation_module._attach_cleanup_cause(primary, cleanup)

    assert primary.__cause__ is original


def test_validation_receipt_rejects_forgery_copy_and_serialization(
    tmp_path: Path,
) -> None:
    workspace, _manifest_path, candidate = _candidate(tmp_path)
    receipt = validation_module._validate_generated_candidate(candidate)
    try:
        with pytest.raises(TypeError, match="must be issued"):
            validation_module._CandidateValidationReceipt()
        with pytest.raises(TypeError, match="cannot be copied"):
            copy.copy(receipt)
        with pytest.raises(TypeError, match="cannot be copied"):
            copy.deepcopy(receipt)
        with pytest.raises(TypeError, match="cannot be serialized"):
            pickle.dumps(receipt)
        forged = object.__new__(validation_module._CandidateValidationReceipt)
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            validation_module._issued_validation_receipt_state(forged)
    finally:
        validation_module._retire_validation_receipt(receipt)
        candidate_module._retire_generated_candidate(candidate)
        workspace.close()


def test_validation_receipt_cannot_authorize_another_candidate(
    tmp_path: Path,
) -> None:
    first_workspace, _first_path, first = _candidate(tmp_path / "first")
    second_workspace, _second_path, second = _candidate(
        tmp_path / "second",
        rule_id="oikos/second",
    )
    first_receipt = validation_module._validate_generated_candidate(first)
    second_receipt = validation_module._validate_generated_candidate(second)
    try:
        with pytest.raises(AcquisitionContractError, match="another candidate"):
            validation_module._consume_validated_candidate(first, second_receipt)
        validation_module._consume_validated_candidate(first, first_receipt)
        validation_module._consume_validated_candidate(second, second_receipt)
    finally:
        first_workspace.close()
        second_workspace.close()
