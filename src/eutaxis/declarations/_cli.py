"""Typer commands for structured declaration validation and acquisition."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import NoReturn

import click
import typer

from .._cli_options import command_path, command_root, root_option
from .byte_carriers import TrustedDirectory, _trusted_directory_from_workspace_path
from .candidate_validation import (
    _attach_cleanup_cause,
    _validated_workspace_candidate_bytes,
)
from .exceptions import (
    AcquisitionAuthorityError,
    AcquisitionContractError,
    ByteCarrierError,
    DeclarationError,
    FacetContextError,
    FacetRegistryError,
    QueryPacketError,
)
from .external_resolution import ExternalResolutionError, resolve_external_compilation_unit
from .external_result import (
    ExternalAcquisitionResult,
    _retire_external_result_tree,
    acquire_external_declarations_from_path,
)
from .lock_publication import (
    _LockPublicationError,
    _check_candidate_bytes,
    _publish_candidate_bytes,
)
from .sarif import declaration_check_sarif
from .query_packet import build_external_query_packet, query_packet_json_bytes
from .resolution_diagnostic import external_resolution_failure_json_bytes

declarations_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Validate structured declarations and manage acquisition locks.",
)


@declarations_app.command("check")
def cli_check(
    workspace: str = typer.Option(
        ...,
        "--workspace",
        help="Workspace root retained for manifest and source acquisition.",
    ),
    manifest: str = typer.Option(
        ...,
        "--manifest",
        help="Workspace-relative acquisition manifest path.",
    ),
) -> None:
    """Validate one manifest-defined corpus and write SARIF to standard output."""
    try:
        trusted = _trusted_directory_from_workspace_path(workspace)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _exit_check(exc, code=2, execution_successful=False)

    try:
        _validated_workspace_candidate_bytes(trusted, manifest)
    except (AcquisitionContractError, DeclarationError, FacetRegistryError) as exc:
        cleanup_error = _check_cleanup_error(trusted)
        if cleanup_error is not None:
            _exit_check(
                cleanup_error,
                exc,
                code=2,
                execution_successful=False,
            )
        _exit_check(exc, code=1, execution_successful=True)
    except (ByteCarrierError, OSError) as exc:
        cleanup_error = _check_cleanup_error(trusted)
        errors: tuple[BaseException, ...] = (
            (exc,) if cleanup_error is None else (exc, cleanup_error)
        )
        _exit_check(*errors, code=2, execution_successful=False)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        cleanup_error = _check_cleanup_error(trusted)
        errors = (exc,) if cleanup_error is None else (exc, cleanup_error)
        _exit_check(*errors, code=2, execution_successful=False)
    except BaseException as exc:  # pylint: disable=broad-exception-caught
        _close_workspace_after_failure(trusted, exc)
        raise

    cleanup_error = _check_cleanup_error(trusted)
    if cleanup_error is not None:
        _exit_check(cleanup_error, code=2, execution_successful=False)

    _write_check_report(declaration_check_sarif())


def _exit_check(
    *errors: BaseException,
    code: int,
    execution_successful: bool,
) -> NoReturn:
    """Write one complete check report and exit with its declared status."""
    _write_check_report(
        declaration_check_sarif(
            *errors,
            execution_successful=execution_successful,
        )
    )
    raise typer.Exit(code=code) from errors[0]


def _write_check_report(content: bytes) -> None:
    """Write one SARIF log, mapping every output failure to exit status 2."""
    try:
        _write_exact_stdout(content)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise typer.Exit(code=2) from exc


def _check_cleanup_error(workspace: TrustedDirectory) -> Exception | None:
    """Close one check workspace and return any operational cleanup failure."""
    try:
        workspace.close()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return exc
    return None


@declarations_app.command("explain")
def cli_explain(
    root: str | None = root_option(
        "Workspace root for acquisition. Default: EUTAXIS_ROOT, then the nearest "
        "configuration root, then the current folder."
    ),
    manifest: str = typer.Option(
        ...,
        "--manifest",
        help="Acquisition manifest path, relative to the current folder.",
    ),
    lock: str = typer.Option(
        ...,
        "--lock",
        help="Acquisition lock path, relative to the current folder.",
    ),
    manifest_id: str = typer.Option(
        ...,
        "--manifest-id",
        help="Composition-manifest declaration to resolve.",
    ),
    context: list[str] | None = typer.Option(
        None,
        "--context",
        help="Typed context entry as KEY=JSON_VALUE; repeat for each facet.",
    ),
) -> None:
    """Explain one completed resolution as a canonical query packet."""
    try:
        workspace = command_root(root)
        manifest_path = _path_below_root(manifest, workspace, role="manifest")
        lock_path = _path_below_root(lock, workspace, role="lock")
        parsed_context = _parse_context_options(context or [])
    except ValueError as exc:
        _exit_explain(exc, code=2, completion="not-started")

    acquisition: ExternalAcquisitionResult | None = None
    try:
        acquisition = acquire_external_declarations_from_path(
            str(workspace), manifest_path, lock_path
        )
        resolution = resolve_external_compilation_unit(
            acquisition,
            manifest_id,
            parsed_context,
        )
        packet = build_external_query_packet(resolution)
        content = query_packet_json_bytes(packet)
    except ExternalResolutionError as exc:
        _exit_failed_resolution(acquisition, exc)
    except FacetContextError as exc:
        _retire_explain_acquisition(acquisition, primary_error=exc)
        _exit_explain(exc, code=2, completion="failed")
    except AcquisitionAuthorityError as exc:
        _retire_explain_acquisition(acquisition, primary_error=exc)
        _exit_explain(exc, code=3, completion="failed")
    except (
        AcquisitionContractError,
        DeclarationError,
        FacetRegistryError,
        QueryPacketError,
    ) as exc:
        _retire_explain_acquisition(acquisition, primary_error=exc)
        _exit_explain(exc, code=1, completion="failed")
    except (ByteCarrierError, OSError) as exc:
        _retire_explain_acquisition(acquisition, primary_error=exc)
        _exit_explain(exc, code=3, completion="failed")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _retire_explain_acquisition(acquisition, primary_error=exc)
        _exit_explain(exc, code=3, completion="failed")
    except BaseException as exc:
        _retire_explain_acquisition(acquisition, primary_error=exc)
        raise

    cleanup_error = _retire_explain_acquisition(acquisition)
    if cleanup_error is not None:
        _exit_explain(
            cleanup_error,
            code=3,
            completion="complete",
            command_completion="failed",
        )
    try:
        _write_exact_stdout(content)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _exit_explain(
            exc,
            code=3,
            completion="complete",
            command_completion="failed",
        )


def _path_below_root(path: str, root: Path, *, role: str) -> str:
    """Convert one current-folder path to its safe root-relative form."""
    resolved = command_path(path)
    if resolved is None:  # pragma: no cover - Typer requires the option value.
        raise ValueError(f"{role} path is required")
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{role} path resolves outside root {root}") from exc
    return relative.as_posix()


def _parse_context_options(entries: list[str]) -> dict[str, object]:
    """Parse unique ``KEY=JSON_VALUE`` options without implicit coercion."""
    context: dict[str, object] = {}
    for entry in entries:
        key, separator, encoded = entry.partition("=")
        if not separator or not key or not encoded:
            raise ValueError(
                f"invalid context entry {entry!r}; expected KEY=JSON_VALUE"
            )
        if key in context:
            raise ValueError(f"duplicate context facet {key!r}")
        try:
            context[key] = json.loads(
                encoded,
                parse_constant=_reject_json_constant,
                parse_float=_finite_json_float,
                object_pairs_hook=_unique_json_object,
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid JSON value for context facet {key!r}: {exc.msg}"
            ) from exc
    return context


def _reject_json_constant(value: str) -> NoReturn:
    """Reject JavaScript constants that are outside the JSON grammar."""
    raise ValueError(f"non-JSON constant {value!r}")


def _finite_json_float(value: str) -> float:
    """Parse one JSON number only when its binary value remains finite."""
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"JSON number {value!r} is outside the finite range")
    return parsed


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build one JSON object while rejecting duplicate member names."""
    value: dict[str, object] = {}
    for key, member in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON object member {key!r}")
        value[key] = member
    return value


