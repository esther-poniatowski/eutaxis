"""Exercise the public structured-declaration lock command."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import eutaxis.declarations._cli as lock_cli_module
import eutaxis.declarations.candidate_validation as validation_module
import eutaxis.declarations.byte_carriers as carrier_module
import eutaxis.declarations.generation_candidate as candidate_module
from eutaxis.cli import app
from eutaxis.declarations.exceptions import AcquisitionContractError


def _write_workspace(root: Path) -> str:
    """Write one semantically valid workspace acquisition fixture."""
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
        ),
        encoding="utf-8",
    )
    manifest = "declarations/acquisition.yaml"
    (root / manifest).write_text(
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
                "    files: [declarations/process-core.yaml]",
                "",
            )
        ),
        encoding="utf-8",
    )
    return manifest


def _invoke(root: Path, manifest: str, *mode: str):
    return CliRunner().invoke(
        app,
        [
            "declarations",
            "lock",
            "--workspace",
            str(root),
            "--manifest",
            manifest,
            *mode,
        ],
    )


def test_lock_stdout_is_exact_canonical_bytes(tmp_path: Path) -> None:
    manifest = _write_workspace(tmp_path)

    result = _invoke(tmp_path, manifest)

    assert result.exit_code == 0
    assert result.stderr == ""
    assert result.stdout_bytes.startswith(b'{"facet-registry":')
    assert result.stdout_bytes.endswith(b"}")
    assert b"\n" not in result.stdout_bytes


def test_lock_check_reports_drift_without_repair(tmp_path: Path) -> None:
    manifest = _write_workspace(tmp_path)
    lock_path = "declarations/acquisition.lock.json"
    target = tmp_path / lock_path
    target.write_bytes(b"stale\n")

    result = _invoke(tmp_path, manifest, "--check", lock_path)

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Drift:" in result.stderr
    assert target.read_bytes() == b"stale\n"


def test_lock_check_accepts_exact_generated_bytes(tmp_path: Path) -> None:
    manifest = _write_workspace(tmp_path)
    lock_path = "declarations/acquisition.lock.json"
    assert _invoke(tmp_path, manifest, "--output", lock_path).exit_code == 0

    result = _invoke(tmp_path, manifest, "--check", lock_path)

    assert result.exit_code == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_lock_output_creates_only_absent_path(tmp_path: Path) -> None:
    manifest = _write_workspace(tmp_path)
    lock_path = "declarations/acquisition.lock.json"

    created = _invoke(tmp_path, manifest, "--output", lock_path)
    repeated = _invoke(tmp_path, manifest, "--output", lock_path)

    assert created.exit_code == 0
    assert created.stdout == ""
    assert (tmp_path / lock_path).read_bytes().startswith(b'{"facet-registry":')
    assert repeated.exit_code == 2
    assert "destination already exists" in repeated.stderr


def test_lock_modes_are_rejected_before_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("generation must not start")

    monkeypatch.setattr(
        lock_cli_module,
        "_validated_workspace_candidate_bytes",
        forbidden,
    )
    result = _invoke(
        tmp_path,
        "missing.yaml",
        "--check",
        "a.json",
        "--output",
        "b.json",
    )

    assert result.exit_code == 2
    assert "mutually exclusive" in result.stderr
    assert not called


def test_candidate_authority_is_retired_before_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _write_workspace(tmp_path)
    original_consume = validation_module._consume_validated_candidate
    retired = False

    def consume_then_check(candidate, receipt):
        nonlocal retired
        content = original_consume(candidate, receipt)
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            candidate_module._issued_generated_candidate_state(candidate)
        retired = True
        return content

    monkeypatch.setattr(
        validation_module,
        "_consume_validated_candidate",
        consume_then_check,
    )

    result = _invoke(tmp_path, manifest)

    assert result.exit_code == 0
    assert retired


def test_partial_stdout_write_fails_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _write_workspace(tmp_path)

    class PartialWriter:
        def __init__(self) -> None:
            self.content = bytearray()
            self.calls = 0

        def write(self, content: bytes) -> int:
            self.calls += 1
            if self.calls > 1:
                return 0
            count = max(1, len(content) // 2)
            self.content.extend(content[:count])
            return count

        def flush(self) -> None:
            pass

    writer = PartialWriter()
    monkeypatch.setattr(
        lock_cli_module.click,
        "get_binary_stream",
        lambda _name: writer,
    )

    result = _invoke(tmp_path, manifest)

    assert result.exit_code == 2
    assert "standard-output write returned an invalid byte count" in result.stderr
    assert writer.content


def test_overreported_stdout_write_fails_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _write_workspace(tmp_path)

    class OverreportingWriter:
        def write(self, content: bytes) -> int:
            return len(content) + 1

        def flush(self) -> None:
            pass

    monkeypatch.setattr(
        lock_cli_module.click,
        "get_binary_stream",
        lambda _name: OverreportingWriter(),
    )

    result = _invoke(tmp_path, manifest)

    assert result.exit_code == 2
    assert "invalid byte count" in result.stderr


@pytest.mark.parametrize(
    "mode", [("--check", "missing.json"), ("--output", "existing.json")]
)
def test_failed_file_mode_retires_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: tuple[str, str],
) -> None:
    manifest = _write_workspace(tmp_path)
    if mode[0] == "--output":
        (tmp_path / mode[1]).write_bytes(b"existing\n")
    captured: list[carrier_module.TrustedDirectory] = []
    original = lock_cli_module._trusted_directory_from_workspace_path

    def capture(path: str):
        workspace = original(path)
        captured.append(workspace)
        return workspace

    monkeypatch.setattr(
        lock_cli_module,
        "_trusted_directory_from_workspace_path",
        capture,
    )

    result = _invoke(tmp_path, manifest, *mode)

    assert result.exit_code == 2
    assert len(captured) == 1
    assert carrier_module._TRUSTED_AUTHORITIES.state(captured[0]) is None


def test_consumption_failure_retires_candidate_and_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _write_workspace(tmp_path)
    captured: dict[str, object] = {}

    def fail_consumption(candidate, receipt):
        captured.update(candidate=candidate, receipt=receipt)
        raise AcquisitionContractError("$", "injected consumption failure")

    monkeypatch.setattr(
        validation_module,
        "_consume_validated_candidate",
        fail_consumption,
    )

    result = _invoke(tmp_path, manifest)

    assert result.exit_code == 1
    assert (
        candidate_module._GENERATED_CANDIDATE_AUTHORITIES.state(captured["candidate"])
        is None
    )
    assert (
        validation_module._VALIDATION_RECEIPT_AUTHORITIES.state(captured["receipt"])
        is None
    )


def test_workspace_cleanup_preserves_existing_diagnostic_cause() -> None:
    original_cause = ValueError("original command cause")
    primary = RuntimeError("primary command failure")
    primary.__cause__ = original_cause
    cleanup = OSError("workspace cleanup failure")

    class FailingWorkspace:
        def close(self) -> None:
            raise cleanup

    lock_cli_module._close_workspace_after_failure(FailingWorkspace(), primary)

    assert primary.__cause__ is cleanup
    assert cleanup.__cause__ is original_cause
