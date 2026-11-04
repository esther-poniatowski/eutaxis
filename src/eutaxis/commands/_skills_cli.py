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
    is_eutaxis_owned,
    load_from_instruction_config,
    measure_skill_budgets,
    plan_skill_sync,
    render_command,
    uninstall_command,
)
from .disclosure import DISCLOSURE_INLINE
from .adapters import AgentAdapter
from .loading_unit_publication import (
    LoadingUnitPublication,
    prepare_published_loading_units,
    sources_by_module,
)
from .cli_errors import exit_with_error
from .models import CommandSource
from .registry import Registry, default_state_dir
from .scopes import validate_scope
from .synchronization import skill_write_transaction
from ..instructions import InstructionConfig, InstructionError, load_config
from ..instructions.loading_units import expand_loading_unit

skills_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Compile config-registered instruction files to Agent Skill artifacts.",
)
loading_unit_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Inspect configured Skill loading units and their publication state.",
)
skills_app.add_typer(loading_unit_app, name="loading-unit")


@loading_unit_app.command("list")
def cli_loading_unit_list(
    config: str = typer.Option(
        ..., "--config", "-c", help="Path to the instruction-assembly configuration."
    ),
    agent: str = typer.Option("all", "--agent", "-a"),
    project_root: str | None = typer.Option(None, "--project"),
) -> None:
    """List loading units, measured sizes, and publication owners."""
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
            if measurement.kind == "loading-unit"
        ]
    except (CommandError, InstructionError, OSError) as exc:
        exit_with_error(exc)

    for measurement in reports:
        owner = ", ".join(measurement.publication_owners) or "unpublished"
        typer.echo(
            f"- {measurement.name}@{measurement.adapter} "
            f"[{measurement.byte_size}/{measurement.byte_budget} B] "
            f"owner: {owner}"
        )
    if any(measurement.over_budget for measurement in reports):
        raise typer.Exit(code=1)