def _retire_explain_acquisition(
    acquisition: ExternalAcquisitionResult | None,
    *,
    primary_error: BaseException | None = None,
) -> BaseException | None:
    """Retire retained authority without replacing an existing failure."""
    if acquisition is None:
        return None
    try:
        _retire_external_result_tree(acquisition)
    except BaseException as cleanup_error:  # pylint: disable=broad-exception-caught
        if primary_error is not None:
            _attach_cleanup_cause(primary_error, cleanup_error)
            primary_error.add_note(
                f"Cleanup error: {_safe_exception_text(cleanup_error)}"
            )
        return cleanup_error
    return None


def _exit_failed_resolution(
    acquisition: ExternalAcquisitionResult | None,
    error: ExternalResolutionError,
) -> NoReturn:
    """Write one closed partial trace and retain the semantic exit status."""
    if acquisition is None:
        _exit_explain(error, code=1, completion="failed")
    try:
        content = external_resolution_failure_json_bytes(error)
    except Exception as diagnostic_error:  # pylint: disable=broad-exception-caught
        _retire_explain_acquisition(acquisition, primary_error=diagnostic_error)
        _exit_explain(
            diagnostic_error,
            code=3,
            completion="failed",
            command_completion="failed",
        )
    _retire_explain_acquisition(acquisition, primary_error=error)
    try:
        _write_exact_stdout(content)
    except Exception as output_error:  # pylint: disable=broad-exception-caught
        _attach_cleanup_cause(output_error, error)
        _exit_explain(
            output_error,
            code=3,
            completion="failed",
            command_completion="failed",
        )
    for note in _safe_exception_notes(error):
        typer.echo(note, err=True)
    raise typer.Exit(code=1) from error


