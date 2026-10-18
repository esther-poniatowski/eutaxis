"""Progressive disclosure: split a skill body into an index and rule files.

A source whose frontmatter declares ``disclosure: progressive`` compiles to a
split skill. Its ``SKILL.md`` keeps the headings and every line outside a rule
block, and an index replaces each run of consecutive rule blocks. Each index
entry names the label, the first ``✓`` line of the rule, and a relative link to
``rules/<label>.md``. That file holds the whole rule block.

Therefore, every line of the source body lands in exactly one emitted file:
text outside rules stays in ``SKILL.md``, and each rule block moves to its own
file. When a body holds no rule, it is returned unchanged.

The functions of this module are pure. The renderer adds the rule files to the
artifact as sibling files, so the content hash and the ownership sidecar cover
them together with the other files of the artifact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..instructions.rules import (
    HeadingBlock,
    ParsedModule,
    Rule,
    RuleBlock,
    TextBlock,
    parse_module,
)
from .exceptions import CommandRenderError
from .models import ArtifactFile

DISCLOSURE_INLINE = "inline"
"""Default mode: the whole module body forms the ``SKILL.md`` body."""

DISCLOSURE_PROGRESSIVE = "progressive"
"""Split mode: ``SKILL.md`` holds an index, each rule holds its own file."""

DISCLOSURE_MODES = frozenset({DISCLOSURE_INLINE, DISCLOSURE_PROGRESSIVE})

RULES_DIRNAME = "rules"
"""Directory of the rule files, relative to the artifact root."""

READING_NOTE = (
    "> Each entry below links to the file of one rule. That file holds the "
    "whole rule: its ✓ and ✗ statements and every field, such as the "
    "exception, the test and the rationale. Read the file of a rule before "
    "applying or citing it."
)
"""Note emitted once, before the first index of a split ``SKILL.md``."""

INDEX_ENTRY_PATTERN = re.compile(
    r"^- \[`(?P<label>[a-z][a-z0-9-]*)`\]\(" + RULES_DIRNAME + r"/(?P=label)\.md\)"
)
"""Grammar of one index entry, read back by the rule query."""


@dataclass(frozen=True)
class DisclosedBody:
    """Result of splitting one skill body."""

    entrypoint_body: str
    """Body of ``SKILL.md``."""

    rule_files: tuple[ArtifactFile, ...]
    """One file per rule, at ``rules/<label>.md``, in source order."""


def rule_file_path(label: str) -> str:
    """Return the artifact-relative path of the file of one rule.

    Examples
    --------
    >>> rule_file_path("topic-first")
    'rules/topic-first.md'
    """
    return f"{RULES_DIRNAME}/{label}.md"


def index_entry(rule: Rule) -> str:
    """Return the index entry of one rule.

    Examples
    --------
    >>> from eutaxis.instructions.rules import parse_module
    >>> rule = parse_module("**short**:\\n\\n✓ Keep it short.\\n", module="m").rules[0]
    >>> index_entry(rule)
    '- [`short`](rules/short.md): Keep it short.'
    """
    entry = f"- [`{rule.label}`]({rule_file_path(rule.label)})"
    summary = rule.summary
    return f"{entry}: {summary}" if summary else entry


def disclose(body: str, *, module: str) -> DisclosedBody:
    """Split a skill body into an index body and one file per rule.

    Parameters
    ----------
    body : str
        Rendered Markdown body of the skill, without frontmatter.
    module : str
        Name of the skill, used in error messages.

    Returns
    -------
    DisclosedBody
        Index body and rule files. A body without rules is returned as the
        index body unchanged, with no rule file.

    Raises
    ------
    CommandRenderError
        When two rules of the body share a label, since both would be written
        to the same file.

    Examples
    --------
    >>> result = disclose(
    ...     "# Style\\n\\nIntro.\\n\\n**short**:\\n\\n✓ Keep it short.\\n",
    ...     module="style",
    ... )
    >>> [f.relative_path for f in result.rule_files]
    ['rules/short.md']
    >>> print(result.entrypoint_body.splitlines()[-1])
    - [`short`](rules/short.md): Keep it short.
    """
    parsed = parse_module(body, module=module)
    if not parsed.rules:
        return DisclosedBody(entrypoint_body=body, rule_files=())
    _check_unique_labels(parsed)
    return DisclosedBody(
        entrypoint_body=_entrypoint_body(parsed),
        rule_files=tuple(
            ArtifactFile(
                relative_path=rule_file_path(rule.label), content=rule.text + "\n"
            )
            for rule in parsed.rules
        ),
    )


def _check_unique_labels(parsed: ParsedModule) -> None:
    first_line: dict[str, int] = {}
    for rule in parsed.rules:
        if rule.label in first_line:
            raise CommandRenderError(
                f"Skill {parsed.name!r} defines label {rule.label!r} twice "
                f"(body lines {first_line[rule.label]} and {rule.start_line}); "
                f"progressive disclosure writes one file per label. Rename "
                f"one of the two rules."
            )
        first_line[rule.label] = rule.start_line


def _entrypoint_body(parsed: ParsedModule) -> str:
    """Join the headings, the text outside rules and the rule indexes."""
    chunks: list[str] = []
    index: list[str] = []
    note_pending = True

    def close_index() -> None:
        nonlocal note_pending
        if not index:
            return
        if note_pending:
            chunks.append(READING_NOTE)
            note_pending = False
        chunks.append("\n".join(index))
        index.clear()

    for block in parsed.blocks:
        if isinstance(block, RuleBlock):
            index.append(index_entry(block.rule))
            continue
        close_index()
        if isinstance(block, HeadingBlock):
            chunks.append(block.line)
        elif isinstance(block, TextBlock):
            text = "\n".join(block.lines).strip("\n")
            if text.strip():
                chunks.append(text)
    close_index()
    return "\n\n".join(chunks) + "\n"
