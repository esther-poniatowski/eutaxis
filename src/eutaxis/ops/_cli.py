"""Typer sub-app for ``eutaxis ops``."""

from __future__ import annotations

import typer

from .._cli_options import explicit_root, former_root_option, root_option
from .exceptions import OpsError
from .memory import clean_memory

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
def cli_clean_memory(
    agent: str = typer.Option(
        ..., "--agent", "-a", help="claude | codex | all"
    ),
    root: str | None = root_option(
        "Project folder whose agent memory is deleted. Default: current folder."
    ),
    former_project: str | None = former_root_option("--project"),
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
        False, "--yes", help="Required to perform a non-dry-run deletion."
    ),
) -> None:
    """Delete this project's agent memory files (Claude and/or Codex)."""
    project_root = explicit_root(root, former_project, "--project")
    if not yes and not dry_run:
        typer.echo(
            "Refusing destructive operation without --yes. "
            "Re-run with --yes to confirm, or --dry-run to preview.",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        result = clean_memory(
            agent=agent,
            project_root=project_root,
            wipe_all=wipe_all,
            backup=backup,
            dry_run=dry_run,
        )
    except OpsError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    verb = "Would remove" if dry_run else "Removed"
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
