"""
Agent instruction file generator.

Assembles unified instruction files for AI agents from modular governance sources
and project-specific configuration. Each agent receives common sources (shared
across all agents) plus agent-specific headers, footers, and additional sources.

Configuration is read from a YAML file (typically ``agent-instructions.yaml``)
whose structure follows the format used by geonexus:

.. code-block:: yaml

    common_sources:
      - path: docs/instructions/style-hard-rules.md
        sections:          # optional: extract only named sections
          - "Hard blockers"
      - path: docs/instructions/note-template.md

    agents:
      - name: claude
        enabled: true
        target:
          path: .claude/CLAUDE.md
          header: |
            # CLAUDE.md
            ...
          footer: |
            ---
            *Auto-generated.*
        sources:            # agent-specific additional sources
          - path: docs/instructions/extra.md
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


def extract_sections(content: str, sections: list[str] | None) -> str:
    """Extract specified sections from markdown content.

    If *sections* is ``None``, return the full content (minus YAML frontmatter).
    """
    # Remove YAML frontmatter if present
    if content.startswith("---"):
        end_frontmatter = content.find("---", 3)
        if end_frontmatter != -1:
            content = content[end_frontmatter + 3 :].strip()

    if sections is None:
        return content

    extracted: list[str] = []
    lines = content.split("\n")
    current_section: str | None = None
    current_content: list[str] = []
    section_level = 0

    for line in lines:
        header_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if header_match:
            level = len(header_match.group(1))
            title = header_match.group(2).strip()

            if title in sections:
                if current_section in sections:
                    extracted.append("\n".join(current_content))
                current_section = title
                section_level = level
                current_content = [line]
            elif current_section and level <= section_level:
                extracted.append("\n".join(current_content))
                current_section = None
                current_content = []
            elif current_section:
                current_content.append(line)
        elif current_section:
            current_content.append(line)

    if current_section in sections:
        extracted.append("\n".join(current_content))

    return "\n\n".join(extracted)


def load_source(source: dict, base_path: Path) -> str:
    """Load content from a source file, optionally extracting sections."""
    file_path = base_path / source["path"]

    if not file_path.exists():
        print(f"  Warning: Source file not found: {file_path}")
        return ""

    content = file_path.read_text(encoding="utf-8")
    sections = source.get("sections")

    return extract_sections(content, sections)


def generate_agent_file(
    agent: dict, common_sources: list, base_path: Path
) -> None:
    """Generate instruction file for a single agent."""
    if not agent.get("enabled", True):
        print(f"  Skipping disabled agent: {agent['name']}")
        return

    target = agent["target"]
    output_path = base_path / target["path"]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    parts: list[str] = []

    if "header" in target:
        parts.append(target["header"].strip())

    for source in common_sources:
        content = load_source(source, base_path)
        if content:
            parts.append(content)

    for source in agent.get("sources", []):
        content = load_source(source, base_path)
        if content:
            parts.append(content)

    if "footer" in target:
        parts.append(target["footer"].strip())

    output = "\n\n".join(parts) + "\n"
    output_path.write_text(output, encoding="utf-8")
    print(f"  Generated: {output_path}")


def main(config_path: Path, domain: str | None = None) -> int:
    """Main entry point for instruction generation.

    Parameters
    ----------
    config_path
        Path to the agent-instructions YAML configuration file.
    domain
        Optional domain name for default source resolution. When provided,
        eutaxis domain content at ``data/domains/<domain>/`` is available
        as the base for relative source paths. Currently informational;
        the YAML config determines actual source paths.
    """
    if not config_path.exists():
        print(f"Error: Configuration file not found: {config_path}")
        return 1

    base_path = config_path.parent

    if domain:
        print(f"Domain: {domain}")
    print(f"Loading configuration: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    common_sources = config.get("common_sources", [])
    agents = config.get("agents", [])

    print(f"Found {len(agents)} agent configurations")

    for agent in agents:
        print(f"\nProcessing agent: {agent['name']}")
        generate_agent_file(agent, common_sources, base_path)

    print("\nDone.")
    return 0
