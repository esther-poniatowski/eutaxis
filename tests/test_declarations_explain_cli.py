"""Command tests for context-specific declaration explanations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import eutaxis.declarations._cli as explain_cli_module
from eutaxis.cli import app
from eutaxis.declarations import (
    AcquisitionAuthorityError,
    ExternalResolutionError,
    acquire_external_declarations_from_path,
    resolve_external_compilation_unit,
)
from eutaxis.declarations.external_result import _retire_external_result_tree
from eutaxis.declarations.resolution import ResolutionError, ResolutionErrorCode
from eutaxis.declarations.resolution_diagnostic import (
    external_resolution_failure_json_bytes,
)
from eutaxis.declarations.resolution_diagnostic_schema import (
    validate_resolution_diagnostic_payload,
)
from eutaxis.declarations.exceptions import ResolutionDiagnosticError
from tests.test_external_acquisition import _write_contract
from tests.test_external_resolution import MANIFEST, RULE


def _arguments(
    tmp_path: Path,
    *context: str,
    include_root: bool = True,
) -> list[str]:
    """Create one complete explanation command for the fixture corpus."""
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="resolution",
        declaration_files=(
            ("declarations/rule.yaml", RULE),
            ("declarations/manifest.yaml", MANIFEST),
        ),
    )
    arguments = [
        "declarations",
        "explain",
        "--manifest",
        str(tmp_path / manifest_path),
        "--lock",
        str(tmp_path / lock_path),
        "--manifest-id",
        "resolution/manifest",
    ]
    if include_root:
        arguments[2:2] = ["--root", str(tmp_path)]
    for entry in context:
        arguments.extend(("--context", entry))
    return arguments


def test_explain_emits_complete_canonical_query_packet(tmp_path: Path) -> None:
    """A successful command reports every candidate and successful completion."""
    result = CliRunner().invoke(
        app,
        _arguments(
            tmp_path,
            "context.available=true",
            "resolution.enabled=true",
        ),
    )

    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["completion"] == "complete"
    assert payload["context"] == {
        "context.available": True,
        "resolution.enabled": True,
    }
    assert [
        (selection["declaration"], selection["outcome"])
        for selection in payload["selections"]
    ] == [("resolution/purpose", "effective")]
    assert result.stdout.encode() == json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def test_explain_reports_failed_resolution_without_packet(tmp_path: Path) -> None:
    """A semantic failure remains a diagnostic and never resembles a packet."""
    result = CliRunner().invoke(
        app,
        _arguments(
            tmp_path,
            "context.available=true",
            "resolution.enabled=false",
        ),
    )

    assert result.exit_code == 1
    diagnostic = json.loads(result.stdout)
    assert diagnostic["_schema"] == "eutaxis:resolution-diagnostic@1"
    assert diagnostic["completion"] == "failed"
    assert diagnostic["error"]["code"] == "manifest-inapplicable"
    assert diagnostic["trace"]["events"][0]["kind"] == "manifest-evaluated"
    assert diagnostic["sources"]


def test_explain_rejects_malformed_context_before_acquisition(tmp_path: Path) -> None:
    """Malformed typed context is a command-line error, not a failed resolution."""
    result = CliRunner().invoke(
        app,
        _arguments(tmp_path, "resolution.enabled=TRUE"),
    )

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "Resolution completion: not-started" in result.stderr
    assert "invalid JSON value" in result.stderr


def test_explain_rejects_duplicate_context_facets(tmp_path: Path) -> None:
    """One invocation cannot give a facet two competing values."""
    result = CliRunner().invoke(
        app,
        _arguments(
            tmp_path,
            "context.available=true",
            "context.available=false",
        ),
    )

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "duplicate context facet 'context.available'" in result.stderr


def test_explain_resolves_omitted_root_from_current_folder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The shared root fallback makes an explicit root optional."""
    arguments = _arguments(
        tmp_path,
        "context.available=true",
        "resolution.enabled=true",
        include_root=False,
    )
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, arguments)

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout)["completion"] == "complete"


