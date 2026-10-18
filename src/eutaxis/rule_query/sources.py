"""Build rule catalogs from configured modules or from deployed skills.

Two sources are supported:

- an instruction-assembly configuration, whose ``common_sources``, agent
  ``sources`` and ``task_modules`` name the authored modules; line numbers
  then refer to the authored files. A source entry that selects sections
  contributes only the rules and the rejected lines inside its selection;
- a skills directory, such as the user-scope directory of an adapter, whose
  eutaxis-owned skills are read as deployed. A skill compiled with
  ``disclosure: progressive`` is read through its index: each indexed rule
  is parsed from its ``rules/<label>.md`` file and takes the heading path of
  its index entry.

This module holds the file-system reads; parsing is delegated to
:mod:`eutaxis.instructions.rules`.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ..commands.disclosure import INDEX_ENTRY_PATTERN, rule_file_path
from ..commands.installer import is_eutaxis_owned
from ..commands.rendering import ENTRYPOINT_FILENAME
from ..instructions.config import load_config
from ..instructions.markdown import MarkdownAssembler
from ..instructions.models import SourceFile
from ..instructions.rules import (
    HeadingBlock,
    ParsedModule,
    TextBlock,
    parse_module,
)
from ..instructions.scanner import declared_sources
from .catalog import LocatedRejection, LocatedRule, RuleCatalog
from .exceptions import RuleSourceError

SKILLS_HINT = (
    "Always-on modules compile into the cumulative instruction file, not "
    "into skills; query their rules with -c <config>."
)


def catalog_from_config(config_path: Path) -> RuleCatalog:
    """Collect the rules of every module that a configuration declares.

    A module declared by several entries contributes the union of their
    selections. An entry without ``sections`` or ``exclude_sections``, and
    every ``task_modules`` entry, selects the whole module.

    Parameters
    ----------
    config_path : Path
        Instruction-assembly configuration.

    Raises
    ------
    RuleSourceError
        When a declared module is missing on disk.
    """
    config = load_config(config_path)
    selections: dict[Path, list[SourceFile | None]] = {}
    for path, source in declared_sources(config):
        selections.setdefault(path, []).append(source)
    assembler = MarkdownAssembler()
    rules: list[LocatedRule] = []
    rejected: list[LocatedRejection] = []
    for path, sources in selections.items():
        if not path.is_file():
            raise RuleSourceError(
                f"Module declared by {config.config_path} is missing: {path}"
            )
        text = path.read_text(encoding="utf-8")
        selected = _selected_lines(assembler, text, sources)
        parsed = parse_module(text, module=path.stem)
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
