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

from typing import TYPE_CHECKING, NoReturn

import typer
from . import info as pkg_info, __version__
from ._cli_options import command_path, command_root, root_option
from .commands._cli import commands_app
from .commands._skills_cli import skills_app
from .declarations._cli import declarations_app
from .ops._cli import ops_app
from .rule_query._cli import rule_app

if TYPE_CHECKING:
    from .declarations import ResolvedCumulativeSource
    from .instructions import DeclarationSource, InstructionConfig, InstructionGenerator

_CONFIG_HELP = (
    "Configuration file, relative to the current folder. Default: "
    "config/tools/eutaxis.yml or eutaxis.yml below the root."
)
_ROOT_HELP = (
    "Folder below which the configuration file is looked up and against which the "
    "paths of the configuration file resolve. Default: EUTAXIS_ROOT, then the "
    "nearest folder above the current one that holds the configuration file, then "
    "the current folder."
)

app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(commands_app, name="commands")
app.add_typer(declarations_app, name="declarations")
app.add_typer(skills_app, name="skills")
app.add_typer(ops_app, name="ops")
app.add_typer(rule_app, name="rule")


@app.command("info")
def cli_info() -> None:
    """Display version and platform diagnostics."""
    typer.echo(pkg_info())


@app.command("generate")
def cli_generate(
    config: str | None = typer.Option(None, "--config", "-c", help=_CONFIG_HELP),
    root: str | None = root_option(_ROOT_HELP),
    agent: str | None = typer.Option(
        None,
        "--agent",
        "-a",
        help="Generate only one configured agent output.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show targets without writing files.",
    ),
    plan: bool = typer.Option(
        False,
        "--plan",
        help=(
            "With --dry-run, report structured selections, target drift, "
            "cumulative budgets and final command state."
        ),
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
    from .instructions import InstructionError, InstructionGenerator

    if plan and not dry_run:
        _exit_artifact_command(ValueError("--plan requires --dry-run"), code=2)

    try:
        loaded = _load_settings(config, root)
        generator = InstructionGenerator(loaded)
        resolution_reports = (
            generator.declaration_resolution_report(agent_name=agent) if plan else []
        )
        _echo_rejected_labels(generator)
        paths = generator.write_all(
            agent_name=agent,
            dry_run=dry_run,
            enforce_budget=not ignore_budget,
        )
        report_lines = None
        if plan:
            report_lines = _declaration_resolution_report_lines(resolution_reports)
            report_lines.extend(_generation_plan_lines(generator, agent_name=agent))
            report_lines.append("[COMMAND  ] complete")
    except InstructionError as exc:
        if plan:
            _exit_artifact_command(exc, code=exc.exit_code)
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc
    except Exception as exc:  # pylint: disable=broad-exception-caught
        if plan:
            _exit_artifact_command(exc, code=2)
        raise

    if plan:
        assert report_lines is not None
        _write_artifact_command_report(report_lines)
        return

    verb = "Would generate" if dry_run else "Generated"
    typer.echo(f"{verb} {len(paths)} instruction file(s):")
    for path in paths:
        typer.echo(f"  - {path}")


def _generation_plan_lines(
    generator: "InstructionGenerator",
    *,
    agent_name: str | None,
) -> list[str]:
    """Report cumulative target drift and budgets without printing full files."""
    lines: list[str] = []
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
        lines.append(
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
            lines.append(
                f"[{status:9}] rule-index "
                f"[{len(content.encode('utf-8'))} B{change_text}]: {path}"
            )

    for chain, size, limit in generator.instruction_chain_budget_report(
        agent_name=agent_name
    ):
        lines.append(
            f"[CHAIN    ] {chain.name} [{size}/{limit} B]: "
            f"{chain.agent} + {len(chain.sources)} project file(s)"
        )
    return lines


def _declaration_resolution_report_lines(
    reports: list[tuple["DeclarationSource", "ResolvedCumulativeSource"]],
) -> list[str]:
    """Report each resolved artifact and its ordered effective records."""
    lines: list[str] = []
    for source, resolved in reports:
        report = resolved.selection
        lines.append(
            f"[SELECT   ] {source.module} <= {report.manifest} "
            f"[{report.mechanism}, {report.scope}, {report.target}, "
            f"{resolved.sha256}]"
        )
        if report.records:
            for record in report.records:
                lines.append(f"  - {record}")
        else:
            lines.append("  - <none>")
    return lines


def _write_artifact_command_report(lines: list[str]) -> None:
    """Publish one complete report or return an operational failure."""
    try:
        typer.echo("\n".join(lines))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _exit_artifact_command(exc, code=2)


def _exit_artifact_command(error: BaseException, *, code: int) -> NoReturn:
    """Report one failed artifact command on the remaining usable stream."""
    try:
        typer.echo(f"Error: {error}", err=True)
        typer.echo("[COMMAND  ] failed", err=True)
    except Exception:  # pragma: no cover - no usable output stream remains.
        pass
    raise typer.Exit(code=code) from error


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
    config: str | None = typer.Option(None, "--config", "-c", help=_CONFIG_HELP),
    root: str | None = root_option(_ROOT_HELP),
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
    from .instructions import InstructionError, InstructionGenerator

    try:
        loaded = _load_settings(config, root)
        generator = InstructionGenerator(loaded)
        resolution_reports = generator.declaration_resolution_report(
            agent_name=agent
        )
        _echo_rejected_labels(generator)
        generator.enforce_rule_labels()
        lines, findings = _check_report_lines(
            generator,
            resolution_reports,
            agent_name=agent,
            show_diff=diff,
            ignore_budget=ignore_budget,
        )
    except InstructionError as exc:
        _exit_artifact_command(exc, code=exc.exit_code)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _exit_artifact_command(exc, code=2)

    _write_artifact_command_report(lines)
    if findings:
        raise typer.Exit(code=1)


def _check_report_lines(
    generator: "InstructionGenerator",
    resolution_reports: list[tuple["DeclarationSource", "ResolvedCumulativeSource"]],
    *,
    agent_name: str | None,
    show_diff: bool,
    ignore_budget: bool,
) -> tuple[list[str], bool]:
    """Construct one complete check report before any standard-output write."""
    diff_reports = list(generator.diff_report(agent_name=agent_name))
    budget_reports = {
        entry[0].name: (entry[1], entry[2])
        for entry in generator.budget_report(agent_name=agent_name)
    }
    chain_reports = list(generator.instruction_chain_budget_report(agent_name=agent_name))
    standalone_report = (
        generator.standalone_rule_index_diff() if agent_name is None else None
    )
    lines = _declaration_resolution_report_lines(resolution_reports)
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
        lines.append(f"[{status:8}] {agent_config.name} [{size_note}]: {path}")
        stale = stale or differs
        if show_diff and differs:
            lines.append(generator.unified_diff(agent_config.name).rstrip("\n"))

    if standalone_report is not None:
        path, content, standalone_diff = standalone_report
        differs = bool(standalone_diff)
        status = "OUTDATED" if differs else "OK"
        lines.append(
            f"[{status:8}] rule-index [{len(content.encode('utf-8'))} B]: {path}"
        )
        stale = stale or differs
        if show_diff and differs:
            lines.append(standalone_diff.rstrip("\n"))

    for chain, size, limit in chain_reports:
        over = size > limit
        if over and not ignore_budget:
            over_budget = True
        flag = "OVER" if over else "ok"
        lines.append(
            f"[CHAIN   ] {chain.name} [{size}/{limit} B {flag}]: "
            f"{chain.agent} + {len(chain.sources)} project file(s)"
        )

    lines.append("[COMMAND  ] complete")
    return lines, stale or over_budget


def _echo_rejected_labels(generator: "InstructionGenerator") -> None:
    """Print each rejected label line of the declared modules on standard error."""
    for path, rejection in generator.rejected_labels():
        typer.echo(
            f"warning: {path}:{rejection.line_number}: {rejection.message}", err=True
        )


def _load_settings(config: str | None, root: str | None) -> "InstructionConfig":
    """Find and load the configuration file of a command.

    The root comes from ``--root``, ``EUTAXIS_ROOT``, the nearest folder that
    holds the configuration file, or the current folder. Without ``--config``, the
    configuration file is looked up below the root. The paths written in the file
    resolve against the root.
    """
    from .instructions import find_config, load_config

    base = command_root(root)
    config_path = find_config(command_path(config), base)
    return load_config(config_path, root=base)


@app.command("list")
def cli_list(
    config: str | None = typer.Option(None, "--config", "-c", help=_CONFIG_HELP),
    root: str | None = root_option(_ROOT_HELP),
) -> None:
    """List configured instruction outputs and their source counts."""
    from .instructions import DeclarationSource, InstructionError

    try:
        loaded = _load_settings(config, root)
    except InstructionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    typer.echo(f"Configuration: {loaded.config_path}")
    typer.echo(f"Root: {loaded.root}")
    typer.echo("")
    typer.echo("Common sources:")
    for source in loaded.common_sources:
        if isinstance(source, DeclarationSource):
            typer.echo(
                f"  - declaration {source.composition_manifest} "
                f"as {source.module}"
            )
        else:
            typer.echo(f"  - {source.path}")
    typer.echo("")
    typer.echo("Agents:")
    for agent_config in loaded.agents:
        status = "enabled" if agent_config.enabled else "disabled"
        target = loaded.resolve(agent_config.target.path)
        typer.echo(f"  - {agent_config.name} ({status}) -> {target}")
        for source in agent_config.sources:
            if isinstance(source, DeclarationSource):
                typer.echo(
                    f"      declaration: {source.composition_manifest} "
                    f"as {source.module}"
                )
            else:
                typer.echo(f"      source: {source.path}")


@app.command("scan")
def cli_scan(
    config: str | None = typer.Option(None, "--config", "-c", help=_CONFIG_HELP),
    root: str | None = root_option(_ROOT_HELP),
    directory: str | None = typer.Option(
        None,
        "--dir",
        help=(
            "Folder walked for instruction files, relative to the current "
            "folder. Default: the folders of the registered files."
        ),
    ),
    register: bool = typer.Option(
        False,
        "--register",
        help="Print a YAML snippet registering any unregistered files.",
    ),
) -> None:
    """Report instruction files that drift from the configured registry."""
    from .instructions import (
        InstructionError,
        format_registration_snippet,
        scan_instructions,
    )

    try:
        loaded = _load_settings(config, root)
        report = scan_instructions(loaded, directory=command_path(directory))
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
    root: str | None = root_option(
        "Folder that receives the scaffold. Default: EUTAXIS_ROOT, then the "
        "nearest folder above the current one that holds the configuration file, "
        "then the current folder."
    ),
    template: str = typer.Option(
        "codex-project",
        "--template",
        help="Template directory under eutaxis data/templates.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing scaffold files, which may hold edits.",
    ),
) -> None:
    """Scaffold prompt-composition structure into a project."""
    from .scaffold import ScaffoldError, scaffold_workspace

    try:
        paths = scaffold_workspace(command_root(root), template=template, force=force)
    except ScaffoldError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

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