def test_explain_interprets_paths_from_an_invoking_subdirectory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Typed paths retain current-folder semantics below an explicit root."""
    arguments = _arguments(
        tmp_path,
        "context.available=true",
        "resolution.enabled=true",
    )
    arguments[arguments.index("--root") + 1] = ".."
    arguments[arguments.index("--manifest") + 1] = "../acquisition.yaml"
    arguments[arguments.index("--lock") + 1] = "../acquisition.lock.json"
    nested = tmp_path / "nested"
    nested.mkdir()
    monkeypatch.chdir(nested)

    result = CliRunner().invoke(app, arguments)

    assert result.exit_code == 0, result.stderr


def test_explain_rejects_a_path_outside_the_root(tmp_path: Path) -> None:
    """A command-line path cannot expand the retained acquisition boundary."""
    outside = tmp_path.parent / "outside-manifest.yaml"
    result = CliRunner().invoke(
        app,
        [
            "declarations",
            "explain",
            "--root",
            str(tmp_path),
            "--manifest",
            str(outside),
            "--lock",
            str(tmp_path / "lock.yaml"),
            "--manifest-id",
            "resolution/manifest",
        ],
    )

    assert result.exit_code == 2
    assert "manifest path resolves outside root" in result.stderr


@pytest.mark.parametrize(
    "encoded, message",
    [
        ("NaN", "non-JSON constant 'NaN'"),
        ('{"key":1,"key":2}', "duplicate JSON object member 'key'"),
        ("1e9999", "outside the finite range"),
        ("-1e9999", "outside the finite range"),
    ],
)
def test_explain_rejects_noncanonical_json_context(
    tmp_path: Path,
    encoded: str,
    message: str,
) -> None:
    """Context parsing rejects values whose JSON meaning is not unique."""
    result = CliRunner().invoke(
        app,
        _arguments(tmp_path, f"resolution.enabled={encoded}"),
    )

    assert result.exit_code == 2
    assert message in result.stderr


def test_explain_reports_digest_drift_as_validation_failure(tmp_path: Path) -> None:
    """Changed acquired content is a validation finding, not an environment error."""
    arguments = _arguments(
        tmp_path,
        "context.available=true",
        "resolution.enabled=true",
    )
    (tmp_path / "declarations" / "rule.yaml").write_bytes(RULE + b"\n")

    result = CliRunner().invoke(app, arguments)

    assert result.exit_code == 1
    assert "digest differs" in result.stderr


def test_explain_reports_unavailable_root_as_environment_failure(
    tmp_path: Path,
) -> None:
    """An unavailable acquisition root is an environmental failure."""
    missing = tmp_path / "missing"
    result = CliRunner().invoke(
        app,
        [
            "declarations",
            "explain",
            "--root",
            str(missing),
            "--manifest",
            str(missing / "manifest.yaml"),
            "--lock",
            str(missing / "lock.yaml"),
            "--manifest-id",
            "resolution/manifest",
        ],
    )

    assert result.exit_code == 3
    assert "Resolution completion: failed" in result.stderr


def test_explain_distinguishes_output_failure_from_completed_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An output failure cannot claim that the overall command completed."""
    def fail_write(_content: bytes) -> None:
        raise OSError("injected output failure")

    monkeypatch.setattr(explain_cli_module, "_write_exact_stdout", fail_write)
    result = CliRunner().invoke(
        app,
        _arguments(
            tmp_path,
            "context.available=true",
            "resolution.enabled=true",
        ),
    )

    assert result.exit_code == 3
    assert "Resolution completion: complete" in result.stderr
    assert "Command completion: failed" in result.stderr


def test_explain_preserves_primary_failure_when_retirement_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cleanup failure remains secondary to the semantic resolution failure."""
    def fail_retirement(_acquisition: object) -> None:
        raise OSError("injected retirement failure")

    monkeypatch.setattr(
        explain_cli_module,
        "_retire_external_result_tree",
        fail_retirement,
    )
    result = CliRunner().invoke(
        app,
        _arguments(
            tmp_path,
            "context.available=true",
            "resolution.enabled=false",
        ),
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "manifest-inapplicable"
    assert "Cleanup error: injected retirement failure" in result.stderr


def test_explain_reports_success_path_retirement_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed cleanup after resolution prevents successful command completion."""
    def fail_retirement(_acquisition: object) -> None:
        raise OSError("injected retirement failure")

    monkeypatch.setattr(
        explain_cli_module,
        "_retire_external_result_tree",
        fail_retirement,
    )
    result = CliRunner().invoke(
        app,
        _arguments(
            tmp_path,
            "context.available=true",
            "resolution.enabled=true",
        ),
    )

    assert result.exit_code == 3
    assert result.stdout == ""
    assert "Resolution completion: complete" in result.stderr
    assert "Command completion: failed" in result.stderr
    assert "injected retirement failure" in result.stderr


