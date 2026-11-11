"""Typer sub-app for ``eutaxis commands``.

Kept in its own module so ``cli.py`` only wires sub-apps and does not
import the subsystem at startup.
"""

from __future__ import annotations

from pathlib import Path

import typer

from .._cli_options import command_root, reports_errors, root_option
from . import (
    CommandError,
    CommandNotFoundError,
    all_adapters,
    diff_command,
    get_adapter,
    install_command,
    load_sources,
    render_command,
    uninstall_command,
)
from .models import CommandSource
from .registry import Registry, default_state_dir
from .scopes import validate_scope
from .cli_errors import exit_with_error
from .synchronization import skill_write_transaction

_ROOT_HELP = (
    "Project folder whose .eutaxis/commands layer is read, used for project "
    "scope and path substitutions. Default: current folder, without the "
    "project layer."
)

commands_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Manage cross-agent slash commands.",
)


@commands_app.command("list")
@reports_errors
def cli_list(
    root: str | None = root_option(_ROOT_HELP),
) -> None:
    """List all discovered command sources and their targets."""
    project_root = command_root(root)
    sources = _load(project_root)
    if not sources:
        typer.echo("No commands found.")
        return
    adapter_names = [adapter.name for adapter in all_adapters()]
    for source in sources:
        targets = ", ".join(_effective_adapter_names(source, adapter_names))
        typer.echo(
            f"- {source.name} ({source.layer}) -> [{targets}]: {source.description}"
        )


@commands_app.command("show")
@reports_errors
def cli_show(
    name: str,
    agent: str = typer.Option("claude", "--agent", "-a", help="Adapter to render for."),
    root: str | None = root_option(_ROOT_HELP),
) -> None:
    """Render and print one skill artifact for one adapter."""
    project_root = command_root(root)
    source = _require_source(name, project_root)
    adapter = get_adapter(agent)
    rendered = render_command(
        source,
        adapter,
        project_root=project_root,
        home=Path.home(),
    )
    for artifact_file in rendered.files:
        typer.echo(f"--- {artifact_file.relative_path} ---")
        typer.echo(artifact_file.content)


@commands_app.command("install")
@reports_errors
def cli_install(
    name: str,
    scope: str = typer.Option(
        "",
        "--scope",
        help="Install scope (user|project). Defaults to the source's scope_default.",
    ),
    agent: str = typer.Option("all", "--agent", "-a", help="Adapter name or 'all'."),
    root: str | None = root_option(_ROOT_HELP),
    force: bool = typer.Option(
        False, "--force", help="Overwrite non-eutaxis directories at the target."
    ),
) -> None:
    """Install one skill artifact into the selected adapters."""
    project_root = command_root(root)
    try:
        source = _require_source(name, project_root)
        chosen_scope = scope or source.scope_default
        validate_scope(chosen_scope)
        registry = Registry(default_state_dir())
        project = project_root
        adapters = _select_adapters(source, agent, scope=chosen_scope)
    except CommandError as exc:
        exit_with_error(exc)
    paths = [
        adapter.artifact_dir(
            source.name,
            chosen_scope,
            home=Path.home(),
            project_root=project,
        )
        for adapter in adapters
    ]

    try:
        outcomes = []
        with skill_write_transaction(paths, registry):
            for adapter in adapters:
                outcomes.append(
                    install_command(
                        source,
                        adapter,
                        scope=chosen_scope,
                        project_root=project,
                        home=Path.home(),
                        registry=registry,
                        force=force,
                    )
                )
    except (CommandError, OSError) as exc:
        exit_with_error(exc)
    for outcome in outcomes:
        typer.echo(
            f"[{outcome.action:9}] {outcome.name}@{outcome.adapter} "
            f"({outcome.scope}) -> {outcome.path}"
        )


