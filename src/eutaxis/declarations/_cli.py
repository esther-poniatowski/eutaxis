"""Typer commands for structured declaration acquisition and lock generation."""

from __future__ import annotations

import click
import typer

from .byte_carriers import TrustedDirectory, _trusted_directory_from_workspace_path
from .candidate_validation import (
    _attach_cleanup_cause,
    _validated_workspace_candidate_bytes,
)
from .exceptions import (
    AcquisitionContractError,
    ByteCarrierError,
    DeclarationError,
)
from .lock_publication import (
    _LockPublicationError,
    _check_candidate_bytes,
    _publish_candidate_bytes,
)

declarations_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Generate and inspect structured-declaration acquisition locks.",
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