def test_explain_reports_concurrent_authority_invalidation_as_environmental(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retired acquisition authority is not misreported as corpus validation."""
    original = explain_cli_module.resolve_external_compilation_unit

    def invalidate_before_resolution(acquisition, manifest_id, context):
        _retire_external_result_tree(acquisition)
        return original(acquisition, manifest_id, context)

    monkeypatch.setattr(
        explain_cli_module,
        "resolve_external_compilation_unit",
        invalidate_before_resolution,
    )
    result = CliRunner().invoke(
        app,
        _arguments(
            tmp_path,
            "context.available=true",
            "resolution.enabled=true",
        ),
    )

    assert result.exit_code == 3
    assert "Resolution completion: failed" in result.stderr
    assert "not issued" in result.stderr


def test_explain_preserves_primary_failure_with_hostile_string(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure reporting never delegates control to exception rendering."""
    class HostileError(Exception):
        def __str__(self) -> str:
            raise RuntimeError("string failed")

    def fail_acquisition(*_args: object) -> object:
        raise HostileError()

    monkeypatch.setattr(
        explain_cli_module,
        "acquire_external_declarations_from_path",
        fail_acquisition,
    )
    result = CliRunner().invoke(
        app,
        _arguments(tmp_path, "context.available=true"),
    )

    assert result.exit_code == 3
    assert "HostileError: string conversion failed with RuntimeError" in result.stderr


def test_explain_preserves_primary_when_cleanup_string_is_hostile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hostile cleanup error remains a secondary printable note."""
    class HostileCleanupError(Exception):
        def __str__(self) -> str:
            raise RuntimeError("string failed")

    def fail_retirement(_acquisition: object) -> None:
        raise HostileCleanupError()

    monkeypatch.setattr(
        explain_cli_module,
        "_retire_external_result_tree",
        fail_retirement,
    )
    result = CliRunner().invoke(
        app,
        _arguments(
            tmp_path,
            "context.available=true",
            "resolution.enabled=false",
        ),
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "manifest-inapplicable"
    assert (
        "Cleanup error: <HostileCleanupError: string conversion failed with "
        "RuntimeError>" in result.stderr
    )


def test_failure_serializer_rejects_an_unissued_resolution_error() -> None:
    """A caller-authored resolver error cannot acquire external provenance."""
    error = ResolutionError(
        ResolutionErrorCode.UNKNOWN_MANIFEST,
        "invented failure",
    )

    with pytest.raises(AcquisitionAuthorityError, match="not issued"):
        external_resolution_failure_json_bytes(error)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda value: value.update({"extra": True}), "Additional properties"),
        (
            lambda value: value["trace"]["events"][0].update({"policy": "x"}),
            "event fields",
        ),
        (
            lambda value: value["trace"]["events"][0].update({"ordinal": 1}),
            "ordinal",
        ),
        (
            lambda value: value["trace"]["events"][0].update({"causes": [0]}),
            "causes",
        ),
        (
            lambda value: value["trace"]["events"][0]["source"].update(
                {"path": "foreign.yaml"}
            ),
            "acquired source set",
        ),
        (
            lambda value: value["error"].pop("applicability"),
            "paired truth and applicability",
        ),
        (
            lambda value: value["error"].update({"truth": "true"}),
            "truth must equal",
        ),
    ],
)
def test_failure_diagnostic_validator_rejects_incoherent_projection(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    """The declared failure format rejects structural and semantic drift."""
    result = CliRunner().invoke(
        app,
        _arguments(
            tmp_path,
            "context.available=true",
            "resolution.enabled=false",
        ),
    )
    payload = json.loads(result.stdout)
    mutation(payload)

    with pytest.raises(ResolutionDiagnosticError, match=message):
        validate_resolution_diagnostic_payload(payload)


def test_explain_renders_hostile_exception_notes_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed notes cannot replace the command's primary diagnostic."""
    class HostileNote:
        def __str__(self) -> str:
            raise RuntimeError("note string failed")

    error = OSError("primary failure")
    error.__notes__ = [HostileNote()]  # type: ignore[list-item]

    def fail_acquisition(*_args: object) -> object:
        raise error

    monkeypatch.setattr(
        explain_cli_module,
        "acquire_external_declarations_from_path",
        fail_acquisition,
    )
    result = CliRunner().invoke(
        app,
        _arguments(tmp_path, "context.available=true"),
    )

    assert result.exit_code == 3
    assert "Error: primary failure" in result.stderr
    assert "HostileNote: string conversion failed with RuntimeError" in result.stderr


def test_failure_authority_rejects_rewritten_public_cause(tmp_path: Path) -> None:
    """Mutating both exposed errors cannot rewrite the issuance snapshot."""
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="resolution",
        declaration_files=(
            ("declarations/rule.yaml", RULE),
            ("declarations/manifest.yaml", MANIFEST),
        ),
    )
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    with pytest.raises(ExternalResolutionError) as raised:
        resolve_external_compilation_unit(
            acquisition,
            "resolution/manifest",
            {"context.available": True, "resolution.enabled": False},
        )
    issued = raised.value
    original = issued.__cause__
    assert isinstance(original, ResolutionError)
    original.detail = "forged"
    issued.detail = "forged"

    with pytest.raises(AcquisitionAuthorityError, match="state changed"):
        external_resolution_failure_json_bytes(issued)


def test_explain_rejects_hostile_notes_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A note container cannot execute iteration during failure reporting."""
    class HostileNotes(list[object]):
        def __iter__(self):
            raise RuntimeError("notes iteration failed")

    error = OSError("primary failure")
    error.__notes__ = HostileNotes()

    def fail_acquisition(*_args: object) -> object:
        raise error

    monkeypatch.setattr(
        explain_cli_module,
        "acquire_external_declarations_from_path",
        fail_acquisition,
    )
    result = CliRunner().invoke(
        app,
        _arguments(tmp_path, "context.available=true"),
    )

    assert result.exit_code == 3
    assert "Error: primary failure" in result.stderr
    assert "malformed exception notes: HostileNotes" in result.stderr