@commands_app.command("uninstall")
@reports_errors
def cli_uninstall(
    name: str,
    scope: str = typer.Option("user", "--scope", help="user|project"),
    agent: str = typer.Option("all", "--agent", "-a"),
    root: str | None = root_option(_ROOT_HELP),
    force: bool = typer.Option(
        False, "--force", help="Delete non-eutaxis directories at the target."
    ),
) -> None:
    """Remove one installed skill artifact from the selected adapters."""
    project_root = command_root(root)
    try:
        validate_scope(scope)
        registry = Registry(default_state_dir())
        project = project_root
        source = _maybe_source(name, project_root)
        adapter_names = (
            [adapter.name for adapter in all_adapters()] if agent == "all" else [agent]
        )
        adapters = []
        for adapter_name in adapter_names:
            if source is not None and adapter_name not in _effective_adapter_names(
                source, [a.name for a in all_adapters()]
            ):
                continue
            adapter = get_adapter(adapter_name)
            if not adapter.supports_scope(scope):
                continue
            adapters.append(adapter)
    except CommandError as exc:
        exit_with_error(exc)
    paths = [
        adapter.artifact_dir(name, scope, home=Path.home(), project_root=project)
        for adapter in adapters
    ]
    try:
        outcomes = []
        with skill_write_transaction(paths, registry):
            for adapter in adapters:
                outcomes.append(
                    uninstall_command(
                        name=name,
                        adapter=adapter,
                        scope=scope,
                        project_root=project,
                        home=Path.home(),
                        registry=registry,
                        force=force,
                    )
                )
    except (CommandError, OSError) as exc:
        exit_with_error(exc)
    for outcome in outcomes:
        typer.echo(
            f"[{outcome.action:9}] {outcome.name}@{outcome.adapter} "
            f"({outcome.scope}) -> {outcome.path}"
        )


@commands_app.command("diff")
@reports_errors
def cli_diff(
    name: str | None = typer.Argument(None, help="Command name (omit for all)."),
    scope: str = typer.Option("user", "--scope"),
    agent: str = typer.Option("all", "--agent", "-a"),
    root: str | None = root_option(_ROOT_HELP),
) -> None:
    """Show drift between rendered output and installed artifacts."""
    project_root = command_root(root)
    try:
        validate_scope(scope)
        sources = (
            [_require_source(name, project_root)]
            if name is not None
            else _load(project_root)
        )
        project = project_root
    except CommandError as exc:
        exit_with_error(exc)

    for source in sources:
        for adapter in _select_adapters(source, agent, scope=scope):
            _, target, diff = diff_command(
                source,
                adapter,
                scope=scope,
                project_root=project,
                home=Path.home(),
            )
            status = "OK" if not diff else "OUTDATED"
            typer.echo(f"[{status:8}] {source.name}@{adapter.name} -> {target}")
            if diff:
                typer.echo(diff)


def _select_adapters(source: CommandSource, agent: str, *, scope: str) -> list:
    adapter_names = [adapter.name for adapter in all_adapters()]
    effective = _effective_adapter_names(source, adapter_names)
    if agent == "all":
        return [
            get_adapter(name)
            for name in effective
            if get_adapter(name).supports_scope(scope)
        ]
    if agent not in effective:
        raise CommandError(
            f"Adapter {agent!r} excluded for command {source.name!r}; "
            f"effective: {effective}"
        )
    selected = get_adapter(agent)
    if not selected.supports_scope(scope):
        raise CommandError(f"Adapter {agent!r} does not support scope {scope!r}.")
    return [selected]


def _effective_adapter_names(source: CommandSource, registered: list[str]) -> list[str]:
    base = list(source.targets.include) if source.targets.include else list(registered)
    excluded = set(source.targets.exclude)
    return [name for name in base if name in registered and name not in excluded]


def _load(project_root: Path) -> list:
    return load_sources(project_root=project_root)


def _require_source(name: str, project_root: Path) -> CommandSource:
    source = _maybe_source(name, project_root)
    if source is None:
        raise CommandNotFoundError(f"Unknown command: {name!r}")
    return source


def _maybe_source(name: str, project_root: Path) -> CommandSource | None:
    for source in _load(project_root):
        if source.name == name:
            return source
    return None
