"""
Command-line interface for the `eutaxis` package.

Defines commands available via `python -m eutaxis` or `eutaxis` if installed as a script.

Commands
--------
info : Display diagnostic information.
generate : Assemble agent instruction files.
validate : Validate prompt family layouts (planned).
init : Scaffold prompt composition into a project (planned).
"""

import typer
from . import info as pkg_info, __version__

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command("info")
def cli_info() -> None:
    """Display version and platform diagnostics."""
    typer.echo(pkg_info())


@app.command("generate")
def cli_generate(
    config: str = typer.Option(
        "agent-instructions.yaml",
        "--config",
        "-c",
        help="Path to generation config.",
    ),
    root: str | None = typer.Option(
        None,
        "--root",
        "-r",
        help="Root used to resolve relative source and target paths.",
    ),
    agent: str | None = typer.Option(
        None,
        "--agent",
        "-a",
        help="Generate only one configured agent output.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show targets without writing files.",
    ),
) -> None:
    """Assemble agent instruction files from modular prompt sources."""
    from pathlib import Path as P
    from .instructions import InstructionError, InstructionGenerator, load_config

    try:
        loaded = load_config(P(config), root=P(root) if root else None)
        generator = InstructionGenerator(loaded)
        paths = generator.write_all(agent_name=agent, dry_run=dry_run)
    except InstructionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    verb = "Would generate" if dry_run else "Generated"
    typer.echo(f"{verb} {len(paths)} instruction file(s):")
    for path in paths:
        typer.echo(f"  - {path}")


@app.command("check")
def cli_check(
    config: str = typer.Option(
        "agent-instructions.yaml",
        "--config",
        "-c",
        help="Path to generation config.",
    ),
    root: str | None = typer.Option(
        None,
        "--root",
        "-r",
        help="Root used to resolve relative source and target paths.",
    ),
    agent: str | None = typer.Option(
        None,
        "--agent",
        "-a",
        help="Check only one configured agent output.",
    ),
    diff: bool = typer.Option(
        False,
        "--diff",
        help="Print unified diffs for stale outputs.",
    ),
) -> None:
    """Check whether generated instruction files are up to date."""
    from pathlib import Path as P
    from .instructions import InstructionError, InstructionGenerator, load_config

    try:
        loaded = load_config(P(config), root=P(root) if root else None)
        generator = InstructionGenerator(loaded)
        reports = list(generator.diff_report(agent_name=agent))
    except InstructionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    stale = False
    for agent_config, path, differs in reports:
        status = "OUTDATED" if differs else "OK"
        typer.echo(f"[{status:8}] {agent_config.name}: {path}")
        stale = stale or differs
        if diff and differs:
            typer.echo(generator.unified_diff(agent_config.name))

    if stale:
        raise typer.Exit(code=1)


@app.command("list")
def cli_list(
    config: str = typer.Option(
        "agent-instructions.yaml",
        "--config",
        "-c",
        help="Path to generation config.",
    ),
    root: str | None = typer.Option(
        None,
        "--root",
        "-r",
        help="Root used to resolve relative source and target paths.",
    ),
) -> None:
    """List configured instruction outputs and their source counts."""
    from pathlib import Path as P
    from .instructions import InstructionError, load_config

    try:
        loaded = load_config(P(config), root=P(root) if root else None)
    except InstructionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    typer.echo(f"Configuration: {loaded.config_path}")
    typer.echo(f"Root: {loaded.root}")
    typer.echo("")
    typer.echo("Common sources:")
    for source in loaded.common_sources:
        typer.echo(f"  - {source.path}")
    typer.echo("")
    typer.echo("Agents:")
    for agent_config in loaded.agents:
        status = "enabled" if agent_config.enabled else "disabled"
        target = loaded.resolve(agent_config.target.path)
        typer.echo(f"  - {agent_config.name} ({status}) -> {target}")
        for source in agent_config.sources:
            typer.echo(f"      source: {source.path}")


@app.command("validate")
def cli_validate(
    paths: list[str] = typer.Argument(..., help="Prompt family files or directories to validate."),
) -> None:
    """Validate prompt family layouts and configs (planned)."""
    _ = paths
    typer.echo("Prompt validation is not yet implemented.")
    raise typer.Exit(code=0)


@app.command("init")
def cli_init(
    target: str = typer.Option(".", "--target", "-t", help="Target workspace directory."),
    template: str = typer.Option(
        "codex-project",
        "--template",
        help="Template directory under eutaxis data/templates.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing scaffold files.",
    ),
) -> None:
    """Scaffold prompt-composition structure into a project."""
    from pathlib import Path as P
    from .scaffold import ScaffoldError, scaffold_workspace

    try:
        paths = scaffold_workspace(P(target), template=template, force=force)
    except ScaffoldError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Created {len(paths)} file(s):")
    for path in paths:
        typer.echo(f"  - {path}")


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False, "--version", "-v", help="Show the package version and exit."
    )
) -> None:
    """Prompt composition framework."""
    if version:
        typer.echo(__version__)
        raise typer.Exit()
