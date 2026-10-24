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

from contextlib import nullcontext
from pathlib import Path

import typer

from . import (
    CommandError,
    CommandNotFoundError,
    SkillSyncManifest,
    all_adapters,
    apply_skill_sync,
    diff_command,
    get_adapter,
    install_command,
    load_from_instruction_config,
    measure_skill_budgets,
    plan_skill_sync,
    render_command,
    uninstall_command,
)
from .disclosure import DISCLOSURE_INLINE
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
        disclosure = (
            "" if source.disclosure == DISCLOSURE_INLINE else f", disclosure: {source.disclosure}"
        )
        typer.echo(
            f"- {source.name} [invocation: {'/'.join(source.invocation)}, "
            f"failure-mode: {source.failure_mode}{disclosure}] "
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
    _echo_warnings(rendered.warnings, set())
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

    reported: set[str] = set()
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
            _echo_warnings(outcome.warnings, reported)
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
    """Show drift between rendered output and installed artifacts.

    Exits with code 1 when any artifact differs from its render: a file
    outdated, edited by hand, missing on disk, or left over from a removed
    rule. Exits with code 0 when every artifact is current.
    """
    sources = (
        [_require_source(name, config)] if name is not None else _load(config)
    )
    project = _resolve_project(project_root)

    drift = False
    reported: set[str] = set()
    for source in sources:
        for adapter in _select_adapters(source, agent, scope=scope):
            rendered, target, diff = diff_command(
                source,
                adapter,
                scope=scope,
                project_root=project,
                home=Path.home(),
            )
            _echo_warnings(rendered.warnings, reported)
            status = "OK" if not diff else "OUTDATED"
            typer.echo(f"[{status:8}] {source.name}@{adapter.name} -> {target}")
            if diff:
                drift = True
                typer.echo(diff)
    if drift:
        raise typer.Exit(code=1)


@skills_app.command("sync")
def cli_sync(
    config: str = typer.Option(
        ..., "--config", "-c", help="Path to the instruction-assembly configuration."
    ),
    scope: str = typer.Option("user", "--scope", help="user|project"),
    agent: str = typer.Option("all", "--agent", "-a"),
    project_root: str | None = typer.Option(None, "--project"),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply the displayed plan. Without this flag, the command is read-only.",
    ),
) -> None:
    """Preview or apply the complete set of managed Skills."""
    from ..instructions import InstructionError

    try:
        config_path = Path(config).expanduser().resolve()
        sources = _load(str(config_path))
        adapters = all_adapters() if agent == "all" else [get_adapter(agent)]
        project = _resolve_project(project_root)
        home = Path.home()
        registry = Registry(default_state_dir(home))
        registry.load()
        manifest = SkillSyncManifest(default_state_dir(home), config_path)
        sync_lock = manifest.locked() if apply else nullcontext()
        with sync_lock:
            managed_names = {
                adapter.name: manifest.managed_names(
                    adapter=adapter.name,
                    scope=scope,
                    project_root=project,
                )
                for adapter in adapters
            }
            protected_names = {
                adapter.name: manifest.names_managed_by_other_configs(
                    adapter=adapter.name,
                    scope=scope,
                    project_root=project,
                )
                for adapter in adapters
            }
            actions = plan_skill_sync(
                sources,
                adapters,
                scope=scope,
                project_root=project,
                home=home,
                managed_names_by_adapter=managed_names,
                protected_names_by_adapter=protected_names,
            )
            if apply:
                expected_names = {
                    adapter.name: {
                        action.name
                        for action in actions
                        if action.adapter.name == adapter.name
                        and action.source is not None
                    }
                    for adapter in adapters
                }
                actions = apply_skill_sync(
                    actions,
                    project_root=project,
                    home=home,
                    registry=registry,
                )
                manifest.update(
                    scope=scope,
                    project_root=project,
                    names_by_adapter=expected_names,
                )
    except (CommandError, InstructionError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=getattr(exc, "exit_code", 1)) from exc

    reported: set[str] = set()
    for action in actions:
        _echo_warnings(action.warnings, reported)
        typer.echo(
            f"[{action.action.upper():9}] {action.name}@{action.adapter.name} "
            f"({action.scope}) -> {action.path}"
        )
    if not apply:
        typer.echo("Preview only; pass --apply to write the plan.")


@skills_app.command("budget")
def cli_budget(
    config: str = typer.Option(
        ..., "--config", "-c", help="Path to the instruction-assembly configuration."
    ),
    agent: str = typer.Option("all", "--agent", "-a", help="Adapter name or 'all'."),
    project_root: str | None = typer.Option(None, "--project"),
) -> None:
    """Report and validate Skill entrypoints and loading units."""
    from ..instructions import InstructionError, load_config

    try:
        config_path = Path(config).expanduser().resolve()
        loaded = load_config(config_path)
        sources = load_from_instruction_config(config_path)
        adapters = all_adapters() if agent == "all" else [get_adapter(agent)]
        project = _resolve_project(project_root)
        reports = [
            measurement
            for adapter in adapters
            for measurement in measure_skill_budgets(
                loaded,
                sources,
                adapter,
                project_root=project,
                home=Path.home(),
            )
        ]
    except (CommandError, InstructionError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=getattr(exc, "exit_code", 1)) from exc

    over_budget = False
    for measurement in reports:
        if measurement.byte_budget is None:
            size_note = f"{measurement.byte_size} B"
        else:
            flag = "OVER" if measurement.over_budget else "ok"
            size_note = f"{measurement.byte_size}/{measurement.byte_budget} B {flag}"
        status = "OVER" if measurement.over_budget else "OK"
        typer.echo(
            f"[{status:4}] {measurement.kind} "
            f"{measurement.name}@{measurement.adapter} [{size_note}]"
        )
        if measurement.kind == "loading-unit":
            for path in measurement.files:
                typer.echo(f"       - {path}")
        over_budget = over_budget or measurement.over_budget
    if over_budget:
        raise typer.Exit(code=1)


def _echo_warnings(warnings: tuple[str, ...], reported: set[str]) -> None:
    """Print each render warning on standard error, once per command run.

    The render of one source repeats its warnings for every adapter, so
    ``reported`` collects the warnings already printed.
    """
    for warning in warnings:
        if warning not in reported:
            reported.add(warning)
            typer.echo(f"warning: {warning}", err=True)


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
    return [
        name for name in base if name in registered and source.targets.admits(name)
    ]


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
