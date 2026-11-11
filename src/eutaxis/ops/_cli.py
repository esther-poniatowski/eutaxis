"""Typer sub-app for ``eutaxis ops``."""

from __future__ import annotations

import functools

import typer

from .._cli_options import command_root, confirmation_needed, reports_errors, root_option
from .memory import MemoryWipeResult, clean_memory

ops_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Imperative shell-side doers invoked by compiled commands.",
)


@ops_app.command("list")
def cli_list() -> None:
    """List available operations."""
    typer.echo("- clean-memory: Delete agent memory directories.")


@ops_app.command("clean-memory")
@reports_errors
def cli_clean_memory(
    agent: str = typer.Option(
        ..., "--agent", "-a", help="claude | codex | all"
    ),
    root: str | None = root_option(
        "Project folder whose agent memory is deleted. Default: EUTAXIS_ROOT, "
        "then the nearest folder above the current one that holds the "
        "settings file, then the current folder."
    ),
    wipe_all: bool = typer.Option(
        False, "--all", help="Wipe all Claude project memories, not just the current one."
    ),
    backup: bool = typer.Option(
        False, "--backup", help="Copy target dir to a timestamped sibling first."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report paths without touching the filesystem."
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help=(
            "Answer the confirmation. Without a terminal, the deletion "
            "requires it."
        ),
    ),
) -> None:
    """Delete this project's agent memory files (Claude and/or Codex).

    The memory files lie outside the outputs of Eutaxis, so the deletion asks
    for a confirmation on a terminal. ``--yes`` answers it; without a
    terminal and without ``--yes``, the command stops with status 2. A
    declined confirmation deletes nothing and exits with status 1.
    """
    clean = functools.partial(
        clean_memory,
        agent=agent,
        project_root=command_root(root),
        wipe_all=wipe_all,
        backup=backup,
    )
    if not dry_run and confirmation_needed(yes, "Deleting agent memory"):
        preview = clean(dry_run=True)
        if preview.removed:
            _echo_result(preview, "Would remove")
            if not typer.confirm(
                f"Delete these {len(preview.removed)} file(s)?", default=False
            ):
                typer.echo("Nothing deleted.")
                raise typer.Exit(1)

    result = clean(dry_run=dry_run)
    _echo_result(result, "Would remove" if dry_run else "Removed")


def _echo_result(result: MemoryWipeResult, verb: str) -> None:
    """Print the files removed, or to remove, with backups and skipped paths."""
    typer.echo(f"{verb} {len(result.removed)} file(s):")
    for path in result.removed:
        typer.echo(f"  - {path}")
    if result.backup_paths:
        typer.echo("Backups:")
        for path in result.backup_paths:
            typer.echo(f"  - {path}")
    if result.skipped:
        typer.echo("Skipped (not present):")
        for path in result.skipped:
            typer.echo(f"  - {path}")
