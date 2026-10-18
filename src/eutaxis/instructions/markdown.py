"""Markdown transformations used by instruction-file assembly."""

from __future__ import annotations

import re
from typing import Any, Sequence

import yaml

from .models import Section, SourceFile


_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


def parse_frontmatter(content: str) -> dict[str, Any]:
    """Parse a Markdown file's YAML frontmatter block.

    Returns an empty dict when the file has no frontmatter or when the
    frontmatter is empty. Raises ``yaml.YAMLError`` if the block is malformed.
    """
    if not content.startswith("---"):
        return {}

    match = _FRONTMATTER_PATTERN.match(content)
    if match is None:
        return {}

    body = match.group(1)
    parsed = yaml.safe_load(body) if body.strip() else {}
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise yaml.YAMLError(
            f"Frontmatter must be a YAML mapping, got {type(parsed).__name__}"
        )
    return parsed


class MarkdownAssembler:
    """Extract and rewrite Markdown source content."""

    heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$")

    def process(self, content: str, source: SourceFile) -> str:
        """Apply frontmatter stripping, section filtering and heading offsets."""
        if source.strip_frontmatter:
            content = self.strip_frontmatter(content)

        if source.sections:
            content = self.include_sections(content, source.sections)

        if source.exclude_sections:
            content = self.exclude_sections(content, source.exclude_sections)

        if source.heading_offset:
            content = self.apply_heading_offset(content, source.heading_offset)

        return content.strip()

    def strip_frontmatter(self, content: str) -> str:
        """Remove top-level YAML frontmatter from Markdown content."""
        if not content.startswith("---"):
            return content

        match = re.match(r"^---\s*\n.*?\n---\s*\n?", content, flags=re.DOTALL)
        if match is None:
            return content
        return content[match.end() :].strip()

    def parse_sections(self, content: str) -> list[Section]:
        """Parse Markdown into sections."""
        lines = content.splitlines()
        sections: list[Section] = []
        start_index: int | None = None
        heading = ""
        level = 0

        for index, line in enumerate(lines):
            match = self.heading_pattern.match(line)
            if match is None:
                continue

            if start_index is not None:
                sections.append(
                    Section(
                        heading=heading,
                        level=level,
                        content="\n".join(lines[start_index:index]).strip(),
                    )
                )

            start_index = index
            level = len(match.group(1))
            heading = match.group(2).strip()

        if start_index is None:
            return []

        sections.append(
            Section(
                heading=heading,
                level=level,
                content="\n".join(lines[start_index:]).strip(),
            )
        )
        return sections

    def include_sections(self, content: str, headings: tuple[str, ...]) -> str:
        """Include named sections and their nested subsections."""
        lines = content.splitlines()
        blocks = (
            "\n".join(lines[index] for index in block).strip()
            for block in self._included_blocks(lines, range(len(lines)), headings)
        )
        return "\n\n".join(block for block in blocks if block)

    def exclude_sections(self, content: str, headings: tuple[str, ...]) -> str:
        """Remove named sections and their nested subsections."""
        lines = content.splitlines()
        kept = self._kept_indices(lines, range(len(lines)), headings)
        return "\n".join(lines[index] for index in kept).strip()

    def selected_line_numbers(
        self, content: str, source: SourceFile
    ) -> frozenset[int] | None:
        """Return the lines of ``content`` that the section selection keeps.

        The selection follows :meth:`process`: frontmatter stripping, then
        ``sections``, then ``exclude_sections``. Heading offsets and blank-line
        trimming change no membership, so they are ignored.

        Parameters
        ----------
        content : str
            Full text of the source file, as read from disk.
        source : SourceFile
            Source entry whose selection applies.

        Returns
        -------
        frozenset[int] or None
            Line numbers of ``content``, counted from 1, that the selection
            keeps; ``None`` when the entry selects no section, so that every
            line is kept.

        Examples
        --------
        >>> from pathlib import Path
        >>> text = "# A\\nkept\\n# B\\ndropped\\n"
        >>> source = SourceFile(path=Path("m.md"), sections=("A",))
        >>> sorted(MarkdownAssembler().selected_line_numbers(text, source))
        [1, 2]
        """
        if not source.sections and not source.exclude_sections:
            return None
        lines = content.splitlines()
        start = 0
        if source.strip_frontmatter and content.startswith("---"):
            match = re.match(r"^---\s*\n.*?\n---\s*\n?", content, flags=re.DOTALL)
            if match is not None:
                start = content[: match.end()].count("\n")
        selected: list[int] = list(range(start, len(lines)))
        if source.sections:
            blocks = self._included_blocks(lines, selected, source.sections)
            selected = [index for block in blocks for index in block]
        if source.exclude_sections:
            selected = self._kept_indices(lines, selected, source.exclude_sections)
        return frozenset(index + 1 for index in selected)

    def _included_blocks(
        self, lines: list[str], indices: Sequence[int], headings: tuple[str, ...]
    ) -> list[list[int]]:
        """Return the indices of each block that ``include_sections`` keeps.

        A block opens on a heading named in ``headings`` and closes before the
        next heading at the same or a higher level, unless that heading is
        itself named, in which case it opens the next block.
        """
        heading_set = set(headings)
        blocks: list[list[int]] = []
        current: list[int] = []
        current_level = 0

        for index in indices:
            match = self.heading_pattern.match(lines[index])
            if match is not None:
                level = len(match.group(1))
                heading = match.group(2).strip()

                if heading in heading_set:
                    if current:
                        blocks.append(current)
                    current = [index]
                    current_level = level
                elif current and level <= current_level:
                    blocks.append(current)
                    current = []
                    current_level = 0
                elif current:
                    current.append(index)
                continue

            if current:
                current.append(index)

        if current:
            blocks.append(current)
        return blocks

    def _kept_indices(
        self, lines: list[str], indices: Sequence[int], headings: tuple[str, ...]
    ) -> list[int]:
        """Return the indices that ``exclude_sections`` keeps."""
        heading_set = set(headings)
        kept: list[int] = []
        excluded_level: int | None = None

        for index in indices:
            match = self.heading_pattern.match(lines[index])
            if match is not None:
                level = len(match.group(1))
                heading = match.group(2).strip()

                if excluded_level is not None and level <= excluded_level:
                    excluded_level = None

                if heading in heading_set:
                    excluded_level = level
                    continue

            if excluded_level is None:
                kept.append(index)

        return kept

    def apply_heading_offset(self, content: str, offset: int) -> str:
        """Increase all Markdown heading levels by ``offset``."""
        if offset == 0:
            return content

        lines: list[str] = []
        for line in content.splitlines():
            match = self.heading_pattern.match(line)
            if match is None:
                lines.append(line)
                continue

            level = min(len(match.group(1)) + offset, 6)
            lines.append(f"{'#' * level} {match.group(2)}")

        return "\n".join(lines)
