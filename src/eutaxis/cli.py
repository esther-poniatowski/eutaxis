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
    config: str = typer.Option("agent-instructions.yaml", "--config", "-c", help="Path to generation config."),
) -> None:
    """Assemble agent instruction files from modular prompt sources."""
    from pathlib import Path as P
    from .generate import main as gen_main

    code = gen_main(P(config))
    raise typer.Exit(code=code)


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
) -> None:
    """Scaffold prompt-composition structure into a project (planned)."""
    _ = target
    typer.echo("Prompt scaffolding is not yet implemented.")
    raise typer.Exit(code=0)


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