def _exit_explain(
    error: BaseException,
    *,
    code: int,
    completion: str,
    command_completion: str | None = None,
) -> NoReturn:
    """Report explicit resolution completion before one command failure."""
    typer.echo(f"Resolution completion: {completion}", err=True)
    if command_completion is not None:
        typer.echo(f"Command completion: {command_completion}", err=True)
    typer.echo(f"Error: {_safe_exception_text(error)}", err=True)
    for note in _safe_exception_notes(error):
        typer.echo(note, err=True)
    raise typer.Exit(code=code) from error


def _safe_exception_text(error: BaseException) -> str:
    """Render one failure without trusting exception string conversion."""
    try:
        return str(error)
    except BaseException as rendering_error:  # pylint: disable=broad-exception-caught
        return (
            f"<{type(error).__name__}: string conversion failed with "
            f"{type(rendering_error).__name__}>"
        )


def _safe_exception_notes(error: BaseException) -> tuple[str, ...]:
    """Return printable exception notes despite malformed note state."""
    try:
        notes = getattr(error, "__notes__", ())
    except BaseException as reading_error:  # pylint: disable=broad-exception-caught
        return (
            "<exception notes unreadable: "
            f"{type(reading_error).__name__}>",
        )
    if type(notes) not in (list, tuple):
        return (f"<malformed exception notes: {type(notes).__name__}>",)
    return tuple(_safe_value_text(note) for note in notes)


def _safe_value_text(value: object) -> str:
    """Render one untrusted diagnostic value without invoking a traceback."""
    try:
        return str(value)
    except BaseException as rendering_error:  # pylint: disable=broad-exception-caught
        return (
            f"<{type(value).__name__}: string conversion failed with "
            f"{type(rendering_error).__name__}>"
        )


