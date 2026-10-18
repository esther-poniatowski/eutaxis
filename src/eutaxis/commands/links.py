"""Rewrite the relative links of a compiled skill for its installed location.

A source module links to sibling modules and files by relative Markdown links,
such as ``[the audit protocol](audit-protocol.md)``. Once compiled, each task
module is installed as its own skill directory, so a link relative to the
source directory resolves nowhere. The renderer therefore rewrites the target
of each relative link in every emitted Markdown file:

- a target that is another source compiled from the same configuration
  becomes the relative path to the ``SKILL.md`` of that skill, from the
  emitting file: ``../<name>/SKILL.md`` from ``SKILL.md``, and
  ``../../<name>/SKILL.md`` from ``rules/<label>.md``;
- any other target that exists on disk becomes its absolute path;
- a target that names a file of the artifact itself, such as the
  ``rules/<label>.md`` entry of a split index, stays as written;
- a target that does not exist stays as written, and :meth:`LinkResolver.missing`
  reports it.

The fragment of a target, such as ``#^anchor``, is kept. Absolute URLs,
``mailto:`` targets and other schemes, absolute paths, pure fragments, and
links inside code spans or fenced code stay untouched. The rewrite covers
inline links, images and link reference definitions.

The rewrite depends only on its inputs, and the existence test is injected,
so that two renders of the same sources produce the same bytes.
"""

from __future__ import annotations

import os
import posixpath
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from ..instructions.rules import FENCE_PATTERN

ENTRYPOINT_LINK_NAME = "SKILL.md"
"""File that a link to a sibling skill points to."""

_MASK = "\x00"
_TICKS = re.compile(r"`+")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_INLINE_LINK = re.compile(
    r"!?\[(?:[^\[\]\\]|\\.|\[[^\[\]]*\])*\]\([ \t]*"
    r"(?:<(?P<wrapped>[^<>\n]*)>|(?P<bare>(?:[^\s()\\]|\\.|\([^\s()]*\))+))"
    r"(?:[ \t]+(?:\"[^\"]*\"|'[^']*'|\([^()]*\)))?[ \t]*\)"
)
_REFERENCE_DEFINITION = re.compile(
    r"^ {0,3}\[[^\]]+\]:[ \t]*(?:<(?P<wrapped>[^<>\n]*)>|(?P<bare>\S+))"
)
_NEEDS_WRAPPER = re.compile(r"[\s()<>]")


@dataclass(frozen=True)
class Link:
    """One link destination found in a Markdown text."""

    line_number: int
    """Line of the link, counted from 1."""

    start: int
    """Offset of the destination in its line, angle brackets included."""

    end: int
    """Offset just past the destination in its line."""

    target: str
    """Destination as written, without angle brackets."""

    wrapped: bool
    """Whether the destination is written between angle brackets."""


def iter_links(text: str) -> Iterator[Link]:
    """Yield the link destinations of ``text`` outside code.

    Lines inside fenced code and characters inside code spans are skipped.

    Examples
    --------
    >>> [link.target for link in iter_links("[a](x.md) `[b](y.md)` ![c](<z w.png>)")]
    ['x.md', 'z w.png']
    """
    in_fence = False
    for index, line in enumerate(text.splitlines()):
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        yield from _line_links(line, index + 1)


def replace_links(text: str, replace: Callable[[Link], str | None]) -> str:
    """Return ``text`` with each link destination replaced by ``replace``.

    ``replace`` receives each :class:`Link` and returns the new destination,
    without angle brackets, or ``None`` to keep the destination as written.
    A new destination that holds a space, a parenthesis or an angle bracket is
    written between angle brackets. Line endings are kept.

    Examples
    --------
    >>> replace_links("[a](x.md#f) [b](y.md)\\n", lambda l: "z.md" if l.target == "y.md" else None)
    '[a](x.md#f) [b](z.md)\\n'
    """
    lines = text.splitlines(keepends=True)
    links_by_line: dict[int, list[Link]] = {}
    for link in iter_links(text):
        links_by_line.setdefault(link.line_number, []).append(link)
    for number, links in links_by_line.items():
        line = lines[number - 1]
        for link in sorted(links, key=lambda item: item.start, reverse=True):
            new = replace(link)
            if new is None or new == link.target:
                continue
            if link.wrapped or _NEEDS_WRAPPER.search(new):
                new = f"<{new}>"
            line = line[: link.start] + new + line[link.end :]
        lines[number - 1] = line
    return "".join(lines)


def is_relative_target(target: str) -> bool:
    """Return whether ``target`` names a path relative to its document.

    Examples
    --------
    >>> targets = ("a.md", "../b.md#x", "#x", "/a", "https://e.org", "mailto:a@b")
    >>> [is_relative_target(target) for target in targets]
    [True, True, False, False, False, False]
    """
    path = target.partition("#")[0]
    return bool(path) and not (path.startswith(("/", "~", "\\")) or _SCHEME.match(path))


