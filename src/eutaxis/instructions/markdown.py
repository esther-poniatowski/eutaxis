"""Markdown transformations used by instruction-file assembly."""

from __future__ import annotations

import re

from .models import Section, SourceFile


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
        heading_set = set(headings)
        blocks: list[str] = []
        current: list[str] = []
        current_level = 0

        for line in lines:
            match = self.heading_pattern.match(line)
            if match is not None:
                level = len(match.group(1))
                heading = match.group(2).strip()

                if heading in heading_set:
                    if current:
                        blocks.append("\n".join(current).strip())
                    current = [line]
                    current_level = level
                elif current and level <= current_level:
                    blocks.append("\n".join(current).strip())
                    current = []
                    current_level = 0
                elif current:
                    current.append(line)
                continue

            if current:
                current.append(line)

        if current:
            blocks.append("\n".join(current).strip())

        return "\n\n".join(block for block in blocks if block)

    def exclude_sections(self, content: str, headings: tuple[str, ...]) -> str:
        """Remove named sections and their nested subsections."""
        lines = content.splitlines()
        heading_set = set(headings)
        kept: list[str] = []
        excluded_level: int | None = None

        for line in lines:
            match = self.heading_pattern.match(line)
            if match is not None:
                level = len(match.group(1))
                heading = match.group(2).strip()

                if excluded_level is not None and level <= excluded_level:
                    excluded_level = None

                if heading in heading_set:
                    excluded_level = level
                    continue

            if excluded_level is None:
                kept.append(line)

        return "\n".join(kept).strip()

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
