"""Instruction-file generation and stale-output checks."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Iterator

from .exceptions import ConfigurationError, SourceNotFoundError
from .markdown import MarkdownAssembler
from .models import AgentConfig, InstructionConfig, SourceFile


class InstructionGenerator:
    """Generate, write and compare instruction outputs."""

    def __init__(
        self,
        config: InstructionConfig,
        assembler: MarkdownAssembler | None = None,
    ) -> None:
        self.config = config
        self.assembler = assembler or MarkdownAssembler()

    def generate_all(self, agent_name: str | None = None) -> dict[str, str]:
        """Generate content for enabled outputs."""
        outputs: dict[str, str] = {}
        for agent in self._selected_agents(agent_name):
            outputs[agent.name] = self.generate_for_agent(agent)
        return outputs

    def generate_for_agent(self, agent: AgentConfig) -> str:
        """Generate content for one output."""
        parts: list[str] = []

        if agent.target.header:
            parts.append(agent.target.header.strip())

        for source in [*self.config.common_sources, *agent.sources]:
            content = self._load_source(source)
            if content:
                parts.append(content)

        if agent.target.footer:
            parts.append(agent.target.footer.strip())

        return "\n\n".join(parts).rstrip() + "\n"

    def write_all(
        self,
        agent_name: str | None = None,
        dry_run: bool = False,
    ) -> list[Path]:
        """Write selected outputs and return their paths."""
        paths: list[Path] = []

        for agent in self._selected_agents(agent_name):
            output_path = self.config.resolve(agent.target.path)
            paths.append(output_path)

            if dry_run:
                continue

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(self.generate_for_agent(agent), encoding="utf-8")

        return paths

    def diff_report(
        self,
        agent_name: str | None = None,
    ) -> Iterator[tuple[AgentConfig, Path, bool]]:
        """Yield whether each selected output differs from generated content."""
        for agent in self._selected_agents(agent_name):
            output_path = self.config.resolve(agent.target.path)
            expected = self.generate_for_agent(agent)
            existing = (
                output_path.read_text(encoding="utf-8")
                if output_path.is_file()
                else ""
            )
            yield agent, output_path, existing != expected

    def unified_diff(self, agent_name: str) -> str:
        """Return a unified diff for one output."""
        agent = self.config.get_agent(agent_name)
        if agent is None:
            raise ConfigurationError(f"Unknown agent: {agent_name}")

        output_path = self.config.resolve(agent.target.path)
        expected = self.generate_for_agent(agent)
        existing = (
            output_path.read_text(encoding="utf-8") if output_path.is_file() else ""
        )

        return "".join(
            difflib.unified_diff(
                existing.splitlines(keepends=True),
                expected.splitlines(keepends=True),
                fromfile=str(output_path),
                tofile=f"{output_path} (generated)",
            )
        )

    def _selected_agents(self, agent_name: str | None) -> list[AgentConfig]:
        if agent_name is None:
            return self.config.enabled_agents()

        agent = self.config.get_agent(agent_name)
        if agent is None:
            raise ConfigurationError(f"Unknown agent: {agent_name}")
        if not agent.enabled:
            raise ConfigurationError(f"Agent is disabled: {agent_name}")
        return [agent]

    def _load_source(self, source: SourceFile) -> str:
        source_path = self.config.resolve(source.path)
        if not source_path.is_file():
            raise SourceNotFoundError(source_path)

        content = source_path.read_text(encoding="utf-8")
        return self.assembler.process(content, source)
