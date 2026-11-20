"""Build rule catalogs from configured modules or from deployed skills.

The query reads two source families:

- an instruction-assembly configuration, whose ``common_sources``, agent
  ``sources`` and ``task_modules`` name Markdown or structured declaration
  modules. For Markdown, line numbers refer to the authored files. For a
  structured record, the displayed synthetic location names the authenticated
  cumulative artifact and its line range. When a Markdown source limits its
  scope, only the admitted rules and rejected lines enter the catalog;
- a skills directory, such as the user-scope directory of an adapter, whose
  eutaxis-owned skills are read as deployed. A skill compiled with
  ``disclosure: progressive`` is read through its index: each indexed rule
  is parsed from its ``rules/<label>.md`` file and takes the heading path of
  its index entry.

This module holds the file-system reads; parsing is delegated to
:mod:`eutaxis.instructions.rules`.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import replace
from pathlib import Path

from ..commands.disclosure import INDEX_ENTRY_PATTERN, rule_file_path
from ..commands.installer import is_eutaxis_owned
from ..commands.rendering import ENTRYPOINT_FILENAME
from ..instructions.config import load_config
from ..instructions.markdown import MarkdownAssembler
from ..instructions.generator import InstructionGenerator
from ..instructions.models import DeclarationSource, SourceFile
from ..instructions.rules import (
    HeadingBlock,
    ParsedModule,
    TextBlock,
    parse_module,
)
from .catalog import LocatedRejection, LocatedRule, RuleCatalog
from .exceptions import RuleSourceError

SKILLS_HINT = (
    "Always-on modules compile into the cumulative instruction file, not "
    "into skills; query their rules with -c <config> or --root <folder>."
)


def catalog_from_config(
    config_path: Path,
    root: Path | None = None,
    *,
    task_module_ids: Collection[str] | None = None,
) -> RuleCatalog:
    """Collect the rules of every module that a configuration declares.

    The complete catalog contains every configured source. A filtered task
    module contributes its ``rule_index_source``, or its ``path`` when no
    override is configured.

    Parameters
    ----------
    config_path : Path
        Instruction-assembly configuration.
    root : Path, optional
        Folder against which the paths of the configuration resolve.
        Default: the folder of the file.
    task_module_ids : collection of str, optional
        Task module identifiers to collect through their rule-index sources.
        Common and agent sources are omitted when this filter is present. The
        complete catalog is collected by default.

    Raises
    ------
    RuleSourceError
        When a declared module is missing on disk.
    """
    config = load_config(config_path, root=root)
    selected_task_ids = None if task_module_ids is None else frozenset(task_module_ids)
    selections: dict[tuple[Path, str], list[SourceFile | None]] = {}
    structured_sources: list[DeclarationSource] = []

    def add_source(
        source: SourceFile | DeclarationSource,
        *,
        module_name: str | None = None,
    ) -> None:
        if isinstance(source, DeclarationSource):
            structured_sources.append(source)
            return
        path = config.resolve(source.path)
        selections.setdefault((path, module_name or path.stem), []).append(source)

    if selected_task_ids is None:
        for source in config.common_sources:
            add_source(source)
        for task_module in config.task_modules:
            path = config.resolve(task_module.path)
            selections.setdefault((path, path.stem), []).append(None)
        for task_module in config.task_modules:
            if task_module.rule_index_source is not None:
                add_source(task_module.rule_index_source)
        for agent in config.agents:
            for source in agent.sources:
                add_source(source)
    else:
        for task_module in config.task_modules:
            if task_module.id not in selected_task_ids:
                continue
            task_source = task_module.rule_index_source
            if task_source is None:
                path = config.resolve(task_module.path)
                selections.setdefault((path, path.stem), []).append(None)
            else:
                add_source(task_source, module_name=task_module.id)
    assembler = MarkdownAssembler()
    rules: list[LocatedRule] = []
    rejected: list[LocatedRejection] = []
    for (path, module_name), sources in selections.items():
        if not path.is_file():
            raise RuleSourceError(
                f"Module declared by {config.config_path} is missing: {path}"
            )
        text = path.read_text(encoding="utf-8")
        selected = _selected_lines(assembler, text, sources)
        parsed = parse_module(text, module=module_name)
        rules.extend(
            LocatedRule(rule=rule, path=path)
            for rule in parsed.rules
            if selected is None or rule.start_line in selected
        )
        rejected.extend(
            LocatedRejection(rejection=item, path=path)
            for item in parsed.rejected
            if selected is None or item.line_number in selected
        )
    generator = InstructionGenerator(config)
    unique_structured_sources: list[DeclarationSource] = []
    for structured_source in structured_sources:
        if structured_source not in unique_structured_sources:
            unique_structured_sources.append(structured_source)
    for structured_source in unique_structured_sources:
        rendered = generator.render_declaration_source(structured_source)
        parsed = parse_module(rendered, module=structured_source.module)
        location = Path(f"<declaration:{structured_source.composition_manifest}>")
        _collect(parsed, location, rules, rejected)
    return RuleCatalog(
        origin=f"the modules of {config.config_path}",
        rules=tuple(rules),
        rejected=tuple(rejected),
    )


def _selected_lines(
    assembler: MarkdownAssembler, text: str, sources: list[SourceFile | None]
) -> frozenset[int] | None:
    """Return the union of the lines selected by ``sources``.

    ``None`` stands for the whole module: it is returned as soon as one
    entry selects the whole module.
    """
    union: set[int] = set()
    for source in sources:
        lines = (
            None if source is None else assembler.selected_line_numbers(text, source)
        )
        if lines is None:
            return None
        union |= lines
    return frozenset(union)


def catalog_from_skills_dir(skills_dir: Path) -> RuleCatalog:
    """Collect the rules of every eutaxis-owned skill under ``skills_dir``.

    Parameters
    ----------
    skills_dir : Path
        Directory holding one sub-directory per skill.

    Raises
    ------
    RuleSourceError
        When the directory is missing, or when an index entry of a split
        skill points to a missing or mismatched rule file.
    """
    if not skills_dir.is_dir():
        raise RuleSourceError(
            f"Skills directory not found: {skills_dir}. Install the skills "
            f"with `eutaxis skills install all -c <config>`, or query the "
            f"authored modules with -c <config>."
        )
    rules: list[LocatedRule] = []
    rejected: list[LocatedRejection] = []
    for skill_dir in sorted(skills_dir.iterdir()):
        entrypoint = skill_dir / ENTRYPOINT_FILENAME
        if not entrypoint.is_file() or not is_eutaxis_owned(skill_dir):
            continue
        parsed = parse_module(
            entrypoint.read_text(encoding="utf-8"), module=skill_dir.name
        )
        _collect(parsed, entrypoint, rules, rejected)
        for label, heading_path in _index_entries(parsed):
            rules.append(_read_rule_file(skill_dir, label, heading_path))
    return RuleCatalog(
        origin=f"the skills of {skills_dir}",
        rules=tuple(rules),
        rejected=tuple(rejected),
        hint=SKILLS_HINT,
    )


def _collect(
    parsed: ParsedModule,
    path: Path,
    rules: list[LocatedRule],
    rejected: list[LocatedRejection],
) -> None:
    rules.extend(LocatedRule(rule=rule, path=path) for rule in parsed.rules)
    rejected.extend(
        LocatedRejection(rejection=item, path=path) for item in parsed.rejected
    )


def _index_entries(parsed: ParsedModule) -> list[tuple[str, tuple[str, ...]]]:
    """Return the label and heading path of each index entry of a split skill."""
    headings: list[tuple[int, str]] = []
    entries: list[tuple[str, tuple[str, ...]]] = []
    for block in parsed.blocks:
        if isinstance(block, HeadingBlock):
            while headings and headings[-1][0] >= block.level:
                headings.pop()
            headings.append((block.level, block.text))
        elif isinstance(block, TextBlock):
            for line in block.lines:
                match = INDEX_ENTRY_PATTERN.match(line)
                if match is not None:
                    entries.append(
                        (match.group("label"), tuple(text for _, text in headings))
                    )
    return entries


def _read_rule_file(
    skill_dir: Path, label: str, heading_path: tuple[str, ...]
) -> LocatedRule:
    path = skill_dir / rule_file_path(label)
    if not path.is_file():
        raise RuleSourceError(
            f"Index of {skill_dir / ENTRYPOINT_FILENAME} lists {label!r}, but "
            f"{path} is missing. Check the drift with `eutaxis skills diff`."
        )
    parsed = parse_module(path.read_text(encoding="utf-8"), module=skill_dir.name)
    rule = parsed.rule(label)
    if rule is None:
        raise RuleSourceError(
            f"{path} does not define the rule {label!r} that the index of "
            f"{skill_dir / ENTRYPOINT_FILENAME} lists."
        )
    return LocatedRule(rule=replace(rule, heading_path=heading_path), path=path)
