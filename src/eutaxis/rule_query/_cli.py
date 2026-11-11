"""Typer sub-app for ``eutaxis rule``.

The sub-app prints one rule, or one part of it, and lists the rules of a
source. The source is chosen by the options:

- ``-c <config>`` or ``-r <root>`` reads the authored modules that the
  settings file declares;
- ``--skills-dir <dir>`` reads the eutaxis-owned skills of a directory;
- with neither option, the user-scope skills directory of ``--agent``
  (default ``claude``) is read, so that an agent can query the rules it was
  given from any working directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import typer

from .._cli_options import command_path, command_root, root_option
from ..commands import CommandError, get_adapter
from ..instructions import InstructionError, find_config, load_config
from ..instructions.loading_units import expand_loading_unit
from .catalog import RuleCatalog, resolve_rule, select_parts
from .exceptions import RuleQueryError, RuleSourceError
from .sources import catalog_from_config, catalog_from_skills_dir

DEFAULT_AGENT = "claude"

rule_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Print individual rules of instruction modules or deployed skills.",
)

_CONFIG_OPTION = typer.Option(
    None,
    "--config",
    "-c",
    help="Settings file whose modules are queried, relative to the current folder.",
)
_ROOT_OPTION = root_option(
    "Folder below which the settings file is looked up and against which its "
    "paths resolve; selects the authored modules."
)
_SKILLS_DIR_OPTION = typer.Option(
    None,
    "--skills-dir",
    help="Directory of deployed skills to query, e.g. ~/.claude/skills.",
)
_AGENT_OPTION = typer.Option(
    None,
    "--agent",
    "-a",
    help=(
        "Adapter whose user-scope skills directory is queried when none of "
        f"--config, --root and --skills-dir is given. Default: {DEFAULT_AGENT}."
    ),
)
_MODULE_OPTION = typer.Option(
    None, "--module", "-m", help="Restrict the query to one module or skill."
)
_LOADING_UNIT_OPTION = typer.Option(
    None,
    "--loading-unit",
    help="Restrict a config query to the modules of one Skill loading unit.",
)


@rule_app.command("show")
def cli_show(
    label: str = typer.Argument(..., help="Label of the rule."),
    part: str | None = typer.Option(
        None,
        "--part",
        "-p",
        help=(
            "Print only this part: valid, invalid, lead, or a field key such "
            "as why, exception, test, how-to-apply."
        ),
    ),
    module: str | None = _MODULE_OPTION,
    config: str | None = _CONFIG_OPTION,
    root: str | None = _ROOT_OPTION,
    skills_dir: str | None = _SKILLS_DIR_OPTION,
    agent: str | None = _AGENT_OPTION,
) -> None:
    """Print one rule, or one part of it, with its location."""
    try:
        catalog = _catalog(config, root, skills_dir, agent)
        located = resolve_rule(catalog, label, module=module)
        rule = located.rule
        trail = " > ".join((rule.module, *rule.heading_path, rule.label))
        if part is None:
            typer.echo(f"{trail} ({located.path}:{rule.start_line}-{rule.end_line})")
            typer.echo("")
            typer.echo(rule.text)
            return
        for index, selected in enumerate(select_parts(rule, part)):
            if index:
                typer.echo("")
            typer.echo(
                f"{trail} [{selected.key}] "
                f"({located.path}:{selected.start_line}-{selected.end_line})"
            )
            typer.echo("")
            typer.echo(selected.text)
    except (RuleQueryError, InstructionError, CommandError) as exc:
        _fail(exc)


@rule_app.command("list")
def cli_list(
    module: str | None = _MODULE_OPTION,
    loading_unit: str | None = _LOADING_UNIT_OPTION,
    config: str | None = _CONFIG_OPTION,
    root: str | None = _ROOT_OPTION,
    skills_dir: str | None = _SKILLS_DIR_OPTION,
    agent: str | None = _AGENT_OPTION,
) -> None:
    """List label, module and first ✓ line of every rule.

    Label-shaped lines that violate the label grammar are reported on
    standard error, since the rule index and the queries omit them.
    """
    try:
        selected_modules = _loading_unit_modules(
            loading_unit,
            module=module,
            config=config,
            root=root,
            skills_dir=skills_dir,
            agent=agent,
        )
        catalog = _catalog(config, root, skills_dir, agent)
        if module is not None and module not in catalog.modules:
            raise RuleQueryError(
                f"Unknown module {module!r} in {catalog.origin}. "
                f"Modules: {', '.join(catalog.modules) or 'none'}."
            )
    except (RuleQueryError, InstructionError, CommandError) as exc:
        _fail(exc)
    rules = tuple(
        item
        for item in catalog.select(module)
        if selected_modules is None or item.rule.module in selected_modules
    )
    label_width = max((len(item.rule.label) for item in rules), default=0)
    module_width = max((len(item.rule.module) for item in rules), default=0)
    for item in rules:
        rule = item.rule
        typer.echo(
            f"{rule.label:<{label_width}}  {rule.module:<{module_width}}  "
            f"{rule.summary}".rstrip()
        )
    for rejected in catalog.rejected:
        if module is not None and rejected.rejection.module != module:
            continue
        if (
            selected_modules is not None
            and rejected.rejection.module not in selected_modules
        ):
            continue
        typer.echo(
            f"warning: {rejected.path}:{rejected.rejection.line_number}: "
            f"{rejected.rejection.message}",
            err=True,
        )


def _catalog(
    config: str | None,
    root: str | None,
    skills_dir: str | None,
    agent: str | None,
) -> RuleCatalog:
    """Build the catalog of the source that the options select."""
    if (config is not None or root is not None) and (
        skills_dir is not None or agent is not None
    ):
        raise RuleSourceError(
            "--config and --root read authored modules; they cannot be combined "
            "with --skills-dir or --agent, which select deployed skills."
        )
    if skills_dir is not None and agent is not None:
        raise RuleSourceError("--skills-dir names the directory to read; drop --agent.")
    if config is not None or root is not None:
        base = command_root(root)
        config_path = find_config(command_path(config), base)
        return catalog_from_config(config_path, root=base)
    if skills_dir is not None:
        return catalog_from_skills_dir(Path(skills_dir).expanduser().resolve())
    return catalog_from_skills_dir(_user_skills_dir(agent or DEFAULT_AGENT))


def _loading_unit_modules(
    loading_unit: str | None,
    *,
    module: str | None,
    config: str | None,
    root: str | None,
    skills_dir: str | None,
    agent: str | None,
) -> frozenset[str] | None:
    """Resolve one loading unit to the authored module names in its config."""
    if loading_unit is None:
        return None
    if config is None and root is None:
        raise RuleSourceError("--loading-unit requires --config or --root.")
    if module is not None or skills_dir is not None or agent is not None:
        raise RuleSourceError(
            "--loading-unit cannot be combined with --module, --skills-dir, "
            "or --agent."
        )
    base = command_root(root)
    config_path = find_config(command_path(config), base)
    loaded = load_config(config_path, root=base)
    unit = next(
        (
            candidate
            for candidate in loaded.skill_loading_units
            if candidate.name == loading_unit
        ),
        None,
    )
    if unit is None:
        names = ", ".join(item.name for item in loaded.skill_loading_units) or "none"
        raise RuleQueryError(
            f"Unknown Skill loading unit {loading_unit!r}. Units: {names}."
        )
    task_modules = {item.id: item for item in loaded.task_modules}
    return frozenset(
        loaded.resolve(task_modules[member.module].path).stem
        for member in expand_loading_unit(unit, loaded.skill_loading_units)
    )


def _user_skills_dir(agent: str) -> Path:
    """Return the user-scope skills directory that ``agent`` installs into."""
    adapter = get_adapter(agent)
    return adapter.skills_root("user", home=Path.home(), project_root=Path.cwd())


def _fail(exc: Exception) -> NoReturn:
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(code=getattr(exc, "exit_code", 1)) from exc