@loading_unit_app.command("show")
def cli_loading_unit_show(
    name: str,
    config: str = typer.Option(
        ..., "--config", "-c", help="Path to the instruction-assembly configuration."
    ),
    agent: str = typer.Option("codex", "--agent", "-a"),
    project_root: str | None = typer.Option(None, "--project"),
) -> None:
    """Show one loading unit's exact files and generated manifest identity."""
    try:
        adapter = get_adapter(agent)
        project = _resolve_project(project_root)
        loaded, _, publications = _prepared(
            config, [adapter], project_root=project, home=Path.home()
        )
        raw_sources = load_from_instruction_config(Path(config).expanduser().resolve())
        measurement = next(
            (
                item
                for item in measure_skill_budgets(
                    loaded,
                    raw_sources,
                    adapter,
                    project_root=project,
                    home=Path.home(),
                )
                if item.kind == "loading-unit" and item.name == name
            ),
            None,
        )
        if measurement is None:
            raise CommandNotFoundError(f"Unknown Skill loading unit: {name!r}")
        publication = next(
            (
                item
                for item in publications
                if item.name == name and item.adapter == adapter.name
            ),
            None,
        )
        batch_publications = tuple(
            item
            for item in publications
            if item.adapter == adapter.name and name in item.batch_units
        )
    except (CommandError, InstructionError, OSError) as exc:
        exit_with_error(exc)

    typer.echo(f"name: {measurement.name}")
    typer.echo(f"adapter: {measurement.adapter}")
    typer.echo(f"bytes: {measurement.byte_size}/{measurement.byte_budget}")
    if publication is None and not batch_publications:
        typer.echo("publication: unpublished")
    if publication is not None:
        typer.echo(f"publication-owner: {publication.owner}")
        typer.echo(f"route-manifest: {publication.owner}/{publication.route_path}")
        typer.echo(f"closure-digest: {publication.closure_digest}")
        for batch_path in publication.batch_paths:
            typer.echo(f"batch-manifest: {publication.owner}/{batch_path}")
    for parent in batch_publications:
        index = parent.batch_units.index(name)
        typer.echo(f"publication-owner: {parent.owner}")
        typer.echo(f"batch-manifest: {parent.owner}/{parent.batch_paths[index]}")
        typer.echo(f"closure-digest: {parent.batch_digests[index]}")
    for path in measurement.files:
        typer.echo(f"file: {path}")
    if measurement.over_budget:
        raise typer.Exit(code=1)


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
            ""
            if source.disclosure == DISCLOSURE_INLINE
            else f", disclosure: {source.disclosure}"
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
    agent: str = typer.Option("claude", "--agent", "-a", help="Adapter to render for."),
    project_root: str | None = typer.Option(
        None, "--project", help="Project root for path substitutions."
    ),
) -> None:
    """Render and print one skill artifact for one adapter."""
    try:
        adapter = get_adapter(agent)
        project = _resolve_project(project_root)
        _, sources, _ = _prepared(
            config, [adapter], project_root=project, home=Path.home()
        )
        source = _require_source_in(name, sources)
        rendered = render_command(
            source,
            adapter,
            project_root=project,
            home=Path.home(),
        )
    except (CommandError, InstructionError, OSError) as exc:
        exit_with_error(exc)
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
    agent: str = typer.Option("all", "--agent", "-a", help="Adapter name or 'all'."),
    project_root: str | None = typer.Option(
        None, "--project", help="Project root for path substitutions."
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite non-eutaxis directories at the target."
    ),
) -> None:
    """Install one (or all) Skill artifact(s) into the selected adapters."""
    try:
        if scope:
            validate_scope(scope)
        registry = Registry(default_state_dir())
        project = _resolve_project(project_root)
        adapters = all_adapters() if agent == "all" else [get_adapter(agent)]
        loaded, prepared, _ = _prepared(
            config, adapters, project_root=project, home=Path.home()
        )
        requested = None if name == "all" else _require_source_in(name, prepared)
        operations: list[tuple[CommandSource, AgentAdapter, str]] = []
        for adapter in adapters:
            if requested is not None and not requested.targets.admits(adapter.name):
                if agent != "all":
                    _select_adapters(
                        requested, adapter.name, scope=scope or requested.scope_default
                    )
                continue
            selected_modules = (
                None
                if requested is None
                else _publication_closure_modules(
                    requested,
                    loaded,
                    prepared,
                    adapter_name=adapter.name,
                )
            )
            sources = _published_install_order(loaded, prepared, selected_modules)
            scopes = _installation_scopes(
                loaded,
                prepared,
                requested=requested,
                explicit_scope=scope,
                adapter_name=adapter.name,
                selected_modules=selected_modules,
            )
            operations.extend(
                (source, adapter, chosen_scope)
                for source in sources
                if source.targets.admits(adapter.name)
                for chosen_scope in scopes[source.name]
                if adapter.supports_scope(chosen_scope)
            )
        registry.load()
    except (CommandError, InstructionError, OSError) as exc:
        exit_with_error(exc)

    paths = [
        adapter.artifact_dir(
            source.name,
            chosen_scope,
            home=Path.home(),
            project_root=project,
        )
        for source, adapter, chosen_scope in operations
    ]
    try:
        outcomes = []
        with skill_write_transaction(paths, registry):
            for source, adapter, chosen_scope in operations:
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
    reported: set[str] = set()
    for outcome in outcomes:
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
    try:
        validate_scope(scope)
        home = Path.home()
        registry = Registry(default_state_dir())
        registry.load()
        project = _resolve_project(project_root)
        config_path = Path(config).expanduser().resolve()
        loaded = load_config(config_path)
        sources = load_from_instruction_config(config_path)
        source = next((item for item in sources if item.name == name), None)
        adapter_names = (
            [adapter.name for adapter in all_adapters()] if agent == "all" else [agent]
        )
        operations = []
        for adapter_name in adapter_names:
            if source is not None and adapter_name not in _effective_adapter_names(
                source, [item.name for item in all_adapters()]
            ):
                continue
            adapter = get_adapter(adapter_name)
            if not adapter.supports_scope(scope):
                continue
            blockers = _installed_publication_owners(
                name,
                adapter=adapter,
                scope=scope,
                project_root=project,
                home=home,
            )
            if blockers:
                raise CommandError(
                    f"Cannot uninstall {name!r}: installed published route "
                    f"owner(s) require it for {adapter.name}/{scope}: "
                    f"{', '.join(blockers)}. Uninstall the owner or use "
                    "`skills sync` after changing the configuration."
                )
            operations.append(
                (
                    adapter,
                    adapter.artifact_dir(name, scope, home=home, project_root=project),
                )
            )
    except (CommandError, InstructionError, OSError) as exc:
        exit_with_error(exc)

    try:
        outcomes = []
        with skill_write_transaction((path for _, path in operations), registry):
            for adapter, _ in operations:
                outcomes.append(
                    uninstall_command(
                        name=name,
                        adapter=adapter,
                        scope=scope,
                        project_root=project,
                        home=home,
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
    project = _resolve_project(project_root)

    try:
        validate_scope(scope)
        adapters = all_adapters() if agent == "all" else [get_adapter(agent)]
        _, prepared, _ = _prepared(
            config, adapters, project_root=project, home=Path.home()
        )
        sources = [_require_source_in(name, prepared)] if name is not None else prepared
    except (CommandError, InstructionError) as exc:
        exit_with_error(exc)

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
    try:
        validate_scope(scope)
        config_path = Path(config).expanduser().resolve()
        loaded = load_config(config_path)
        raw_sources = _load(str(config_path))
        adapters = all_adapters() if agent == "all" else [get_adapter(agent)]
        project = _resolve_project(project_root)
        home = Path.home()
        sources, _ = prepare_published_loading_units(
            loaded,
            raw_sources,
            adapters,
            project_root=project,
            home=home,
        )
        sources = _published_install_order(loaded, sources, None)
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
                    finalize=lambda: manifest.update(
                        scope=scope,
                        project_root=project,
                        names_by_adapter=expected_names,
                    ),
                    rollback_files=(manifest.path,),
                )
    except (CommandError, InstructionError, OSError) as exc:
        exit_with_error(exc)

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
        exit_with_error(exc)

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
            if measurement.publication_owners:
                typer.echo(
                    "       published-to: " + ", ".join(measurement.publication_owners)
                )
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
        raise CommandError(f"Adapter {agent!r} does not support scope {scope!r}.")
    return [selected]


def _effective_adapter_names(source: CommandSource, registered: list[str]) -> list[str]:
    base = list(source.targets.include) if source.targets.include else list(registered)
    return [name for name in base if name in registered and source.targets.admits(name)]


def _load(config: str) -> list[CommandSource]:
    return load_from_instruction_config(Path(config).expanduser().resolve())


def _require_source(name: str, config: str) -> CommandSource:
    source = _maybe_source(name, config)
    if source is None:
        raise CommandNotFoundError(f"Unknown skill: {name!r}")
    return source


def _require_source_in(name: str, sources: list[CommandSource]) -> CommandSource:
    for source in sources:
        if source.name == name:
            return source
    raise CommandNotFoundError(f"Unknown skill: {name!r}")


def _prepared(
    config: str,
    adapters: list,
    *,
    project_root: Path,
    home: Path,
) -> tuple[
    InstructionConfig,
    list[CommandSource],
    tuple[LoadingUnitPublication, ...],
]:
    config_path = Path(config).expanduser().resolve()
    loaded = load_config(config_path)
    sources = load_from_instruction_config(config_path)
    prepared, publications = prepare_published_loading_units(
        loaded,
        sources,
        adapters,
        project_root=project_root,
        home=home,
    )
    return loaded, prepared, publications


def _publication_closure_modules(
    requested: CommandSource,
    config: InstructionConfig,
    sources: list[CommandSource],
    *,
    adapter_name: str,
) -> set[str]:
    """Return every module that must refresh with one requested source."""
    by_module = sources_by_module(config, sources)
    module_by_source_name = {
        source.name: module_id for module_id, source in by_module.items()
    }
    required_modules = {module_by_source_name[requested.name]}
    changed = True
    while changed:
        changed = False
        for unit in config.skill_loading_units:
            if unit.publish_to is None:
                continue
            if not by_module[unit.publish_to].targets.admits(adapter_name):
                continue
            route_modules = {
                member.module
                for member in expand_loading_unit(unit, config.skill_loading_units)
            }
            if not (route_modules & required_modules):
                continue
            expanded = route_modules | {unit.publish_to}
            if not expanded <= required_modules:
                required_modules.update(expanded)
                changed = True
    return required_modules


def _published_install_order(
    config: InstructionConfig,
    sources: list[CommandSource],
    selected_modules: set[str] | None,
) -> list[CommandSource]:
    """Order dependencies before every owner whose manifest links to them."""
    by_module = sources_by_module(config, sources)
    selected = selected_modules or set(by_module)
    dependencies: dict[str, set[str]] = {module: set() for module in selected}
    module_order = {
        module.id: index for index, module in enumerate(config.task_modules)
    }
    for unit in config.skill_loading_units:
        if unit.publish_to not in selected:
            continue
        dependencies[unit.publish_to].update(
            member.module
            for member in expand_loading_unit(unit, config.skill_loading_units)
            if member.module in selected and member.module != unit.publish_to
        )
    ordered: list[str] = []
    active: set[str] = set()
    complete: set[str] = set()

    def visit(module: str) -> None:
        if module in complete:
            return
        if module in active:
            raise CommandError(
                "Published Skill routes form an install dependency cycle"
            )
        active.add(module)
        for dependency in sorted(
            dependencies[module], key=lambda item: module_order[item]
        ):
            visit(dependency)
        active.remove(module)
        complete.add(module)
        ordered.append(module)

    for module in (item.id for item in config.task_modules if item.id in selected):
        visit(module)
    return [by_module[module] for module in ordered]


def _installation_scopes(
    config: InstructionConfig,
    sources: list[CommandSource],
    *,
    requested: CommandSource | None,
    explicit_scope: str,
    adapter_name: str,
    selected_modules: set[str] | None,
) -> dict[str, tuple[str, ...]]:
    """Close installed ``(module, scope)`` pairs over published routes."""
    by_module = sources_by_module(config, sources)
    selected = selected_modules or set(by_module)
    admitted = {
        module for module in selected if by_module[module].targets.admits(adapter_name)
    }
    pairs: set[tuple[str, str]] = set()
    if explicit_scope:
        pairs.update((module, explicit_scope) for module in admitted)
    elif requested is None:
        pairs.update((module, by_module[module].scope_default) for module in admitted)
    else:
        module_by_name = {source.name: module for module, source in by_module.items()}
        requested_module = module_by_name[requested.name]
        pairs.add((requested_module, requested.scope_default))
        pairs.update(
            (unit.publish_to, by_module[unit.publish_to].scope_default)
            for unit in config.skill_loading_units
            if unit.publish_to is not None and unit.publish_to in admitted
        )

    changed = True
    while changed:
        changed = False
        for unit in config.skill_loading_units:
            owner = unit.publish_to
            if owner is None or owner not in admitted:
                continue
            members = {
                member.module
                for member in expand_loading_unit(unit, config.skill_loading_units)
                if member.module in admitted
            }
            owner_scopes = {scope for module, scope in pairs if module == owner}
            additions = {
                (member, owner_scope)
                for owner_scope in owner_scopes
                for member in members
            }
            if not additions <= pairs:
                pairs.update(additions)
                changed = True

    scopes: dict[str, set[str]] = {source.name: set() for source in sources}
    for module, chosen_scope in pairs:
        scopes[by_module[module].name].add(chosen_scope)
    return {name: tuple(sorted(values)) for name, values in scopes.items()}


def _installed_publication_owners(
    name: str,
    *,
    adapter,
    scope: str,
    project_root: Path,
    home: Path,
) -> list[str]:
    """Return installed route owners whose manifests require ``name``."""
    blockers: list[str] = []
    skills_root = adapter.skills_root(scope, home=home, project_root=project_root)
    if not skills_root.is_dir():
        return blockers
    selected_prefix = f"1. [`{name}/"
    for owner_dir in skills_root.iterdir():
        if owner_dir.name == name or not is_eutaxis_owned(owner_dir):
            continue
        routes = owner_dir / "routes"
        if not routes.is_dir():
            continue
        for manifest in routes.glob("*.md"):
            if selected_prefix in manifest.read_text(encoding="utf-8"):
                blockers.append(owner_dir.name)
                break
    return sorted(set(blockers))


def _maybe_source(name: str, config: str) -> CommandSource | None:
    for source in _load(config):
        if source.name == name:
            return source
    return None


def _resolve_project(project_root: str | None) -> Path:
    return Path(project_root).expanduser().resolve() if project_root else Path.cwd()
