"""Rule catalog and the resolution of one rule query.

A :class:`RuleCatalog` holds the rule records collected from a set of
modules, each located at the file that holds it. The functions of this
module resolve a label to one rule and a part name to the matching parts,
and raise an error naming the available choices when the query does not
resolve. They perform no I/O.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

from ..instructions.rules import RejectedLabel, Rule, RulePart
from .exceptions import AmbiguousRuleError, UnknownPartError, UnknownRuleError


@dataclass(frozen=True)
class LocatedRule:
    """A rule record and the file whose line numbers it carries."""

    rule: Rule
    path: Path


@dataclass(frozen=True)
class LocatedRejection:
    """A rejected label line and the file that holds it."""

    rejection: RejectedLabel
    path: Path


@dataclass(frozen=True)
class RuleCatalog:
    """Rules collected from one source of modules."""

    origin: str
    """Description of the source, quoted in error messages."""

    rules: tuple[LocatedRule, ...]
    """Rules in module order, then source order."""

    rejected: tuple[LocatedRejection, ...] = ()
    """Label-shaped lines that the parser rejected."""

    hint: str = ""
    """Advice appended to the message of an unknown label, such as the reason
    why a label may be absent from this source."""

    def select(self, module: str | None = None) -> tuple[LocatedRule, ...]:
        """Return the rules of ``module``, or every rule when it is ``None``."""
        if module is None:
            return self.rules
        return tuple(item for item in self.rules if item.rule.module == module)

    @property
    def modules(self) -> tuple[str, ...]:
        """Names of the modules that hold at least one rule, in order."""
        return tuple(dict.fromkeys(item.rule.module for item in self.rules))


def resolve_rule(
    catalog: RuleCatalog, label: str, *, module: str | None = None
) -> LocatedRule:
    """Return the one rule labelled ``label``.

    Parameters
    ----------
    catalog : RuleCatalog
        Rules to search.
    label : str
        Requested label.
    module : str, optional
        Module that must hold the rule; required when several modules
        define the label.

    Raises
    ------
    UnknownRuleError
        When no rule carries the label. The message lists close labels,
        a rejected label line with the same token, and the hint of the
        catalog.
    AmbiguousRuleError
        When several modules define the label and ``module`` is ``None``.
    """
    if module is not None and module not in catalog.modules:
        raise UnknownRuleError(
            f"Unknown module {module!r} in {catalog.origin}. "
            f"Modules: {', '.join(catalog.modules) or 'none'}."
        )
    matches = [item for item in catalog.select(module) if item.rule.label == label]
    if len(matches) == 1:
        return matches[0]
    if matches:
        names = ", ".join(item.rule.module for item in matches)
        raise AmbiguousRuleError(
            f"Label {label!r} is defined in several modules ({names}); "
            f"select one with --module."
        )
    raise UnknownRuleError(_unknown_label_message(catalog, label, module))


def select_parts(rule: Rule, part: str) -> tuple[RulePart, ...]:
    """Return the parts of ``rule`` whose key equals ``part``.

    Raises
    ------
    UnknownPartError
        When the rule has no such part; the message lists the parts the rule
        has.

    Examples
    --------
    >>> from eutaxis.instructions.rules import parse_module
    >>> rule = parse_module("**r**:\\n\\n✓ Do.\\n", module="m").rules[0]
    >>> [p.text for p in select_parts(rule, "valid")]
    ['✓ Do.']
    """
    parts = rule.parts_for(part)
    if parts:
        return parts
    raise UnknownPartError(
        f"Rule {rule.label!r} has no {part!r} part. "
        f"Available parts: {', '.join(rule.part_keys) or 'none'}."
    )


def _unknown_label_message(catalog: RuleCatalog, label: str, module: str | None) -> str:
    scope = f"module {module!r} of " if module else ""
    message = f"Unknown rule label {label!r} in {scope}{catalog.origin}."
    for item in catalog.rejected:
        if item.rejection.token.strip() == label:
            message += (
                f" Line {item.rejection.line_number} of {item.path} holds "
                f"{item.rejection.line.strip()!r}, which the parser rejects: "
                f"{item.rejection.reason}."
            )
    labels = [item.rule.label for item in catalog.select(module)]
    close = difflib.get_close_matches(label, labels, n=3)
    if close:
        message += f" Close labels: {', '.join(close)}."
    message += " List the labels with `eutaxis rule list` and the same source options."
    if catalog.hint:
        message += f" {catalog.hint}"
    return message
