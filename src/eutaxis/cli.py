"""
Command-line interface for the ``eutaxis`` package.

Defines commands available via ``python -m eutaxis`` or ``eutaxis`` if
installed as a script. Subcommands:

- ``info`` — display diagnostic information.
- ``generate`` — assemble agent instruction files.
- ``rule`` — print individual rules of instruction modules or skills.
- ``validate`` — validate prompt family layouts (planned).
- ``init`` — scaffold prompt composition into a project (planned).
"""

from typing import TYPE_CHECKING

import typer
from . import info as pkg_info, __version__
from .commands._cli import commands_app
from .commands._skills_cli import skills_app
from .ops._cli import ops_app
from .rule_query._cli import rule_app

if TYPE_CHECKING:
    from .instructions import InstructionGenerator

app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(commands_app, name="commands")
app.add_typer(skills_app, name="skills")
app.add_typer(ops_app, name="ops")
app.add_typer(rule_app, name="rule")


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
    plan: bool = typer.Option(
        False,
        "--plan",
        help="With --dry-run, report target drift and all cumulative budgets.",
    ),
    ignore_budget: bool = typer.Option(
        False,
        "--ignore-budget",
        help="Render even if outputs exceed their configured max_bytes.",
    ),
) -> None:
    """Assemble agent instruction files from modular prompt sources.

    Every label line rejected by the label grammar is reported on standard
    error. Under ``strict_rule_labels``, such a line fails the command before
    any file is written.
    """
    from pathlib import Path as P
    from .instructions import InstructionError, InstructionGenerator, load_config

    if plan and not dry_run:
        typer.echo("Error: --plan requires --dry-run.", err=True)
        raise typer.Exit(code=2)

    try:
        loaded = load_config(P(config), root=P(root) if root else None)
        generator = InstructionGenerator(loaded)
        _echo_rejected_labels(generator)
        paths = generator.write_all(
            agent_name=agent,
            dry_run=dry_run,
            enforce_budget=not ignore_budget,
        )
    except InstructionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    if plan:
        _echo_generation_plan(generator, agent_name=agent)
        return

    verb = "Would generate" if dry_run else "Generated"
    typer.echo(f"{verb} {len(paths)} instruction file(s):")
    for path in paths:
        typer.echo(f"  - {path}")


def _echo_generation_plan(
    generator: "InstructionGenerator",
    *,
    agent_name: str | None,
) -> None:
    """Report cumulative target drift and budgets without printing full files."""
    budgets = {
        agent.name: (size, limit)
        for agent, size, limit in generator.budget_report(agent_name=agent_name)
    }
    for agent, path, differs in generator.diff_report(agent_name=agent_name):
        size, limit = budgets[agent.name]
        status = "CREATE" if differs and not path.exists() else "UPDATE"
        if not differs:
            status = "UNCHANGED"
        limit_text = "unlimited" if limit is None else str(limit)
        change_text = ""
        if differs:
            added, removed = _line_changes(generator.unified_diff(agent.name))
            change_text = f", +{added}/-{removed} lines"
        typer.echo(
            f"[{status:9}] {agent.name} [{size}/{limit_text} B{change_text}]: "
            f"{path}"
        )

    if agent_name is None:
        standalone = generator.standalone_rule_index_diff()
        if standalone is not None:
            path, content, diff = standalone
            status = "CREATE" if diff and not path.exists() else "UPDATE"
            if not diff:
                status = "UNCHANGED"
            change_text = ""
            if diff:
                added, removed = _line_changes(diff)
                change_text = f", +{added}/-{removed} lines"
            typer.echo(
                f"[{status:9}] rule-index "
                f"[{len(content.encode('utf-8'))} B{change_text}]: {path}"
            )

    for chain, size, limit in generator.instruction_chain_budget_report(
        agent_name=agent_name
    ):
        typer.echo(
            f"[CHAIN    ] {chain.name} [{size}/{limit} B]: "
            f"{chain.agent} + {len(chain.sources)} project file(s)"
        )


