"""
Command-line interface for the `eutaxis` package.

Defines commands available via `python -m eutaxis` or `eutaxis` if installed as a script.

Commands
--------
info : Display diagnostic information.
lint : Lint Markdown files against style rules.
generate : Assemble agent instruction files.
validate : Validate registry files (planned).
init : Scaffold governance into a workspace (planned).
"""

import typer
from . import info as pkg_info, __version__

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command("info")
def cli_info() -> None:
    """Display version and platform diagnostics."""
    typer.echo(pkg_info())


@app.command("lint")
def cli_lint(
    paths: list[str] = typer.Argument(..., help="Markdown files or directories to lint."),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to override config (YAML)."),
    domain: str = typer.Option("math", "--domain", "-d", help="Domain whose rules to apply (default: math)."),
    include_archives: bool = typer.Option(False, "--include-archives", help="Include files under bak/ and to-move/."),
) -> None:
    """Lint Markdown files against style rules."""
    from pathlib import Path as P
    from .lint import main as lint_main, load_config

    override_config = load_config(P(config)) if config else None
    argv = ["--include-archives"] if include_archives else []
    argv.extend(paths)
    code = lint_main(argv, config=override_config, domain=domain)
    raise typer.Exit(code=code)


@app.command("generate")
def cli_generate(
    config: str = typer.Option("agent-instructions.yaml", "--config", "-c", help="Path to generation config."),
    domain: str | None = typer.Option(None, "--domain", "-d", help="Domain to use for default source resolution."),
) -> None:
    """Assemble agent instruction files from governance sources."""
    from pathlib import Path as P
    from .generate import main as gen_main

    code = gen_main(P(config), domain=domain)
    raise typer.Exit(code=code)


@app.command("validate")
def cli_validate(
    paths: list[str] = typer.Argument(..., help="Registry files or directories to validate."),
) -> None:
    """Validate registry files against schemas (planned)."""
    typer.echo("Registry validation is not yet implemented.")
    raise typer.Exit(code=0)


@app.command("init")
def cli_init(
    target: str = typer.Option(".", "--target", "-t", help="Target workspace directory."),
    domain: str = typer.Option("software", "--domain", "-d", help="Domain to scaffold (default: software)."),
) -> None:
    """Scaffold governance structure into a workspace (planned)."""
    typer.echo("Workspace scaffolding is not yet implemented.")
    raise typer.Exit(code=0)


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False, "--version", "-v", help="Show the package version and exit."
    )
) -> None:
    """Domain-agnostic quality validation framework."""
    if version:
        typer.echo(__version__)
        raise typer.Exit()