@declarations_app.command("lock")
def cli_lock(
    workspace: str = typer.Option(
        ...,
        "--workspace",
        help="Workspace root retained for manifest and source acquisition.",
    ),
    manifest: str = typer.Option(
        ...,
        "--manifest",
        help="Workspace-relative acquisition manifest path.",
    ),
    check: str | None = typer.Option(
        None,
        "--check",
        help="Workspace-relative lock path to compare without repair.",
    ),
    output: str | None = typer.Option(
        None,
        "--output",
        help="Workspace-relative absent path to create without replacement.",
    ),
) -> None:
    """Generate and semantically validate one canonical acquisition lock."""
    if check is not None and output is not None:
        typer.echo("Error: --check and --output are mutually exclusive.", err=True)
        raise typer.Exit(code=2)

    try:
        trusted = _trusted_directory_from_workspace_path(workspace)
    except (ByteCarrierError, OSError) as exc:
        _exit_error(exc, code=2)

    try:
        try:
            candidate_bytes = _validated_workspace_candidate_bytes(trusted, manifest)
        except BaseException as primary_error:
            try:
                trusted.close()
            except BaseException as cleanup_error:
                _attach_cleanup_cause(primary_error, cleanup_error)
            raise

        if check is not None:
            matches = _check_candidate_bytes(trusted, check, candidate_bytes)
            trusted.close()
            if not matches:
                typer.echo(f"Drift: checked lock differs at {check!r}.", err=True)
                raise typer.Exit(code=1)
            return
        if output is not None:
            outcome = _publish_candidate_bytes(
                trusted,
                output,
                candidate_bytes,
            )
            trusted_warning: str | None = None
            try:
                trusted.close()
            except BaseException as cleanup_error:
                trusted_warning = f"workspace cleanup failed: {cleanup_error}"
            _echo_publication_warnings(
                outcome.cleanup_warning,
                outcome.temporary_residue,
                trusted_warning,
            )
            return
        trusted.close()
        _write_exact_stdout(candidate_bytes)
    except typer.Exit:
        raise
    except _LockPublicationError as exc:
        _close_workspace_after_failure(trusted, exc)
        _exit_error(exc, code=2)
    except ByteCarrierError as exc:
        _close_workspace_after_failure(trusted, exc)
        _exit_error(exc, code=2)
    except (AcquisitionContractError, DeclarationError) as exc:
        _close_workspace_after_failure(trusted, exc)
        _exit_error(exc, code=1)
    except OSError as exc:
        _close_workspace_after_failure(trusted, exc)
        _exit_error(exc, code=2)


def _write_exact_stdout(content: bytes) -> None:
    """Write complete canonical bytes or fail after the first stalled write."""
    stream = click.get_binary_stream("stdout")
    offset = 0
    while offset < len(content):
        remaining = content[offset:]
        written = stream.write(remaining)
        if type(written) is not int or not 1 <= written <= len(remaining):
            raise OSError("standard-output write returned an invalid byte count")
        offset += written
    stream.flush()


def _echo_publication_warnings(
    cleanup_warning: str | None,
    temporary_residue: str | None,
    workspace_warning: str | None,
) -> None:
    """Report every post-commit cleanup side effect on standard error."""
    for warning in (cleanup_warning, workspace_warning):
        if warning is not None:
            typer.echo(f"Warning: {warning}", err=True)
    if temporary_residue is not None:
        typer.echo(
            f"Warning: temporary file may remain at {temporary_residue!r}.",
            err=True,
        )


def _exit_error(error: BaseException, *, code: int) -> None:
    """Report one declaration command failure on standard error."""
    typer.echo(f"Error: {error}", err=True)
    raise typer.Exit(code=code) from error


def _close_workspace_after_failure(
    workspace: TrustedDirectory,
    primary_error: BaseException,
) -> None:
    """Retire the workspace capability without replacing the command failure."""
    try:
        workspace.close()
    except BaseException as cleanup_error:
        _attach_cleanup_cause(primary_error, cleanup_error)
