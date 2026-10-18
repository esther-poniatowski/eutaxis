"""Parse instruction modules into rule records.

An instruction module states each rule under a label line, ``**<label>**:``
alone at the start of a line. The rule block runs from its label line to the
nearer of two boundaries: the next label line and the next heading. Inside a
block, three kinds of line open a *part* of the rule:

- a line opening on ``✓`` opens a valid statement (part key ``valid``);
- a line opening on ``✗`` opens an invalid statement (part key ``invalid``);
- a line opening on an italic title, such as ``*Why.*``, ``*Exception*:`` or
  ``*Why the tiers.*``, opens a field.

A part runs until the next part opens or the block ends. Text between the
label line and the first part forms the ``lead`` part.

Field keys are normalized from the italic title by :func:`field_key`. A
canonical marker absorbs its plural form and its titled variants, and every
other title is keyed by its slug. The canonical markers are listed in
:data:`CANONICAL_KEYS`.

The parser reads and writes no file. Its input is the text of one module, and
its output is a :class:`ParsedModule` holding the ordered blocks, the rule
records and the rejected label-shaped lines of that module. Line numbers start
at 1 on the first line of the text given, frontmatter included.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LABEL_PATTERN = re.compile(r"^\*\*([a-z][a-z0-9-]*)\*\*:\s*$", re.MULTILINE)
"""Grammar of a label line. Shared with the rule index of the generator."""

_LABEL_SHAPE = re.compile(r"^(?P<indent>\s*)\*\*(?P<token>[^*\s][^*]*?)\*\*:\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")
"""Opening or closing line of a fenced code block. Shared with the link rewriter."""
_FIELD_MARKER = re.compile(
    r"^\*(?!\*)(?P<title>[A-Z][^*\n]*?)(?P<inner>[.:?!])?\*(?P<outer>:)?(?:\s|$)"
)
_VALID_MARK = "✓"
_INVALID_MARK = "✗"

VALID_KEY = "valid"
"""Part key of the ``✓`` statements."""

INVALID_KEY = "invalid"
"""Part key of the ``✗`` statements."""

LEAD_KEY = "lead"
"""Part key of the text between the label line and the first marked part."""

_CANONICAL_WORDS = {
    "why": "why",
    "exception": "exception",
    "exceptions": "exception",
    "test": "test",
    "tests": "test",
    "key": "key",
    "scope": "scope",
    "note": "note",
    "notes": "note",
    "warning": "warning",
    "warnings": "warning",
    "relation": "relation",
    "relations": "relation",
}
_CANONICAL_PHRASES = {"how to apply": "how-to-apply"}

CANONICAL_KEYS = tuple(
    dict.fromkeys([*_CANONICAL_WORDS.values(), *_CANONICAL_PHRASES.values()])
)
"""Field keys that absorb the plural forms and the titled variants of a marker."""


@dataclass(frozen=True)
class RulePart:
    """One part of a rule: a statement, a field, or the lead text."""

    key: str
    """Normalized key: ``valid``, ``invalid``, ``lead``, a canonical field
    key, or the slug of a field title."""

    title: str
    """Title as written in the module, without its closing punctuation
    (``"Why the tiers"``); ``"✓"`` or ``"✗"`` for a statement; empty for the
    lead text."""

    text: str
    """Text of the part, marker line included, trailing blank lines removed."""

    start_line: int
    """First line of the part in the parsed text."""

    end_line: int
    """Last line of the part in the parsed text."""


@dataclass(frozen=True)
class Rule:
    """One labelled rule of an instruction module."""

    label: str
    """Label of the rule, as written on its label line."""

    module: str
    """Name of the module that holds the rule."""

    heading_path: tuple[str, ...]
    """Texts of the headings enclosing the rule, outermost first."""

    parts: tuple[RulePart, ...]
    """Parts of the rule, in source order."""

    text: str
    """Raw text of the block, label line included."""

    start_line: int
    """First line of the block in the parsed text."""

    end_line: int
    """Last line of the block in the parsed text."""

    @property
    def valid(self) -> tuple[str, ...]:
        """Texts of the ``✓`` statements."""
        return tuple(part.text for part in self.parts_for(VALID_KEY))

    @property
    def invalid(self) -> tuple[str, ...]:
        """Texts of the ``✗`` statements."""
        return tuple(part.text for part in self.parts_for(INVALID_KEY))

    @property
    def fields(self) -> dict[str, tuple[RulePart, ...]]:
        """Fields of the rule, grouped by normalized key in source order."""
        grouped: dict[str, list[RulePart]] = {}
        for part in self.parts:
            if part.key in (VALID_KEY, INVALID_KEY, LEAD_KEY):
                continue
            grouped.setdefault(part.key, []).append(part)
        return {key: tuple(parts) for key, parts in grouped.items()}

    @property
    def part_keys(self) -> tuple[str, ...]:
        """Distinct part keys of the rule, in order of first occurrence."""
        return tuple(dict.fromkeys(part.key for part in self.parts))

    def parts_for(self, key: str) -> tuple[RulePart, ...]:
        """Return every part whose key equals ``key``, in source order."""
        return tuple(part for part in self.parts if part.key == key)

    @property
    def summary(self) -> str:
        """First line of the first ``✓`` statement, without its marker.

        A rule without a ``✓`` statement is summarized by the first line of
        its first part. A rule without any part yields an empty string.
        """
        valid = self.parts_for(VALID_KEY)
        if valid:
            return valid[0].text.splitlines()[0].lstrip(_VALID_MARK).strip()
        if self.parts:
            return self.parts[0].text.splitlines()[0].strip()
        return ""


@dataclass(frozen=True)
class RejectedLabel:
    """A line shaped as a label line whose token violates the label grammar.

    A rejected line still ends the preceding rule block, so its text is not
    attributed to the rule above it.
    """

    module: str
    """Name of the module that holds the line."""

    line_number: int
    """Line number in the parsed text."""

    line: str
    """The line as written."""

    token: str
    """Text between the bold markers."""

    reason: str
    """Part of the grammar that the token violates."""

    @property
    def message(self) -> str:
        """Diagnostic naming the line and the violated part of the grammar.

        Examples
        --------
        >>> parse_module("**3d-plots**:\\n", module="m").rejected[0].message
        "rejected label line '**3d-plots**:': a label must start with a lowercase letter"
        """
        return f"rejected label line {self.line.strip()!r}: {self.reason}"


@dataclass(frozen=True)
class HeadingBlock:
    """A Markdown heading outside fenced code."""

    level: int
    text: str
    line: str
    start_line: int


@dataclass(frozen=True)
class TextBlock:
    """A run of lines that belongs to no rule block."""

    lines: tuple[str, ...]
    start_line: int


@dataclass(frozen=True)
class RuleBlock:
    """The block of one rule."""

    rule: Rule


Block = HeadingBlock | TextBlock | RuleBlock
"""One structural block of a module."""


@dataclass(frozen=True)
class ParsedModule:
    """Structure of one instruction module."""

    name: str
    """Name of the module."""

    blocks: tuple[Block, ...]
    """Headings, rule blocks and remaining text, in source order. The
    frontmatter is excluded."""

    rejected: tuple[RejectedLabel, ...]
    """Label-shaped lines that violate the label grammar."""

    @property
    def rules(self) -> tuple[Rule, ...]:
        """Rule records of the module, in source order."""
        return tuple(
            block.rule for block in self.blocks if isinstance(block, RuleBlock)
        )

    def rule(self, label: str) -> Rule | None:
        """Return the first rule labelled ``label``, if any."""
        for rule in self.rules:
            if rule.label == label:
                return rule
        return None


def field_key(title: str) -> str:
    """Normalize the title of a field into its part key.

    A title whose words read ``how to apply`` maps to ``how-to-apply``. A
    title whose first word is a canonical marker, in singular or plural
    form, maps to that marker, so titled variants share the key of their
    marker. Every other title maps to the slug of its words.

    Parameters
    ----------
    title : str
        Field title, with or without closing punctuation.

    Returns
    -------
    str
        Normalized key.

    Examples
    --------
    >>> field_key("Why the tiers")
    'why'
    >>> field_key("Exceptions")
    'exception'
    >>> field_key("How to apply")
    'how-to-apply'
    >>> field_key("Relation to the neighbouring rules")
    'relation'
    >>> field_key("Precedence among the three enumeration rules")
    'precedence-among-the-three-enumeration-rules'
    """
    words = re.findall(r"[^\W_]+", title.lower())
    phrase = " ".join(words)
    if phrase in _CANONICAL_PHRASES:
        return _CANONICAL_PHRASES[phrase]
    if words and words[0] in _CANONICAL_WORDS:
        return _CANONICAL_WORDS[words[0]]
    return "-".join(words)


def parse_module(text: str, *, module: str) -> ParsedModule:
    """Parse the text of one instruction module.

    Parameters
    ----------
    text : str
        Full text of the module, with or without YAML frontmatter.
    module : str
        Name recorded on every rule and rejected line.

    Returns
    -------
    ParsedModule
        Blocks, rules and rejected label lines of the module.

    Examples
    --------
    >>> parsed = parse_module(
    ...     "# Style\\n\\n**short-sentences**:\\n\\n✓ Keep sentences short.\\n\\n"
    ...     "*Exception.* Quoted text.\\n",
    ...     module="style",
    ... )
    >>> rule = parsed.rule("short-sentences")
    >>> rule.heading_path, rule.part_keys
    (('Style',), ('valid', 'exception'))
    >>> rule.parts_for("exception")[0].text
    '*Exception.* Quoted text.'
    >>> rule.start_line, rule.end_line
    (3, 7)
    """
    return _ModuleParser(text.splitlines(), module).parse()


@dataclass
class _Pending:
    """Lines of the block under construction, with its label if it is a rule."""

    lines: list[str]
    start_line: int
    label: str | None


class _ModuleParser:
    """Single-pass segmentation of a module into blocks."""

    def __init__(self, lines: list[str], module: str) -> None:
        self._lines = lines
        self._module = module
        self._blocks: list[Block] = []
        self._rejected: list[RejectedLabel] = []
        self._headings: list[tuple[int, str]] = []
        self._pending: _Pending | None = None

    def parse(self) -> ParsedModule:
        """Segment the lines after the frontmatter into blocks.

        Headings and label lines are recognized only outside fenced code. A
        label-shaped line that violates the grammar is recorded as rejected
        and opens a text block, so it ends the preceding rule.
        """
        in_fence = False
        for index in range(_body_start(self._lines), len(self._lines)):
            line = self._lines[index]
            number = index + 1
            if FENCE_PATTERN.match(line):
                in_fence = not in_fence
                self._append(line, number)
                continue
            if in_fence:
                self._append(line, number)
                continue
            heading = _HEADING.match(line)
            if heading is not None:
                self._heading(heading, line, number)
                continue
            label = LABEL_PATTERN.match(line)
            if label is not None:
                self._flush()
                self._pending = _Pending([line], number, label.group(1))
                continue
            shape = _LABEL_SHAPE.match(line)
            if shape is not None:
                self._reject(shape, line, number)
                self._flush()
                self._pending = _Pending([line], number, None)
                continue
            self._append(line, number)
        self._flush()
        return ParsedModule(
            name=self._module,
            blocks=tuple(self._blocks),
            rejected=tuple(self._rejected),
        )

    def _heading(self, match: re.Match[str], line: str, number: int) -> None:
        self._flush()
        level = len(match.group(1))
        text = match.group(2).strip()
        while self._headings and self._headings[-1][0] >= level:
            self._headings.pop()
        self._headings.append((level, text))
        self._blocks.append(
            HeadingBlock(level=level, text=text, line=line, start_line=number)
        )

    def _reject(self, match: re.Match[str], line: str, number: int) -> None:
        token = match.group("token")
        if match.group("indent"):
            reason = "the label line is indented; a label line starts at column 0"
        elif not re.match(r"[a-z]", token):
            reason = "a label must start with a lowercase letter"
        else:
            reason = "a label may contain only lowercase letters, digits and hyphens"
        self._rejected.append(
            RejectedLabel(
                module=self._module,
                line_number=number,
                line=line,
                token=token,
                reason=reason,
            )
        )

    def _append(self, line: str, number: int) -> None:
        if self._pending is None:
            self._pending = _Pending([line], number, None)
        else:
            self._pending.lines.append(line)

    def _flush(self) -> None:
        pending = self._pending
        if pending is None:
            return
        self._pending = None
        if pending.label is None:
            self._blocks.append(
                TextBlock(lines=tuple(pending.lines), start_line=pending.start_line)
            )
            return
        lines = _strip_trailing_blank(pending.lines)
        self._blocks.append(
            RuleBlock(
                rule=Rule(
                    label=pending.label,
                    module=self._module,
                    heading_path=tuple(text for _, text in self._headings),
                    parts=_split_parts(lines, pending.start_line),
                    text="\n".join(lines),
                    start_line=pending.start_line,
                    end_line=pending.start_line + len(lines) - 1,
                )
            )
        )


def _body_start(lines: list[str]) -> int:
    """Return the index of the first line after the YAML frontmatter."""
    if not lines or lines[0].strip() != "---":
        return 0
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return index + 1
    return 0


def _strip_trailing_blank(lines: list[str]) -> list[str]:
    end = len(lines)
    while end > 0 and not lines[end - 1].strip():
        end -= 1
    return lines[:end]


def _part_opening(line: str) -> tuple[str, str] | None:
    """Return ``(key, title)`` when ``line`` opens a marked part."""
    if line.startswith(_VALID_MARK):
        return VALID_KEY, _VALID_MARK
    if line.startswith(_INVALID_MARK):
        return INVALID_KEY, _INVALID_MARK
    marker = _FIELD_MARKER.match(line)
    if marker is None or not (marker.group("inner") or marker.group("outer")):
        return None
    title = marker.group("title").strip()
    return field_key(title), title


def _split_parts(lines: list[str], start: int) -> tuple[RulePart, ...]:
    """Split the lines of a rule block, label line first, into parts."""
    parts: list[RulePart] = []
    current: list[str] = []
    current_key = ""
    current_title = ""
    current_start = 0

    def close() -> None:
        body = _strip_trailing_blank(current)
        if body:
            parts.append(
                RulePart(
                    key=current_key,
                    title=current_title,
                    text="\n".join(body),
                    start_line=current_start,
                    end_line=current_start + len(body) - 1,
                )
            )

    in_fence = False
    for offset, line in enumerate(lines[1:], start=1):
        number = start + offset
        opening = None if in_fence else _part_opening(line)
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
        if opening is not None:
            close()
            current_key, current_title = opening
            current = [line]
            current_start = number
        elif current:
            current.append(line)
        elif line.strip():
            current_key, current_title = LEAD_KEY, ""
            current = [line]
            current_start = number
    close()
    return tuple(parts)
