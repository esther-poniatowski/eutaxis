"""Typer sub-app for ``eutaxis skills``.

The ``skills`` sub-app compiles instruction files registered in an
instruction-assembly configuration to native Agent Skill artifacts.
It is the config-driven analogue of ``eutaxis commands``, which
discovers sources from layered directories.

Discovery is config-driven: every Markdown file listed under
``task_modules`` becomes a Skill candidate, provided its frontmatter
satisfies the source schema (``regime``, ``failure-mode``, and
``required-visibility`` when silent). The renderer's failure-mode gate
applies unchanged.
"""

from __future__ import annotations

from pathlib import Path

import typer

from . import (
    CommandError,
    CommandNotFoundError,
    all_adapters,
    diff_command,
    get_adapter,
    install_command,
    load_from_instruction_config,
    render_command,
    uninstall_command,
)
from .models import CommandSource
from .registry import Registry, default_state_dir

skills_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Compile config-registered instruction files to Agent Skill artifacts.",
)


@skills_app.command("list")
def cli_list(
    config: str = typer.Option(
        ...,
        "--config",
        "-c",
        help="Path to the instruction-assembly configuration.",
    ),
) -> None:
    """List Skill sources registered in the configuration."""
    sources = _load(config)
    if not sources:
        typer.echo("No skill sources found in the configuration.")
        return
    adapter_names = [adapter.name for adapter in all_adapters()]
    for source in sources:
        targets = ", ".join(_effective_adapter_names(source, adapter_names))
        typer.echo(
            f"- {source.name} [{source.regime}, {source.failure_mode}] "
            f"-> [{targets}]: {source.description}"
        )


@skills_app.command("show")
def cli_show(
    name: str,
    config: str = typer.Option(
        ..., "--config", "-c", help="Path to the instruction-assembly configuration."
    ),
    agent: str = typer.Option(
        "claude", "--agent", "-a", help="Adapter to render for."
    ),
    project_root: str | None = typer.Option(
        None, "--project", help="Project root for path substitutions."
    ),
) -> None:
    """Render and print one skill artifact for one adapter."""
    source = _require_source(name, config)
    adapter = get_adapter(agent)
    rendered = render_command(
        source,
        adapter,
        project_root=_resolve_project(project_root),
        home=Path.home(),
    )
    for artifact_file in rendered.files:
        typer.echo(f"--- {artifact_file.relative_path} ---")
        typer.echo(artifact_file.content)


@skills_app.command("install")
def cli_install(
    name: str = typer.Argument(
        ..., help="Skill name or 'all' to install every config-registered source."
    ),
    config: str = typer.Option(
        ..., "--config", "-c", help="Path to the instruction-assembly configuration."
    ),
    scope: str = typer.Option(
        "",
        "--scope",
        help="Install scope (user|project). Defaults to the source's scope_default.",
    ),
    agent: str = typer.Option(
        "all", "--agent", "-a", help="Adapter name or 'all'."
    ),
    project_root: str | None = typer.Option(
        None, "--project", help="Project root for path substitutions."
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite non-eutaxis directories at the target."
    ),
) -> None:
    """Install one (or all) Skill artifact(s) into the selected adapters."""
    registry = Registry(default_state_dir())
    project = _resolve_project(project_root)
    sources = (
        _load(config) if name == "all" else [_require_source(name, config)]
    )

    for source in sources:
        chosen_scope = scope or source.scope_default
        for adapter in _select_adapters(source, agent, scope=chosen_scope):
            outcome = install_command(
                source,
                adapter,
                scope=chosen_scope,
                project_root=project,
                home=Path.home(),
                registry=registry,
                force=force,
            )
            typer.echo(
                f"[{outcome.action:9}] {outcome.name}@{outcome.adapter} "
                f"({outcome.scope}) -> {outcome.path}"
            )


@skills_app.command("uninstall")
def cli_uninstall(
    name: str,
    config: str = typer.Option(
        ..., "--config", "-c", help="Path to the instruction-assembly configuration."
    ),
    scope: str = typer.Option("user", "--scope", help="user|project"),
    agent: str = typer.Option("all", "--agent", "-a"),
    project_root: str | None = typer.Option(None, "--project"),
    force: bool = typer.Option(
        False, "--force", help="Delete non-eutaxis directories at the target."
    ),
) -> None:
    """Remove one installed Skill artifact from the selected adapters."""
    registry = Registry(default_state_dir())
    project = _resolve_project(project_root)
    source = _maybe_source(name, config)
    adapter_names = (
        [adapter.name for adapter in all_adapters()] if agent == "all" else [agent]
    )
    for adapter_name in adapter_names:
        if source is not None and adapter_name not in _effective_adapter_names(
            source, [a.name for a in all_adapters()]
        ):
            continue
        adapter = get_adapter(adapter_name)
        if not adapter.supports_scope(scope):
            continue
        outcome = uninstall_command(
            name=name,
            adapter=adapter,
            scope=scope,
            project_root=project,
            home=Path.home(),
            registry=registry,
            force=force,
        )
        typer.echo(
            f"[{outcome.action:9}] {outcome.name}@{outcome.adapter} "
            f"({outcome.scope}) -> {outcome.path}"
        )


@skills_app.command("diff")
def cli_diff(
    name: str | None = typer.Argument(
        None, help="Skill name (omit for all config-registered sources)."
    ),
    config: str = typer.Option(
        ..., "--config", "-c", help="Path to the instruction-assembly configuration."
    ),
    scope: str = typer.Option("user", "--scope"),
    agent: str = typer.Option("all", "--agent", "-a"),
    project_root: str | None = typer.Option(None, "--project"),
) -> None:
    """Show drift between rendered output and installed artifacts."""
    sources = (
        [_require_source(name, config)] if name is not None else _load(config)
    )
    project = _resolve_project(project_root)

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
            f"Adapter {agent!r} excluded for skill {source.name!r}; "
            f"effective: {effective}"
        )
    selected = get_adapter(agent)
    if not selected.supports_scope(scope):
        raise CommandError(
            f"Adapter {agent!r} does not support scope {scope!r}."
        )
    return [selected]


def _effective_adapter_names(
    source: CommandSource, registered: list[str]
) -> list[str]:
    base = (
        list(source.targets.include) if source.targets.include else list(registered)
    )
    excluded = set(source.targets.exclude)
    return [name for name in base if name in registered and name not in excluded]


def _load(config: str) -> list[CommandSource]:
    return load_from_instruction_config(Path(config).expanduser().resolve())


def _require_source(name: str, config: str) -> CommandSource:
    source = _maybe_source(name, config)
    if source is None:
        raise CommandNotFoundError(f"Unknown skill: {name!r}")
    return source


def _maybe_source(name: str, config: str) -> CommandSource | None:
    for source in _load(config):
        if source.name == name:
            return source
    return None


def _resolve_project(project_root: str | None) -> Path:
    return (
        Path(project_root).expanduser().resolve() if project_root else Path.cwd()
    )