def normalize_path(path: Path) -> Path:
    """Return the absolute, lexically normalized form of ``path``.

    Symbolic links are not followed, so the result does not depend on the
    state of the file system.
    """
    return Path(os.path.normpath(path.absolute()))


@dataclass(frozen=True)
class MissingLink:
    """A relative link of a source whose target does not exist."""

    source_path: Path
    line_number: int
    target: str
    resolved: Path

    @property
    def message(self) -> str:
        """Diagnostic with the location of the link in its source."""
        return (
            f"{self.source_path}:{self.line_number}: link target "
            f"{self.target!r} resolves to {self.resolved}, which does not exist"
        )


@dataclass(frozen=True)
class LinkResolver:
    """Resolve the relative links of one source for its compiled skill."""

    source_dir: Path
    """Directory against which the relative links of the source resolve."""

    skills: Mapping[Path, str] = field(default_factory=dict)
    """Normalized source path of each sibling skill, mapped to its name."""

    exists: Callable[[Path], bool] = Path.exists
    """Existence test of a resolved target."""

    def resolve(self, target: str) -> Path:
        """Return the normalized path that a relative ``target`` names."""
        path = unquote(target.partition("#")[0])
        return normalize_path(self.source_dir / path)

    def missing(
        self, text: str, *, source_path: Path, first_line: int = 1
    ) -> list[MissingLink]:
        """Return the relative links of ``text`` that resolve to no file.

        Parameters
        ----------
        text : str
            Body of the source, before any split.
        source_path : Path
            Source file, quoted in each diagnostic.
        first_line : int
            Line of the source file on which ``text`` starts.
        """
        found: list[MissingLink] = []
        for link in iter_links(text):
            if not is_relative_target(link.target):
                continue
            resolved = self.resolve(link.target)
            if resolved in self.skills or self.exists(resolved):
                continue
            found.append(
                MissingLink(
                    source_path=source_path,
                    line_number=first_line + link.line_number - 1,
                    target=link.target,
                    resolved=resolved,
                )
            )
        return found

    def rewrite(
        self, text: str, *, emitter: str, artifact_paths: frozenset[str]
    ) -> str:
        """Rewrite the relative links of one emitted file.

        Parameters
        ----------
        text : str
            Content of the emitted Markdown file.
        emitter : str
            Path of that file relative to the artifact root, such as
            ``"SKILL.md"`` or ``"rules/topic-first.md"``.
        artifact_paths : frozenset[str]
            Paths of every file of the artifact, relative to its root. A link
            to one of them stays as written.

        Examples
        --------
        >>> resolver = LinkResolver(
        ...     source_dir=Path("/src/tasks"),
        ...     skills={Path("/src/tasks/style.md"): "style"},
        ...     exists=lambda path: False,
        ... )
        >>> resolver.rewrite(
        ...     "[s](style.md#^a) [r](rules/x.md)",
        ...     emitter="rules/y.md",
        ...     artifact_paths=frozenset({"rules/x.md"}),
        ... )
        '[s](../../style/SKILL.md#^a) [r](rules/x.md)'
        """
        emitter_dir = posixpath.dirname(emitter)
        up = "../" * (len(emitter_dir.split("/")) + 1 if emitter_dir else 1)

        def target_for(link: Link) -> str | None:
            if not is_relative_target(link.target):
                return None
            path, sep, fragment = link.target.partition("#")
            if posixpath.normpath(posixpath.join(emitter_dir, path)) in artifact_paths:
                return None
            resolved = self.resolve(link.target)
            name = self.skills.get(resolved)
            if name is not None:
                return f"{up}{name}/{ENTRYPOINT_LINK_NAME}{sep}{fragment}"
            if self.exists(resolved):
                return f"{resolved.as_posix()}{sep}{fragment}"
            return None

        return replace_links(text, target_for)


def _line_links(line: str, number: int) -> Iterator[Link]:
    masked = _mask_code_spans(line)
    matches = [*_INLINE_LINK.finditer(masked)]
    definition = _REFERENCE_DEFINITION.match(masked)
    if definition is not None:
        matches.insert(0, definition)
    for match in matches:
        group = "wrapped" if match.group("wrapped") is not None else "bare"
        start, end = match.span(group)
        if _MASK in masked[start:end]:
            continue
        wrapped = group == "wrapped"
        yield Link(
            line_number=number,
            start=start - 1 if wrapped else start,
            end=end + 1 if wrapped else end,
            target=line[start:end],
            wrapped=wrapped,
        )


def _mask_code_spans(line: str) -> str:
    """Replace every character of each code span of ``line`` by a mask.

    A code span opens on a run of backticks and closes on the next run of the
    same length. An unclosed run is literal text.
    """
    chars = list(line)
    position = 0
    while (opening := _TICKS.search(line, position)) is not None:
        closing = next(
            (
                run
                for run in _TICKS.finditer(line, opening.end())
                if len(run.group()) == len(opening.group())
            ),
            None,
        )
        if closing is None:
            position = opening.end()
            continue
        chars[opening.start() : closing.end()] = _MASK * (
            closing.end() - opening.start()
        )
        position = closing.end()
    return "".join(chars)