def _line_changes(diff: str) -> tuple[int, int]:
    """Count lines added and deleted in one unified diff."""
    added = sum(
        line.startswith("+") and not line.startswith("+++")
        for line in diff.splitlines()
    )
    removed = sum(
        line.startswith("-") and not line.startswith("---")
        for line in diff.splitlines()
    )
    return added, removed


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
    ignore_budget: bool = typer.Option(
        False,
        "--ignore-budget",
        help="Do not exit non-zero when outputs exceed max_bytes.",
    ),
) -> None:
    """Check whether generated instruction files are up to date.

    Rejected label lines are reported as by ``generate``, and they fail the
    check under ``strict_rule_labels``.
    """
    from pathlib import Path as P
    from .instructions import InstructionError, InstructionGenerator, load_config

    try:
        loaded = load_config(P(config), root=P(root) if root else None)
        generator = InstructionGenerator(loaded)
        _echo_rejected_labels(generator)
        generator.enforce_rule_labels()
        diff_reports = list(generator.diff_report(agent_name=agent))
        budget_reports = {
            entry[0].name: (entry[1], entry[2])
            for entry in generator.budget_report(agent_name=agent)
        }
        chain_reports = list(
            generator.instruction_chain_budget_report(agent_name=agent)
        )
    except InstructionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    stale = False
    over_budget = False
    for agent_config, path, differs in diff_reports:
        size, limit = budget_reports[agent_config.name]
        over = limit is not None and size > limit
        if over and not ignore_budget:
            over_budget = True
        status = "OUTDATED" if differs else "OK"
        if limit is None:
            size_note = f"{size} B"
        else:
            flag = "OVER" if over else "ok"
            size_note = f"{size}/{limit} B {flag}"
        typer.echo(f"[{status:8}] {agent_config.name} [{size_note}]: {path}")
        stale = stale or differs
        if diff and differs:
            typer.echo(generator.unified_diff(agent_config.name))

    for chain, size, limit in chain_reports:
        over = size > limit
        if over and not ignore_budget:
            over_budget = True
        flag = "OVER" if over else "ok"
        typer.echo(
            f"[CHAIN   ] {chain.name} [{size}/{limit} B {flag}]: "
            f"{chain.agent} + {len(chain.sources)} project file(s)"
        )

    if stale or over_budget:
        raise typer.Exit(code=1)


def _echo_rejected_labels(generator: "InstructionGenerator") -> None:
    """Print each rejected label line of the declared modules on standard error."""
    for path, rejection in generator.rejected_labels():
        typer.echo(
            f"warning: {path}:{rejection.line_number}: {rejection.message}", err=True
        )


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


@app.command("scan")
def cli_scan(
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
        help="Override the directory walked for instruction files.",
    ),
    register: bool = typer.Option(
        False,
        "--register",
        help="Print a YAML snippet registering any unregistered files.",
    ),
) -> None:
    """Report instruction files that drift from the configured registry."""
    from pathlib import Path as P
    from .instructions import (
        InstructionError,
        format_registration_snippet,
        load_config,
        scan_instructions,
    )

    try:
        loaded = load_config(P(config), root=P(root) if root else None)
        report = scan_instructions(
            loaded, root=P(root) if root else None
        )
    except InstructionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    typer.echo(
        f"Registered and present: {len(report.registered_present)}"
    )
    typer.echo(
        f"Unregistered and present: {len(report.unregistered_present)}"
    )
    for path in report.unregistered_present:
        typer.echo(f"  + {path}")
    typer.echo(
        f"Registered but missing: {len(report.registered_missing)}"
    )
    for path in report.registered_missing:
        typer.echo(f"  - {path}")
    if report.frontmatter_errors:
        typer.echo(f"Frontmatter errors: {len(report.frontmatter_errors)}")
        for path, message in report.frontmatter_errors:
            typer.echo(f"  ! {path}: {message}")

    if register and report.unregistered_present:
        snippet = format_registration_snippet(
            loaded, report.unregistered_present
        )
        typer.echo("")
        typer.echo("# Suggested config addition:")
        typer.echo(snippet, nl=False)

    if report.has_issues:
        raise typer.Exit(code=1)


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
